extends SceneTree
## Runtime contracts; visible lighting is independently checked by GPU read-back.
var scene: Node3D
var checks: Array = []
var failures: Array = []
var output := "res://build/forest-hamlet/atmosphere-r3-final"

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--forest-output="):
            output = arg.trim_prefix("--forest-output=")
        elif arg.begins_with("--output="):
            output = arg.trim_prefix("--output=")
    output = ProjectSettings.globalize_path(output)
    DirAccess.make_dir_recursive_absolute(output)
    call_deferred("run")

func check(condition: bool, label: String) -> void:
    checks.append({"label":label,"passed":condition})
    if not condition:
        failures.append(label)
        print("ATMOSPHERE_FAIL ",label)

func settle(frames: int) -> void:
    for i in range(frames):
        await physics_frame

func geometry_under(node: Node) -> Array:
    var result: Array = []
    if node is GeometryInstance3D:
        result.append(node)
    for child in node.get_children():
        result.append_array(geometry_under(child))
    return result

func main_peak(state: Dictionary) -> Vector2:
    for item in state.get("landmarks",[]):
        if item.get("id","") == "main_peak":
            return Vector2(item.projected_pixels[0],item.projected_pixels[1])
    return Vector2(INF,INF)

func split_energy_matches_source() -> bool:
    var split: Dictionary = scene.cloud_lighting.snapshot().light_split
    return is_equal_approx(float(split.base70.energy),scene.main_light.light_energy*.70) and is_equal_approx(float(split.cloud30.energy),scene.main_light.light_energy*.30) and is_equal_approx(float(split.total_direct_energy),scene.main_light.light_energy)

func partial_cloud_contracts() -> Dictionary:
    scene.cloud_lighting.sync_sun_lights()
    var initial: Dictionary = scene.cloud_lighting.snapshot()
    var split: Dictionary = initial.light_split
    var layer: int = split.cloud_layer_mask
    check(split.source.sky_mode==DirectionalLight3D.SKY_MODE_SKY_ONLY and split.base70.sky_mode==DirectionalLight3D.SKY_MODE_LIGHT_ONLY and split.cloud30.sky_mode==DirectionalLight3D.SKY_MODE_LIGHT_ONLY and split.real_scene_light_count==2,"authoritative sky sun feeds exactly two real native scene light branches")
    check(split_energy_matches_source(),"native 70 and 30 percent branch energies sum to the authoritative sun")
    check(initial.caster_layers==layer and (int(split.base70.shadow_caster_mask)&layer)==0 and (int(split.cloud30.shadow_caster_mask)&layer)==layer,"only the 30 percent native branch sees the exclusive cloud caster layer")
    check(split.base70.shadow_enabled and split.cloud30.shadow_enabled and is_equal_approx(float(split.base70.shadow_opacity),1.0) and is_equal_approx(float(split.cloud30.shadow_opacity),1.0) and (int(split.base70.shadow_caster_mask)&1)==1 and (int(split.cloud30.shadow_caster_mask)&1)==1,"both native branches preserve opaque ordinary entity shadows")
    check(split.base70.direction==split.source.direction and split.cloud30.direction==split.source.direction and split.base70.color==split.source.color and split.cloud30.color==split.source.color,"split native lights retain the authoritative sun direction and color")
    var states: Array = []
    var controls_ok := true
    for attenuation in [0.0,.10,.30]:
        scene.cloud_lighting.set_uniform_attenuation(attenuation)
        var state: Dictionary = scene.cloud_lighting.snapshot()
        var ray: Dictionary = scene.cloud_lighting.cloud_ray_sample(Vector3(0,.1,2))
        controls_ok = controls_ok and is_equal_approx(float(state.uniform_attenuation),attenuation) and ray.inside_caster and is_equal_approx(float(ray.effective_attenuation),attenuation) and is_equal_approx(float(ray.branch_blocked_coverage),attenuation/.30) and is_equal_approx(float(ray.expected_direct_transmittance),1.0-attenuation)
        states.append({"state":state,"ray_diagnostic":ray})
    check(controls_ok,"uniform calibration controls request clear thin and thick coverage on the production cloud shader")
    scene.cloud_lighting.set_uniform_attenuation(.9)
    check(is_equal_approx(float(scene.cloud_lighting.snapshot().uniform_attenuation),.30),"cloud attenuation control clamps at the 30 percent maximum")
    scene.cloud_lighting.set_uniform_attenuation(-1.0)
    var transfer_ok := true
    var last_attenuation := 0.0
    var min_attenuation := 1.0
    var max_attenuation := 0.0
    for index in range(101):
        var value: float = scene.cloud_lighting._attenuation_from_density(float(index)/100.0)
        transfer_ok = transfer_ok and value>=last_attenuation-.000001 and value>=0.0 and value<=.30
        min_attenuation = minf(min_attenuation,value)
        max_attenuation = maxf(max_attenuation,value)
        last_attenuation = value
    check(transfer_ok and is_zero_approx(min_attenuation) and is_equal_approx(max_attenuation,.30) and is_equal_approx(scene.cloud_lighting._attenuation_from_density(scene.cloud_lighting.mask_cutoff),.10),"natural density transfer is monotonic clear to thin 10 percent to thick 30 percent")
    for repeat in range(20):
        scene.cloud_lighting.sync_sun_lights()
    check(split_energy_matches_source() and is_equal_approx(scene.main_light.light_energy,float(split.source.energy)),"repeated branch synchronization never compounds or changes total sunlight")
    scene.set_feature("clouds",false)
    var disabled: Dictionary = scene.cloud_lighting.snapshot()
    check(split_energy_matches_source() and disabled.light_split.base70.visible and disabled.light_split.cloud30.visible and not scene.cloud_lighting.caster.visible,"cloud off preserves both scene light branches and removes only cloud occlusion")
    scene.set_feature("clouds",true)
    return {"initial":initial,"uniform_controls":states,"disabled":disabled,"natural_transfer_range":[min_attenuation,max_attenuation],"scope":"Runtime energy and control contracts; actual transmission is measured separately on GPU receivers"}

