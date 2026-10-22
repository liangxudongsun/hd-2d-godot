extends Node3D
## Moving overhead cloud shadows and independent native volumetric lighting.
## No per-object albedo overlay, screen darkening, or animated solar energy.
## The atmosphere controller deliberately does not own Glow or character data.

const CLOUD_SEED := 20261022
const MASK_SIZE := 256
const SHADER_PATH := "res://shaders/forest_hamlet/cloud_occluder.gdshader"

@export var cloud_height_m: float = 24.0
@export var cloud_width_m: float = 220.0
@export var pattern_span_m: float = 96.0
@export var wind_velocity: Vector2 = Vector2(0.32, 0.13)
@export_range(0.0, 1.0) var mask_cutoff: float = 0.515
@export var pattern_phase: Vector2 = Vector2(0.65, 0.0)

var enabled := true
var atmosphere_enabled := true
var motion_enabled := true
var clock_seconds := 0.0
var preset := "day"
var sun: DirectionalLight3D
var environment: Environment
var caster: MeshInstance3D
var material: ShaderMaterial
var mask_image: Image
var mask_texture: ImageTexture
var mask_sha256 := ""

func configure(sunlight: DirectionalLight3D, world_environment: Environment) -> void:
    assert(sunlight != null and world_environment != null)
    sun = sunlight
    environment = world_environment
    _ensure_caster()
    set_time(clock_seconds)
    set_enabled(enabled)
    set_preset(preset)

func _ensure_caster() -> void:
    if is_instance_valid(caster):
        return
    _make_mask()
    material = ShaderMaterial.new()
    material.shader = load(SHADER_PATH)
    material.set_shader_parameter("cloud_mask", mask_texture)
    material.set_shader_parameter("pattern_span_m", pattern_span_m)
    material.set_shader_parameter("mask_cutoff", mask_cutoff)
    material.set_shader_parameter("wind_velocity", wind_velocity)
    material.set_shader_parameter("pattern_phase", pattern_phase)
    var plane := PlaneMesh.new()
    plane.size = Vector2(cloud_width_m, cloud_width_m)
    # Smaller triangles avoid very large triangle / shadow-frustum pancaking
    # artifacts. The stock directional shadow depth range is left unchanged.
    plane.subdivide_width = 31
    plane.subdivide_depth = 31
    caster = MeshInstance3D.new()
    caster.name = "OverheadCloudShadowCaster"
    caster.mesh = plane
    caster.material_override = material
    caster.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
    caster.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
    caster.ignore_occlusion_culling = true
    caster.position = Vector3(0.0, cloud_height_m, -8.0)
    caster.extra_cull_margin = 2.0
    add_child(caster)

func _make_mask() -> void:
    # Fixed-seed native FastNoiseLite, made synchronously once. NoiseTexture2D's
    # asynchronous first update is avoided so captures cannot race a blank map.
    var noise := FastNoiseLite.new()
    noise.seed = CLOUD_SEED
    noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
    noise.frequency = 0.016
    noise.fractal_type = FastNoiseLite.FRACTAL_FBM
    noise.fractal_octaves = 3
    noise.fractal_lacunarity = 2.0
    noise.fractal_gain = 0.42
    mask_image = Image.create(MASK_SIZE, MASK_SIZE, false, Image.FORMAT_L8)
    var span := float(MASK_SIZE)
    for y in range(MASK_SIZE):
        var fy := float(y) / span
        var wy := fy * fy * (3.0 - 2.0 * fy)
        for x in range(MASK_SIZE):
            var fx := float(x) / span
            var wx := fx * fx * (3.0 - 2.0 * fx)
            # Blend four translated noise samples to make a periodic field;
            # no hard seam enters a shadow as the wind carries the pattern.
            var top := lerpf(noise.get_noise_2d(float(x), float(y)), noise.get_noise_2d(float(x) - span, float(y)), wx)
            var bottom := lerpf(noise.get_noise_2d(float(x), float(y) - span), noise.get_noise_2d(float(x) - span, float(y) - span), wx)
            var value := clampf(0.5 + lerpf(top, bottom, wy) * 0.82, 0.0, 1.0)
            mask_image.set_pixel(x, y, Color(value, value, value, 1.0))
    mask_texture = ImageTexture.create_from_image(mask_image)
    var hash_context := HashingContext.new()
    hash_context.start(HashingContext.HASH_SHA256)
    hash_context.update(mask_image.get_data())
    mask_sha256 = hash_context.finish().hex_encode()

func set_enabled(value: bool) -> void:
    enabled = value
    if is_instance_valid(caster):
        caster.visible = enabled

func set_atmosphere_enabled(value: bool) -> void:
    atmosphere_enabled = value
    if environment != null:
        environment.volumetric_fog_enabled = atmosphere_enabled

func set_motion_enabled(value: bool) -> void:
    motion_enabled = value

func set_time(seconds: float) -> void:
    clock_seconds = maxf(seconds, 0.0)
    if material != null:
        material.set_shader_parameter("cloud_clock", clock_seconds)

func tick(delta: float) -> void:
    if motion_enabled:
        set_time(clock_seconds + maxf(delta, 0.0))

