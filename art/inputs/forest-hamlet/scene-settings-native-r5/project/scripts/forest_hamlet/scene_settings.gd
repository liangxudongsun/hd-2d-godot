extends RefCounted
## Pure scene-profile validation and persistence. No node or renderer is mutated.
## Schema 2 retains the original [clouds] payload for older scene versions.

const SCHEMA_VERSION := 2
const FEATURE_DEFAULTS := {
    "normals": true,
    "bloom": true,
    "dof": true,
    "wind": true,
    "backdrop_normals": true,
    "parallax": true,
    "clouds": true,
    "atmosphere": true,
    "global_light": true,
}
const PARAMETER_SPECS := {
    "cloud_contrast": {"default": 0.30, "min": 0.0, "max": 0.8, "step": 0.01},
    "cloud_density": {"default": 0.50, "min": 0.0, "max": 1.0, "step": 0.01},
    "dof_amount": {"default": 0.035, "min": 0.0, "max": 0.3, "step": 0.005},
    "dof_near_margin": {"default": 5.0, "min": 0.5, "max": 15.0, "step": 0.1},
    "dof_near_transition": {"default": 3.0, "min": 0.1, "max": 20.0, "step": 0.1},
    "dof_far_margin": {"default": 10.0, "min": 0.5, "max": 40.0, "step": 0.5},
    "dof_far_transition": {"default": 16.0, "min": 0.1, "max": 40.0, "step": 0.1},
    "glow_intensity": {"default": 0.42, "min": 0.0, "max": 2.0, "step": 0.01},
    "glow_strength": {"default": 0.85, "min": 0.0, "max": 2.0, "step": 0.01},
    "glow_bloom": {"default": 0.025, "min": 0.0, "max": 1.0, "step": 0.005},
    "glow_hdr_threshold": {"default": 0.95, "min": 0.0, "max": 4.0, "step": 0.05},
    "glow_hdr_scale": {"default": 1.6, "min": 0.1, "max": 4.0, "step": 0.1},
    "exposure": {"default": 1.0, "min": 0.25, "max": 2.5, "step": 0.05},
    "contrast": {"default": 1.06, "min": 0.5, "max": 1.5, "step": 0.01},
    "saturation": {"default": 0.98, "min": 0.0, "max": 1.5, "step": 0.01},
    "wind_strength": {"default": 0.06, "min": 0.0, "max": 0.16, "step": 0.005},
    "parallax_strength": {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01},
    "fog_density_scale": {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.05},
    "sun_variation": {"default": 0.18, "min": 0.0, "max": 0.5, "step": 0.01},
    "ambient_variation": {"default": 0.10, "min": 0.0, "max": 0.3, "step": 0.01},
}
const PROFILE_KEYS := {"schema_version": true, "time_preset": true, "features": true, "parameters": true}
const SCENE_KEYS := {"schema_version": true, "time_preset": true}
const CLOUD_KEYS := {"schema_version": true, "max_attenuation": true, "density": true}

static func default_parameters() -> Dictionary:
    var parameters: Dictionary = {}
    for key in PARAMETER_SPECS:
        parameters[key] = float(PARAMETER_SPECS[key]["default"])
    return parameters

static func default_profile() -> Dictionary:
    return {
        "schema_version": SCHEMA_VERSION,
        "time_preset": "day",
        "features": FEATURE_DEFAULTS.duplicate(true),
        "parameters": default_parameters(),
    }

static func normalize_profile(candidate: Dictionary) -> Dictionary:
    var key_error := _unknown_key_error(candidate, PROFILE_KEYS, "profile")
    if not key_error.is_empty():
        return _normalization_error(key_error)
    var version: Variant = candidate.get("schema_version", SCHEMA_VERSION)
    if typeof(version) != TYPE_INT or version != SCHEMA_VERSION:
        return _normalization_error("Unsupported scene settings schema version.")
    var preset: Variant = candidate.get("time_preset", "day")
    if typeof(preset) != TYPE_STRING or preset not in ["day", "dusk"]:
        return _normalization_error("Invalid scene time preset.")
    var features: Variant = candidate.get("features", {})
    var parameters: Variant = candidate.get("parameters", {})
    if typeof(features) != TYPE_DICTIONARY or typeof(parameters) != TYPE_DICTIONARY:
        return _normalization_error("Features and parameters must be dictionaries.")
    key_error = _unknown_key_error(features, FEATURE_DEFAULTS, "features")
    if not key_error.is_empty():
        return _normalization_error(key_error)
    key_error = _unknown_key_error(parameters, PARAMETER_SPECS, "parameters")
    if not key_error.is_empty():
        return _normalization_error(key_error)
    var profile := default_profile()
    profile.time_preset = preset
    for key in features:
        if typeof(features[key]) != TYPE_BOOL:
            return _normalization_error("Feature '%s' must be a boolean." % key)
        profile.features[key] = features[key]
    for key in parameters:
        var value: Variant = parameters[key]
        if typeof(value) not in [TYPE_INT, TYPE_FLOAT]:
            return _normalization_error("Parameter '%s' must be numeric." % key)
        var number := float(value)
        if not is_finite(number):
            return _normalization_error("Parameter '%s' must be finite." % key)
        var spec: Dictionary = PARAMETER_SPECS[key]
        # Step describes the slider UI; saved values are never quantized to it.
        profile.parameters[key] = clampf(number, float(spec.min), float(spec.max))
    return {"ok": true, "profile": profile, "error": ""}

