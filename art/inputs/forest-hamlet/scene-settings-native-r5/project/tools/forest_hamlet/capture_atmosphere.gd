extends "res://tools/forest_hamlet/capture.gd"
## Eighteen gameplay GPU views; calibrated direct-cloud probe is a separate capture.
var validation_checks: Array = []
var route_views: Array = []
var capture_phase := "gameplay"
var normal_probe_light := ""
var preview_only := false
const CLOUD_A := 0.0
const CLOUD_B := 24.0

func _initialize() -> void:
    output = "res://build/forest-hamlet/atmosphere-r3-final"
    for arg in OS.get_cmdline_user_args():
        if arg=="--atmosphere-preview":
            preview_only = true
    super._initialize()

func check(condition: bool, label: String) -> void:
    validation_checks.append({"label":label,"passed":condition})
    if not condition:
        failed.append(label)
        print("ATMOSPHERE_CAPTURE_FAIL ",label)

func snapshot(label: String) -> void:
    # Volumetric history is allowed to settle; no scene motion runs between pairs.
    scene.backdrop.update_frame()
    scene.cloud_lighting.sync_sun_lights()
    var before: Dictionary = scene.cloud_lighting.snapshot()
    var global_before: Dictionary = scene.global_lighting.snapshot()
    for i in range(24):
        await process_frame
    await super.snapshot(label)
    var after: Dictionary = scene.cloud_lighting.snapshot()
    var global_after: Dictionary = scene.global_lighting.snapshot()
    check(is_equal_approx(float(before.get("clock_seconds",-1)),float(after.get("clock_seconds",-2))) and is_equal_approx(float(global_before.clock_seconds),float(global_after.clock_seconds)) and is_equal_approx(float(global_before.sun_energy),float(global_after.sun_energy)) and is_equal_approx(float(global_before.ambient_energy),float(global_after.ambient_energy)),label+": cloud phase and global light stay fixed during controlled read-back")
    var split: Dictionary = after.light_split
    check(is_equal_approx(float(split.total_direct_energy),scene.main_light.light_energy) and is_equal_approx(float(split.base70.energy),scene.main_light.light_energy*.70) and is_equal_approx(float(split.cloud30.energy),scene.main_light.light_energy*.30),label+": real 70/30 native branches conserve authoritative solar energy")
    screenshots[-1]["phase"] = capture_phase
    screenshots[-1]["cloud_lighting"] = after
    screenshots[-1]["global_light"] = global_after
    screenshots[-1]["global_light_readback"] = {"before_clock_seconds":global_before.clock_seconds,"after_clock_seconds":global_after.clock_seconds,"before_sun_energy":global_before.sun_energy,"after_sun_energy":global_after.sun_energy,"before_ambient_energy":global_before.ambient_energy,"after_ambient_energy":global_after.ambient_energy}
    screenshots[-1]["backdrop"] = scene.backdrop.snapshot()
    screenshots[-1]["main_light"] = {"energy":scene.main_light.light_energy,"rotation":[scene.main_light.rotation.x,scene.main_light.rotation.y,scene.main_light.rotation.z],"color":[scene.main_light.light_color.r,scene.main_light.light_color.g,scene.main_light.light_color.b]}
    screenshots[-1]["environment"] = {"glow_enabled":scene.environment.glow_enabled,"glow_intensity":scene.environment.glow_intensity,"glow_threshold":scene.environment.glow_hdr_threshold,"volumetric_fog_enabled":scene.environment.volumetric_fog_enabled,"volumetric_fog_density":scene.environment.volumetric_fog_density,"ambient_energy":scene.environment.ambient_light_energy}
    screenshots[-1]["motion"]["sky"] = "approved static snow panorama; explicit fixed cloud and global-light clocks"
    if not normal_probe_light.is_empty():
        screenshots[-1]["normal_probe_light"] = normal_probe_light

