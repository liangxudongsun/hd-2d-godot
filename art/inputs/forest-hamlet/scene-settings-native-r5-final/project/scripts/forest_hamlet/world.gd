extends Node3D
## Scene assembly: structural props use versioned Blender geometry; all plants
## are camera-facing color/normal cutouts produced through the AW workflow.

const TEXTURE_ROOT := "res://assets/forest-hamlet/textures/"
const MODEL_ROOT := "res://assets/forest-hamlet/models/"
const SEED := 20261022
var spawn := Vector3(0,0.15,2.5)
var bounds := Rect2(-18,-13,36,26)
var ground_material: ShaderMaterial
var water_material: ShaderMaterial
var foliage_material: ShaderMaterial
var lamps: Array[OmniLight3D] = []
var lamp_glass_materials: Array[StandardMaterial3D] = []
var asset_instances := 0
var terrain_triangles := 0
var rng := RandomNumberGenerator.new()
var model_cache: Dictionary = {}
var model_pixel_materials: Dictionary = {}
var view_occluders: Array[Node3D] = []
var vegetation := preload("res://scripts/forest_hamlet/vegetation.gd").new()
var vegetation_sprites: Array[Sprite3D] = []

func _ready() -> void:
    rng.seed=SEED
    _materials()
    _terrain()
    _water()
    _village()
    _forest()
    _shore()
    _details()
    _boundaries()

func _materials() -> void:
    ground_material=ShaderMaterial.new()
    ground_material.shader=load("res://shaders/forest_hamlet/ground.gdshader")
    for pair in [["grass_tex","grass"],["earth_tex","earth"],["stone_tex","stone"]]:
        ground_material.set_shader_parameter(pair[0],load(TEXTURE_ROOT+pair[1]+".png"))
    water_material=ShaderMaterial.new()
    water_material.shader=load("res://shaders/forest_hamlet/water.gdshader")
    vegetation.configure()
    foliage_material = vegetation.material("broadleaf_a")

func _process(delta: float) -> void:
    vegetation.tick(delta)

func set_vegetation_normals(enabled: bool) -> void:
    vegetation.set_normals(enabled)

func set_vegetation_wind(strength: float) -> void:
    vegetation.set_wind_strength(strength)

func _plant(id: String, p: Vector3, uniform_scale := 1.0, wind_phase := 0.0) -> Sprite3D:
    var sprite: Sprite3D = vegetation.create(id, uniform_scale, wind_phase)
    sprite.name = id.capitalize().replace(" ", "") + str(asset_instances)
    sprite.position = p
    add_child(sprite)
    vegetation_sprites.append(sprite)
    asset_instances += 1
    return sprite

func _point(surface: SurfaceTool, p: Vector3) -> void:
    surface.set_normal(Vector3.UP)
    surface.set_tangent(Plane(Vector3.RIGHT,1.0))
    surface.set_uv(Vector2(p.x,p.z)/4.0)
    surface.add_vertex(p)

func _pond_value(x: float,z: float) -> float:
    return Vector2((x+8.0)/5.0,(z-6.3)/3.0).length()