func global_light_contracts() -> Dictionary:
    scene.set_time_preset("day")
    scene.set_feature("clouds",false)
    scene.cloud_lighting.set_time(24.0)
    scene.set_feature("global_light",true)
    scene.global_lighting.set_time(0.0)
    var zero: Dictionary = scene.global_lighting.snapshot()
    check(is_equal_approx(float(zero.sun_multiplier),1.0) and is_equal_approx(float(zero.ambient_multiplier),1.0),"global modulation has a neutral reproducible t0 baseline")
    var samples: Array = []
    var weak: Dictionary = zero
    var strong: Dictionary = zero
    var ambient_min := float(zero.ambient_multiplier)
    var ambient_max := ambient_min
    var consistent := true
    var bounded := true
    var branches_consistent := true
    for second in range(91):
        scene.global_lighting.set_time(float(second))
        scene.cloud_lighting.sync_sun_lights()
        var state: Dictionary = scene.global_lighting.snapshot()
        samples.append({"clock_seconds":state.clock_seconds,"sun_multiplier":state.sun_multiplier,"ambient_multiplier":state.ambient_multiplier,"sun_energy":state.sun_energy,"ambient_energy":state.ambient_energy})
        if float(state.sun_multiplier)<float(weak.sun_multiplier):
            weak = state
        if float(state.sun_multiplier)>float(strong.sun_multiplier):
            strong = state
        ambient_min = minf(ambient_min,float(state.ambient_multiplier))
        ambient_max = maxf(ambient_max,float(state.ambient_multiplier))
        consistent = consistent and is_equal_approx(scene.main_light.light_energy,float(state.sun_base_energy)*float(state.sun_multiplier)) and is_equal_approx(scene.environment.ambient_light_energy,float(state.ambient_base_energy)*float(state.ambient_multiplier))
        bounded = bounded and is_finite(float(state.sun_multiplier)) and is_finite(float(state.ambient_multiplier)) and float(state.sun_multiplier)>=float(state.sun_multiplier_bounds[0]) and float(state.sun_multiplier)<=float(state.sun_multiplier_bounds[1]) and float(state.ambient_multiplier)>=float(state.ambient_multiplier_bounds[0]) and float(state.ambient_multiplier)<=float(state.ambient_multiplier_bounds[1])
        branches_consistent = branches_consistent and split_energy_matches_source()
    check(float(strong.sun_multiplier)-float(weak.sun_multiplier)>.02 and ambient_max-ambient_min>.005,"seeded global sun and ambient modulation both vary across the 0 to 90 second scan")
    check(consistent and bounded,"global multipliers remain bounded and immediately drive actual native sun and ambient energies")
    check(branches_consistent,"independent global modulation reaches both native scene branches throughout all 91 time samples")
    check(not scene.cloud_lighting.snapshot().enabled and is_equal_approx(float(scene.cloud_lighting.snapshot().clock_seconds),24.0),"global variation works with cloud occlusion disabled and its independent clock held fixed")
    scene.global_lighting.set_time(float(strong.clock_seconds))
    var replay: Dictionary = scene.global_lighting.snapshot()
    check(is_equal_approx(float(replay.sun_energy),float(strong.sun_energy)) and is_equal_approx(float(replay.ambient_energy),float(strong.ambient_energy)),"explicit global time reproduces the same deterministic light energies")
    scene.set_feature("global_light",false)
    var disabled: Dictionary = scene.global_lighting.snapshot()
    check(not disabled.enabled and is_equal_approx(float(disabled.sun_multiplier),1.0) and is_equal_approx(float(disabled.ambient_multiplier),1.0) and is_equal_approx(scene.main_light.light_energy,1.45) and is_equal_approx(scene.environment.ambient_light_energy,.55),"disabling global modulation restores the day base energies")
    var preset_states: Array = []
    var base_safe := true
    var factors_safe := true
    scene.global_lighting.set_time(float(weak.clock_seconds))
    scene.set_feature("global_light",true)
    for id in ["day","dusk","day","dusk"]:
        scene.set_time_preset(id)
        scene.cloud_lighting.sync_sun_lights()
        var state: Dictionary = scene.global_lighting.snapshot()
        preset_states.append(state)
        var sun_base := 1.45 if id=="day" else 1.15
        var ambient_base := .55 if id=="day" else .40
        base_safe = base_safe and is_equal_approx(float(state.sun_base_energy),sun_base) and is_equal_approx(float(state.ambient_base_energy),ambient_base) and is_equal_approx(float(state.sun_energy),sun_base*float(weak.sun_multiplier)) and is_equal_approx(float(state.ambient_energy),ambient_base*float(weak.ambient_multiplier))
        factors_safe = factors_safe and is_equal_approx(float(state.clock_seconds),float(weak.clock_seconds)) and is_equal_approx(float(state.sun_multiplier),float(weak.sun_multiplier)) and is_equal_approx(float(state.ambient_multiplier),float(weak.ambient_multiplier))
        base_safe = base_safe and split_energy_matches_source()
    check(base_safe and factors_safe,"repeated day and dusk changes apply the same multipliers to fixed preset bases without accumulation")
    scene.set_feature("global_light",false)
    check(is_equal_approx(scene.main_light.light_energy,1.15) and is_equal_approx(scene.environment.ambient_light_energy,.40),"disabling global modulation also restores the dusk base energies")
    scene.set_time_preset("day")
    scene.set_feature("global_light",true)
    scene.global_lighting.set_time(float(weak.clock_seconds))
    var restored: Dictionary = scene.global_lighting.snapshot()
    check(is_equal_approx(float(restored.sun_energy),float(weak.sun_energy)) and is_equal_approx(float(restored.ambient_energy),float(weak.ambient_energy)),"reenabling modulation after preset and toggle cycles does not drift the day baseline")
    scene.global_lighting.set_motion_enabled(false)
    scene.global_lighting.tick(5.0)
    var paused: Dictionary = scene.global_lighting.snapshot()
    check(is_equal_approx(float(paused.clock_seconds),float(weak.clock_seconds)) and is_equal_approx(float(paused.sun_energy),float(weak.sun_energy)),"global motion pause holds its clock and energy")
    scene.global_lighting.set_motion_enabled(true)
    scene.global_lighting.tick(.5)
    var resumed: Dictionary = scene.global_lighting.snapshot()
    check(is_equal_approx(float(resumed.clock_seconds),float(weak.clock_seconds)+.5) and is_equal_approx(float(scene.cloud_lighting.snapshot().clock_seconds),24.0),"global ticking advances independently of the cloud clock")
    await settle(5)
    check(is_equal_approx(float(scene.global_lighting.snapshot().clock_seconds),float(resumed.clock_seconds)),"scene freeze holds the global light clock during actual process frames")
    scene.global_lighting.set_time(0.0)
    scene.cloud_lighting.sync_sun_lights()
    scene.set_feature("clouds",true)
    scene.cloud_lighting.set_time(0.0)
    return {"sample_interval_seconds":[0,90],"sample_step_seconds":1,"selection":"minimum and maximum sun multiplier","samples":samples,"weak":weak,"strong":strong,"disabled":disabled,"preset_states":preset_states,"paused":paused,"resumed":resumed}

