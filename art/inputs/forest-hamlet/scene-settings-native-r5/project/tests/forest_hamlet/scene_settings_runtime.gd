extends SceneTree
## Public scene settings, real controls, isolated persistence and unchanged physics.
const DEFAULT_PARAMETERS := {
    "cloud_contrast":.30,"cloud_density":.5,
    "dof_amount":.035,"dof_near_margin":5.0,"dof_near_transition":3.0,"dof_far_margin":10.0,"dof_far_transition":16.0,
    "glow_intensity":.42,"glow_strength":.85,"glow_bloom":.025,"glow_hdr_threshold":.95,"glow_hdr_scale":1.6,
    "exposure":1.0,"contrast":1.06,"saturation":.98,
    "wind_strength":.06,"parallax_strength":.35,"fog_density_scale":1.0,"sun_variation":.18,"ambient_variation":.10,
}
const EDIT_PARAMETERS := {
    "cloud_contrast":.43,"cloud_density":.68,
    "dof_amount":.12,"dof_near_margin":2.5,"dof_near_transition":2.0,"dof_far_margin":6.0,"dof_far_transition":8.0,
    "glow_intensity":.78,"glow_strength":1.25,"glow_bloom":.08,"glow_hdr_threshold":1.2,"glow_hdr_scale":2.1,
    "exposure":1.15,"contrast":1.14,"saturation":1.08,
    "wind_strength":.09,"parallax_strength":.52,"fog_density_scale":.7,"sun_variation":.27,"ambient_variation":.16,
}
const FEATURE_NAMES := ["normals","bloom","dof","wind","backdrop_normals","parallax","clouds","atmosphere","global_light"]
const SOURCE_FILES := [
    "scripts/forest_hamlet/scene.gd","scripts/forest_hamlet/close_scene.gd","scripts/forest_hamlet/scene_settings.gd","scripts/forest_hamlet/settings_panel.gd",
    "scripts/forest_hamlet/cloud_lighting.gd","scripts/forest_hamlet/global_lighting.gd","scripts/forest_hamlet/actor.gd",
    "shaders/forest_hamlet/cloud_occluder.gdshader","tests/forest_hamlet/scene_settings_runtime.gd",
    "tools/forest_hamlet/capture_scene_settings.gd","tools/forest_hamlet/scene_settings_checks.py","tools/forest_hamlet/run_scene_settings.py",
]
var scene: Node3D
var checks: Array = []
var failures: Array = []
var output := "res://build/forest-hamlet/scene-settings-r5"
var runtime_fingerprint := ""
var source_fingerprint := ""
var saved_path := ""

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--forest-output="):
            output = arg.trim_prefix("--forest-output=")
        elif arg.begins_with("--forest-fingerprint="):
            runtime_fingerprint = arg.trim_prefix("--forest-fingerprint=")
        elif arg.begins_with("--forest-source-fingerprint="):
            source_fingerprint = arg.trim_prefix("--forest-source-fingerprint=")
    output = ProjectSettings.globalize_path(output)
    DirAccess.make_dir_recursive_absolute(output)
    saved_path = output.path_join("isolated-scene-settings.cfg")
    call_deferred("run")

func check(condition: bool, label: String) -> void:
    checks.append({"label":label,"passed":condition})
    if not condition:
        failures.append(label)
        print("SCENE_SETTINGS_FAIL ",label)

func settle(frames: int = 3) -> void:
    for index in range(frames):
        await process_frame

func equivalent(left: Variant, right: Variant) -> bool:
    if typeof(left) in [TYPE_INT,TYPE_FLOAT] and typeof(right) in [TYPE_INT,TYPE_FLOAT]:
        return is_equal_approx(float(left),float(right))
    if typeof(left) != typeof(right):
        return false
    if left is Dictionary:
        if left.size() != right.size():
            return false
        for key in left:
            if not right.has(key) or not equivalent(left[key],right[key]):
                return false
        return true
    return left == right

