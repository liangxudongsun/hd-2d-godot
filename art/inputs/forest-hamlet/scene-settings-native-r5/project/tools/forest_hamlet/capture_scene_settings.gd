extends "res://tools/forest_hamlet/capture.gd"
## Actual Forward+ read-back, isolated preferences and real viewport GUI input.
const SECTION_PARAMETERS := {
    "environment":["exposure","contrast","saturation","fog_density_scale"],
    "dof":["dof_amount","dof_near_margin","dof_near_transition","dof_far_margin","dof_far_transition"],
    "glow":["glow_intensity","glow_strength","glow_bloom","glow_hdr_threshold","glow_hdr_scale"],
    "clouds":["cloud_contrast","cloud_density","sun_variation","ambient_variation"],
    "other":["wind_strength","parallax_strength"],
}
const SOURCE_FILES := [
    "scripts/forest_hamlet/scene.gd","scripts/forest_hamlet/close_scene.gd","scripts/forest_hamlet/scene_settings.gd","scripts/forest_hamlet/settings_panel.gd",
    "scripts/forest_hamlet/cloud_lighting.gd","scripts/forest_hamlet/global_lighting.gd","scripts/forest_hamlet/actor.gd",
    "shaders/forest_hamlet/cloud_occluder.gdshader","tests/forest_hamlet/scene_settings_runtime.gd",
    "tools/forest_hamlet/capture_scene_settings.gd","tools/forest_hamlet/scene_settings_checks.py","tools/forest_hamlet/run_scene_settings.py",
]
var validation_checks: Array = []
var pointer_tests: Array = []
var source_fingerprint := ""
var active_section := "clouds"
var saved_settings: Dictionary = {}
var restored_settings: Dictionary = {}
var saved_settings_hash := ""

func _initialize() -> void:
    output = "res://build/forest-hamlet/scene-settings-r5"
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--forest-source-fingerprint="):
            source_fingerprint = arg.trim_prefix("--forest-source-fingerprint=")
    super._initialize()

func check(condition: bool, label: String) -> void:
    validation_checks.append({"label":label,"passed":condition})
    if not condition:
        failed.append(label)
        print("SCENE_SETTINGS_CAPTURE_FAIL ",label)

func settle(frames: int = 4) -> void:
    for index in range(frames):
        await process_frame

func rect_array(rect: Rect2) -> Array:
    return [rect.position.x,rect.position.y,rect.size.x,rect.size.y]

func panel_state() -> Dictionary:
    var viewport_rect := Rect2(Vector2.ZERO,Vector2(viewport.size))
    var scroll: ScrollContainer = scene.setting_scrolls[active_section]
    var clip_rect: Rect2 = scroll.get_global_rect().intersection(scene.panel.get_global_rect())
    var result := {
        "visible":scene.panel.is_visible_in_tree(),"section":active_section,
        "panel_rect":rect_array(scene.panel.get_global_rect()),"panel_inside_viewport":viewport_rect.encloses(scene.panel.get_global_rect()),
        "clip_rect":rect_array(clip_rect),"viewport":[viewport.size.x,viewport.size.y],"controls":{},"actions":{},
    }
    for id in SECTION_PARAMETERS[active_section]:
        var slider: HSlider = scene.effect_sliders[id]
        var label: Label = scene.effect_value_labels[id]
        var rect: Rect2 = slider.get_global_rect()
        var label_rect: Rect2 = label.get_global_rect()
        result.controls[id] = {
            "value":slider.value,"min":slider.min_value,"max":slider.max_value,"step":slider.step,
            "rect":rect_array(rect),"visible":slider.is_visible_in_tree(),"inside_viewport":viewport_rect.encloses(rect),
            "inside_clip":clip_rect.encloses(rect),"label":label.text,"label_rect":rect_array(label_rect),
            "label_inside_viewport":viewport_rect.encloses(label_rect),"label_inside_clip":clip_rect.encloses(label_rect),
        }
    var actions := {"save":scene.tuning_save_button,"load":scene.tuning_load_button,"reset":scene.tuning_reset_button,"day":scene.time_buttons.day,"dusk":scene.time_buttons.dusk}
    for id in actions:
        var button: Button = actions[id]
        result.actions[id] = {"text":button.text,"visible":button.is_visible_in_tree(),"rect":rect_array(button.get_global_rect()),"inside_viewport":viewport_rect.encloses(button.get_global_rect())}
    return result