func run() -> void:
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    root.add_child(scene)
    await settle(45)
    scene.frozen = true
    scene.player.set_physics_process(false)
    scene.set_time_preset("day")
    scene.global_lighting.set_time(0.0)
    scene.cloud_lighting.sync_sun_lights()
    scene.update_camera(true)
    scene.backdrop.update_frame()
    var initial: Dictionary = scene.snapshot_state()
    var frame: Dictionary = scene.framing_state()
    var spawn_pose: Vector3 = scene.player.position
    check(absf(frame.pitch_degrees-14.0)<.1 and is_equal_approx(scene.camera.fov,39.0),"near reference camera remains 14 degrees and 39 degree FOV")
    check(frame.silhouette_rect[3]>.22 and frame.silhouette_rect[3]<.24 and frame.in_frame,"original character keeps reference screen scale and complete silhouette")
    check(is_equal_approx(scene.player.sprite.pixel_size,.009) and scene.player.sprite.scale.is_equal_approx(Vector3.ONE),"original character pixel size and uniform aspect retained")
    check(scene.world.vegetation_sprites.size()==218,"all 218 existing image vegetation instances retained")
    check(scene.environment.glow_enabled and scene.environment.glow_intensity>0.0,"native WorldEnvironment Glow enabled")
    for id in ["backdrop_normals","parallax","clouds","atmosphere","bloom","global_light"]:
        check(scene.values.has(id),"public independent feature toggle: "+id)
    var backdrop: Dictionary = scene.backdrop.snapshot()
    check(backdrop.get("geometry_count",0)==1 and backdrop.get("parallax_kind","")=="single_distant_board","single distant board is honestly identified, not fabricated multilayer assets")
    check(backdrop.get("source_sha256","").length()==64,"backdrop source image identity is recorded")
    var bg_geometry: Array = geometry_under(scene.backdrop)
    var no_bg_shadow := not bg_geometry.is_empty()
    for geometry in bg_geometry:
        no_bg_shadow = no_bg_shadow and geometry.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    check(no_bg_shadow,"far background does not cast spurious shadows across the village")
    var sky_geometry: Array = geometry_under(scene.cloud_lighting)
    var shadows_only := not sky_geometry.is_empty()
    for geometry in sky_geometry:
        shadows_only = shadows_only and geometry.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
    check(shadows_only,"real overhead cloud geometry participates only in native shadow passes")
    scene.cloud_lighting.set_time(0.0)
    var cloud_a: Dictionary = scene.cloud_lighting.snapshot()
    var sun_energy: float = scene.main_light.light_energy
    var ambient_energy: float = scene.environment.ambient_light_energy
    scene.cloud_lighting.set_time(24.0)
    var cloud_b: Dictionary = scene.cloud_lighting.snapshot()
    check(is_equal_approx(float(cloud_a.get("clock_seconds",-1)),0.0) and is_equal_approx(float(cloud_b.get("clock_seconds",-1)),24.0),"cloud field has deterministic explicitly controllable time")
    check(is_equal_approx(sun_energy,scene.main_light.light_energy) and is_equal_approx(ambient_energy,scene.environment.ambient_light_energy),"cloud A/B keeps native sun and ambient stable with global modulation held at t0")
    check(cloud_b.get("shadow_only",false) and cloud_b.get("native_shadow_pass",false),"cloud diagnostics declare actual native shadow participation")
    scene.set_feature("clouds",false)
    check(not scene.cloud_lighting.snapshot().get("enabled",true),"cloud occlusion has an independent working off switch")
    scene.set_feature("clouds",true)
    scene.set_feature("atmosphere",false)
    check(not scene.environment.volumetric_fog_enabled,"volumetric atmosphere independently disabled")
    scene.set_feature("atmosphere",true)
    check(scene.environment.volumetric_fog_enabled,"volumetric atmosphere independently restored")
    scene.set_feature("backdrop_normals",false)
    check(not scene.backdrop.snapshot().get("normals_enabled",true),"far-range normal lighting independently disabled")
    scene.set_feature("backdrop_normals",true)
    check(scene.backdrop.snapshot().get("normals_enabled",false),"far-range normal lighting independently restored")
    var cloud_contracts: Dictionary = partial_cloud_contracts()
    var global_contracts: Dictionary = await global_light_contracts()
    var poses: Array = []
    for enabled in [false,true]:
        scene.set_feature("parallax",enabled)
        var projected: Array[Vector2] = []
        for x in [-10.0,10.0]:
            scene.player.position = Vector3(x,spawn_pose.y,spawn_pose.z)
            scene.update_camera(true)
            scene.backdrop.update_frame()
            var state: Dictionary = scene.backdrop.snapshot()
            projected.append(main_peak(state))
            poses.append({"parallax":enabled,"player_x":x,"backdrop":state})
            check(scene.framing_state().in_frame,"full character remains framed while changing parallax camera x="+str(x))
            if state.has("viewport_coverage_ok"):
                check(state.viewport_coverage_ok,"distant image covers the viewport at x="+str(x))
        var distance: float = projected[0].distance_to(projected[1])
        check(is_finite(distance) and (distance>.5 if enabled else distance<.5),"parallax on moves the same snow peak; parallax off locks it" if enabled else "disabled parallax keeps snow peak fixed under camera translation")
    scene.player.position = spawn_pose
    scene.update_camera(true)
    scene.backdrop.update_frame()
    var time_states: Array = []
    for preset in ["day","dusk"]:
        scene.set_time_preset(preset)
        scene.cloud_lighting.set_time(0.0)
        scene.global_lighting.set_time(0.0)
        scene.cloud_lighting.sync_sun_lights()
        scene.backdrop.update_frame()
        time_states.append(scene.snapshot_state())
        check(scene.environment.glow_enabled and scene.environment.volumetric_fog_enabled,"Glow and atmosphere remain enabled under "+preset+" preset")
    var report: Dictionary = {"schema":3,"passed":failures.is_empty(),"checks":checks,"failures":failures,"scope":"Runtime geometry, partial native cloud light branches, independent global modulation and projection contracts; calibrated GPU measurements independently verify direct cloud transmission","initial":initial,"cloud_at_0":cloud_a,"cloud_at_24":cloud_b,"partial_clouds":cloud_contracts,"global_light":global_contracts,"parallax_poses":poses,"preset_states":time_states}
    var file: FileAccess = FileAccess.open(output.path_join("atmosphere-runtime-report.json"),FileAccess.WRITE)
    if file==null:
        push_error("Unable to write atmosphere-runtime-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("ATMOSPHERE_RUNTIME_DONE passed=",report.passed," checks=",checks.size())
    quit(0 if failures.is_empty() else 1)
