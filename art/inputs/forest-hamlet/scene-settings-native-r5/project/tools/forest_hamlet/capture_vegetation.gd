extends "res://tools/forest_hamlet/capture.gd"
## Actual scene views plus isolated, frozen real-material lighting experiments.
const SPECIES := ["broadleaf_a","broadleaf_b","fir","grass","fern","reeds","flowers_white","flowers_pink","window_flowers","lily_pad"]
var probe_cards: Array[Sprite3D] = []
var probe_layout: Array = []
var probe_mode := false
var near_framing: Dictionary = {}
var validation_checks: Array = []

func _initialize() -> void:
    output = "res://build/forest-hamlet/vegetation-gpu"
    super._initialize()

func check(condition: bool, label: String) -> void:
    validation_checks.append({"label":label,"passed":condition})
    if not condition:
        failed.append(label)
        print("VEGETATION_CAPTURE_FAIL ",label)

func snapshot(label: String) -> void:
    await super.snapshot(label)
    if comparison_frozen:
        check(not scene.world.is_processing(),label+": vegetation clock is paused for controlled GPU comparison")
    var normal_states: Dictionary = {}
    for sprite in (probe_cards if probe_mode else scene.world.vegetation_sprites):
        var material: ShaderMaterial = sprite.material_override as ShaderMaterial
        normal_states[str(sprite.get_meta("asset_id"))] = material.get_shader_parameter("use_normals")
    screenshots[-1]["vegetation_normals"] = normal_states
    screenshots[-1]["vegetation_clock_paused"] = not scene.world.is_processing()
    screenshots[-1]["scope"] = "isolated actual vegetation Sprite3D materials, normalized specimen size, symmetric directional lighting" if probe_mode else "actual forest scene, original gameplay camera, normal-size original character"
    if probe_mode:
        screenshots[-1]["probe_light_position"] = [scene.main_light.position.x,scene.main_light.position.y,scene.main_light.position.z]
        screenshots[-1]["probe_light_rotation"] = [scene.main_light.rotation.x,scene.main_light.rotation.y,scene.main_light.rotation.z]

func load_scene(path: String) -> void:
    if is_instance_valid(scene):
        viewport.remove_child(scene)
        scene.queue_free()
        await process_frame
    scene = load(path).instantiate()
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
    scene.overlay.hide()
    scene.set_feature("wind",false)
    scene.world.set_vegetation_wind(0.0)
    scene.world.set_process(false)
    scene.world.water_material.set_shader_parameter("flow_speed",0.0)
    scene.world.set_vegetation_normals(true)
    scene.update_camera(true)
    comparison_frozen = true
    await process_frame
    await process_frame

func vector2_value(value: Variant) -> Vector2:
    if value is Vector2:
        return value
    return Vector2(value[0],value[1])

func rect_value(value: Variant) -> Rect2:
    if value is Rect2:
        return value
    return Rect2(value[0],value[1],value[2],value[3])

func set_probe_normals(enabled: bool) -> void:
    for card in probe_cards:
        (card.material_override as ShaderMaterial).set_shader_parameter("use_normals",enabled)

func probe_crop(card: Sprite3D, visible_rect: Rect2, pivot: Vector2) -> Array:
    # Match the actual full-billboard vertex transform with wind fixed at zero.
    # Use the global instance scale, camera basis and pixel pivot explicitly.
    var camera: Camera3D = scene.camera
    var world_scale: Vector3 = card.global_basis.get_scale()
    var minimum: Vector2 = Vector2(INF,INF)
    var maximum: Vector2 = Vector2(-INF,-INF)
    for point in [visible_rect.position,Vector2(visible_rect.end.x,visible_rect.position.y),visible_rect.end,Vector2(visible_rect.position.x,visible_rect.end.y)]:
        var pixel: Vector2 = point-pivot
        var vertex: Vector3 = card.global_position + camera.global_basis.x.normalized()*pixel.x*card.pixel_size*world_scale.x - camera.global_basis.y.normalized()*pixel.y*card.pixel_size*world_scale.y
        var projected: Vector2 = camera.unproject_position(vertex)
        minimum = minimum.min(projected)
        maximum = maximum.max(projected)
    return [maxi(0,floori(minimum.x)-3),maxi(0,floori(minimum.y)-3),mini(1920,ceili(maximum.x)+3),mini(1080,ceili(maximum.y)+3)]

