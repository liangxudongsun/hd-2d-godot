extends SceneTree
## Live-control contracts. User preferences are never read or overwritten.
var scene: Node3D
var checks: Array = []
var failures: Array = []
var output := "res://build/forest-hamlet/cloud-tuning-r4"
var runtime_fingerprint := ""

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--forest-output="):
            output = arg.trim_prefix("--forest-output=")
        elif arg.begins_with("--output="):
            output = arg.trim_prefix("--output=")
        elif arg.begins_with("--forest-fingerprint="):
            runtime_fingerprint = arg.trim_prefix("--forest-fingerprint=")
    output = ProjectSettings.globalize_path(output)
    DirAccess.make_dir_recursive_absolute(output)
    call_deferred("run")

func check(condition: bool, label: String) -> void:
    checks.append({"label":label,"passed":condition})
    if not condition:
        failures.append(label)
        print("CLOUD_TUNING_FAIL ",label)

func settle(frames: int = 3) -> void:
    for i in range(frames):
        await process_frame

func same_tuning(contrast: float, density: float) -> bool:
    return is_equal_approx(scene.cloud_lighting.contrast_strength,contrast) and is_equal_approx(scene.cloud_lighting.cloud_density,density)

func shader_matches() -> bool:
    var material: ShaderMaterial = scene.cloud_lighting.material
    return is_equal_approx(float(material.get_shader_parameter("contrast_strength")),scene.cloud_lighting.contrast_strength) and is_equal_approx(float(material.get_shader_parameter("cloud_density")),scene.cloud_lighting.cloud_density)

func split_matches(contrast: float) -> bool:
    var split: Dictionary = scene.cloud_lighting.snapshot().light_split
    return is_equal_approx(float(split.base70.energy),scene.main_light.light_energy*(1.0-contrast)) and is_equal_approx(float(split.cloud30.energy),scene.main_light.light_energy*contrast) and is_equal_approx(float(split.base_ratio),1.0-contrast) and is_equal_approx(float(split.cloud_ratio),contrast) and is_equal_approx(float(split.total_direct_energy),scene.main_light.light_energy)

func default_transfer_matches() -> bool:
    for index in range(101):
        var density := float(index)/100.0
        var expected := smoothstep(.515-.12,.515,density)*lerpf(.10,.30,smoothstep(.515,.515+.18,density))
        if not is_equal_approx(scene.cloud_lighting._attenuation_from_density(density),expected):
            return false
    return true

