shader_type spatial;
render_mode unshaded, cull_disabled;

// Only the cloud native sun branch sees this shadow-only geometry. Alpha hash
// writes dithered shadow depth: ALPHA is blocked coverage of that branch,
// not a full-screen tint or the total sunlight transmission.
uniform sampler2D cloud_mask : filter_linear, repeat_enable;
uniform float cloud_clock = 0.0;
uniform vec2 wind_velocity = vec2(0.32, 0.13);
uniform float pattern_span_m = 96.0;
uniform float mask_cutoff : hint_range(0.0, 1.0) = 0.515;
uniform float mask_edge_width : hint_range(0.01, 0.30) = 0.12;
uniform float mask_body_width : hint_range(0.01, 0.40) = 0.18;
uniform vec2 pattern_phase = vec2(0.65, 0.0);
uniform float alpha_hash_scale : hint_range(0.1, 2.0) = 1.0;
// User controls: default (0.30, 0.5) preserves the previous 10-30% transfer.
// Contrast is maximum attenuation; density changes the smooth field coverage.
uniform float contrast_strength : hint_range(0.0, 0.80) = 0.30;
// Controller keeps this in sync with the actual native light energy split.
uniform float cloud_branch_ratio : hint_range(0.0, 0.80) = 0.30;
uniform float cloud_density : hint_range(0.0, 1.0) = 0.5;
// Negative: natural density. Nonnegative: exact requested cloud attenuation
// for real shadow-map probes using this same shader and the same geometry.
// Calibration bypasses both user controls and uses its original 30% branch.
uniform float uniform_attenuation : hint_range(-1.0, 0.30) = -1.0;

varying vec2 cloud_world_xz;

void vertex() {
    cloud_world_xz = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
}

void fragment() {
    vec2 mask_uv = (cloud_world_xz + wind_velocity * cloud_clock) / pattern_span_m + pattern_phase;
    float raw_density = texture(cloud_mask, mask_uv).r;
    float density = clamp(raw_density + 2.0 * (cloud_density - 0.5), 0.0, 1.0);
    // Smooth clear -> thin edge, then thin -> dense core. Default remains
    // 10-30%; thin cloud is one third of the selected maximum attenuation.
    // Zero density clears all clouds; full density fills the field.
    float edge = smoothstep(mask_cutoff - mask_edge_width, mask_cutoff, density);
    float body = smoothstep(mask_cutoff, mask_cutoff + mask_body_width, density);
    float attenuation = edge * mix(0.10, 0.30, body) * (contrast_strength / 0.30);
    if (cloud_density <= 0.0) {
        attenuation = 0.0;
    } else if (cloud_density >= 1.0) {
        attenuation = contrast_strength;
    }
    if (uniform_attenuation >= 0.0) {
        attenuation = clamp(uniform_attenuation, 0.0, 0.30);
    }
    ALBEDO = vec3(1.0);
    // At zero contrast the cloud light has zero energy and casts no cloud
    // attenuation; the guarded divide avoids undefined 0/0 shader values.
    ALPHA = cloud_branch_ratio > 0.0 ? clamp(attenuation / cloud_branch_ratio, 0.0, 1.0) : 0.0;
    // This selects the native alpha-hash shadow path. Scale controls the
    // dither pattern, never the requested attenuation or light-energy split.
    ALPHA_HASH_SCALE = alpha_hash_scale;
}
