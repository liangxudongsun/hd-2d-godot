extends SceneTree
## Actual native cloud shadow transmission on a controlled diffuse receiver.
## PNG is display-referred. The companion analysis calibrates and inverts sRGB;
## this capture does not claim to contain raw HDR radiance.

const SIZE := Vector2i(1024, 768)
const CLOUD_SCRIPT := "res://scripts/forest_hamlet/cloud_lighting.gd"
const CLOUD_SHADER := "res://shaders/forest_hamlet/cloud_occluder.gdshader"
var output := "res://build/forest-hamlet/cloud-transmission-r3-prototype"
var runtime_fingerprint := ""
var viewport: SubViewport
var world: Node3D
var camera: Camera3D
var environment: Environment
var sun: DirectionalLight3D
var clouds
var screenshots: Array = []
var checks: Array = []
var failures: Array = []

func _initialize() -> void:
    root.set_flag(Window.FLAG_NO_FOCUS, true)
    root.gui_embed_subwindows = true
    for argument in OS.get_cmdline_user_args():
        if argument.begins_with("--forest-output="):
            output = argument.trim_prefix("--forest-output=")
        elif argument.begins_with("--output="):
            output = argument.trim_prefix("--output=")
        elif argument.begins_with("--forest-fingerprint="):
            runtime_fingerprint = argument.trim_prefix("--forest-fingerprint=")
    output = ProjectSettings.globalize_path(output)
    DirAccess.make_dir_recursive_absolute(output)
    call_deferred("run")

func _process(_delta: float) -> bool:
    RenderingServer.force_draw()
    return false

func check(condition: bool, label: String) -> void:
    checks.append({"label": label, "passed": condition})
    if not condition:
        failures.append(label)
        print("CLOUD_TRANSMISSION_FAIL ", label)

func material_gray() -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(0.5, 0.5, 0.5, 1.0)
    material.roughness = 1.0
    material.metallic = 0.0
    material.metallic_specular = 0.0
    material.diffuse_mode = BaseMaterial3D.DIFFUSE_LAMBERT
    material.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
    material.emission_enabled = false
    return material

func make_probe() -> void:
    RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_ULTRA)
    viewport = SubViewport.new()
    viewport.size = SIZE
    viewport.own_world_3d = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    viewport.msaa_3d = Viewport.MSAA_DISABLED
    viewport.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
    viewport.use_taa = false
    viewport.use_debanding = false
    root.add_child(viewport)
    world = Node3D.new()
    viewport.add_child(world)

    environment = Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color.BLACK
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
    environment.ambient_light_energy = 0.0
    environment.ambient_light_sky_contribution = 0.0
    environment.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
    environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
    environment.tonemap_exposure = 1.0
    environment.glow_enabled = false
    environment.fog_enabled = false
    environment.volumetric_fog_enabled = false
    environment.ssao_enabled = false
    environment.ssil_enabled = false
    environment.ssr_enabled = false
    environment.sdfgi_enabled = false
    environment.adjustment_enabled = false
    var environment_node := WorldEnvironment.new()
    environment_node.environment = environment
    world.add_child(environment_node)

    camera = Camera3D.new()
    camera.projection = Camera3D.PROJECTION_ORTHOGONAL
    camera.size = 42.0
    camera.near = 0.1
    camera.far = 150.0
    camera.position = Vector3(0.0, 45.0, 0.0)
    var attributes := CameraAttributesPractical.new()
    attributes.exposure_multiplier = 1.0
    attributes.auto_exposure_enabled = false
    attributes.dof_blur_far_enabled = false
    attributes.dof_blur_near_enabled = false
    camera.attributes = attributes
    world.add_child(camera)
    camera.look_at(Vector3.ZERO, Vector3.FORWARD)
    camera.current = true

    var receiver := MeshInstance3D.new()
    receiver.name = "DiffuseGrayReceiver"
    var plane := PlaneMesh.new()
    plane.size = Vector2(80.0, 80.0)
    receiver.mesh = plane
    receiver.material_override = material_gray()
    receiver.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    receiver.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
    receiver.layers = 1
    world.add_child(receiver)
    # A solid object verifies that the 70% branch retains ordinary shadows.
    # Main radiometry ROIs are on the opposite half of the receiver.
    var blocker := MeshInstance3D.new()
    blocker.name = "OrdinaryShadowControl"
    var box := BoxMesh.new()
    box.size = Vector3(3.0, 6.0, 3.0)
    blocker.mesh = box
    blocker.material_override = material_gray()
    blocker.position = Vector3(15.0, 3.0, 6.0)
    blocker.layers = 1
    blocker.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
    world.add_child(blocker)

    sun = DirectionalLight3D.new()
    sun.name = "AuthoritativeTotalSun"
    sun.rotation_degrees = Vector3(-53.0, -42.0, 0.0)
    sun.light_color = Color.WHITE
    sun.light_energy = 1.0
    sun.shadow_enabled = true
    sun.shadow_bias = 0.035
    sun.shadow_opacity = 1.0
    sun.light_angular_distance = 0.65
    sun.directional_shadow_max_distance = 80.0
    sun.directional_shadow_blend_splits = true
    world.add_child(sun)
    clouds = load(CLOUD_SCRIPT).new()
    world.add_child(clouds)
    clouds.configure(sun, environment)
    clouds.set_motion_enabled(false)
    clouds.set_time(0.0)
    clouds.set_atmosphere_enabled(false)
    clouds.sync_sun_lights()

