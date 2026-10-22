extends Node3D
## Partial native cloud shadows split sunlight into clear and cloud branches.
## Default is 70/30; user contrast can raise cloud attenuation to at most 80%.
## Both branches retain ordinary entity shadows and preserve total sun energy.
## The original sun remains the authoritative total-energy and sky driver.
## No albedo overlay, exposure change, character edit, or global-noise owner.

const CLOUD_SEED := 20261022
const MASK_SIZE := 256
const SHADER_PATH := "res://shaders/forest_hamlet/cloud_occluder.gdshader"
const CLOUD_LAYER_MASK := 1 << 19
# Default and legacy radiometry calibration ratios.
const BASE_SUN_RATIO := 0.70
const CLOUD_SUN_RATIO := 0.30
const THIN_ATTENUATION := 0.10
const MAX_ATTENUATION := 0.80
const DEFAULT_CLOUD_CONTRAST := 0.30
const DEFAULT_CLOUD_DENSITY := 0.5
const SUN_COPIED_PROPERTIES := [
    &"light_color", &"light_indirect_energy", &"light_specular",
    &"light_negative", &"light_cull_mask", &"light_angular_distance",
    &"light_bake_mode", &"light_intensity_lux", &"light_temperature",
    &"light_volumetric_fog_energy", &"shadow_enabled", &"shadow_bias",
    &"shadow_normal_bias", &"shadow_blur", &"shadow_reverse_cull_face",
    &"shadow_transmittance_bias", &"directional_shadow_mode",
    &"directional_shadow_max_distance", &"directional_shadow_fade_start",
    &"directional_shadow_blend_splits", &"directional_shadow_pancake_size",
    &"directional_shadow_split_1", &"directional_shadow_split_2",
    &"directional_shadow_split_3"
]

@export var cloud_height_m: float = 24.0
@export var cloud_width_m: float = 220.0
@export var pattern_span_m: float = 96.0
@export var wind_velocity: Vector2 = Vector2(0.32, 0.13)
@export_range(0.0, 1.0) var mask_cutoff: float = 0.515
@export_range(0.01, 0.30) var mask_edge_width: float = 0.12
@export_range(0.01, 0.40) var mask_body_width: float = 0.18
@export_range(0.1, 2.0) var alpha_hash_scale: float = 1.0
@export var pattern_phase: Vector2 = Vector2(0.65, 0.0)
# Contrast is maximum attenuation as a fraction; total sunlight stays fixed.
# Density changes the same seeded smooth field without regenerating the mask.
@export_range(0.0, 0.80, 0.01) var contrast_strength: float = DEFAULT_CLOUD_CONTRAST:
    set(value):
        if not is_finite(value):
            return
        contrast_strength = clampf(value, 0.0, MAX_ATTENUATION)
        if material != null:
            material.set_shader_parameter("contrast_strength", contrast_strength)
        sync_sun_lights()
@export_range(0.0, 1.0, 0.01) var cloud_density: float = DEFAULT_CLOUD_DENSITY:
    set(value):
        if not is_finite(value):
            return
        cloud_density = clampf(value, 0.0, 1.0)
        if material != null:
            material.set_shader_parameter("cloud_density", cloud_density)

var enabled := true
var atmosphere_enabled := true
var motion_enabled := true
var clock_seconds := 0.0
var preset := "day"
var uniform_attenuation := -1.0
var sun: DirectionalLight3D
var base_sun: DirectionalLight3D
var cloud_sun: DirectionalLight3D
var environment: Environment
var caster: MeshInstance3D
var material: ShaderMaterial
var mask_image: Image
var mask_texture: ImageTexture
var mask_sha256 := ""
var _original_sky_mode: int = DirectionalLight3D.SKY_MODE_LIGHT_AND_SKY

func configure(sunlight: DirectionalLight3D, world_environment: Environment) -> void:
    assert(sunlight != null and world_environment != null)
    if sun != sunlight:
        if is_instance_valid(sun):
            sun.sky_mode = _original_sky_mode
        _original_sky_mode = sunlight.sky_mode
    sun = sunlight
    environment = world_environment
    _ensure_caster()
    _ensure_sun_lights()
    set_time(clock_seconds)
    set_enabled(enabled)
    set_preset(preset)
    sync_sun_lights()