func run() -> void:
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    scene.cloud_settings_enabled = false
    scene.settings_path = output.path_join("isolated-cloud-settings.cfg")
    root.add_child(scene)
    for i in range(45):
        await physics_frame
    scene.frozen = true
    scene.player.set_physics_process(false)
    scene.cloud_lighting.set_time(24.0)
    scene.global_lighting.set_time(57.0)
    scene.cloud_lighting.sync_sun_lights()
    var initial: Dictionary = scene.snapshot_state()
    check(same_tuning(.30,.5) and shader_matches() and split_matches(.30),"unsaved scene starts with accepted contrast 30 and density 50 defaults with the same 70/30 sun split")
    check(default_transfer_matches(),"default natural density transfer exactly retains the previous thin 10 percent and thick 30 percent behavior")
    check(scene.tuning_sliders.size()==2 and scene.tuning_sliders.has("contrast") and scene.tuning_sliders.has("density"),"both public tuning controls are real HSlider instances")
    var contrast: HSlider = scene.tuning_sliders.contrast
    var density: HSlider = scene.tuning_sliders.density
    check(contrast.min_value==0.0 and contrast.max_value==80.0 and density.min_value==0.0 and density.max_value==100.0 and contrast.step==1.0 and density.step==1.0,"contrast covers 0 to 80 percent and density covers 0 to 100 percent with one percent steps")
    var initial_contrast_text: String = scene.tuning_value_labels.contrast.text
    var initial_density_text: String = scene.tuning_value_labels.density.text
    contrast.value = 35.0
    density.value = 72.0
    await settle()
    check(same_tuning(.35,.72) and shader_matches(),"actual slider value_changed signals immediately reach both production shader parameters")
    check(scene.tuning_value_labels.contrast.text!=initial_contrast_text and scene.tuning_value_labels.density.text!=initial_density_text and not scene.tuning_value_labels.contrast.text.is_empty() and not scene.tuning_value_labels.density.text.is_empty(),"both visible value labels follow the live slider values")
    var edited: Dictionary = scene.snapshot_state()
    scene.set_time_preset("dusk")
    scene.set_feature("clouds",false)
    scene.set_feature("clouds",true)
    scene.set_time_preset("day")
    check(same_tuning(.35,.72) and shader_matches(),"day dusk and cloud visibility changes preserve the chosen tuning")
    check(is_equal_approx(scene.cloud_lighting.clock_seconds,24.0) and is_equal_approx(scene.global_lighting.clock_seconds,57.0),"tuning and preset changes never reset independent cloud or global light clocks")
    var split: Dictionary = scene.cloud_lighting.snapshot().light_split
    check(split_matches(.35),"current contrast directly controls the native sun split while preserving total light energy")
    check(split.base70.shadow_enabled and split.cloud30.shadow_enabled and is_equal_approx(float(split.base70.shadow_opacity),1.0) and is_equal_approx(float(split.cloud30.shadow_opacity),1.0),"ordinary object shadows stay enabled and opaque on both sun branches")
    scene.set_cloud_contrast(2.0)
    scene.set_cloud_density(-2.0)
    check(same_tuning(.80,0.0) and shader_matches() and split_matches(.80),"out of range settings clamp to 80 percent attenuation with a protected 20 percent sun branch")
    scene.set_cloud_contrast(NAN)
    scene.set_cloud_density(INF)
    check(same_tuning(.80,0.0) and shader_matches(),"nonfinite settings cannot poison the live lighting shader")
    var endpoints_ok := true
    for index in range(101):
        endpoints_ok = endpoints_ok and is_zero_approx(scene.cloud_lighting._attenuation_from_density(float(index)/100.0))
    scene.set_cloud_density(1.0)
    for index in range(101):
        endpoints_ok = endpoints_ok and is_equal_approx(scene.cloud_lighting._attenuation_from_density(float(index)/100.0),.80)
    scene.set_cloud_contrast(0.0)
    for index in range(101):
        endpoints_ok = endpoints_ok and is_zero_approx(scene.cloud_lighting._attenuation_from_density(float(index)/100.0))
    var zero_ray: Dictionary = scene.cloud_lighting.cloud_ray_sample(Vector3(0,.1,2))
    check(endpoints_ok and split_matches(0.0) and is_finite(float(zero_ray.branch_blocked_coverage)) and is_zero_approx(float(zero_ray.branch_blocked_coverage)),"density zero clears clouds density 100 reaches the selected 80 percent maximum and zero contrast safely removes attenuation")
    scene.cloud_lighting.set_uniform_attenuation(.10)
    check(is_equal_approx(scene.cloud_lighting._attenuation_from_density(.0),.10) and is_equal_approx(scene.cloud_lighting._attenuation_from_density(1.0),.10) and split_matches(.30),"explicit legacy radiometry calibration bypasses controls and restores its original 70/30 split")
    scene.cloud_lighting.set_uniform_attenuation(-1.0)
    check(split_matches(0.0),"leaving calibration restores the user's current zero contrast split")
    scene.tuning_reset_button.pressed.emit()
    await settle()
    check(same_tuning(.30,.5) and contrast.value==30.0 and density.value==50.0 and shader_matches() and default_transfer_matches() and split_matches(.30),"restore default button restores both sliders shader and accepted 10/30 percent density transfer")
    contrast.value = 43.0
    density.value = 68.0
    scene.tuning_save_button.pressed.emit()
    await settle()
    check(FileAccess.file_exists(scene.settings_path),"save button writes a project-isolated test preference file")
    scene.tuning_reset_button.pressed.emit()
    scene.tuning_load_button.pressed.emit()
    await settle()
    check(same_tuning(.43,.68) and contrast.value==43.0 and density.value==68.0 and shader_matches(),"load button restores saved values and both visible sliders")
    var restored: Dictionary = scene.snapshot_state()
    scene.tuning_reset_button.pressed.emit()
    var frame: Dictionary = scene.framing_state()
    check(absf(frame.pitch_degrees-14.0)<.1 and is_equal_approx(scene.camera.fov,39.0) and frame.silhouette_rect[3]>.22 and frame.silhouette_rect[3]<.24 and frame.in_frame,"close camera and original actor screen proportion remain unchanged")
    check(scene.world.vegetation_sprites.size()==218 and scene.player.sprite.scale.is_equal_approx(Vector3.ONE) and is_equal_approx(scene.player.sprite.pixel_size,.009),"all 218 image plants and original character scale remain unchanged")
    var source_files: Dictionary = {}
    for path in ["scripts/forest_hamlet/scene.gd","scripts/forest_hamlet/cloud_lighting.gd","shaders/forest_hamlet/cloud_occluder.gdshader","tests/forest_hamlet/cloud_tuning_runtime.gd"]:
        source_files[path] = FileAccess.get_sha256("res://"+path)
    var report := {"schema":1,"passed":failures.is_empty(),"checks":checks,"failures":failures,"runtime_fingerprint":runtime_fingerprint,"source_files":source_files,"initial":initial,"edited":edited,"restored":restored,"settings_scope":"isolated file under requested build output; normal user preferences neither read nor overwritten","scope":"actual scene and HSlider signal integration; real rendered differences and pointer routing are checked separately on GPU"}
    var file := FileAccess.open(output.path_join("cloud-tuning-runtime-report.json"),FileAccess.WRITE)
    if file==null:
        push_error("Unable to write cloud-tuning-runtime-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("CLOUD_TUNING_RUNTIME_DONE passed=",report.passed," checks=",checks.size())
    quit(0 if failures.is_empty() else 1)