static func read_profile(path: String) -> Dictionary:
    var config := ConfigFile.new()
    var error := config.load(path)
    if error != OK:
        return _read_error("Unable to read scene settings (%d)." % error, error)
    var legacy := not config.has_section("scene")
    if not legacy:
        var scene_version: Variant = config.get_value("scene", "schema_version", null)
        if typeof(scene_version) != TYPE_INT or scene_version != SCHEMA_VERSION:
            return _read_error("Unsupported scene settings schema version.", ERR_INVALID_DATA)
    var key_error := _config_key_error(config, legacy)
    if not key_error.is_empty():
        return _read_error(key_error, ERR_INVALID_DATA, legacy)
    var cloud_version: Variant = config.get_value("clouds", "schema_version", null)
    if typeof(cloud_version) != TYPE_INT or cloud_version != 1:
        return _read_error("Missing or unsupported cloud settings schema version.", ERR_INVALID_DATA, legacy)
    # Both original keys are required, even in schema 2. Newly introduced
    # feature/effect keys may be omitted and then inherit explicit defaults.
    if not config.has_section_key("clouds", "max_attenuation") or not config.has_section_key("clouds", "density"):
        return _read_error("Cloud settings require attenuation and density.", ERR_INVALID_DATA, legacy)
    var candidate := default_profile()
    candidate.parameters.cloud_contrast = config.get_value("clouds", "max_attenuation")
    candidate.parameters.cloud_density = config.get_value("clouds", "density")
    if not legacy:
        candidate.time_preset = config.get_value("scene", "time_preset", "day")
        for key in FEATURE_DEFAULTS:
            if config.has_section_key("features", key):
                candidate.features[key] = config.get_value("features", key)
        for key in PARAMETER_SPECS:
            if key not in ["cloud_contrast", "cloud_density"] and config.has_section_key("effects", key):
                candidate.parameters[key] = config.get_value("effects", key)
    var normalized := normalize_profile(candidate)
    if not normalized.ok:
        return _read_error(normalized.error, ERR_INVALID_DATA, legacy)
    return {"ok": true, "profile": normalized.profile, "error": "", "error_code": OK, "legacy": legacy}

static func write_profile(path: String, profile: Dictionary) -> Dictionary:
    var normalized := normalize_profile(profile)
    if not normalized.ok:
        return _write_error(normalized.error, ERR_INVALID_DATA)
    if path.strip_edges().is_empty():
        return _write_error("Scene settings path must not be empty.", ERR_INVALID_PARAMETER)
    var clean: Dictionary = normalized.profile
    var config := ConfigFile.new()
    config.set_value("clouds", "schema_version", 1)
    config.set_value("clouds", "max_attenuation", clean.parameters.cloud_contrast)
    config.set_value("clouds", "density", clean.parameters.cloud_density)
    config.set_value("scene", "schema_version", SCHEMA_VERSION)
    config.set_value("scene", "time_preset", clean.time_preset)
    for key in FEATURE_DEFAULTS:
        config.set_value("features", key, clean.features[key])
    for key in PARAMETER_SPECS:
        if key not in ["cloud_contrast", "cloud_density"]:
            config.set_value("effects", key, clean.parameters[key])
    var absolute := ProjectSettings.globalize_path(path)
    var temporary := absolute + ".tmp"
    # Never overwrite or clean a temporary path owned by another operation.
    if FileAccess.file_exists(temporary) or DirAccess.dir_exists_absolute(temporary):
        return _write_error("The temporary scene settings path is already in use.", ERR_ALREADY_EXISTS)
    var error := DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
    if error != OK:
        return _write_error("Unable to create the settings directory (%d)." % error, error)
    error = config.save(temporary)
    if error == OK:
        # Same-directory rename is the only operation that replaces the target.
        # A failed save or rename therefore leaves the previous file intact.
        error = DirAccess.rename_absolute(temporary, absolute)
    if error != OK:
        if FileAccess.file_exists(temporary):
            DirAccess.remove_absolute(temporary)
        return _write_error("Unable to save scene settings (%d)." % error, error)
    return {"ok": true, "error": "", "error_code": OK}

static func _unknown_key_error(candidate: Dictionary, known: Dictionary, context: String) -> String:
    for key in candidate:
        if typeof(key) != TYPE_STRING or not known.has(key):
            return "Unknown %s key '%s'." % [context, str(key)]
    return ""

static func _config_key_error(config: ConfigFile, legacy: bool) -> String:
    var known_sections := {"clouds": true}
    if not legacy:
        known_sections.merge({"scene": true, "features": true, "effects": true})
    for section in config.get_sections():
        if not known_sections.has(section):
            return "Unknown scene settings section '%s'." % section
        for key in config.get_section_keys(section):
            var known := false
            match section:
                "clouds": known = CLOUD_KEYS.has(key)
                "scene": known = SCENE_KEYS.has(key)
                "features": known = FEATURE_DEFAULTS.has(key)
                "effects": known = PARAMETER_SPECS.has(key) and key not in ["cloud_contrast", "cloud_density"]
            if not known:
                return "Unknown %s key '%s'." % [section, key]
    return ""

static func _normalization_error(message: String) -> Dictionary:
    return {"ok": false, "profile": {}, "error": message}

static func _read_error(message: String, code: int, legacy: bool = false) -> Dictionary:
    return {"ok": false, "profile": {}, "error": message, "error_code": code, "legacy": legacy}

static func _write_error(message: String, code: int) -> Dictionary:
    return {"ok": false, "error": message, "error_code": code}
