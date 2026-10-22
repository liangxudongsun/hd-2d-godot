extends "res://tools/forest_hamlet/capture.gd"
## Nine actual GPU frames for cloud controls, with untouched user preferences.
var validation_checks: Array = []
var pointer_test: Dictionary = {}

func _initialize() -> void:
    output = "res://build/forest-hamlet/cloud-tuning-r4"
    super._initialize()

func check(condition: bool, label: String) -> void:
    validation_checks.append({"label":label,"passed":condition})
    if not condition:
        failed.append(label)
        print("CLOUD_TUNING_CAPTURE_FAIL ",label)

func rect_array(rect: Rect2) -> Array:
    return [rect.position.x,rect.position.y,rect.size.x,rect.size.y]

func panel_state() -> Dictionary:
    var viewport_rect := Rect2(Vector2.ZERO,Vector2(viewport.size))
    var result := {"visible":scene.panel.is_visible_in_tree(),"panel_rect":rect_array(scene.panel.get_global_rect()),"viewport":[viewport.size.x,viewport.size.y],"controls":{}}
    for id in ["contrast","density"]:
        var slider: HSlider = scene.tuning_sliders[id]
        var label: Label = scene.tuning_value_labels[id]
        var rect := slider.get_global_rect()
        result.controls[id] = {"value":slider.value,"min":slider.min_value,"max":slider.max_value,"rect":rect_array(rect),"visible":slider.is_visible_in_tree(),"inside_viewport":viewport_rect.encloses(rect),"label":label.text,"label_rect":rect_array(label.get_global_rect()),"label_inside_viewport":viewport_rect.encloses(label.get_global_rect())}
    return result

func snapshot(label: String) -> void:
    scene.cloud_lighting.sync_sun_lights()
    scene.backdrop.update_frame()
    for i in range(24):
        await process_frame
    await super.snapshot(label)
    screenshots[-1]["panel"] = panel_state()
    var split: Dictionary = scene.cloud_lighting.snapshot().light_split
    var contrast: float = scene.cloud_lighting.contrast_strength
    check(is_equal_approx(float(split.total_direct_energy),scene.main_light.light_energy) and is_equal_approx(float(split.cloud_ratio),contrast) and is_equal_approx(float(split.base_ratio),1.0-contrast) and float(split.base_ratio)>=.199999,label+": selected cloud contrast conserves sunlight with at least a 20 percent unoccluded branch")
    check(is_equal_approx(scene.cloud_lighting.clock_seconds,0.0) and is_equal_approx(scene.global_lighting.clock_seconds,0.0),label+": independent light clocks stay frozen for the comparison")

func check_panel(label: String) -> void:
    var state := panel_state()
    var viewport_rect := Rect2(Vector2.ZERO,Vector2(viewport.size))
    check(state.visible and viewport_rect.encloses(scene.panel.get_global_rect()),label+": whole panel lies inside the viewport")
    for id in ["contrast","density"]:
        var row: Dictionary = state.controls[id]
        check(row.visible and row.inside_viewport and row.label_inside_viewport and row.rect[2]>=120.0 and row.rect[3]>=20.0 and not row.label.is_empty(),label+": "+id+" slider and live value label are visible and usable")

func tune(contrast: float, density: float) -> void:
    # Exercise the same value_changed signal route the user drives.
    scene.tuning_sliders.contrast.value = contrast*100.0
    scene.tuning_sliders.density.value = density*100.0

func send_key(code: Key) -> void:
    for pressed in [true,false]:
        var event := InputEventKey.new()
        event.keycode = code
        event.physical_keycode = code
        event.pressed = pressed
        viewport.push_input(event,true)
        await process_frame