func freeze_scene() -> void:
    scene.frozen = true
    scene.player.controls_enabled = false
    scene.player.set_physics_process(false)
    scene.player.velocity = Vector3.ZERO
    scene.player.direction_override = 0
    scene.player.frame_override = 0
    scene.player.paused = true
    scene.player.update_animation()
    scene.overlay.hide()
    scene.set_feature("wind",false)
    scene.world.set_vegetation_wind(0.0)
    scene.world.set_process(false)
    scene.world.water_material.set_shader_parameter("flow_speed",0.0)
    scene.cloud_lighting.set_process(false)
    scene.global_lighting.set_process(false)
    scene.backdrop.set_process(false)
    scene.update_camera(true)
    scene.backdrop.update_frame()
    comparison_frozen = true

func cloud_scene_probes() -> void:
    capture_phase = "controlled_partial_cloud_scene"
    scene.cloud_lighting.set_time(CLOUD_A)
    scene.global_lighting.set_time(0.0)
    scene.set_feature("clouds",true)
    for item in [["thin",.10],["thick",.30],["natural",-1.0]]:
        scene.cloud_lighting.set_uniform_attenuation(float(item[1]))
        await snapshot("close-day-clouds-"+String(item[0]))
    capture_phase = "gameplay"

func global_light_probes() -> Dictionary:
    capture_phase = "controlled_global_light"
    scene.set_time_preset("day")
    scene.set_feature("clouds",false)
    scene.cloud_lighting.set_time(CLOUD_A)
    scene.set_feature("global_light",true)
    scene.global_lighting.set_time(0.0)
    var samples: Array = []
    var weak: Dictionary = scene.global_lighting.snapshot()
    var strong: Dictionary = weak
    for second in range(91):
        scene.global_lighting.set_time(float(second))
        var state: Dictionary = scene.global_lighting.snapshot()
        samples.append({"clock_seconds":state.clock_seconds,"sun_multiplier":state.sun_multiplier,"ambient_multiplier":state.ambient_multiplier,"sun_energy":state.sun_energy,"ambient_energy":state.ambient_energy})
        if float(state.sun_multiplier)<float(weak.sun_multiplier):
            weak = state
        if float(state.sun_multiplier)>float(strong.sun_multiplier):
            strong = state
    check(float(strong.sun_multiplier)-float(weak.sun_multiplier)>.02,"0 to 90 second scan locates distinct reproducible global weak and strong light")
    scene.global_lighting.set_time(float(weak.clock_seconds))
    await snapshot("close-day-global-weak")
    scene.global_lighting.set_time(float(strong.clock_seconds))
    await snapshot("close-day-global-strong")
    scene.set_feature("global_light",false)
    await snapshot("close-day-global-off")
    check(is_equal_approx(scene.main_light.light_energy,1.45) and is_equal_approx(scene.environment.ambient_light_energy,.55),"global off capture restores the day base energies independently of cloud state")
    scene.set_feature("global_light",true)
    scene.global_lighting.set_time(0.0)
    scene.set_feature("clouds",true)
    capture_phase = "gameplay"
    return {"sample_interval_seconds":[0,90],"sample_step_seconds":1,"selected_by":"sun_multiplier","weak_time_seconds":weak.clock_seconds,"strong_time_seconds":strong.clock_seconds,"samples":samples,"clouds_enabled":false,"cloud_clock_seconds":CLOUD_A,"off_clock_seconds":strong.clock_seconds}

func backdrop_probes() -> void:
    capture_phase = "isolated_actual_backdrop"
    scene.world.hide()
    scene.player.hide()
    scene.camera_locked = true
    scene.set_feature("clouds",false)
    scene.set_feature("global_light",false)
    scene.set_feature("atmosphere",false)
    scene.set_feature("bloom",false)
    scene.set_feature("dof",false)
    scene.environment.fog_enabled = false
    scene.environment.ssao_enabled = false
    scene.environment.ssr_enabled = false
    scene.environment.ambient_light_energy = .15
    scene.environment.background_mode = Environment.BG_COLOR
    scene.environment.background_color = Color(.15,.18,.24)
    scene.main_light.shadow_enabled = false
    scene.main_light.light_energy = 1.0
    scene.main_light.light_color = Color.WHITE
    for side in ["left","right"]:
        normal_probe_light = side
        var sign_x := -1.0 if side=="left" else 1.0
        var incoming: Vector3 = (scene.camera.global_basis.x*sign_x*.62+scene.camera.global_basis.y*.45+scene.camera.global_basis.z*.65).normalized()
        scene.main_light.look_at(scene.main_light.global_position-incoming,Vector3.UP)
        scene.backdrop.update_frame()
        scene.set_feature("backdrop_normals",true)
        await snapshot("snow-"+side+"-normals-on")
        scene.set_feature("backdrop_normals",false)
        await snapshot("snow-"+side+"-normals-off")
    normal_probe_light = ""