func capture_material_probes() -> void:
    # The same Sprite3D resources used in the village are duplicated for an
    # isolated control. Only their uniform scale and stage position are changed.
    probe_mode = true
    scene.world.hide()
    scene.player.hide()
    scene.camera_locked = true
    scene.camera.position = Vector3(0,1.2,12.5)
    scene.camera.look_at(Vector3(0,1.2,0),Vector3.UP)
    scene.camera.fov = 39.0
    scene.set_feature("dof",false)
    scene.set_feature("bloom",false)
    scene.environment.background_mode = Environment.BG_COLOR
    scene.environment.background_color = Color(.035,.045,.04)
    scene.environment.fog_enabled = false
    scene.environment.ssao_enabled = false
    scene.environment.ssr_enabled = false
    scene.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    scene.environment.ambient_light_color = Color(.5,.5,.5)
    scene.environment.ambient_light_energy = .12
    scene.main_light.shadow_enabled = false
    scene.main_light.light_color = Color.WHITE
    scene.main_light.light_energy = 1.8
    var stage: Node3D = Node3D.new()
    stage.name = "ActualVegetationMaterialProbes"
    scene.add_child(stage)
    for index in range(SPECIES.size()):
        var asset_id: String = SPECIES[index]
        var source: Sprite3D
        for candidate in scene.world.vegetation_sprites:
            if str(candidate.get_meta("asset_id")) == asset_id:
                source = candidate
                break
        if source == null:
            failed.append("missing real vegetation specimen: "+asset_id)
            continue
        var card: Sprite3D = source.duplicate() as Sprite3D
        card.name = "Probe_"+asset_id
        var probe_material: ShaderMaterial = source.material_override.duplicate() as ShaderMaterial
        card.material_override = probe_material
        probe_material.set_shader_parameter("wind_strength",0.0)
        probe_material.set_shader_parameter("wind_clock",0.0)
        card.set_instance_shader_parameter("wind_weight",0.0)
        card.set_instance_shader_parameter("wind_phase",0.0)
        card.transparency = 0.0
        card.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
        stage.add_child(card)
        card.rotation = Vector3.ZERO
        var visible_rect: Rect2 = rect_value(card.get_meta("visible_rect_px"))
        var pivot: Vector2 = vector2_value(card.get_meta("pivot_px"))
        var original_size: Vector2 = visible_rect.size * card.pixel_size
        var uniform_scale: float = minf(2.55 / original_size.x,2.7 / original_size.y)
        card.scale = Vector3.ONE * uniform_scale
        var cell_center: Vector3 = Vector3((index%5-2)*3.1,2.85 if index<5 else -.45,0.0)
        var pixel_center: Vector2 = visible_rect.position + visible_rect.size*.5 - pivot
        var visual_offset: Vector3 = Vector3(pixel_center.x,-pixel_center.y,0.0)*card.pixel_size*uniform_scale
        card.position = cell_center-visual_offset
        card.show()
        probe_cards.append(card)
        var crop: Array = probe_crop(card,visible_rect,pivot)
        probe_layout.append({"id":asset_id,"crop_px":crop,"uniform_scale":uniform_scale,"pixel_size":card.pixel_size,"color_path":card.get_meta("color_path"),"normal_path":card.get_meta("normal_path")})
    for side in ["left","right"]:
        scene.main_light.position = Vector3(-8.0 if side=="left" else 8.0,8.0,12.0)
        scene.main_light.look_at(Vector3(0,1.2,0),Vector3.UP)
        set_probe_normals(true)
        await snapshot("plants-light-"+side+"-normals-on")
        set_probe_normals(false)
        await snapshot("plants-light-"+side+"-normals-off")