func native_effects() -> Dictionary:
    return {
        "dof_amount":scene.attributes.dof_blur_amount,"dof_near_enabled":scene.attributes.dof_blur_near_enabled,
        "dof_far_enabled":scene.attributes.dof_blur_far_enabled,"dof_near":scene.attributes.dof_blur_near_distance,
        "dof_far":scene.attributes.dof_blur_far_distance,"dof_near_transition":scene.attributes.dof_blur_near_transition,
        "dof_far_transition":scene.attributes.dof_blur_far_transition,
        "glow_enabled":scene.environment.glow_enabled,"glow_intensity":scene.environment.glow_intensity,
        "glow_strength":scene.environment.glow_strength,"glow_bloom":scene.environment.glow_bloom,
        "glow_hdr_threshold":scene.environment.glow_hdr_threshold,"glow_hdr_scale":scene.environment.glow_hdr_scale,
    }

func snapshot(label: String) -> void:
    scene.cloud_lighting.sync_sun_lights()
    scene.backdrop.update_frame()
    await settle(32)
    await super.snapshot(label)
    screenshots[-1]["settings"] = scene.get_scene_settings()
    screenshots[-1]["native_effects"] = native_effects()
    screenshots[-1]["panel"] = panel_state()
    var frame: Dictionary = scene.framing_state()
    check(frame.in_frame and frame.view_depth > frame.dof_near and frame.view_depth < frame.dof_far,label+": full unchanged actor stays inside the sharp DOF interval and the frame")
    check(is_equal_approx(scene.cloud_lighting.clock_seconds,0.0) and is_equal_approx(scene.global_lighting.clock_seconds,0.0),label+": both lighting clocks remain frozen at zero")

func freeze_comparison() -> void:
    scene.frozen = true
    scene.player.controls_enabled = false
    scene.player.set_physics_process(false)
    scene.player.velocity = Vector3.ZERO
    scene.player.direction_override = 0
    scene.player.frame_override = 0
    scene.player.paused = true
    scene.player.update_animation()
    scene.set_feature("wind",false)
    scene.world.set_vegetation_wind(0.0)
    scene.world.set_process(false)
    scene.world.water_material.set_shader_parameter("flow_speed",0.0)
    scene.cloud_lighting.set_time(0.0)
    scene.global_lighting.set_time(0.0)
    scene.cloud_lighting.set_uniform_attenuation(-1.0)
    scene.update_camera(true)
    scene.backdrop.update_frame()
    comparison_frozen = true

func set_slider(id: String, value: float) -> void:
    scene.effect_sliders[id].value = value*(100.0 if id in ["cloud_contrast","cloud_density"] else 1.0)

func select_section(id: String) -> void:
    check(scene.select_settings_tab(id),"settings section is selectable: "+id)
    active_section = id
    scene.setting_scrolls[id].scroll_vertical = 0
    await settle(6)

func check_panel(label: String, verify_every_control: bool) -> void:
    var state: Dictionary = panel_state()
    check(state.visible and state.panel_inside_viewport,label+": the entire panel fits the viewport")
    for id in state.actions:
        var action: Dictionary = state.actions[id]
        check(action.visible and action.inside_viewport and not action.text.is_empty(),label+": fixed "+id+" action is visible without scrolling")
    var scroll: ScrollContainer = scene.setting_scrolls[active_section]
    var identifiers: Array = SECTION_PARAMETERS[active_section] if verify_every_control else [SECTION_PARAMETERS[active_section][0]]
    for id in identifiers:
        var slider: HSlider = scene.effect_sliders[id]
        var value_label: Label = scene.effect_value_labels[id]
        scroll.ensure_control_visible(value_label)
        scroll.ensure_control_visible(slider)
        await settle()
        var row: Dictionary = panel_state().controls[id]
        check(row.visible and row.inside_viewport and row.inside_clip and row.label_inside_viewport and row.label_inside_clip and row.rect[2]>=120.0 and row.rect[3]>=20.0 and not row.label.is_empty(),label+": "+id+" slider and value are readable inside the actual scroll clipping rectangle")
    scroll.scroll_vertical = 0
    await settle()