func expected_default_profile() -> Dictionary:
    var features: Dictionary = {}
    for id in FEATURE_NAMES:
        features[id] = true
    return {"schema_version":2,"time_preset":"day","features":features,"parameters":DEFAULT_PARAMETERS.duplicate(true)}

func native_state() -> Dictionary:
    return {
        "dof_near_enabled":scene.attributes.dof_blur_near_enabled,"dof_far_enabled":scene.attributes.dof_blur_far_enabled,
        "dof_amount":scene.attributes.dof_blur_amount,"dof_near":scene.attributes.dof_blur_near_distance,
        "dof_near_transition":scene.attributes.dof_blur_near_transition,"dof_far":scene.attributes.dof_blur_far_distance,
        "dof_far_transition":scene.attributes.dof_blur_far_transition,
        "glow_enabled":scene.environment.glow_enabled,"glow_intensity":scene.environment.glow_intensity,
        "glow_strength":scene.environment.glow_strength,"glow_bloom":scene.environment.glow_bloom,
        "glow_hdr_threshold":scene.environment.glow_hdr_threshold,"glow_hdr_scale":scene.environment.glow_hdr_scale,
        "exposure":scene.environment.tonemap_exposure,"contrast":scene.environment.adjustment_contrast,
        "saturation":scene.environment.adjustment_saturation,"fog_density":scene.environment.fog_density,
        "volumetric_fog_density":scene.environment.volumetric_fog_density,
        "wind_strength":scene.world.foliage_material.get_shader_parameter("wind_strength"),
        "parallax_strength":scene.backdrop.parallax_strength,
        "cloud_contrast":scene.cloud_lighting.material.get_shader_parameter("contrast_strength"),
        "cloud_density":scene.cloud_lighting.material.get_shader_parameter("cloud_density"),
        "sun_energy":scene.main_light.light_energy,"ambient_energy":scene.environment.ambient_light_energy,
    }

func observed_state() -> Dictionary:
    var ui: Dictionary = {}
    for id in scene.effect_sliders:
        ui[id] = {"value":scene.effect_sliders[id].value,"label":scene.effect_value_labels[id].text}
    return {"settings":scene.get_scene_settings(),"native":native_state(),"controls":ui}

func native_matches(id: String, value: float) -> bool:
    var actual := 0.0
    var expected := value
    var depth: float = -scene.camera.to_local(scene.player.global_position).z
    match id:
        "cloud_contrast": actual = float(scene.cloud_lighting.material.get_shader_parameter("contrast_strength"))
        "cloud_density": actual = float(scene.cloud_lighting.material.get_shader_parameter("cloud_density"))
        "dof_amount": actual = scene.attributes.dof_blur_amount
        "dof_near_margin":
            actual = scene.attributes.dof_blur_near_distance
            expected = maxf(1.0,depth-value)
        "dof_near_transition": actual = scene.attributes.dof_blur_near_transition
        "dof_far_margin":
            actual = scene.attributes.dof_blur_far_distance
            expected = depth+value
        "dof_far_transition": actual = scene.attributes.dof_blur_far_transition
        "glow_intensity": actual = scene.environment.glow_intensity
        "glow_strength": actual = scene.environment.glow_strength
        "glow_bloom": actual = scene.environment.glow_bloom
        "glow_hdr_threshold": actual = scene.environment.glow_hdr_threshold
        "glow_hdr_scale": actual = scene.environment.glow_hdr_scale
        "exposure": actual = scene.environment.tonemap_exposure
        "contrast": actual = scene.environment.adjustment_contrast
        "saturation": actual = scene.environment.adjustment_saturation
        "wind_strength":
            actual = float(scene.world.foliage_material.get_shader_parameter("wind_strength"))
            expected = value if scene.values.wind else 0.0
        "parallax_strength": actual = scene.backdrop.parallax_strength
        "fog_density_scale":
            actual = scene.environment.fog_density
            expected = value*(.0015 if scene.time_preset == "day" else .0023)
            if not is_equal_approx(scene.environment.volumetric_fog_density,value*(.0030 if scene.time_preset == "day" else .0038)):
                return false
        "sun_variation": actual = float(scene.global_lighting.snapshot().sun_multiplier_bounds[1])-1.0
        "ambient_variation": actual = float(scene.global_lighting.snapshot().ambient_multiplier_bounds[1])-1.0
        _: return false
    return is_equal_approx(actual,expected)