func _exit_tree() -> void:
    # Removing this controller also removes its branch lights. Restore the
    # original source mode so a surviving scene is not left without a sun.
    if is_instance_valid(sun):
        sun.sky_mode = _original_sky_mode

func _ensure_sun_lights() -> void:
    if not is_instance_valid(base_sun):
        base_sun = DirectionalLight3D.new()
        base_sun.name = "SunBase"
        base_sun.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY
        add_child(base_sun)
    if not is_instance_valid(cloud_sun):
        cloud_sun = DirectionalLight3D.new()
        cloud_sun.name = "SunCloud"
        cloud_sun.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY
        add_child(cloud_sun)

func _cloud_branch_ratio() -> float:
    # The legacy explicit radiometry probe keeps its original 70/30 split.
    # Natural mode takes the user-selected maximum attenuation, including zero.
    return CLOUD_SUN_RATIO if uniform_attenuation >= 0.0 else contrast_strength

func sync_sun_lights() -> void:
    # The scene calls this AFTER global_lighting updates and also while frozen.
    # Nothing ever scales sun.light_energy in place: repeated sync is stable.
    if not is_instance_valid(sun):
        return
    _ensure_sun_lights()
    sun.sky_mode = DirectionalLight3D.SKY_MODE_SKY_ONLY
    var ordinary_mask: int = sun.shadow_caster_mask & ~CLOUD_LAYER_MASK
    for branch: DirectionalLight3D in [base_sun, cloud_sun]:
        branch.global_transform = sun.global_transform
        branch.visible = sun.is_visible_in_tree()
        branch.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY
        for property_name: StringName in SUN_COPIED_PROPERTIES:
            var source_value: Variant = sun.get(property_name)
            if branch.get(property_name) != source_value:
                branch.set(property_name, source_value)
        # Entity shadows stay opaque on BOTH branches. Only the caster mask
        # prevents the base branch from seeing the cloud-only render layer.
        branch.shadow_opacity = 1.0
    base_sun.shadow_caster_mask = ordinary_mask
    cloud_sun.shadow_caster_mask = ordinary_mask | CLOUD_LAYER_MASK
    var cloud_ratio := _cloud_branch_ratio()
    base_sun.light_energy = sun.light_energy * (1.0 - cloud_ratio)
    cloud_sun.light_energy = sun.light_energy * cloud_ratio
    if material != null:
        material.set_shader_parameter("cloud_branch_ratio", cloud_ratio)

func _ensure_caster() -> void:
    if is_instance_valid(caster):
        return
    _make_mask()
    material = ShaderMaterial.new()
    material.shader = load(SHADER_PATH)
    material.set_shader_parameter("cloud_mask", mask_texture)
    material.set_shader_parameter("pattern_span_m", pattern_span_m)
    material.set_shader_parameter("mask_cutoff", mask_cutoff)
    material.set_shader_parameter("mask_edge_width", mask_edge_width)
    material.set_shader_parameter("mask_body_width", mask_body_width)
    material.set_shader_parameter("alpha_hash_scale", alpha_hash_scale)
    material.set_shader_parameter("uniform_attenuation", uniform_attenuation)
    material.set_shader_parameter("wind_velocity", wind_velocity)
    material.set_shader_parameter("pattern_phase", pattern_phase)
    material.set_shader_parameter("contrast_strength", contrast_strength)
    material.set_shader_parameter("cloud_density", cloud_density)
    material.set_shader_parameter("cloud_branch_ratio", _cloud_branch_ratio())
    var plane := PlaneMesh.new()
    plane.size = Vector2(cloud_width_m, cloud_width_m)
    # Smaller triangles avoid large-triangle shadow-frustum pancaking artifacts.
    plane.subdivide_width = 31
    plane.subdivide_depth = 31
    caster = MeshInstance3D.new()
    caster.name = "OverheadCloudShadowCaster"
    caster.mesh = plane
    caster.material_override = material
    # The layer must be exclusive: also leaving default layer 1 would let the
    # cloud cast a shadow through the base branch's ordinary caster mask.
    caster.layers = CLOUD_LAYER_MASK
    caster.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
    caster.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
    caster.ignore_occlusion_culling = true
    caster.position = Vector3(0.0, cloud_height_m, -8.0)
    caster.extra_cull_margin = 2.0
    add_child(caster)

func _make_mask() -> void:
    # The same synchronous, fixed-seed periodic density field as r2.
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
    # Keep the two entity-shadow lights present for clear/cloudy A/B captures.
    sync_sun_lights()

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

