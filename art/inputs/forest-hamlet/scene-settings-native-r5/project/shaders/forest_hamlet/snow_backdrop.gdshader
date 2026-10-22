shader_type spatial;
render_mode unshaded, cull_disabled, fog_disabled;

// The approved painted color is untouched. This is explicit dynamic normal
// relighting of a matte plate, not recovered physical albedo or a fake 3D mesh.
uniform sampler2D color_texture : source_color, filter_linear, repeat_disable;
uniform sampler2D normal_texture : hint_normal, filter_linear, repeat_disable;
uniform sampler2D region_texture : filter_linear, repeat_disable;
uniform vec2 source_uv_scale = vec2(1.0, 1.3);
uniform vec2 source_uv_offset = vec2(0.0, 0.23);
uniform vec3 sun_direction_local = vec3(-0.4, 0.67, 0.63);
uniform vec3 sun_color : source_color = vec3(1.0, 0.95, 0.86);
uniform vec3 preset_tint : source_color = vec3(1.0);
uniform float brightness : hint_range(0.25, 2.0) = 0.93;
uniform bool use_normals = true;
uniform float normal_strength : hint_range(0.0, 1.5) = 0.8;
uniform float relight_strength : hint_range(0.0, 1.0) = 0.72;

void fragment() {
    vec2 source_uv = clamp((UV - vec2(0.5)) * source_uv_scale + vec2(0.5) + source_uv_offset, vec2(0.0001), vec2(0.9999));
    vec3 original = texture(color_texture, source_uv).rgb;
    float confidence = texture(region_texture, source_uv).r;
    // Reconstruct positive Z so BC5/RGTC normal texture import also works.
    vec2 tangent = (texture(normal_texture, source_uv).rg * 2.0 - 1.0) * normal_strength;
    vec3 normal = normalize(vec3(tangent, sqrt(max(0.0001, 1.0 - dot(tangent, tangent)))));
    vec3 light_direction = normalize(sun_direction_local);
    float flat_response = max(dot(vec3(0.0, 0.0, 1.0), light_direction), 0.0);
    float ridge_response = max(dot(normal, light_direction), 0.0);
    float response = clamp(1.0 + (ridge_response - flat_response) * relight_strength, 0.65, 1.3);
    // Region mask leaves the sky and soft mist perfectly flat/unbumped.
    float normal_weight = use_normals ? smoothstep(0.005, 0.6, confidence) : 0.0;
    vec3 light_tint = mix(vec3(1.0), sun_color, confidence * 0.10);
    ALBEDO = original * mix(1.0, response, normal_weight) * light_tint * preset_tint * brightness;
    ROUGHNESS = 1.0;
}