func set_preset(id: String) -> bool:
    if id not in ["day", "dusk"]:
        return false
    preset = id
    if environment == null or sun == null:
        return true
    environment.volumetric_fog_enabled = atmosphere_enabled
    environment.volumetric_fog_density = 0.0030 if preset == "day" else 0.0038
    environment.volumetric_fog_albedo = Color(0.88, 0.92, 0.98) if preset == "day" else Color(0.96, 0.88, 0.78)
    environment.volumetric_fog_emission = Color(0.29, 0.37, 0.53)
    environment.volumetric_fog_emission_energy = 0.015
    environment.volumetric_fog_length = 78.0
    environment.volumetric_fog_detail_spread = 2.0
    environment.volumetric_fog_anisotropy = 0.48
    environment.volumetric_fog_ambient_inject = 0.12
    environment.volumetric_fog_gi_inject = 0.0
    environment.volumetric_fog_sky_affect = 0.12
    environment.volumetric_fog_temporal_reprojection_enabled = true
    environment.volumetric_fog_temporal_reprojection_amount = 0.65
    sun.light_volumetric_fog_energy = 3.2 if preset == "day" else 4.2
    return true

func set_pattern(cutoff: float, span_m: float, velocity: Vector2) -> void:
    mask_cutoff = clampf(cutoff, 0.05, 0.95)
    pattern_span_m = clampf(span_m, 24.0, 192.0)
    wind_velocity = velocity.limit_length(3.0)
    if material != null:
        material.set_shader_parameter("mask_cutoff", mask_cutoff)
        material.set_shader_parameter("pattern_span_m", pattern_span_m)
        material.set_shader_parameter("wind_velocity", wind_velocity)

func _sample_mask(position_xz: Vector2, seconds: float) -> float:
    if mask_image == null:
        return 0.0
    var uv := (position_xz + wind_velocity * seconds) / pattern_span_m + pattern_phase
    # Match linear repeating texture sampling; this is a diagnostic sampler,
    # not a substitute for actual rendered shadow coverage evidence.
    var pixel := Vector2(fposmod(uv.x, 1.0), fposmod(uv.y, 1.0)) * float(MASK_SIZE) - Vector2(0.5, 0.5)
    var x0 := int(floorf(pixel.x))
    var y0 := int(floorf(pixel.y))
    var fx := pixel.x - floorf(pixel.x)
    var fy := pixel.y - floorf(pixel.y)
    var a := mask_image.get_pixel(posmod(x0, MASK_SIZE), posmod(y0, MASK_SIZE)).r
    var b := mask_image.get_pixel(posmod(x0 + 1, MASK_SIZE), posmod(y0, MASK_SIZE)).r
    var c := mask_image.get_pixel(posmod(x0, MASK_SIZE), posmod(y0 + 1, MASK_SIZE)).r
    var d := mask_image.get_pixel(posmod(x0 + 1, MASK_SIZE), posmod(y0 + 1, MASK_SIZE)).r
    return lerpf(lerpf(a, b, fx), lerpf(c, d, fx), fy)

func cloud_ray_sample(world_point: Vector3, seconds: float = -1.0) -> Dictionary:
    var sample_clock := clock_seconds if seconds < 0.0 else seconds
    if sun == null or mask_image == null:
        return {"available": false}
    # Light travels along -Z; trace from the receiver towards +Z to the cloud.
    var towards_sun := sun.global_basis.z.normalized()
    if towards_sun.y <= 0.0001:
        return {"available": false}
    var distance_to_plane := (cloud_height_m - world_point.y) / towards_sun.y
    var hit := world_point + towards_sun * distance_to_plane
    var density := _sample_mask(Vector2(hit.x, hit.z), sample_clock)
    var inside := absf(hit.x) <= cloud_width_m * 0.5 and absf(hit.z + 8.0) <= cloud_width_m * 0.5
    return {"available": true, "world_point": [world_point.x, world_point.y, world_point.z], "cloud_hit": [hit.x, hit.y, hit.z], "inside_caster": inside, "mask_value": density, "blocked": enabled and inside and density >= mask_cutoff}

func snapshot() -> Dictionary:
    var samples: Array = []
    for point in [Vector3(-12, 0.1, 2), Vector3(0, 0.1, 2), Vector3(12, 0.1, 2), Vector3(-5, 5, -3), Vector3(7, 4, -6)]:
        samples.append(cloud_ray_sample(point))
    return {
        "enabled": enabled,
        "atmosphere_enabled": atmosphere_enabled,
        "motion_enabled": motion_enabled,
        "clock_seconds": clock_seconds,
        "preset": preset,
        "seed": CLOUD_SEED,
        "mask_sha256": mask_sha256,
        "mask_size": [MASK_SIZE, MASK_SIZE],
        "cloud_height_m": cloud_height_m,
        "cloud_width_m": cloud_width_m,
        "pattern_span_m": pattern_span_m,
        "mask_cutoff": mask_cutoff,
        "wind_velocity": [wind_velocity.x, wind_velocity.y],
        "pattern_phase": [pattern_phase.x, pattern_phase.y],
        "shadow_only": is_instance_valid(caster) and caster.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY,
        "native_shadow_pass": true,
        "fog_density": environment.volumetric_fog_density if environment != null else 0.0,
        "sun_energy": sun.light_energy if sun != null else 0.0,
        "ray_samples": samples
    }