func set_cloud_contrast(value: float) -> void:
    contrast_strength = value

func set_cloud_density(value: float) -> void:
    cloud_density = value

func reset_cloud_tuning() -> void:
    set_cloud_contrast(DEFAULT_CLOUD_CONTRAST)
    set_cloud_density(DEFAULT_CLOUD_DENSITY)

func set_uniform_attenuation(value: float) -> void:
    # Calibration bypasses both user controls and restores the original 70/30
    # branch split. Its explicit 0-30% contract remains stable for prior probes.
    # Negative returns to the user's live natural cloud tuning and light split.
    if not is_finite(value):
        return
    uniform_attenuation = -1.0 if value < 0.0 else clampf(value, 0.0, CLOUD_SUN_RATIO)
    if material != null:
        material.set_shader_parameter("uniform_attenuation", uniform_attenuation)
    sync_sun_lights()

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
    # This is a secondary multiplier. Both branches copy it unchanged because
    # their light_energy is already split. SKY_ONLY source does not light fog.
    sun.light_volumetric_fog_energy = 3.2 if preset == "day" else 4.2
    sync_sun_lights()
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
    # CPU diagnostics mirror linear/repeat sampling; GPU evidence still owns
    # measured transmission, hash variance, and real receiver shadow behavior.
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

func _tuned_density(raw_density: float) -> float:
    return clampf(raw_density + 2.0 * (cloud_density - DEFAULT_CLOUD_DENSITY), 0.0, 1.0)

func _attenuation_from_density(density: float) -> float:
    if uniform_attenuation >= 0.0:
        return uniform_attenuation
    # Explicit endpoints also hold if a developer changes the pattern cutoff.
    if cloud_density <= 0.0:
        return 0.0
    if cloud_density >= 1.0:
        return contrast_strength
    var tuned_density := _tuned_density(density)
    var edge := smoothstep(mask_cutoff - mask_edge_width, mask_cutoff, tuned_density)
    var body := smoothstep(mask_cutoff, mask_cutoff + mask_body_width, tuned_density)
    return edge * lerpf(THIN_ATTENUATION, CLOUD_SUN_RATIO, body) * (contrast_strength / CLOUD_SUN_RATIO)

func cloud_ray_sample(world_point: Vector3, seconds: float = -1.0) -> Dictionary:
    var sample_clock := clock_seconds if seconds < 0.0 else seconds
    if sun == null or mask_image == null:
        return {"available": false}
    var towards_sun := sun.global_basis.z.normalized()
    if towards_sun.y <= 0.0001:
        return {"available": false}
    var distance_to_plane := (cloud_height_m - world_point.y) / towards_sun.y
    var hit := world_point + towards_sun * distance_to_plane
    var density := _sample_mask(Vector2(hit.x, hit.z), sample_clock)
    var inside := distance_to_plane >= 0.0 and absf(hit.x) <= cloud_width_m * 0.5 and absf(hit.z + 8.0) <= cloud_width_m * 0.5
    var requested := _attenuation_from_density(density)
    var effective := requested if enabled and inside else 0.0
    var cloud_ratio := _cloud_branch_ratio()
    return {
        "available": true,
        "world_point": [world_point.x, world_point.y, world_point.z],
        "cloud_hit": [hit.x, hit.y, hit.z],
        "inside_caster": inside,
        "mask_value": density,
        "tuned_density": _tuned_density(density),
        "uniform_mode": uniform_attenuation >= 0.0,
        "requested_attenuation": requested,
        "effective_attenuation": effective,
        "branch_blocked_coverage": effective / cloud_ratio if cloud_ratio > 0.0 else 0.0,
        "expected_direct_transmittance": 1.0 - effective,
        "blocked": effective > 0.0
    }

func _light_snapshot(light: DirectionalLight3D) -> Dictionary:
    if not is_instance_valid(light):
        return {"available": false}
    var direction := -light.global_basis.z.normalized()
    return {
        "available": true,
        "name": String(light.name),
        "energy": light.light_energy,
        "shadow_caster_mask": light.shadow_caster_mask,
        "light_cull_mask": light.light_cull_mask,
        "sky_mode": light.sky_mode,
        "shadow_enabled": light.shadow_enabled,
        "shadow_opacity": light.shadow_opacity,
        "volumetric_fog_energy": light.light_volumetric_fog_energy,
        "direction": [direction.x, direction.y, direction.z],
        "color": [light.light_color.r, light.light_color.g, light.light_color.b],
        "angular_distance": light.light_angular_distance,
        "shadow_mode": light.directional_shadow_mode,
        "shadow_max_distance": light.directional_shadow_max_distance,
        "visible": light.is_visible_in_tree()
    }

