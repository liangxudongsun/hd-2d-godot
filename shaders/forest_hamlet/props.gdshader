shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
uniform sampler2D surface_texture : source_color, filter_nearest, repeat_enable;
uniform vec4 base_tone : source_color = vec4(.50,.32,.18,1.0);
uniform float texture_weight : hint_range(0.0,1.0) = .58;
uniform float texel_density = 16.0;
varying vec3 world_point;
varying vec3 world_normal;
void vertex() {
    world_point=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
    world_normal=normalize(MODEL_NORMAL_MATRIX*NORMAL);
}
void fragment() {
    vec3 p=(floor(world_point*texel_density)+vec3(.5))/texel_density;
    vec3 weights=pow(abs(normalize(world_normal)),vec3(16.0));
    weights/=max(dot(weights,vec3(1.0)),.0001);
    vec3 sample_x=texture(surface_texture,p.zy/4.0).rgb;
    vec3 sample_y=texture(surface_texture,p.xz/4.0).rgb;
    vec3 sample_z=texture(surface_texture,p.xy/4.0).rgb;
    vec3 surface=sample_x*weights.x+sample_y*weights.y+sample_z*weights.z;
    // A material-specific base keeps stone and timber colour masses readable;
    // the limited-colour AW texels remain visible without photographic contrast.
    ALBEDO=mix(base_tone.rgb,surface,texture_weight);
    ROUGHNESS=.93;
    SPECULAR=.12;
}