func run() -> void:
    if DisplayServer.get_name() == "headless":
        push_error("Vegetation GPU evidence requires a graphical display.")
        quit(2)
        return
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS,true)
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
    await load_scene("res://scenes/forest_hamlet.tscn")
    scene.set_time_preset("day")
    await snapshot("overview-day")
    scene.set_time_preset("dusk")
    await snapshot("overview-dusk")
    await load_scene("res://scenes/forest_hamlet_close.tscn")
    near_framing = scene.framing_state()
    check(near_framing.pitch_degrees >= 13.9 and near_framing.pitch_degrees <= 14.1,"near scene retains 14 degree reference camera")
    check(near_framing.silhouette_rect[3] >= .22 and near_framing.silhouette_rect[3] <= .24,"original character retains 22-24 percent animation-union screen height")
    check(near_framing.foot[1] >= .61 and near_framing.foot[1] <= .64,"original foot anchor remains at 61-64 percent screen height")
    check(is_equal_approx(scene.player.sprite.pixel_size,.009) and scene.player.sprite.scale.is_equal_approx(Vector3.ONE),"original character world size and aspect unchanged")
    scene.set_time_preset("day")
    scene.world.set_vegetation_normals(true)
    await snapshot("close-normals-on")
    scene.world.set_vegetation_normals(false)
    await snapshot("close-normals-off")
    scene.world.set_vegetation_normals(true)
    scene.set_time_preset("dusk")
    await snapshot("close-dusk")
    scene.set_time_preset("day")
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
        while scene.route_running and frames < 7200:
            await physics_frame
            frames += 1
            var framing: Dictionary = scene.framing_state()
            framing_safe = framing_safe and framing.in_frame
            focus_safe = focus_safe and framing.view_depth > framing.dof_near and framing.view_depth < framing.dof_far
            if scene.route_index in [1,3] and not captured.has(scene.route_index):
                var index: int = scene.route_index
                captured[index] = true
                scene.frozen = true
                scene.player.set_physics_process(false)
                scene.update_camera(true)
                await snapshot("close-route-left" if index==1 else "close-route-right")
                scene.player.set_physics_process(true)
                scene.frozen = false
        if scene.route_running:
            scene.stop_route("timeout")
        route_report = scene.route_result
        check(route_report.get("completed",false),"full physical route completes through sprite vegetation scene")
        check(captured.size()==2,"actual left and right route views captured")
        check(framing_safe and focus_safe,"character stays in frame and sharp throughout physical route")
    scene.frozen = true
    scene.player.set_physics_process(false)
    comparison_frozen = true
    await capture_material_probes()
    check(probe_cards.size()==SPECIES.size(),"all ten real vegetation species included in lighting probes")
    var adapter: String = RenderingServer.get_video_adapter_name()
    var renderer: String = RenderingServer.get_current_rendering_method()
    check(renderer=="forward_plus" and not adapter.is_empty(),"actual Forward+ GPU rendered every frame")
    var report: Dictionary = {"passed":failed.is_empty(),"failures":failed,"checks":validation_checks,"gpu":true,"renderer":renderer,"adapter":adapter,"viewport":[1920,1080],"runtime_fingerprint":runtime_fingerprint,"near_framing":near_framing,"probe_layout":probe_layout,"probe_conditions":{"albedo":"unchanged runtime originals","geometry":"frozen camera-facing Sprite3D; uniform fit to each specimen cell","wind_strength":0.0,"water_flow_speed":0.0,"fog":false,"dof":false,"bloom":false,"shadows":false,"light":"same white directional light, symmetric left and right positions","normal_toggle":"only use_normals changes within each on/off pair"},"screenshots":screenshots,"route":route_report,"scope":"real gameplay frames and isolated actual-material GPU lighting comparisons; artistic approval remains external"}
    var file: FileAccess = FileAccess.open(output.path_join("vegetation-gpu-report.json"),FileAccess.WRITE)
    if file == null:
        push_error("Unable to write vegetation-gpu-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("VEGETATION_CAPTURE_DONE passed=",report.passed," screenshots=",screenshots.size()," species=",probe_cards.size()," route=",route_report.get("status","not-run"))
    quit(0 if failed.is_empty() else 1)