func _terrain() -> void:
    var st:=SurfaceTool.new()
    st.begin(Mesh.PRIMITIVE_TRIANGLES)
    var step:=0.5
    for zi in range(104):
        for xi in range(100):
            var x: float=-25.0+xi*step
            var z: float=-32.0+zi*step
            if _pond_value(x+step*.5,z+step*.5)<.96: continue
            var a:=Vector3(x,0,z)
            var b:=a+Vector3(step,0,0)
            var c:=a+Vector3(step,0,step)
            var d:=a+Vector3(0,0,step)
            for v in [a,b,c,a,c,d]: _point(st,v)
            terrain_triangles+=2
    st.set_material(ground_material)
    var mesh:=st.commit()
    var floor_mesh:=MeshInstance3D.new()
    floor_mesh.name="MeadowAndEarthPaths"
    floor_mesh.mesh=mesh
    add_child(floor_mesh)
    var body:=StaticBody3D.new()
    body.name="WalkableGroundWithPondOpening"
    var shape:=CollisionShape3D.new()
    shape.shape=mesh.create_trimesh_shape()
    body.add_child(shape)
    add_child(body)
    # Visual-only outskirts cover the follow camera's corner rays. Preserve the
    # original collision mesh, playable bounds and the real pond opening.
    var skirt := SurfaceTool.new()
    skirt.begin(Mesh.PRIMITIVE_TRIANGLES)
    for area in [Rect2(-80,-80,55,160),Rect2(25,-80,55,160),Rect2(-25,-80,50,48),Rect2(-25,20,50,60)]:
        var a := Vector3(area.position.x,0,area.position.y)
        var b := Vector3(area.end.x,0,area.position.y)
        var c := Vector3(area.end.x,0,area.end.y)
        var d := Vector3(area.position.x,0,area.end.y)
        for v in [a,b,c,a,c,d]:
            _point(skirt,v)
        terrain_triangles += 2
    skirt.set_material(ground_material)
    var outskirts := MeshInstance3D.new()
    outskirts.name = "CameraVisibleMeadowOutskirts"
    outskirts.mesh = skirt.commit()
    add_child(outskirts)

func _water() -> void:
    var st:=SurfaceTool.new()
    st.begin(Mesh.PRIMITIVE_TRIANGLES)
    var center:=Vector3(-8,-.12,6.3)
    for i in range(96):
        var a: float=TAU*float(i)/96.0
        var b: float=TAU*float(i+1)/96.0
        for v in [center,center+Vector3(cos(a)*4.98,0,sin(a)*2.98),center+Vector3(cos(b)*4.98,0,sin(b)*2.98)]:
            _point(st,v)
    st.set_material(water_material)
    var water:=MeshInstance3D.new()
    water.name="PondSurface"
    water.mesh=st.commit()
    water.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    add_child(water)
    # The static pond perimeter provides a true collision boundary.
    for i in range(36):
        var a: float=TAU*float(i)/36.0
        var p:=center+Vector3(cos(a)*4.9,.30,sin(a)*2.95)
        var block:=_collision("PondRim",p,Vector3(.89,.65,.61))
        block.rotation.y=-a

func _instance(id: String,p: Vector3,scale_value:=Vector3.ONE,yaw:=0.0) -> Node3D:
    assert(id in ["cottage_without_plants", "fence", "rock", "lamp", "bench", "sign"], "Only structural props may load GLB resources")
    if not model_cache.has(id): model_cache[id]=load(MODEL_ROOT+id+".glb")
    var packed: PackedScene=model_cache[id]
    var instance:=packed.instantiate() as Node3D
    instance.name=id.capitalize()+str(asset_instances)
    instance.position=p
    instance.scale=scale_value
    instance.rotation.y=yaw
    add_child(instance)
    _model_materials(instance)
    asset_instances+=1
    return instance

func _model_materials(node: Node) -> void:
    if node is MeshInstance3D:
        var mi:=node as MeshInstance3D
        for i in range(mi.mesh.get_surface_count()):
            var material:=mi.get_active_material(i)
            if material==null: continue
            assert(not material.resource_name.begins_with("leaf_") and material.resource_name not in ["flower_white", "flower_pink", "flower_blue"], "Structural GLB still contains plant material")
            if material is StandardMaterial3D:
                material.texture_filter=BaseMaterial3D.TEXTURE_FILTER_NEAREST
                if material.albedo_texture != null:
                    # Every model uses 64px over 4m, including tiny roof courses.
                    # Object UVs otherwise squeeze a full texture onto each plank.
                    var key: String = material.resource_name + "@" + material.albedo_texture.resource_path
                    if not model_pixel_materials.has(key):
                        var pixel := ShaderMaterial.new()
                        pixel.shader = load("res://shaders/forest_hamlet/props.gdshader")
                        pixel.set_shader_parameter("surface_texture",material.albedo_texture)
                        var tone := Color(.50,.32,.18)
                        var weight := .58
                        if material.resource_name == "stone":
                            tone = Color(.48,.51,.47)
                            weight = .35
                        elif material.resource_name == "roof":
                            tone = Color(.62,.40,.19)
                            weight = .62
                        elif material.resource_name == "trunk":
                            tone = Color(.33,.23,.14)
                            weight = .45
                        pixel.set_shader_parameter("base_tone",tone)
                        pixel.set_shader_parameter("texture_weight",weight)
                        model_pixel_materials[key] = pixel
                    mi.set_surface_override_material(i,model_pixel_materials[key])
                if material.resource_name=="window_glow" and material not in lamp_glass_materials:
                    lamp_glass_materials.append(material)
    for child in node.get_children(): _model_materials(child)