func all_native_match(profile: Dictionary) -> bool:
    for id in profile.parameters:
        if not native_matches(id,float(profile.parameters[id])):
            return false
    return true

func feature_outputs_match() -> bool:
    return scene.environment.glow_enabled == scene.values.bloom \
        and scene.attributes.dof_blur_far_enabled == scene.values.dof and scene.attributes.dof_blur_near_enabled == scene.values.dof \
        and scene.world.ground_material.get_shader_parameter("use_normals") == scene.values.normals \
        and scene.backdrop.normals_enabled == scene.values.backdrop_normals and scene.backdrop.parallax_enabled == scene.values.parallax \
        and scene.cloud_lighting.enabled == scene.values.clouds and scene.environment.volumetric_fog_enabled == scene.values.atmosphere \
        and scene.global_lighting.enabled == scene.values.global_light \
        and native_matches("wind_strength",float(scene.get_scene_settings().parameters.wind_strength))

func replace_scene(as_main: bool, load_enabled: bool) -> void:
    if is_instance_valid(scene):
        if current_scene == scene:
            current_scene = null
        scene.queue_free()
        await settle()
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    scene.settings_path = saved_path
    scene.cloud_settings_enabled = load_enabled
    root.add_child(scene)
    if as_main:
        current_scene = scene
    for index in range(45):
        await physics_frame
    scene.frozen = true
    scene.player.set_physics_process(false)
    scene.player.velocity = Vector3.ZERO
    scene.update_camera(true)

func reject_fixture(section: String, key: String, invalid: Variant, label: String) -> void:
    var config := ConfigFile.new()
    check(config.load(saved_path) == OK,"invalid fixture starts from a complete saved profile: "+label)
    # A valid early value ensures failure cannot accidentally apply half a file.
    config.set_value("clouds","max_attenuation",.11)
    config.set_value(section,key,invalid)
    var path: String = output.path_join("invalid-"+label+".cfg")
    check(config.save(path) == OK,"invalid fixture writes in the isolated output: "+label)
    var before: Dictionary = observed_state()
    scene.settings_path = path
    var accepted: bool = scene.load_scene_settings()
    check(not accepted and equivalent(observed_state(),before),"invalid "+label+" rejects the whole load without changing any settings native outputs or visible controls")
    scene.settings_path = saved_path