func snapshot() -> Dictionary:
    var samples: Array = []
    for point in [Vector3(-12, 0.1, 2), Vector3(0, 0.1, 2), Vector3(12, 0.1, 2), Vector3(-5, 5, -3), Vector3(7, 4, -6)]:
        samples.append(cloud_ray_sample(point))
    var source_energy := sun.light_energy if is_instance_valid(sun) else 0.0
    var base_energy := base_sun.light_energy if is_instance_valid(base_sun) else 0.0
    var cloud_energy := cloud_sun.light_energy if is_instance_valid(cloud_sun) else 0.0
    var natural_cap := contrast_strength
    var natural_thin := THIN_ATTENUATION * (contrast_strength / CLOUD_SUN_RATIO)
    var cloud_ratio := _cloud_branch_ratio()
    # These bounds cover possible raw density values in [0,1] inside the caster;
    # they describe the active transfer function, not measured screen coverage.
    var active_min := _attenuation_from_density(0.0) if enabled else 0.0
    var active_max := _attenuation_from_density(1.0) if enabled else 0.0
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
        "mask_edge_width": mask_edge_width,
        "mask_body_width": mask_body_width,
        "wind_velocity": [wind_velocity.x, wind_velocity.y],
        "pattern_phase": [pattern_phase.x, pattern_phase.y],
        "alpha_hash_scale": alpha_hash_scale,
        "uniform_attenuation": uniform_attenuation,
        "attenuation_range": [0.0, natural_cap],
        "cloud_body_attenuation_range": [natural_thin, natural_cap],
        "direct_transmittance_bounds": [1.0 - natural_cap, 1.0],
        "cloud_tuning": {
            "contrast_strength": contrast_strength,
            "contrast_unit": "fraction of direct sunlight attenuated by thick cloud",
            "cloud_density": cloud_density,
            "default_contrast_strength": DEFAULT_CLOUD_CONTRAST,
            "default_cloud_density": DEFAULT_CLOUD_DENSITY,
            "density_bias": 2.0 * (cloud_density - DEFAULT_CLOUD_DENSITY),
            "thin_attenuation": natural_thin,
            "maximum_attenuation": natural_cap,
            "hard_attenuation_cap": MAX_ATTENUATION,
            "active_attenuation_bounds": [active_min, active_max],
            "active_direct_transmittance_bounds": [1.0 - active_max, 1.0 - active_min],
            "active_bounds_scope": "possible raw density values inside caster; not measured pixel coverage",
            "uniform_calibration_bypasses_user_controls": uniform_attenuation >= 0.0
        },
        "density_transfer": "smooth_clear_edge_then_thin_to_thick",
        "shadow_only": is_instance_valid(caster) and caster.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY,
        "caster_layers": caster.layers if is_instance_valid(caster) else 0,
        "native_shadow_pass": true,
        "shadow_method": "alpha_hash_on_variable_cloud_native_directional_branch",
        "fog_density": environment.volumetric_fog_density if environment != null else 0.0,
        "sun_energy": source_energy,
        "light_split": {
            "source": _light_snapshot(sun),
            "base70": _light_snapshot(base_sun),
            "cloud30": _light_snapshot(cloud_sun),
            "source_total_energy": source_energy,
            "total_direct_energy": base_energy + cloud_energy,
            "energy_sum_error": base_energy + cloud_energy - source_energy,
            "cloud_layer_mask": CLOUD_LAYER_MASK,
            "ordinary_caster_mask": (sun.shadow_caster_mask & ~CLOUD_LAYER_MASK) if is_instance_valid(sun) else 0,
            "base_ratio": 1.0 - cloud_ratio,
            "cloud_ratio": cloud_ratio,
            "legacy_snapshot_aliases": "base70 and cloud30 identify the same branches at every tuning; read actual ratios and energies",
            "source_is_sky_only": is_instance_valid(sun) and sun.sky_mode == DirectionalLight3D.SKY_MODE_SKY_ONLY,
            "real_scene_light_count": 2
        },
        "ray_samples": samples
    }
