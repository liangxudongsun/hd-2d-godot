extends "res://tools/forest_hamlet/capture.gd"
## Twelve actual GPU views: spatial cloud light, Glow, fog, real route and normals.
var validation_checks: Array = []
var route_views: Array = []
var capture_phase := "gameplay"
var normal_probe_light := ""
var preview_only := false
const CLOUD_A := 0.0
const CLOUD_B := 24.0

func _initialize() -> void:
    output = "res://build/forest-hamlet/atmosphere-gpu"
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
    var before: Dictionary = scene.cloud_lighting.snapshot()
    for i in range(24):
        await process_frame
    await super.snapshot(label)
    var after: Dictionary = scene.cloud_lighting.snapshot()
    check(is_equal_approx(float(before.get("clock_seconds",-1)),float(after.get("clock_seconds",-2))),label+": cloud phase stays fixed during controlled read-back")
    screenshots[-1]["phase"] = capture_phase
    screenshots[-1]["cloud_lighting"] = after
    screenshots[-1]["backdrop"] = scene.backdrop.snapshot()
    screenshots[-1]["main_light"] = {"energy":scene.main_light.light_energy,"rotation":[scene.main_light.rotation.x,scene.main_light.rotation.y,scene.main_light.rotation.z],"color":[scene.main_light.light_color.r,scene.main_light.light_color.g,scene.main_light.light_color.b]}
    screenshots[-1]["environment"] = {"glow_enabled":scene.environment.glow_enabled,"glow_intensity":scene.environment.glow_intensity,"glow_threshold":scene.environment.glow_hdr_threshold,"volumetric_fog_enabled":scene.environment.volumetric_fog_enabled,"volumetric_fog_density":scene.environment.volumetric_fog_density,"ambient_energy":scene.environment.ambient_light_energy}
    screenshots[-1]["motion"]["sky"] = "approved static snow panorama; explicit fixed cloud occlusion clock"
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
    scene.backdrop.set_process(false)
    scene.update_camera(true)
    scene.backdrop.update_frame()
    comparison_frozen = true

func backdrop_probes() -> void:
    capture_phase = "isolated_actual_backdrop"
    scene.world.hide()
    scene.player.hide()
    scene.camera_locked = true
    scene.set_feature("clouds",false)
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
    for id in ["backdrop_normals","parallax","clouds","atmosphere","bloom"]:
        scene.set_feature(id,true)
    scene.cloud_lighting.set_time(CLOUD_A)
    await snapshot("close-day-clouds-a")
    scene.set_feature("clouds",false)
    await snapshot("close-day-clouds-off")
    if preview_only:
        scene.set_feature("clouds",true)
        scene.set_time_preset("dusk")
        scene.cloud_lighting.set_time(CLOUD_A)
        await snapshot("close-dusk-atmosphere")
        var preview_report: Dictionary = {"schema":1,"preview_only":true,"passed":failed.is_empty(),"checks":validation_checks,"failures":failed,"gpu":true,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name(),"viewport":[1920,1080],"runtime_fingerprint":runtime_fingerprint,"near_framing":near_framing,"screenshots":screenshots,"scope":"Three-frame composition and lighting preview only; not final atmosphere validation"}
        var preview_file: FileAccess = FileAccess.open(output.path_join("atmosphere-preview-report.json"),FileAccess.WRITE)
        if preview_file==null:
            push_error("Unable to write atmosphere-preview-report.json")
            quit(3)
            return
        preview_file.store_string(JSON.stringify(preview_report,"  ")+"\n")
        print("ATMOSPHERE_PREVIEW_DONE screenshots=",screenshots.size()," errors=",failed.size())
        quit(0 if failed.is_empty() else 1)
        return
    scene.set_feature("clouds",true)
    scene.cloud_lighting.set_time(CLOUD_B)
    await snapshot("close-day-clouds-b")
    scene.cloud_lighting.set_time(CLOUD_A)
    scene.set_feature("bloom",false)
    await snapshot("close-day-glow-off")
    scene.set_feature("bloom",true)
    scene.set_feature("atmosphere",false)
    await snapshot("close-day-atmosphere-off")
    scene.set_feature("atmosphere",true)
    scene.set_time_preset("dusk")
    scene.cloud_lighting.set_time(CLOUD_A)
    await snapshot("close-dusk-atmosphere")
    scene.set_time_preset("day")
    scene.cloud_lighting.set_time(CLOUD_A)
    var route_report: Dictionary = {"scope":"not run","completed":false}
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
                await snapshot("close-route-left" if index==1 else "close-route-right")
                route_views.append(screenshots[-1].duplicate(true))
                scene.player.set_physics_process(true)
                scene.frozen = false
        if scene.route_running:
            scene.stop_route("timeout")
        route_report = scene.route_result
        check(route_report.get("completed",false),"six-waypoint real-physics route completes with the atmosphere enabled")
        check(route_views.size()==2,"actual left and right movement views captured")
        check(framing_safe and focus_safe,"entire route keeps the original character visible and in focus")
    freeze_scene()
    await backdrop_probes()
    var adapter: String = RenderingServer.get_video_adapter_name()
    var renderer: String = RenderingServer.get_current_rendering_method()
    check(renderer=="forward_plus" and not adapter.is_empty(),"actual Forward+ hardware GPU rendered every capture")
    check(screenshots.size()==(12 if include_route else 10),"only the requested controlled capture set was generated")
    var report: Dictionary = {"schema":1,"passed":failed.is_empty(),"failures":failed,"checks":validation_checks,"gpu":true,"renderer":renderer,"adapter":adapter,"viewport":[1920,1080],"runtime_fingerprint":runtime_fingerprint,"near_framing":near_framing,"screenshots":screenshots,"route":route_report,"route_views":route_views,"cloud_clock_seconds":[CLOUD_A,CLOUD_B],"cloud_receiver_rois":{"ground":[.56,.69,.75,.89],"house":[.19,.29,.35,.44],"vegetation":[.895,.12,.988,.32]},"comparison_conditions":{"actor_frame":0,"vegetation_wind":0.0,"water_flow":0.0,"cloud_clock":"explicit and held; temporal fog settles 32 frames","glow_pair":"only native glow_enabled differs","normal_probes":"actual unmodified backdrop material, two symmetric white-light directions, normals toggled, no world/fog/Glow/DoF/shadow"},"scope":"Real gameplay frames and isolated actual-material GPU comparisons; does not imply user aesthetic approval"}
    var file: FileAccess = FileAccess.open(output.path_join("atmosphere-gpu-report.json"),FileAccess.WRITE)
    if file==null:
        push_error("Unable to write atmosphere-gpu-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("ATMOSPHERE_CAPTURE_DONE passed=",report.passed," screenshots=",screenshots.size()," route=",route_report.get("status","not-run"))
    quit(0 if failed.is_empty() else 1)