func run() -> void:
    if DisplayServer.get_name()=="headless":
        push_error("Cloud tuning evidence requires a real graphical GPU.")
        quit(2)
        return
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS,true)
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    scene.cloud_settings_enabled = false
    viewport.add_child(scene)
    for i in range(45):
        await physics_frame
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
    scene.update_camera(true)
    scene.backdrop.update_frame()
    comparison_frozen = true
    scene.set_time_preset("day")
    scene.cloud_lighting.set_time(0.0)
    scene.global_lighting.set_time(0.0)
    scene.cloud_lighting.set_uniform_attenuation(-1.0)
    scene.overlay.hide()
    tune(.30,.5)
    await snapshot("cloud-tuning-default")
    tune(.10,.5)
    await snapshot("cloud-tuning-contrast-low")
    tune(0.0,.5)
    await snapshot("cloud-tuning-contrast-zero")
    tune(.30,0.0)
    await snapshot("cloud-tuning-density-zero")
    tune(.30,1.0)
    await snapshot("cloud-tuning-density-full")
    tune(.80,1.0)
    await snapshot("cloud-tuning-contrast-maximum")
    tune(.30,.5)
    scene.overlay.show()
    scene.panel.show()
    await snapshot("cloud-tuning-panel-1080")
    check_panel("1920 by 1080")
    viewport.size = Vector2i(1280,720)
    for i in range(8):
        await process_frame
    await snapshot("cloud-tuning-panel-720")
    check_panel("1280 by 720")
    var slider: HSlider = scene.tuning_sliders.density
    var before := slider.value
    var rect := slider.get_global_rect()
    var pointer := Vector2(rect.position.x+rect.size.x*.25,rect.get_center().y)
    for pressed in [true,false]:
        var event := InputEventMouseButton.new()
        event.button_index = MOUSE_BUTTON_LEFT
        event.pressed = pressed
        event.position = pointer
        event.global_position = pointer
        viewport.push_input(event,true)
        await process_frame
    var after := slider.value
    pointer_test = {"control":"density","before":before,"after":after,"pointer":[pointer.x,pointer.y],"shader_value":scene.cloud_lighting.material.get_shader_parameter("cloud_density"),"method":"InputEventMouseButton routed through the live SubViewport GUI"}
    check(absf(after-before)>10.0 and after>=10.0 and after<=40.0 and is_equal_approx(scene.cloud_lighting.cloud_density,after/100.0),"real viewport mouse press reaches the visible density slider and production lighting")
    await snapshot("cloud-tuning-input-720")
    check_panel("1280 by 720 after mouse input")
    # Exercise the real GUI key path after all nine original screenshots.
    # Keep pointer_test and its screenshot values unchanged for pixel checks.
    check(viewport.gui_get_focus_owner()==slider and not scene.player.controls_enabled,"mouse focus on the density slider prevents character movement")
    await send_key(KEY_RIGHT)
    check(is_equal_approx(slider.value,after+1.0) and viewport.gui_get_focus_owner()==slider and not scene.player.controls_enabled and is_equal_approx(scene.cloud_lighting.cloud_density,slider.value/100.0),"right arrow changes the focused slider by one step without enabling character movement")
    await send_key(KEY_M)
    check(not scene.panel.visible and not scene.tuning_sliders.values().has(viewport.gui_get_focus_owner()) and not scene.player.controls_enabled,"M closes the panel releases slider focus and preserves previously disabled controls")
    scene.set_control_panel_visible(true)
    scene.player.controls_enabled = true
    scene.tuning_sliders.contrast.grab_focus()
    var focus_disabled_controls: bool = not scene.player.controls_enabled
    await send_key(KEY_M)
    check(focus_disabled_controls and not scene.panel.visible and not scene.tuning_sliders.values().has(viewport.gui_get_focus_owner()) and scene.player.controls_enabled,"M restores previously enabled character controls after a focused slider is dismissed")
    scene.player.controls_enabled = false
    var renderer := RenderingServer.get_current_rendering_method()
    var adapter := RenderingServer.get_video_adapter_name()
    check(renderer=="forward_plus" and not adapter.is_empty(),"capture uses the actual Forward Plus GPU renderer")
    var source_files: Dictionary = {}
    for path in ["scripts/forest_hamlet/scene.gd","scripts/forest_hamlet/cloud_lighting.gd","shaders/forest_hamlet/cloud_occluder.gdshader","tools/forest_hamlet/capture_cloud_tuning.gd","tools/forest_hamlet/cloud_tuning_checks.py","tools/forest_hamlet/run_cloud_tuning.py"]:
        source_files[path] = FileAccess.get_sha256("res://"+path)
    var report := {"schema":1,"passed":failed.is_empty(),"checks":validation_checks,"failures":failed,"runtime_fingerprint":runtime_fingerprint,"source_files":source_files,"gpu":true,"renderer":renderer,"adapter":adapter,"screenshots":screenshots,"pointer_test":pointer_test,"scope":"six frozen production scene comparisons including the selected 80 percent maximum plus panel layout at two sizes and actual GUI mouse input; no new scene route or calibrated radiometry claim"}
    var file := FileAccess.open(output.path_join("cloud-tuning-gpu-report.json"),FileAccess.WRITE)
    if file==null:
        push_error("Unable to write cloud-tuning-gpu-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("CLOUD_TUNING_CAPTURE_DONE passed=",report.passed," screenshots=",screenshots.size()," checks=",validation_checks.size())
    quit(0 if failed.is_empty() else 1)