func run() -> void:
    await replace_scene(false,false)
    var defaults: Dictionary = expected_default_profile()
    var initial: Dictionary = scene.snapshot_state()
    check(equivalent(scene.get_scene_settings(),defaults),"unsaved scene keeps all accepted scene defaults")
    check(all_native_match(defaults) and feature_outputs_match(),"accepted defaults reach the actual camera environment shader and lighting controllers")
    check(scene.effect_sliders.size() == 20 and scene.effect_value_labels.size() == 20,"all twenty numeric settings have actual live slider and value-label controls")
    check(scene.tuning_sliders.size() == 2 and scene.tuning_sliders.contrast == scene.effect_sliders.cloud_contrast and scene.tuning_sliders.density == scene.effect_sliders.cloud_density,"legacy cloud slider references retain their two-control contract")
    for id in EDIT_PARAMETERS:
        if not scene.effect_sliders.has(id) or not scene.effect_value_labels.has(id):
            check(false,"missing required public control: "+id)
            continue
        var slider: HSlider = scene.effect_sliders[id]
        var old_label: String = scene.effect_value_labels[id].text
        slider.value = float(EDIT_PARAMETERS[id])*(100.0 if id in ["cloud_contrast","cloud_density"] else 1.0)
        await settle(1)
        check(is_equal_approx(float(scene.get_scene_settings().parameters[id]),float(EDIT_PARAMETERS[id])) and native_matches(id,float(EDIT_PARAMETERS[id])),id+": actual HSlider value_changed updates the persisted setting and its live production effect")
        check(not scene.effect_value_labels[id].text.is_empty() and scene.effect_value_labels[id].text != old_label,id+": visible numeric label follows the slider")
    scene.cloud_lighting.set_time(24.0)
    scene.global_lighting.set_time(57.0)
    scene.set_time_preset("dusk")
    scene.set_time_preset("day")
    scene.update_camera(true)
    check(equivalent(scene.get_scene_settings().parameters,EDIT_PARAMETERS) and all_native_match(scene.get_scene_settings()),"day dusk and camera updates preserve all twenty chosen numeric effects")
    check(is_equal_approx(scene.cloud_lighting.clock_seconds,24.0) and is_equal_approx(scene.global_lighting.clock_seconds,57.0),"changing effects and presets never resets either independent lighting clock")
    scene.set_effect_parameter("sun_variation",0.0)
    scene.set_effect_parameter("ambient_variation",0.0)
    check(is_equal_approx(scene.main_light.light_energy,1.45) and is_equal_approx(scene.environment.ambient_light_energy,.55),"zero variation amplitudes remove native energy modulation at a nonzero clock")
    scene.set_effect_parameter("sun_variation",EDIT_PARAMETERS.sun_variation)
    scene.set_effect_parameter("ambient_variation",EDIT_PARAMETERS.ambient_variation)
    check(not is_equal_approx(scene.main_light.light_energy,1.45) and not is_equal_approx(scene.environment.ambient_light_energy,.55),"nonzero variation controls restore actual native light changes without resetting time")
    var before_nonfinite: Dictionary = observed_state()
    var rejected_nonfinite := true
    for id in EDIT_PARAMETERS:
        rejected_nonfinite = not scene.set_effect_parameter(id,NAN) and rejected_nonfinite
        rejected_nonfinite = not scene.set_effect_parameter(id,INF) and rejected_nonfinite
    check(rejected_nonfinite and equivalent(observed_state(),before_nonfinite),"nonfinite input to every public numeric setter is rejected atomically")
    check(not scene.set_effect_parameter("missing_setting",1.0) and equivalent(observed_state(),before_nonfinite),"unknown parameter names cannot alter any live setting")
    scene.set_effect_parameter("dof_amount",8.0)
    scene.set_effect_parameter("glow_intensity",-4.0)
    check(is_equal_approx(scene.attributes.dof_blur_amount,.3) and is_zero_approx(scene.environment.glow_intensity) and is_equal_approx(scene.effect_sliders.dof_amount.value,.3) and is_zero_approx(scene.effect_sliders.glow_intensity.value),"finite out-of-range effect input clamps safely and synchronizes visible controls")
    scene.set_effect_parameter("dof_amount",EDIT_PARAMETERS.dof_amount)
    scene.set_effect_parameter("glow_intensity",EDIT_PARAMETERS.glow_intensity)
    for index in range(FEATURE_NAMES.size()):
        var id: String = FEATURE_NAMES[index]
        scene.feature_buttons[id].button_pressed = index % 2 == 0
    scene.time_buttons.dusk.pressed.emit()
    await settle()
    check(scene.time_preset == "dusk" and feature_outputs_match(),"real preset buttons and feature toggles drive all nine live switches")
    var selected: Dictionary = scene.get_scene_settings()
    check(equivalent(selected.parameters,EDIT_PARAMETERS),"feature toggles preserve the numeric settings they temporarily disable")
    scene.tuning_save_button.pressed.emit()
    await settle()
    check(FileAccess.file_exists(saved_path) and not FileAccess.file_exists(saved_path+".tmp"),"save button writes a complete isolated profile and removes its atomic temporary file")
    var saved_hash: String = FileAccess.get_sha256(saved_path)
    var saved_config := ConfigFile.new()
    check(saved_config.load(saved_path) == OK and saved_config.get_value("scene","schema_version",0) == 2 and saved_config.get_value("clouds","schema_version",0) == 1,"saved file is version two while retaining the version one cloud compatibility section")
    scene.tuning_reset_button.pressed.emit()
    await settle()
    check(equivalent(scene.get_scene_settings(),defaults) and all_native_match(defaults) and feature_outputs_match(),"restore-default button resets every numeric value all switches and the time preset")
    scene.tuning_load_button.pressed.emit()
    await settle()
    check(equivalent(scene.get_scene_settings(),selected) and all_native_match(selected) and feature_outputs_match(),"load button round-trips all twenty numbers nine flags and the dusk preset")
    var restored: Dictionary = observed_state()
    await reject_fixture("scene","schema_version",999,"unsupported-schema")
    await reject_fixture("scene","time_preset","midnight","unknown-preset")
    await reject_fixture("features","bloom","true","non-boolean-feature")
    await reject_fixture("effects","glow_hdr_scale","bright","invalid-late-number")
    var invalid_profile: Dictionary = selected.duplicate(true)
    invalid_profile.parameters.cloud_contrast = .11
    invalid_profile.parameters.glow_strength = NAN
    check(not scene.apply_scene_settings(invalid_profile) and equivalent(observed_state(),restored),"invalid public profile application is all-or-nothing across early and late settings")
    var partial := ConfigFile.new()
    partial.load(saved_path)
    partial.erase_section_key("effects","glow_strength")
    var partial_path: String = output.path_join("partial-scene-settings.cfg")
    check(partial.save(partial_path) == OK,"partial version two fixture writes in the isolated output")
    scene.settings_path = partial_path
    var partial_expected: Dictionary = selected.duplicate(true)
    partial_expected.parameters.glow_strength = DEFAULT_PARAMETERS.glow_strength
    check(scene.load_scene_settings() and equivalent(scene.get_scene_settings(),partial_expected),"a missing new version two numeric key receives its accepted default while other saved values restore")
    var legacy := ConfigFile.new()
    legacy.set_value("clouds","schema_version",1)
    legacy.set_value("clouds","max_attenuation",.37)
    legacy.set_value("clouds","density",.61)
    var legacy_path: String = output.path_join("legacy-cloud-settings.cfg")
    check(legacy.save(legacy_path) == OK,"legacy clouds-only fixture writes in the isolated output")
    scene.settings_path = legacy_path
    var legacy_expected: Dictionary = defaults.duplicate(true)
    legacy_expected.parameters.cloud_contrast = .37
    legacy_expected.parameters.cloud_density = .61
    check(scene.load_scene_settings() and equivalent(scene.get_scene_settings(),legacy_expected) and all_native_match(legacy_expected),"legacy clouds-only preferences migrate with their original cloud values and accepted defaults elsewhere")
    check(scene.save_scene_settings(),"migrated legacy preferences can be saved as a full version two profile")
    var migrated := ConfigFile.new()
    check(migrated.load(legacy_path) == OK and migrated.get_value("scene","schema_version",0) == 2,"legacy save produces the version two configuration schema")
    # A competing temporary file is a genuine save failure that must not
    # replace the valid destination or erase another operation's pending data.
    var blocker_path: String = saved_path+".tmp"
    var blocker := FileAccess.open(blocker_path,FileAccess.WRITE)
    check(blocker != null,"save-failure fixture exists")
    if blocker != null:
        blocker.store_string("isolated failure fixture\n")
        blocker.close()
    var blocker_hash: String = FileAccess.get_sha256(blocker_path)
    scene.settings_path = saved_path
    var before_failed_save: Dictionary = observed_state()
    check(not scene.save_scene_settings() and equivalent(observed_state(),before_failed_save) and FileAccess.get_sha256(saved_path) == saved_hash and FileAccess.get_sha256(blocker_path) == blocker_hash,"failed save preserves the current preview the last valid saved profile and a competing temporary file")
    DirAccess.remove_absolute(blocker_path)
    await replace_scene(false,true)
    check(equivalent(scene.get_scene_settings(),defaults),"child scene instantiation does not read existing preferences even when loading is enabled")
    await replace_scene(true,false)
    check(equivalent(scene.get_scene_settings(),defaults),"the explicit loading opt-out also protects main-scene tests and captures")
    await replace_scene(true,true)
    check(equivalent(scene.get_scene_settings(),selected) and all_native_match(selected) and feature_outputs_match(),"a fresh main scene automatically restores the saved dusk profile after ready")
    check(FileAccess.get_sha256(saved_path) == saved_hash,"startup loading never rewrites the saved preference file")
    var startup: Dictionary = observed_state()
    var frame: Dictionary = scene.framing_state()
    check(absf(float(frame.pitch_degrees)-14.0)<.1 and is_equal_approx(scene.camera.fov,39.0) and frame.silhouette_rect[3]>.22 and frame.silhouette_rect[3]<.24 and frame.in_frame,"original close camera and actor screen proportion remain unchanged")
    check(scene.player.sprite.scale.is_equal_approx(Vector3.ONE) and scene.player.scale.is_equal_approx(Vector3.ONE) and is_equal_approx(scene.player.sprite.pixel_size,.009) and scene.world.vegetation_sprites.size()==218,"all 218 plants and original character world scale remain intact")
    check(scene.player.color_atlases.size()==4 and scene.player.normal_atlases.size()==4 and scene.player.silver_atlases.size()==4,"all four original color normal and silver animation directions remain available")
    var expected_route: Array[Vector3] = [Vector3(-13,.15,1.8),Vector3(0,.15,1.8),Vector3(12,.15,1.8),Vector3(0,.15,1.8),Vector3(0,.15,-10),Vector3(0,.15,1.8)]
    check(scene.route_points == expected_route,"the original six route waypoints are unchanged")
    scene.frozen = false
    scene.player.controls_enabled = true
    scene.player.set_physics_process(true)
    scene.start_route()
    var frames := 0
    var min_y: float = scene.player.position.y
    var framing_safe := true
    var focus_safe := true
    while scene.route_running and frames < 7200:
        await physics_frame
        frames += 1
        min_y = minf(min_y,scene.player.position.y)
        var current: Dictionary = scene.framing_state()
        framing_safe = framing_safe and current.in_frame
        focus_safe = focus_safe and current.view_depth > current.dof_near and current.view_depth < current.dof_far
    if scene.route_running:
        scene.stop_route("timeout")
    check(scene.route_result.get("completed",false) and scene.route_result.get("waypoints",0)==6 and scene.route_trajectory.size()>30,"the original six-waypoint route still completes with real character physics and saved effects")
    check(min_y > -.5 and framing_safe and focus_safe,"the full original actor stays on terrain in frame and inside the edited sharp DOF interval throughout the route")
    check(equivalent(scene.get_scene_settings(),selected) and all_native_match(selected),"normal camera follow and route movement never replace chosen numeric settings with defaults")
    var sources: Dictionary = {}
    for path in SOURCE_FILES:
        sources[path] = FileAccess.get_sha256("res://"+path)
    var report := {
        "schema":1,"passed":failures.is_empty(),"checks":checks,"failures":failures,
        "runtime_fingerprint":runtime_fingerprint,"source_fingerprint":source_fingerprint,"source_files":sources,
        "initial":initial,"selected":selected,"restored":restored,"startup":startup,
        "route":scene.route_result,"minimum_route_height":min_y,"settings_sha256":saved_hash,
        "settings_scope":"isolated fixtures under requested build output; normal user preferences are neither read nor overwritten",
        "scope":"actual scene control signals, native effect outputs, complete persistence, failure behavior, fresh main-scene startup, unchanged source character and six-waypoint physics route; GPU differences checked separately",
    }
    var report_file := FileAccess.open(output.path_join("scene-settings-runtime-report.json"),FileAccess.WRITE)
    if report_file == null:
        push_error("Unable to write scene-settings-runtime-report.json")
        quit(3)
        return
    report_file.store_string(JSON.stringify(report,"  ")+"\n")
    print("SCENE_SETTINGS_RUNTIME_DONE passed=",report.passed," checks=",checks.size()," route=",scene.route_result.get("status","missing"))
    quit(0 if failures.is_empty() else 1)
