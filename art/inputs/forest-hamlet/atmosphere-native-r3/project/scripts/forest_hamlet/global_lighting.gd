extends Node
## Seeded irregular energy variation, independent of spatial cloud shadows.
## The scene owns tick/freeze; this controller never processes itself.
## Only native sun and ambient energies change. Exposure, color, cloud masks,
## fog settings, geometry and source artwork remain outside this controller.

const GLOBAL_LIGHT_SEED := 20261022
const SUN_AMPLITUDE := 0.18
const AMBIENT_AMPLITUDE := 0.10
const COMPONENT_WEIGHTS := [0.47, 0.31, 0.14, 0.08]
const SUN_SCALES_SECONDS := [11.3, 22.7, 3.9, 6.3]
const AMBIENT_SCALES_SECONDS := [15.7, 24.1, 4.7, 6.9]
const SIGNAL_GAIN := 1.65

var enabled := true
var motion_enabled := true
var clock_seconds := 0.0
var preset := "day"
var sun: DirectionalLight3D
var environment: Environment
var sun_base_energy := 1.45
var ambient_base_energy := 0.55
var sun_multiplier := 1.0
var ambient_multiplier := 1.0

var _sun_noise: Array[FastNoiseLite] = []
var _ambient_noise: Array[FastNoiseLite] = []
var _sun_origins: Array[float] = []
var _ambient_origins: Array[float] = []

func configure(sunlight: DirectionalLight3D, world_environment: Environment) -> void:
    assert(sunlight != null and world_environment != null)
    sun = sunlight
    environment = world_environment
    _apply()

func _ensure_noise() -> void:
    if not _sun_noise.is_empty():
        return
    _build_channel(101, _sun_noise, _sun_origins)
    _build_channel(7919, _ambient_noise, _ambient_origins)

func _build_channel(seed_offset: int, destination: Array[FastNoiseLite], origins: Array[float]) -> void:
    for index in range(COMPONENT_WEIGHTS.size()):
        var noise := FastNoiseLite.new()
        noise.seed = GLOBAL_LIGHT_SEED + seed_offset + index * 104729
        noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
        noise.frequency = 1.0
        # Explicit temporal scales below own the spectrum. Disable automatic
        # fractal octaves so no unrecorded high-frequency component is added.
        noise.fractal_type = FastNoiseLite.FRACTAL_NONE
        destination.append(noise)
        origins.append(_noise_sample(noise, index, 0.0))

func _noise_sample(noise: FastNoiseLite, index: int, coordinate: float) -> float:
    # Separate seeds and paths avoid locking sun and ambient to one envelope.
    return noise.get_noise_2d(coordinate + float(index) * 7.31, 17.23 + float(index) * 5.17)

func _channel_signal(noises: Array[FastNoiseLite], origins: Array[float], scales: Array, seconds: float) -> float:
    var combined := 0.0
    for index in range(COMPONENT_WEIGHTS.size()):
        var sample := _noise_sample(noises[index], index, seconds / float(scales[index]))
        combined += float(COMPONENT_WEIGHTS[index]) * (sample - origins[index])
    # Subtracting the exact t=0 samples gives a reproducible neutral baseline.
    # Smooth bounded compression avoids hard clipping / flat-topped pulses.
    var shaped := combined * SIGNAL_GAIN
    return shaped / sqrt(1.0 + shaped * shaped)

func _apply() -> void:
    _ensure_noise()
    sun_multiplier = 1.0
    ambient_multiplier = 1.0
    if enabled and clock_seconds > 0.0:
        sun_multiplier += SUN_AMPLITUDE * _channel_signal(_sun_noise, _sun_origins, SUN_SCALES_SECONDS, clock_seconds)
        ambient_multiplier += AMBIENT_AMPLITUDE * _channel_signal(_ambient_noise, _ambient_origins, AMBIENT_SCALES_SECONDS, clock_seconds)
    if is_instance_valid(sun):
        sun.light_energy = sun_base_energy * sun_multiplier
    if environment != null:
        environment.ambient_light_energy = ambient_base_energy * ambient_multiplier

func set_enabled(value: bool) -> void:
    enabled = value
    _apply()

func set_motion_enabled(value: bool) -> void:
    motion_enabled = value

func set_time(seconds: float) -> void:
    clock_seconds = maxf(seconds, 0.0)
    _apply()

func tick(delta: float) -> void:
    if motion_enabled:
        set_time(clock_seconds + maxf(delta, 0.0))

func set_preset(id: String) -> bool:
    if id not in ["day", "dusk"]:
        return false
    preset = id
    sun_base_energy = 1.45 if preset == "day" else 1.15
    ambient_base_energy = 0.55 if preset == "day" else 0.40
    _apply()
    return true

func snapshot() -> Dictionary:
    return {
        "enabled": enabled,
        "motion_enabled": motion_enabled,
        "clock_seconds": clock_seconds,
        "preset": preset,
        "seed": GLOBAL_LIGHT_SEED,
        "sun_base_energy": sun_base_energy,
        "ambient_base_energy": ambient_base_energy,
        "sun_multiplier": sun_multiplier,
        "ambient_multiplier": ambient_multiplier,
        "sun_energy": sun.light_energy if is_instance_valid(sun) else 0.0,
        "ambient_energy": environment.ambient_light_energy if environment != null else 0.0,
        "sun_multiplier_bounds": [1.0 - SUN_AMPLITUDE, 1.0 + SUN_AMPLITUDE],
        "ambient_multiplier_bounds": [1.0 - AMBIENT_AMPLITUDE, 1.0 + AMBIENT_AMPLITUDE],
        "sun_component_seconds": SUN_SCALES_SECONDS.duplicate(),
        "ambient_component_seconds": AMBIENT_SCALES_SECONDS.duplicate(),
        "component_weights": COMPONENT_WEIGHTS.duplicate(),
        "noise_kind": "FastNoiseLite.TYPE_SIMPLEX_SMOOTH",
        "signal_kind": "seeded_multiscale_time_noise",
        "signal_gain": SIGNAL_GAIN,
        "sun_seed_offset": 101,
        "ambient_seed_offset": 7919,
        "component_seed_stride": 104729,
        "origin_subtracted": true,
        "native_energy_only": true
    }
