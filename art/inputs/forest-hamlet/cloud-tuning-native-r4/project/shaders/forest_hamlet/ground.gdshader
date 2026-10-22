shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

// Native 64px AW outputs cover 4m: one coherent 16-texel/m material grid.
// Sampling and relief use the same cell centres, so close views stay deliberate.
uniform sampler2D grass_tex : source_color, filter_nearest, repeat_enable;
uniform sampler2D earth_tex : source_color, filter_nearest, repeat_enable;
uniform sampler2D stone_tex : source_color, filter_nearest, repeat_enable;
uniform bool use_normals = true;
uniform float normal_strength : hint_range(0.0, 2.0) = 0.55;
uniform float texel_density = 16.0;
varying vec3 world_point;

float hash21(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float noise2(vec2 p) {
    vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(hash21(i),hash21(i+vec2(1,0)),f.x),mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)),f.x),f.y);
}
float box_distance(vec2 p, vec2 center, vec2 half_size) {
    vec2 q=abs(p-center)-half_size;
    return length(max(q,vec2(0)))+min(max(q.x,q.y),0.0);
}
float path_distance(vec2 p) {
    float horizontal=box_distance(p,vec2(0,1.8),vec2(18,1.05));
    float vertical=box_distance(p,vec2(0,-5.4),vec2(1.18,8.5));
    float left_door=box_distance(p,vec2(-5.6,.0),vec2(.84,2.0));
    float right_door=box_distance(p,vec2(6.6,-.5),vec2(.82,3.3));
    return min(min(horizontal,vertical),min(left_door,right_door));
}
void vertex() { world_point=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz; }
void fragment() {
    vec2 p=(floor(world_point.xz*texel_density)+vec2(.5))/texel_density;
    float edge_noise=(noise2(p*1.6)-.5)*.34+(noise2(p*4.0)-.5)*.10;
    float blend=1.0-smoothstep(-.10,.14,path_distance(p)+edge_noise);
    float path=floor(blend*3.0+.5)/3.0;
    vec2 uv=p/4.0;
    vec3 grass=texture(grass_tex,uv).rgb;
    vec3 earth=texture(earth_tex,uv).rgb;
    grass=mix(vec3(.045,.10,.025),grass*vec3(.78,.88,.70),.22);
    earth=mix(vec3(.30,.19,.085),earth*vec3(.94,.95,.91),.50);
    // Broad, stepped colour clusters replace continuously varying speckle.
    float large_variation=.88+floor(noise2(p*.38)*4.0)*.065;
    vec3 color=mix(grass,earth,path)*large_variation;
    float shore=abs(length((p-vec2(-8.0,6.3))/vec2(5.0,3.0))-1.0);
    float bank=floor((1.0-smoothstep(.04,.16,shore))*3.0+.5)/3.0;
    color=mix(color,color*vec3(.72,.78,.62),bank);
    ALBEDO=color;
    ROUGHNESS=mix(.96,.91,path);
    SPECULAR=.12;
    // Authored relief is independent of albedo and constant inside pixel cells.
    vec2 relief=vec2(noise2(p*3.0),noise2(p*3.0+vec2(31.7,17.2)));
    relief=floor(relief*3.0)/1.5-1.0;
    float amplitude=mix(.11,.065,path)*normal_strength;
    NORMAL_MAP=use_normals ? normalize(vec3(relief*amplitude,1.0))*.5+.5 : vec3(.5,.5,1.0);
}
