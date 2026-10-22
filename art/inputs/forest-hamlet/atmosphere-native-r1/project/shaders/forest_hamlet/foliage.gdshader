shader_type spatial;
render_mode diffuse_burley, cull_disabled;
uniform sampler2D leaf_texture : source_color, filter_nearest, repeat_enable;
uniform float wind_strength : hint_range(0.0,0.3) = 0.06;
uniform float texel_density = 16.0;
varying vec3 material_point;
void vertex() {
    // Keep texture cells attached to each tree while the crown sways.
    material_point=VERTEX;
    float phase=dot(MODEL_MATRIX[3].xz,vec2(.63,.81));
    float weight=clamp(VERTEX.y*.65+.3,0.0,1.0);
    VERTEX.x+=sin(TIME*1.15+phase+VERTEX.y*.8)*wind_strength*weight;
    VERTEX.z+=cos(TIME*.8+phase)*wind_strength*.4*weight;
}
void fragment() {
    vec3 p=(floor(material_point*texel_density)+vec3(.5))/texel_density;
    vec2 uv=vec2(p.x+p.y*.5,p.z+p.y*.75)/4.0;
    vec3 grain=texture(leaf_texture,uv).rgb;
    vec3 leaf_color=COLOR.rgb;
    if(length(leaf_color)>1.65) leaf_color=vec3(.32,.46,.17);
    float clusters=floor(clamp(grain.g*3.5,0.0,.999)*4.0)/3.0;
    ALBEDO=leaf_color*vec3(.41,.48,.37)*(.70+clusters*.70);
    ROUGHNESS=.96;
    SPECULAR=.08;
    BACKLIGHT=ALBEDO*.07;
}