func _collision(id: String,p: Vector3,size: Vector3) -> StaticBody3D:
    var body:=StaticBody3D.new()
    body.name=id
    body.position=p
    var collision:=CollisionShape3D.new()
    var shape:=BoxShape3D.new()
    shape.size=size
    collision.shape=shape
    body.add_child(collision)
    add_child(body)
    return body

func _village() -> void:
    for data in [[Vector3(-5,0,-3),1.0],[Vector3(7,0,-6),.86],[Vector3(-12,0,-5),.72]]:
        var p: Vector3=data[0]
        var s: float=data[1]
        _instance("cottage_without_plants",p,Vector3.ONE*s)
        for window_x in [-1.91, 1.38]:
            _plant("window_flowers", p + Vector3(window_x, 1.42, 2.54) * s, s, window_x)
        _collision("HouseSolid",p+Vector3(0,1.6*s,0),Vector3(5.5,3.2,4.3)*s)
    for data in [[Vector3(-8.8,0,-.45),0.0],[Vector3(-2.2,0,-.45),0.0],[Vector3(4.7,0,-3.4),0.0],[Vector3(9.4,0,-3.4),0.0],[Vector3(-12.5,0,.0),0.0],[Vector3(11.3,0,-5.0),PI*.5]]:
        _instance("fence",data[0],Vector3.ONE,data[1])
        var c:=_collision("FenceSolid",data[0]+Vector3.UP*.65,Vector3(2.12,1.3,.2))
        c.rotation.y=data[1]
    for p in [Vector3(3.3,0,3.6),Vector3(-1.9,0,-4.0)]:
        _instance("lamp",p)
        _collision("LampPost",p+Vector3.UP,Vector3(.32,2.0,.32))
        var light:=OmniLight3D.new()
        light.position=p+Vector3(0,2.9,0)
        light.light_color=Color(1,.69,.34)
        light.light_energy=.45
        light.omni_range=6.0
        light.omni_attenuation=1.3
        light.shadow_enabled=true
        light.shadow_bias=.04
        add_child(light)
        lamps.append(light)
    _instance("bench",Vector3(3.7,0,5.2),Vector3.ONE,PI)
    _collision("BenchSolid",Vector3(3.7,.65,5.2),Vector3(2.0,1.3,.9))
    _instance("sign",Vector3(1.9,0,3.5),Vector3.ONE)

func _tree(p: Vector3,s: float,id: String="broadleaf") -> void:
    var plant_id := id if id == "fir" else ("broadleaf_a" if asset_instances % 2 == 0 else "broadleaf_b")
    var tree := _plant(plant_id, p, s, rng.randf_range(-PI, PI))
    view_occluders.append(tree)
    _collision("TreeTrunk",p+Vector3.UP*(1.2*s),Vector3(.52,2.4,.52)*s)

