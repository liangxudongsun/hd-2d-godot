shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform sampler2D color_texture : source_color, filter_nearest, repeat_disable;
uniform sampler2D normal_texture : hint_normal, filter_nearest, repeat_disable;
uniform bool use_normals = true;
uniform float normal_strength : hint_range(0.0, 2.0) = 1.0;
uniform float wind_strength = 0.06;
uniform float wind_clock = 0.0;
uniform float pivot_v = 1.0;
instance uniform float wind_phase = 0.0;
instance uniform float wind_weight = 1.0;

void vertex() {
    // The main camera determines the same cutout plane in the visible and
    // shadow passes. Original image aspect and the bottom pivot are preserved.
    vec3 model_scale = vec3(length(MODEL_MATRIX[0].xyz), length(MODEL_MATRIX[1].xyz), length(MODEL_MATRIX[2].xyz));
    mat3 view_basis = mat3(normalize(MAIN_CAM_INV_VIEW_MATRIX[0].xyz), normalize(MAIN_CAM_INV_VIEW_MATRIX[1].xyz), normalize(MAIN_CAM_INV_VIEW_MATRIX[2].xyz));
    mat4 facing = mat4(vec4(view_basis[0] * model_scale.x, 0.0), vec4(view_basis[1] * model_scale.y, 0.0), vec4(view_basis[2] * model_scale.z, 0.0), MODEL_MATRIX[3]);
    MODELVIEW_MATRIX = VIEW_MATRIX * facing;
    MODELVIEW_NORMAL_MATRIX = transpose(inverse(mat3(MODELVIEW_MATRIX)));
    // A shear pinned exactly at the supplied root pixel moves color and normal
    // together. UV coordinates are never warped or sampled on different grids.
    float sway = sin(wind_clock * 1.25 + wind_phase) * wind_strength * wind_weight;
    VERTEX.x += sway * (pivot_v - UV.y);
}

void fragment() {
    vec4 color = texture(color_texture, UV);
    if (color.a < 0.5) {
        discard;
    }
    ALBEDO = color.rgb * COLOR.rgb;
    // Godot may store normal textures as RGTC/BC5. Reconstruct positive Z
    // from RG before strength normalization instead of reading a missing B.
    vec2 normal_xy = texture(normal_texture, UV).rg * 2.0 - 1.0;
    vec3 mapped = vec3(normal_xy, sqrt(max(0.000001, 1.0 - dot(normal_xy, normal_xy))));
    mapped.xy *= normal_strength;
    mapped = normalize(mapped);
    NORMAL_MAP = use_normals ? mapped * 0.5 + 0.5 : vec3(0.5, 0.5, 1.0);
    NORMAL_MAP_DEPTH = 1.0;
    ROUGHNESS = 0.92;
    SPECULAR = 0.12;
    METALLIC = 0.0;
    // Leave ALPHA at the engine's default (1 - instance transparency). Ordinary
    // plants use opaque depth and cutout shadows; close-camera fades remain
    // compatible with GeometryInstance3D.transparency and keep real shadows.
}