func send_key(code: Key) -> void:
    for pressed in [true,false]:
        var event := InputEventKey.new()
        event.keycode = code
        event.physical_keycode = code
        event.pressed = pressed
        viewport.push_input(event,true)
        await process_frame

func pointer_edit(id: String, fraction: float) -> void:
    var slider: HSlider = scene.effect_sliders[id]
    var before: float = slider.value
    var rect: Rect2 = slider.get_global_rect()
    var pointer := Vector2(rect.position.x+rect.size.x*fraction,rect.get_center().y)
    for pressed in [true,false]:
        var event := InputEventMouseButton.new()
        event.button_index = MOUSE_BUTTON_LEFT
        event.pressed = pressed
        event.position = pointer
        event.global_position = pointer
        viewport.push_input(event,true)
        await process_frame
    var after: float = slider.value
    var native_value: float = scene.attributes.dof_blur_amount if id == "dof_amount" else scene.environment.glow_intensity
    pointer_tests.append({"control":id,"before":before,"after":after,"step":slider.step,"pointer":[pointer.x,pointer.y],"native_value":native_value,"method":"InputEventMouseButton routed through the live SubViewport GUI"})
    check(absf(after-before)>slider.step*2.0 and is_equal_approx(native_value,after),id+": real pointer input changes the live native effect")
    check(viewport.gui_get_focus_owner() == slider and not scene.player.controls_enabled,id+": focus on the effect slider disables character controls")

