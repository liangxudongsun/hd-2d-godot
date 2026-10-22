extends SceneTree
## Runtime contracts; visible lighting is independently checked by GPU read-back.
var scene: Node3D
var checks: Array = []
var failures: Array = []
var output := "res://build/forest-hamlet/atmosphere-runtime"

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

func run() -> void:
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    root.add_child(scene)
    await settle(45)
    scene.frozen = true
    scene.player.set_physics_process(false)
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
    for id in ["backdrop_normals","parallax","clouds","atmosphere","bloom"]:
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
    check(is_equal_approx(sun_energy,scene.main_light.light_energy) and is_equal_approx(ambient_energy,scene.environment.ambient_light_energy),"cloud drift does not imitate spatial lighting by pulsing global sun or ambient energy")
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
        scene.backdrop.update_frame()
        time_states.append(scene.snapshot_state())
        check(scene.environment.glow_enabled and scene.environment.volumetric_fog_enabled,"Glow and atmosphere remain enabled under "+preset+" preset")
    var report: Dictionary = {"schema":1,"passed":failures.is_empty(),"checks":checks,"failures":failures,"scope":"Runtime geometry, toggles and projection contracts only; GPU files independently verify visual effects","initial":initial,"cloud_at_0":cloud_a,"cloud_at_24":cloud_b,"parallax_poses":poses,"preset_states":time_states}
    var file: FileAccess = FileAccess.open(output.path_join("atmosphere-runtime-report.json"),FileAccess.WRITE)
    if file==null:
        push_error("Unable to write atmosphere-runtime-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("ATMOSPHERE_RUNTIME_DONE passed=",report.passed," checks=",checks.size())
    quit(0 if failures.is_empty() else 1)