func projected_rect(center: Vector3, half_size_px: float) -> Array:
    var pixel := camera.unproject_position(center)
    return [roundi(pixel.x-half_size_px), roundi(pixel.y-half_size_px), roundi(pixel.x+half_size_px), roundi(pixel.y+half_size_px)]

func natural_samples() -> Array:
    var result: Array = []
    for yi in range(8):
        for xi in range(8):
            var pixel := Vector2(80.0+float(xi)*76.0, 80.0+float(yi)*84.0)
            var origin := camera.project_ray_origin(pixel)
            var direction := camera.project_ray_normal(pixel)
            var point := origin+direction*(-origin.y/direction.y)
            var sample: Dictionary = clouds.cloud_ray_sample(point)
            sample["projected_pixel"] = [pixel.x, pixel.y]
            result.append(sample)
    return result

func capture(label: String, energy: float, enabled: bool, attenuation: float) -> void:
    sun.light_energy = energy
    clouds.set_enabled(enabled)
    clouds.set_uniform_attenuation(attenuation)
    clouds.set_time(0.0)
    clouds.sync_sun_lights()
    var before: Dictionary = clouds.snapshot()
    for frame in range(32):
        await process_frame
    await RenderingServer.frame_post_draw
    var rendered: Image = viewport.get_texture().get_image()
    var path := output.path_join(label+".png")
    var saved := rendered.save_png(path)
    check(saved == OK, label+": original GPU PNG saved")
    var after: Dictionary = clouds.snapshot()
    check(before == after, label+": all cloud and native light state held during GPU readback")
    var split: Dictionary = after.light_split
    check(absf(float(split.total_direct_energy)-energy)<0.00001, label+": actual native branch energy sum equals source total")
    screenshots.append({
        "file":label+".png", "sha256":FileAccess.get_sha256(path),
        "size":[rendered.get_width(),rendered.get_height()], "image_format":rendered.get_format(),
        "source_energy":energy, "clouds_enabled":enabled, "uniform_attenuation":attenuation,
        "cloud_lighting":after, "natural_ray_samples":natural_samples(),
        "render_counts":{
            "visible_objects":viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_OBJECTS_IN_FRAME),
            "visible_draw_calls":viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME),
            "shadow_draw_calls":viewport.get_render_info(Viewport.RENDER_INFO_TYPE_SHADOW, Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME)}
    })
    print("CLOUD_TRANSMISSION_FRAME ", label)

