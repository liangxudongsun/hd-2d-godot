extends "res://tools/forest_hamlet/capture.gd"
## Focused camera acceptance. Reuses the actual GPU viewport, screenshot writer
## and five billboard probes; run.py.validate_billboard_capture measures those
## probes against the original PNG without changing their test conditions.
var framing_checks: Array = []

func _initialize() -> void:
    output = "res://build/forest-hamlet/camera-reference"
    super._initialize()

func camera_check(condition: bool, label: String) -> void:
    framing_checks.append({"label":label,"passed":condition})
    if not condition:
        failed.append(label)
        print("FOREST_CAMERA_FAIL ",label)

func check_gameplay_framing(label: String) -> void:
    var framing: Dictionary = scene.framing_state()
    camera_check(framing.silhouette_rect[3] >= .22 and framing.silhouette_rect[3] <= .24,label+": original animation silhouette occupies 22-24 percent of screen height")
    camera_check(framing.foot[1] >= .61 and framing.foot[1] <= .64 and absf(framing.foot[0]-.5)<.02,label+": feet centred at 61-64 percent of screen height")
    camera_check(framing.in_frame,label+": entire original animation silhouette in frame")
    camera_check(framing.view_depth > framing.dof_near and framing.view_depth < framing.dof_far,label+": original billboard remains inside sharp DoF interval")
    camera_check(is_equal_approx(scene.player.sprite.pixel_size,.009) and scene.player.sprite.scale.is_equal_approx(Vector3.ONE) and scene.player.scale.is_equal_approx(Vector3.ONE),label+": original character world scale retained without stretching")
    camera_check(scene.player.surface.get_shader_parameter("camera_facing_billboard")==true,label+": full camera-facing shader enabled")

func gameplay_snapshot(label: String) -> void:
    # This is the same camera method used during exploration, without a special
    # inspection transform. A snap only removes follow lag for the still frame.
    scene.update_camera(true)
    check_gameplay_framing(label)
    await snapshot(label)
    screenshots[-1]["camera_scope"] = "normal gameplay camera; unchanged offset and FOV; follow settled"
    screenshots[-1]["original_animation_frame"] = {"direction":scene.player.displayed_facing,"frame":scene.player.animation_frame,"texture":scene.player.sprite.texture.resource_path}

func run() -> void:
    if DisplayServer.get_name() == "headless":
        push_error("Actual GPU camera acceptance requires a graphical display.")
        quit(2)
        return
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS,true)
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    viewport.add_child(scene)
    for i in range(45):
        await physics_frame
    scene.frozen = true
    scene.player.controls_enabled = false
    scene.player.set_physics_process(false)
    scene.player.velocity = Vector3.ZERO
    scene.overlay.hide()
    scene.player.direction_override = 0
    scene.player.frame_override = 0
    scene.player.paused = true
    scene.player.update_animation()
    scene.set_time_preset("day")
    await gameplay_snapshot("gameplay-day")
    scene.set_time_preset("dusk")
    await gameplay_snapshot("gameplay-dusk")
    scene.set_time_preset("day")
    var directions := ["front","back","left","right"]
    for direction in range(4):
        scene.player.direction_override = direction
        scene.player.frame_override = 9
        scene.player.update_animation()
        await gameplay_snapshot("gameplay-walk-"+directions[direction])
    # Reuse the established real shader probes and their external pixel-readback
    # validator. These isolated pictures are not presented as gameplay framing.
    await capture_billboard_probes()
    scene.player.direction_override = -1
    scene.player.frame_override = -1
    scene.player.paused = false
    scene.player.update_animation()
    var route_report := {"scope":"not run", "completed":false}
    if include_route:
        scene.frozen = false
        scene.player.controls_enabled = true
        scene.player.set_physics_process(true)
        scene.start_route()
        var captured: Dictionary = {}
        var frames := 0
        var route_framing_safe := true
        var route_focus_safe := true
        while scene.route_running and frames < 7200:
            await physics_frame
            frames += 1
            var current: Dictionary = scene.framing_state()
            route_framing_safe = route_framing_safe and current.in_frame
            route_focus_safe = route_focus_safe and current.view_depth > current.dof_near and current.view_depth < current.dof_far
            # route_index advances after physically reaching the previous point.
            if scene.route_index in [1,3] and not captured.has(scene.route_index):
                var index: int = scene.route_index
                captured[index] = true
                scene.frozen = true
                scene.player.set_physics_process(false)
                await gameplay_snapshot("gameplay-route-left" if index==1 else "gameplay-route-right")
                scene.player.set_physics_process(true)
                scene.frozen = false
        if scene.route_running:
            scene.stop_route("timeout")
        route_report = scene.route_result
        camera_check(route_report.get("completed",false),"six-waypoint physical exploration route completes")
        camera_check(captured.size()==2,"both left and right gameplay views captured on actual physical route")
        camera_check(route_framing_safe,"entire original silhouette stays in frame throughout actual route")
        camera_check(route_focus_safe,"entire actual route stays inside protected DoF interval")
    var adapter := RenderingServer.get_video_adapter_name()
    var renderer := RenderingServer.get_current_rendering_method()
    camera_check(renderer=="forward_plus","actual GPU uses project Forward+ renderer")
    camera_check(not adapter.is_empty(),"actual GPU adapter reported")
    camera_check(scene.player.normal_atlases.size()==4 and scene.player.color_atlases.size()==4,"all four original color and normal directions retained")
    var report := {"passed":failed.is_empty(),"failures":failed,"checks":framing_checks,"scope":"normal gameplay framing, actual physical movement and real GPU captures; reference-angle similarity remains a visual judgement","runtime_fingerprint":runtime_fingerprint,"gpu":true,"adapter":adapter,"renderer":renderer,"viewport":[1920,1080],"no_focus":root.get_flag(Window.FLAG_NO_FOCUS),"main_window_minimized":DisplayServer.window_get_mode()==DisplayServer.WINDOW_MODE_MINIMIZED,"framing_targets":{"animation_union_height_fraction":[.22,.24],"feet_height_fraction":[.61,.64],"character_pixel_size":.009},"billboard_pixel_validation":"The five billboard-*.png frames use the existing run.py.validate_billboard_capture conditions; read billboard-gpu-report.json for independent pixel measurements.","screenshots":screenshots,"route":route_report}
    var file := FileAccess.open(output.path_join("camera-gpu-report.json"),FileAccess.WRITE)
    if file == null:
        push_error("Unable to write camera-gpu-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("FOREST_CAMERA_CAPTURE_DONE passed=",report.passed," screenshots=",screenshots.size()," checks=",framing_checks.size()," route=",route_report.get("status","not-run")," adapter=",adapter)
    quit(0 if failed.is_empty() else 1)
