shader_type spatial;
render_mode unshaded, cull_disabled;

// Only the 30% native sun branch sees this shadow-only geometry. Alpha hash
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
// Negative: natural density. Nonnegative: exact requested cloud attenuation
// for real shadow-map probes using this same shader and the same geometry.
uniform float uniform_attenuation : hint_range(-1.0, 0.30) = -1.0;

varying vec2 cloud_world_xz;

void vertex() {
    cloud_world_xz = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
}

void fragment() {
    vec2 mask_uv = (cloud_world_xz + wind_velocity * cloud_clock) / pattern_span_m + pattern_phase;
    float density = texture(cloud_mask, mask_uv).r;
    // Smooth clear -> thin edge, then thin (10%) -> dense core (30%).
    float edge = smoothstep(mask_cutoff - mask_edge_width, mask_cutoff, density);
    float body = smoothstep(mask_cutoff, mask_cutoff + mask_body_width, density);
    float attenuation = edge * mix(0.10, 0.30, body);
    if (uniform_attenuation >= 0.0) {
        attenuation = clamp(uniform_attenuation, 0.0, 0.30);
    }
    ALBEDO = vec3(1.0);
    ALPHA = clamp(attenuation / 0.30, 0.0, 1.0);
    // This selects the native alpha-hash shadow path. Scale controls the
    // dither pattern, never the requested attenuation or light-energy split.
    ALPHA_HASH_SCALE = alpha_hash_scale;
}