func run() -> void:
    if DisplayServer.get_name()=="headless":
        push_error("Atmosphere evidence requires the real Forward+ GPU.")
        quit(2)
        return
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS,true)
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    viewport.add_child(scene)
    for i in range(45):
        await physics_frame
    freeze_scene()
    var near_framing: Dictionary = scene.framing_state()
    check(absf(near_framing.pitch_degrees-14.0)<.1,"accepted 14 degree close camera retained")
    check(near_framing.silhouette_rect[3]>.22 and near_framing.silhouette_rect[3]<.24,"original character screen proportion retained")
    check(scene.world.vegetation_sprites.size()==218,"all existing 218 vegetation sprites remain")
    scene.set_time_preset("day")
    for id in ["backdrop_normals","parallax","clouds","atmosphere","bloom","global_light"]:
        scene.set_feature(id,true)
    scene.cloud_lighting.set_time(CLOUD_A)
    scene.global_lighting.set_time(0.0)
    scene.cloud_lighting.set_uniform_attenuation(-1.0)
    if preview_only:
        await cloud_scene_probes()
        var preview_report: Dictionary = {"schema":1,"preview_only":true,"passed":failed.is_empty(),"checks":validation_checks,"failures":failed,"gpu":true,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name(),"viewport":[1920,1080],"runtime_fingerprint":runtime_fingerprint,"near_framing":near_framing,"screenshots":screenshots,"scope":"Three real partial-cloud appearance frames: thin/thick/natural; not final atmosphere validation"}
        var preview_file: FileAccess = FileAccess.open(output.path_join("atmosphere-preview-report.json"),FileAccess.WRITE)
        if preview_file==null:
            push_error("Unable to write atmosphere-preview-report.json")
            quit(3)
            return
        preview_file.store_string(JSON.stringify(preview_report,"  ")+"\n")
        print("ATMOSPHERE_PREVIEW_DONE screenshots=",screenshots.size()," errors=",failed.size())
        quit(0 if failed.is_empty() else 1)
        return
    await snapshot("close-day-clouds-a")
    scene.set_feature("clouds",false)
    await snapshot("close-day-clouds-off")
    scene.set_feature("clouds",true)
    scene.cloud_lighting.set_time(CLOUD_B)
    await snapshot("close-day-clouds-b")
    await cloud_scene_probes()
    scene.cloud_lighting.set_time(CLOUD_A)
    scene.set_feature("bloom",false)
    await snapshot("close-day-glow-off")
    scene.set_feature("bloom",true)
    scene.set_feature("atmosphere",false)
    await snapshot("close-day-atmosphere-off")
    scene.set_feature("atmosphere",true)
    scene.set_time_preset("dusk")
    scene.cloud_lighting.set_time(CLOUD_A)
    scene.global_lighting.set_time(0.0)
    await snapshot("close-dusk-atmosphere")
    var global_probe: Dictionary = await global_light_probes()
    scene.set_time_preset("day")
    scene.cloud_lighting.set_time(CLOUD_A)
    scene.global_lighting.set_time(0.0)
    var route_report: Dictionary = {"scope":"not run","completed":false}
    var route_global: Array = [{"stage":"start","global_light":scene.global_lighting.snapshot()}]
    if include_route:
        comparison_frozen = false
        scene.player.direction_override = -1
        scene.player.frame_override = -1
        scene.player.paused = false
        scene.player.controls_enabled = true
        scene.player.set_physics_process(true)
        scene.frozen = false
        scene.start_route()
        var frames := 0
        var captured: Dictionary = {}
        var framing_safe := true
        var focus_safe := true
        while scene.route_running and frames<7200:
            await physics_frame
            frames += 1
            var frame: Dictionary = scene.framing_state()
            framing_safe = framing_safe and frame.in_frame
            focus_safe = focus_safe and frame.view_depth>frame.dof_near and frame.view_depth<frame.dof_far
            if scene.route_index in [1,3] and not captured.has(scene.route_index):
                var index: int = scene.route_index
                captured[index] = true
                scene.frozen = true
                scene.player.set_physics_process(false)
                scene.update_camera(true)
                scene.backdrop.update_frame()
                scene.cloud_lighting.set_time(CLOUD_A)
                var live_global: Dictionary = scene.global_lighting.snapshot()
                route_global.append({"stage":"left" if index==1 else "right","global_light":live_global})
                scene.global_lighting.set_time(0.0)
                await snapshot("close-route-left" if index==1 else "close-route-right")
                route_views.append(screenshots[-1].duplicate(true))
                scene.global_lighting.set_time(float(live_global.clock_seconds))
                scene.player.set_physics_process(true)
                scene.frozen = false
        if scene.route_running:
            scene.stop_route("timeout")
        route_report = scene.route_result
        route_global.append({"stage":"end","global_light":scene.global_lighting.snapshot()})
        check(route_report.get("completed",false),"six-waypoint real-physics route completes with the atmosphere enabled")
        check(route_views.size()==2,"actual left and right movement views captured")
        check(framing_safe and focus_safe,"entire route keeps the original character visible and in focus")
        check(float(route_global[-1].global_light.clock_seconds)>float(route_global[0].global_light.clock_seconds)+1.0,"global light clock advances during actual route motion between controlled read-backs")
    freeze_scene()
    await backdrop_probes()
    var adapter: String = RenderingServer.get_video_adapter_name()
    var renderer: String = RenderingServer.get_current_rendering_method()
    check(renderer=="forward_plus" and not adapter.is_empty(),"actual Forward+ hardware GPU rendered every capture")
    check(screenshots.size()==(18 if include_route else 16),"only the requested controlled capture set was generated")
    var report: Dictionary = {"schema":3,"passed":failed.is_empty(),"complete_final_evidence":include_route and screenshots.size()==18 and route_report.get("completed",false),"failures":failed,"checks":validation_checks,"gpu":true,"renderer":renderer,"adapter":adapter,"viewport":[1920,1080],"runtime_fingerprint":runtime_fingerprint,"near_framing":near_framing,"screenshots":screenshots,"route":route_report,"route_views":route_views,"route_global_light":route_global,"global_lighting_probe":global_probe,"cloud_clock_seconds":[CLOUD_A,CLOUD_B],"partial_cloud_controls":{"requested_attenuation":{"close-day-clouds-thin.png":.10,"close-day-clouds-thick.png":.30,"close-day-clouds-natural.png":-1.0},"native_energy_split":[.70,.30],"direct_transmission_measurement":"cloud-transmission/cloud-transmission-pixel-report.json","measurement_scope":"Scene PNG differences are LDR appearance, not direct-light percentages; calibrated separate receiver probe measures transmission"},"cloud_receiver_rois":{"ground":[.56,.69,.75,.89],"house":[.19,.29,.35,.44],"vegetation":[.895,.12,.988,.32]},"comparison_conditions":{"actor_frame":0,"vegetation_wind":0.0,"water_flow":0.0,"cloud_clock":"explicit and held; temporal fog settles 32 frames","global_clock":"t0 throughout cloud/Glow/fog A-B; scan-selected frozen weak/strong with clouds off; live during physical route, temporarily t0 for parallax read-back then restored","glow_pair":"only native glow_enabled differs","normal_probes":"global modulation disabled; actual unmodified backdrop material, two symmetric white-light directions, normals toggled, no world/fog/Glow/DoF/shadow"},"scope":"Real gameplay frames with natural and controlled partial native clouds, isolated actual-material comparisons, independent global light and physical route; direct transmission uses the separate calibrated receiver probe"}
    var file: FileAccess = FileAccess.open(output.path_join("atmosphere-gpu-report.json"),FileAccess.WRITE)
    if file==null:
        push_error("Unable to write atmosphere-gpu-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("ATMOSPHERE_CAPTURE_DONE passed=",report.passed," screenshots=",screenshots.size()," route=",route_report.get("status","not-run"))
    quit(0 if failed.is_empty() else 1)
