extends SceneTree
## Independent close-camera contract; actual character physics and source frames.
var scene: Node3D
var checks: Array = []
var failures: Array = []
var output := "res://build/forest-hamlet/close-runtime"

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--forest-output="):
            output = arg.trim_prefix("--forest-output=")
    output = ProjectSettings.globalize_path(output)
    DirAccess.make_dir_recursive_absolute(output)
    call_deferred("run")

func check(condition: bool, label: String) -> void:
    checks.append({"label":label,"passed":condition})
    if not condition:
        failures.append(label)
        print("ASSERT_FAIL ",label)

func settle(frames: int) -> void:
    for i in range(frames):
        await physics_frame

func mesh_transparency(node: Node, expected: float) -> Dictionary:
    var result := {"passed":true,"meshes":0}
    if node is GeometryInstance3D:
        var geometry := node as GeometryInstance3D
        var drawable := true
        if geometry is MeshInstance3D:
            drawable = (geometry as MeshInstance3D).mesh != null
        if drawable:
            result.meshes += 1
            result.passed = is_equal_approx(geometry.transparency,expected)
    for child in node.get_children():
        var child_result := mesh_transparency(child,expected)
        result.passed = result.passed and child_result.passed
        result.meshes += child_result.meshes
    return result

func run() -> void:
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    root.add_child(scene)
    await settle(45)
    scene.update_camera(true)
    var initial: Dictionary = scene.framing_state()
    var spawn_pose: Vector3 = scene.player.position
    check(scene.player.is_on_floor() and spawn_pose.y > -.4 and spawn_pose.y < 1.0,"spawn has real physical floor contact")
    check(initial.pitch_degrees >= 13.9 and initial.pitch_degrees <= 14.1,"close gameplay camera uses reference 14 degree pitch")
    check(is_equal_approx(scene.camera.fov,39.0),"close camera preserves 39 degree vertical FOV")
    check(initial.silhouette_rect[3] >= .22 and initial.silhouette_rect[3] <= .24,"original animation union occupies 22-24 percent of screen height")
    check(initial.foot[1] >= .61 and initial.foot[1] <= .64 and absf(initial.foot[0]-.5)<.02,"feet centred at 61-64 percent of screen height")
    check(initial.in_frame,"full original silhouette fits the initial gameplay view")
    check(initial.view_depth > initial.dof_near and initial.view_depth < initial.dof_far,"entire original billboard inside sharp DoF interval")
    check(is_equal_approx(scene.player.sprite.pixel_size,.009) and scene.player.sprite.scale.is_equal_approx(Vector3.ONE) and scene.player.scale.is_equal_approx(Vector3.ONE),"original character world scale retained without stretching")
    check(scene.player.surface.get_shader_parameter("camera_facing_billboard")==true,"close sprite uses full camera-facing rendering")
    check(scene.player.color_atlases.size()==4 and scene.player.normal_atlases.size()==4 and scene.player.silver_atlases.size()==4,"all four original color normal and silver directions retained")
    var frame_count := 0
    for definition in scene.player.color_definitions:
        frame_count += definition.frames.size()
    check(frame_count==108,"all 108 original character frames retained")
    var initial_occlusion: Dictionary = scene.occlusion.snapshot()
    check(initial_occlusion.registered_trees > 0 and int(initial_occlusion.get("geometry_count",initial_occlusion.get("mesh_count",0))) > 0,"tree visibility controller has actual geometry registered")
    scene.player.position = Vector3(12,0,1.8)
    scene.player.velocity = Vector3.ZERO
    scene.update_camera(true)
    var right_occlusion: Dictionary = scene.occlusion.snapshot()
    check(right_occlusion.occluding_trees > 0 and right_occlusion.faded_trees > 0,"right route point detects foreground tree obstruction")
    var blocked_meshes := 0
    var blocked_meshes_clear := true
    for tree in scene.world.view_occluders:
        if str(tree.name) in right_occlusion.faded_names:
            var measured := mesh_transparency(tree,1.0)
            blocked_meshes += measured.meshes
            blocked_meshes_clear = blocked_meshes_clear and measured.passed
    check(blocked_meshes > 0 and blocked_meshes_clear,"every actual geometry instance of obstructing trees becomes fully transparent at settled camera")
    scene.player.position = spawn_pose
    scene.update_camera(true)
    var restored_occlusion: Dictionary = scene.occlusion.snapshot()
    var restored_meshes := 0
    var all_trees_opaque := true
    for tree in scene.world.view_occluders:
        var measured := mesh_transparency(tree,0.0)
        restored_meshes += measured.meshes
        all_trees_opaque = all_trees_opaque and measured.passed
    check(restored_occlusion.faded_trees==0 and restored_occlusion.occluding_trees==0,"return to spawn releases all foreground tree protection")
    check(restored_meshes > 0 and all_trees_opaque,"all actual tree geometry restores opaque rendering at spawn")
    for point in [Vector3(-17.1,0,1.8),Vector3(17.1,0,1.8),Vector3(0,0,-12.1),Vector3(0,0,12.1),Vector3(-17.1,0,12.1),Vector3(17.1,0,-12.1)]:
        scene.player.position = point
        scene.update_camera(true)
        check(scene.framing_state().in_frame,"complete silhouette stays inside close camera at map boundary "+str(point))
    scene.player.position = spawn_pose
    scene.player.velocity = Vector3.ZERO
    scene.update_camera(true)
    await settle(15)
    scene.start_route()
    var frames := 0
    var min_y: float = scene.player.position.y
    var route_framing_safe := true
    var route_focus_safe := true
    while scene.route_running and frames < 7200:
        await physics_frame
        frames += 1
        min_y = minf(min_y,scene.player.position.y)
        var current: Dictionary = scene.framing_state()
        route_framing_safe = route_framing_safe and current.in_frame
        route_focus_safe = route_focus_safe and current.view_depth > current.dof_near and current.view_depth < current.dof_far
    if scene.route_running:
        scene.stop_route("timeout")
    check(scene.route_result.get("completed",false) and scene.route_result.get("waypoints",0)==6,"complete six-waypoint route uses real character physics")
    check(min_y > -.5,"entire physical route remains on terrain")
    check(route_framing_safe,"full original silhouette remains in frame throughout physical route")
    check(route_focus_safe,"entire physical route stays inside protected DoF interval")
    check(scene.route_trajectory.size()>30,"route report contains actual motion samples")
    scene.update_camera(true)
    var report := {"passed":failures.is_empty(),"scope":"independent close scene; headless geometry, source bindings, geometry transparency and physical movement; real GPU appearance is checked separately","scene":"res://scenes/forest_hamlet_close.tscn","checks":checks,"failures":failures,"initial_framing":initial,"right_occlusion":right_occlusion,"restored_occlusion":restored_occlusion,"route":scene.route_result,"minimum_route_height":min_y,"state":scene.snapshot_state()}
    var file := FileAccess.open(output.path_join("close-runtime-report.json"),FileAccess.WRITE)
    if file == null:
        push_error("Unable to write close-runtime-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("FOREST_CLOSE_RUNTIME_DONE checks=",checks.size()," failures=",failures.size()," route=",scene.route_result.get("status","missing"))
    quit(0 if failures.is_empty() else 1)