func run() -> void:
    if DisplayServer.get_name() == "headless":
        push_error("Cloud transmission requires the actual Forward+ GPU.")
        quit(2)
        return
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
    make_probe()
    for frame in range(40):
        await process_frame
    await capture("cloud-direct-dark", 0.0, false, 0.0)
    await capture("cloud-direct-clear", 1.0, false, 0.0)
    await capture("cloud-direct-half-calibration", 0.5, false, 0.0)
    await capture("cloud-direct-uniform-clear", 1.0, true, 0.0)
    await capture("cloud-direct-thin", 1.0, true, 0.10)
    await capture("cloud-direct-thin-repeat", 1.0, true, 0.10)
    await capture("cloud-direct-thick", 1.0, true, 0.30)
    await capture("cloud-direct-natural", 1.0, true, -1.0)
    var toward_sun := sun.global_basis.z.normalized()
    var shadow_center := Vector3(15.0, 0.0, 6.0)-Vector3(toward_sun.x, 0.0, toward_sun.z)*(5.0/toward_sun.y)
    var report := {
        "schema":1, "passed":failures.is_empty(), "checks":checks, "failures":failures,
        "scope":"Actual native shadow GPU capture on a gray Lambert receiver; companion pixel analysis decides transmission, not CPU density diagnostics",
        "gpu":true, "renderer":RenderingServer.get_current_rendering_method(),
        "adapter":RenderingServer.get_video_adapter_name(), "viewport":[SIZE.x,SIZE.y],
        "runtime_fingerprint":runtime_fingerprint,
        "source_files":{
            CLOUD_SCRIPT:FileAccess.get_sha256(CLOUD_SCRIPT), CLOUD_SHADER:FileAccess.get_sha256(CLOUD_SHADER),
            "res://tools/forest_hamlet/capture_cloud_transmission.gd":FileAccess.get_sha256("res://tools/forest_hamlet/capture_cloud_transmission.gd"),
            "res://tools/forest_hamlet/cloud_transmission_checks.py":FileAccess.get_sha256("res://tools/forest_hamlet/cloud_transmission_checks.py")},
        "measurement_encoding":"8-bit display PNG; calibrated inverse sRGB estimate after LINEAR tonemap; not raw HDR",
        "conditions":{
            "tone_mapper":"LINEAR", "tonemap_mode":environment.tonemap_mode, "exposure":environment.tonemap_exposure,
            "ambient_energy":environment.ambient_light_energy,
            "ambient_source_disabled":environment.ambient_light_source == Environment.AMBIENT_SOURCE_DISABLED,
            "sky_reflections_disabled":environment.reflected_light_source == Environment.REFLECTION_SOURCE_DISABLED,
            "fog":environment.fog_enabled or environment.volumetric_fog_enabled,
            "glow":environment.glow_enabled, "ssao":environment.ssao_enabled,
            "ssil":environment.ssil_enabled, "ssr":environment.ssr_enabled, "gi":environment.sdfgi_enabled,
            "auto_exposure":camera.attributes.auto_exposure_enabled, "adjustments":environment.adjustment_enabled,
            "global_modulation":false,
            "light_color":[1.0,1.0,1.0], "light_rotation_degrees":[-53.0,-42.0,0.0],
            "material":"StandardMaterial3D Lambert gray; metallic=0, specular=0, roughness=1, emission off",
            "albedo":[0.5,0.5,0.5], "cloud_clock_seconds":0.0,
            "msaa":"off", "taa":false, "debanding":false, "soft_shadow_quality":"SOFT_ULTRA",
            "note":"Only dark and half calibration change the authoritative source energy; clear/uniform-clear/thin/repeat/thick/natural all hold total native energy 1"
        },
        "receiver_rois_px":[
            {"id":"upper_left","rect":[80,80,336,272]},
            {"id":"center","rect":[350,288,606,480]},
            {"id":"lower_left","rect":[80,496,336,688]}],
        "natural_grid_rect_px":[80,80,688,688],
        "ordinary_shadow_control":{"world":[shadow_center.x,shadow_center.y,shadow_center.z],"rect_px":projected_rect(shadow_center,4.0)},
        "screenshots":screenshots
    }
    var file := FileAccess.open(output.path_join("cloud-transmission-capture.json"), FileAccess.WRITE)
    file.store_string(JSON.stringify(report,"  ")+"\n")
    file.close()
    print("CLOUD_TRANSMISSION_CAPTURE_DONE passed=", failures.is_empty(), " views=", screenshots.size())
    viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
    world.queue_free()
    await process_frame
    clouds = null
    world = null
    camera = null
    sun = null
    environment = null
    viewport.queue_free()
    await process_frame
    viewport = null
    quit(0 if failures.is_empty() else 2)