func _forest() -> void:
    # Multiple depths and varied crowns create parallax through real perspective.
    for row in range(4):
        for column in range(13):
            var x: float=-21+column*3.4+rng.randf_range(-.5,.5)
            var z: float=-13-row*3.1+rng.randf_range(-.5,.5)
            if absf(x)<2.4 and row<2: continue
            _tree(Vector3(x,0,z),rng.randf_range(.86,1.26),"fir" if (row+column)%5<3 else "broadleaf")
    for side in [-1.0,1.0]:
        for i in range(7):
            var x: float=side*(17+rng.randf_range(-.5,1.4))
            var z: float=-9+i*3.0+rng.randf_range(-.5,.5)
            _tree(Vector3(x,0,z),rng.randf_range(.8,1.15),"fir" if i%3==0 else "broadleaf")
    for data in [[Vector3(-15.5,0,4.4),.70],[Vector3(11.8,0,5.6),.82],[Vector3(14.3,0,8.6),.90],[Vector3(-15,0,-1.8),.64]]:
        _tree(data[0],data[1])

func _shore() -> void:
    for i in range(56):
        var a: float=TAU*float(i)/56.0
        var p:=Vector3(-8+cos(a)*5.08,-.08,6.3+sin(a)*3.07)
        _instance("rock",p,Vector3(rng.randf_range(.67,.9),rng.randf_range(.65,1.08),.76),-a)
    for i in range(11):
        var a: float=rng.randf_range(.2,TAU)
        var p:=Vector3(-8+cos(a)*4.55,-.06,6.3+sin(a)*2.62)
        _plant("reeds", p, 1.0, a)
    for p in [Vector3(-10,-.098,6.9),Vector3(-9.6,-.098,7.3),Vector3(-5.2,-.098,6.1),Vector3(-10.5,-.098,5.5)]:
        _plant("lily_pad", p)

func _flower_bed(center: Vector3, id: String, count: int) -> void:
    # Each painted cutout already contains flowers and their leaves. Cluster
    # roots share ground height instead of floating individual 3D spheres.
    var clusters := maxi(2, ceili(float(count) / 4.0))
    for i in range(clusters):
        var x := (float(i) - float(clusters - 1) * 0.5) * 0.42
        var p := center + Vector3(x + rng.randf_range(-.07, .07), 0.0, rng.randf_range(-.18, .18))
        _plant(id, p, rng.randf_range(.86, 1.12), rng.randf_range(-PI, PI))
    for i in range(2):
        var p := center + Vector3(rng.randf_range(-.7, .7), 0.0, rng.randf_range(-.28, .28))
        _plant("fern" if i == 0 else "grass", p, rng.randf_range(.7, 1.0), rng.randf_range(-PI, PI))

func _details() -> void:
    for p in [Vector3(-7.1,0,-.7),Vector3(-3.1,0,-.7),Vector3(5.4,0,-3.5),Vector3(8.7,0,-3.5),Vector3(5.2,0,5.4),Vector3(-13.7,0,.1)]:
        _flower_bed(p,"flowers_white",12)
        _flower_bed(p+Vector3(.1,0,.2),"flowers_pink",8)
    for i in range(125):
        var x:=rng.randf_range(-16,16)
        var z:=rng.randf_range(-11,10)
        if absf(z-1.8)<1.45 or absf(x)<1.8 or _pond_value(x,z)<1.13: continue
        if (x>-8 and x<-2 and z>-5.5 and z<.0) or (x>4 and x<10 and z>-8.5 and z<-3): continue
        _plant("fern" if i % 5 == 0 else "grass", Vector3(x,0,z), rng.randf_range(.7,1.4), rng.randf_range(-PI,PI))
    for p in [Vector3(2.4,0,-7),Vector3(12.8,0,-2),Vector3(-14.1,0,2.8),Vector3(8.5,0,7.6)]:
        _instance("rock",p,Vector3.ONE*.85,rng.randf_range(-PI,PI))

func _boundaries() -> void:
    for p in [Vector3(-17.7,1,0),Vector3(17.7,1,0)]:
        _collision("MapSide",p,Vector3(.3,2,28))
    for p in [Vector3(0,1,-12.7),Vector3(0,1,12.7)]:
        _collision("MapEnd",p,Vector3(36,2,.3))
