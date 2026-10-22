shader_type spatial;
render_mode unshaded, cull_disabled;

// A real horizontal cutout participates in the native sun shadow map. The
// owning MeshInstance3D is SHADOWS_ONLY, so this never paints a screen overlay.
uniform sampler2D cloud_mask : filter_linear, repeat_enable;
uniform float cloud_clock = 0.0;
uniform vec2 wind_velocity = vec2(0.32, 0.13);
uniform float pattern_span_m = 96.0;
uniform float mask_cutoff : hint_range(0.0, 1.0) = 0.515;
uniform vec2 pattern_phase = vec2(0.173, 0.319);

varying vec2 cloud_world_xz;

void vertex() {
    // The same world coordinates are used for every directional shadow split.
    cloud_world_xz = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
}

void fragment() {
    vec2 mask_uv = (cloud_world_xz + wind_velocity * cloud_clock) / pattern_span_m + pattern_phase;
    float coverage = texture(cloud_mask, mask_uv).r;
    // Deliberate binary cutout: writes native opaque shadow depth. PCSS/PCF
    // supplies the penumbra. Avoid alpha blending, which would lose shadows.
    if (coverage < mask_cutoff) {
        discard;
    }
    ALBEDO = vec3(1.0);
}