func run() -> void:
    if DisplayServer.get_name() == "headless":
        push_error("Scene settings evidence requires a real graphical GPU.")
        quit(2)
        return
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS,true)
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    scene.cloud_settings_enabled = false
    scene.settings_path = output.path_join("isolated-gpu-scene-settings.cfg")
    viewport.add_child(scene)
    for index in range(45):
        await physics_frame
    freeze_comparison()
    scene.set_time_preset("day")
    scene.overlay.hide()
    set_slider("dof_near_margin",.5)
    set_slider("dof_near_transition",1.0)
    set_slider("dof_far_margin",.5)
    set_slider("dof_far_transition",1.0)
    set_slider("dof_amount",0.0)
    await snapshot("scene-settings-dof-off")
    set_slider("dof_amount",.25)
    await snapshot("scene-settings-dof-strong")
    scene.reset_scene_settings()
    freeze_comparison()
    scene.set_time_preset("dusk")
    set_slider("glow_strength",1.6)
    set_slider("glow_bloom",.2)
    set_slider("glow_hdr_threshold",.5)
    set_slider("glow_hdr_scale",2.5)
    set_slider("glow_intensity",0.0)
    await snapshot("scene-settings-glow-off")
    set_slider("glow_intensity",1.6)
    await snapshot("scene-settings-glow-strong")
    scene.reset_scene_settings()
    scene.set_time_preset("dusk")
    var chosen := {
        "cloud_contrast":.41,"cloud_density":.66,"dof_amount":.09,"dof_near_margin":3.0,"dof_near_transition":2.5,"dof_far_margin":7.0,"dof_far_transition":10.0,
        "glow_intensity":.65,"glow_strength":1.1,"glow_bloom":.055,"glow_hdr_threshold":1.05,"glow_hdr_scale":1.8,
        "exposure":1.05,"contrast":1.08,"saturation":1.04,"fog_density_scale":.9,
        "wind_strength":.08,"parallax_strength":.4,"sun_variation":.22,"ambient_variation":.12,
    }
    for id in chosen:
        set_slider(id,float(chosen[id]))
    freeze_comparison()
    saved_settings = scene.get_scene_settings()
    scene.tuning_save_button.pressed.emit()
    await settle()
    var preference_path: String = scene.settings_path
    check(FileAccess.file_exists(preference_path),"GPU save button writes only the isolated preference file")
    saved_settings_hash = FileAccess.get_sha256(preference_path)
    var saved_pose: Vector3 = scene.player.position
    await snapshot("scene-settings-dusk-saved")
    scene.queue_free()
    await settle()
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    scene.cloud_settings_enabled = false
    scene.settings_path = preference_path
    viewport.add_child(scene)
    for index in range(45):
        await physics_frame
    # A SubViewport child cannot be SceneTree.current_scene. The headless test
    # separately verifies automatic main-scene startup. Here a newly created
    # scene exercises the real Load button before the fresh-instance read-back.
    scene.tuning_load_button.pressed.emit()
    await settle()
    scene.player.position = saved_pose
    restored_settings = scene.get_scene_settings()
    check(restored_settings == saved_settings and scene.time_preset == "dusk","a fresh scene Load button restores the saved dusk preset every number and every switch before capture")
    freeze_comparison()
    scene.overlay.hide()
    check(FileAccess.get_sha256(preference_path) == saved_settings_hash,"fresh-instance loading does not rewrite the isolated saved file")
    await snapshot("scene-settings-dusk-restored")
    scene.overlay.show()
    scene.set_control_panel_visible(true)
    check(scene.settings_tabs.get_tab_count() == 5,"five scene-settings sections are present")
    for section in ["environment","dof","glow","clouds","other"]:
        await select_section(section)
        await check_panel("1920 by 1080 "+section,true)
        await snapshot("scene-settings-panel-"+section+"-1080")
    viewport.size = Vector2i(1280,720)
    await settle(8)
    await select_section("dof")
    await check_panel("1280 by 720 dof",false)
    await snapshot("scene-settings-panel-dof-720")
    await pointer_edit("dof_amount",.8)
    await snapshot("scene-settings-input-dof-720")
    var dof_slider: HSlider = scene.effect_sliders.dof_amount
    var before_arrow: float = dof_slider.value
    await send_key(KEY_RIGHT)
    check(is_equal_approx(dof_slider.value,minf(dof_slider.max_value,before_arrow+dof_slider.step)) and is_equal_approx(scene.attributes.dof_blur_amount,dof_slider.value) and not scene.player.controls_enabled,"right arrow edits a focused DOF slider without enabling character movement")
    await send_key(KEY_M)
    check(not scene.panel.visible and viewport.gui_get_focus_owner() != dof_slider and not scene.player.controls_enabled,"M releases DOF slider focus and preserves previously disabled player controls")
    scene.set_control_panel_visible(true)
    await select_section("glow")
    await check_panel("1280 by 720 glow",false)
    await snapshot("scene-settings-panel-glow-720")
    scene.player.controls_enabled = true
    await pointer_edit("glow_intensity",.75)
    await snapshot("scene-settings-input-glow-720")
    await send_key(KEY_M)
    check(not scene.panel.visible and viewport.gui_get_focus_owner() != scene.effect_sliders.glow_intensity and scene.player.controls_enabled,"M releases Glow slider focus and restores previously enabled player controls")
    scene.player.controls_enabled = false
    var renderer: String = RenderingServer.get_current_rendering_method()
    var adapter: String = RenderingServer.get_video_adapter_name()
    check(renderer == "forward_plus" and not adapter.is_empty(),"all fifteen captures use the actual Forward Plus GPU renderer")
    var sources: Dictionary = {}
    for path in SOURCE_FILES:
        sources[path] = FileAccess.get_sha256("res://"+path)
    var report := {
        "schema":1,"passed":failed.is_empty(),"checks":validation_checks,"failures":failed,
        "runtime_fingerprint":runtime_fingerprint,"source_fingerprint":source_fingerprint,"source_files":sources,
        "gpu":true,"renderer":renderer,"adapter":adapter,"screenshots":screenshots,"pointer_tests":pointer_tests,
        "saved_settings":saved_settings,"restored_settings":restored_settings,"settings_sha256":saved_settings_hash,
        "settings_scope":"isolated GPU preference file under requested build output; no normal user settings read or written",
        "scope":"original frozen Forward+ frames for numeric DOF and Glow endpoints, saved-versus-fresh-instance dusk reload, all five panel sections and real mouse/keyboard interaction at 720p; automatic main-scene startup is verified in the separate runtime test",
    }
    var report_file := FileAccess.open(output.path_join("scene-settings-gpu-report.json"),FileAccess.WRITE)
    if report_file == null:
        push_error("Unable to write scene-settings-gpu-report.json")
        quit(3)
        return
    report_file.store_string(JSON.stringify(report,"  ")+"\n")
    print("SCENE_SETTINGS_CAPTURE_DONE passed=",report.passed," screenshots=",screenshots.size()," checks=",validation_checks.size())
    quit(0 if failed.is_empty() else 1)
