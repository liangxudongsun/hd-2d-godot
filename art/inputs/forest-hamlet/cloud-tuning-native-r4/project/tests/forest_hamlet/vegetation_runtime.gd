extends SceneTree
## Structural and binding checks; the existing close runtime retains full route
## regression, and the separate GPU run verifies the real lighting response.
const IDS := ["broadleaf_a","broadleaf_b","fir","grass","fern","reeds","flowers_white","flowers_pink","window_flowers","lily_pad"]
const OLD_PLANT_MODELS := ["broadleaf.glb","fir.glb","grass.glb","cottage.glb"]
var scene: Node3D
var checks: Array = []
var failures: Array = []
var output := "res://build/forest-hamlet/vegetation-runtime"
var discovered_sprites: Array[Sprite3D] = []
var forbidden_geometry: Array[String] = []
var loaded_models: Array[String] = []

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--forest-output="):
            output = arg.trim_prefix("--forest-output=")
    output = ProjectSettings.globalize_path(output)
    DirAccess.make_dir_recursive_absolute(output)
    call_deferred("run")

func check(condition: bool, label: String) -> void:
    checks.append({"label":label,"passed":condition})
    if not condition:
        failures.append(label)
        print("ASSERT_FAIL ",label)

func inspect_world(node: Node) -> void:
    if node is Sprite3D:
        discovered_sprites.append(node as Sprite3D)
    if node is MultiMeshInstance3D:
        forbidden_geometry.append(str(node.get_path())+": legacy instanced flower geometry")
    if not node.scene_file_path.is_empty():
        var file: String = node.scene_file_path.get_file()
        if node.scene_file_path.get_extension()=="glb":
            loaded_models.append(node.scene_file_path)
        if file in OLD_PLANT_MODELS:
            forbidden_geometry.append(str(node.get_path())+": old plant-bearing model "+file)
    if node is MeshInstance3D:
        var mesh: MeshInstance3D = node as MeshInstance3D
        if mesh.mesh != null:
            for surface in range(mesh.mesh.get_surface_count()):
                # Inspect original materials, before scene-local prop overrides
                # could obscure the identity of an imported foliage surface.
                var material: Material = mesh.mesh.surface_get_material(surface)
                if material == null:
                    continue
                var name: String = material.resource_name
                if name.begins_with("leaf_") or name in ["flower_white","flower_pink","flower_blue"]:
                    forbidden_geometry.append(str(node.get_path())+": live 3D plant surface "+name)
    for child in node.get_children():
        inspect_world(child)

func find_mask_pixel(mask: BitMap, visible: Rect2, opaque: bool) -> Vector2i:
    for y in range(int(visible.position.y),int(visible.end.y)):
        for x in range(int(visible.position.x),int(visible.end.x)):
            if mask.get_bitv(Vector2i(x,y))==opaque:
                return Vector2i(x,y)
    return Vector2i(-1,-1)

func pixel_world(sprite: Sprite3D, pixel: Vector2i) -> Vector3:
    var pivot: Vector2 = sprite.get_meta("pivot_px")
    var scale: Vector3 = sprite.global_basis.get_scale()
    var offset: Vector2 = Vector2(pixel)+Vector2(.5,.5)-pivot
    return sprite.global_position + scene.camera.global_basis.x.normalized()*offset.x*sprite.pixel_size*scale.x - scene.camera.global_basis.y.normalized()*offset.y*sprite.pixel_size*scale.y

func run() -> void:
    scene = load("res://scenes/forest_hamlet_close.tscn").instantiate()
    root.add_child(scene)
    for i in range(45):
        await physics_frame
    scene.world.set_vegetation_wind(0.0)
    scene.update_camera(true)
    inspect_world(scene.world)
    var counts: Dictionary = {}
    var registered: Dictionary = {}
    var bindings_valid := true
    var proportions_valid := true
    var cutouts_valid := true
    for sprite in scene.world.vegetation_sprites:
        var id: String = str(sprite.get_meta("asset_id",""))
        counts[id] = int(counts.get(id,0))+1
        registered[sprite.get_instance_id()] = true
        var surface: ShaderMaterial = sprite.material_override as ShaderMaterial
        if surface == null:
            bindings_valid = false
            continue
        var color: Texture2D = surface.get_shader_parameter("color_texture") as Texture2D
        var normal: Texture2D = surface.get_shader_parameter("normal_texture") as Texture2D
        bindings_valid = bindings_valid and color != null and normal != null
        if color != null and normal != null:
            bindings_valid = bindings_valid and color.get_size()==normal.get_size() and color.resource_path==str(sprite.get_meta("color_path")) and normal.resource_path==str(sprite.get_meta("normal_path")) and color.resource_path!=normal.resource_path
        bindings_valid = bindings_valid and surface.shader.resource_path=="res://shaders/forest_hamlet/vegetation.gdshader" and surface.get_shader_parameter("use_normals")==true
        proportions_valid = proportions_valid and sprite.pixel_size > 0.0 and is_equal_approx(sprite.scale.x,sprite.scale.y) and is_equal_approx(sprite.scale.x,sprite.scale.z)
        cutouts_valid = cutouts_valid and sprite.billboard==BaseMaterial3D.BILLBOARD_ENABLED and sprite.alpha_cut==SpriteBase3D.ALPHA_CUT_DISCARD and sprite.texture_filter==BaseMaterial3D.TEXTURE_FILTER_NEAREST
    check(forbidden_geometry.is_empty(),"no legacy plant GLB, flower MultiMesh or original 3D leaf surface is instantiated")
    check(scene.world.model_cache.has("cottage_without_plants") and not scene.world.model_cache.has("cottage"),"houses use the plant-free structural model")
    check(not scene.world.model_cache.has("broadleaf") and not scene.world.model_cache.has("fir") and not scene.world.model_cache.has("grass"),"old tree and grass GLBs remain outside runtime model cache")
    check(discovered_sprites.size()==scene.world.vegetation_sprites.size() and registered.size()==discovered_sprites.size(),"all live world plant Sprite3D instances are registered exactly once")
    var all_registered := true
    for sprite in discovered_sprites:
        all_registered = all_registered and registered.has(sprite.get_instance_id())
    check(all_registered,"no unregistered world sprite escapes plant validation")
    for id in IDS:
        check(int(counts.get(id,0))>0,"live color-plus-normal Sprite3D family: "+id)
    check(counts.size()==IDS.size(),"only the ten produced plant families are active")
    check(bindings_valid,"every plant binds its real matching color and normal textures to the dedicated shader")
    check(proportions_valid and cutouts_valid,"every plant uses uniform scaling, nearest-sampled cutout pixels and full billboard mode")
    var original_ground: Variant = scene.world.ground_material.get_shader_parameter("use_normals")
    var original_actor: Variant = scene.player.surface.get_shader_parameter("use_normals")
    scene.world.set_vegetation_normals(false)
    var disabled := true
    for sprite in scene.world.vegetation_sprites:
        disabled = disabled and (sprite.material_override as ShaderMaterial).get_shader_parameter("use_normals")==false
    check(disabled,"vegetation normal switch reaches every actual plant material")
    scene.world.set_vegetation_normals(true)
    var restored := true
    for sprite in scene.world.vegetation_sprites:
        restored = restored and (sprite.material_override as ShaderMaterial).get_shader_parameter("use_normals")==true
    check(restored,"vegetation normals restore across every plant family")
    check(scene.world.ground_material.get_shader_parameter("use_normals")==original_ground and scene.player.surface.get_shader_parameter("use_normals")==original_actor,"vegetation normal switch preserves terrain and original character materials")
    var occlusion: Dictionary = scene.occlusion.snapshot()
    check(occlusion.get("mode","")=="billboard_alpha_aware" and int(occlusion.get("sprite_count",0))>0 and int(occlusion.get("mesh_count",-1))==0,"close camera occlusion protects live Sprite3D trees without legacy mesh occluders")
    var tree: Sprite3D = scene.world.view_occluders[0] as Sprite3D
    var mask: BitMap = tree.get_meta("alpha_bitmap") as BitMap
    var visible: Rect2 = tree.get_meta("visible_rect_px")
    var solid_pixel: Vector2i = find_mask_pixel(mask,visible,true)
    var clear_pixel: Vector2i = find_mask_pixel(mask,visible,false)
    check(solid_pixel.x>=0 and clear_pixel.x>=0,"real tree cutout provides opaque pixels and transparent space inside its image bounds")
    if solid_pixel.x>=0 and clear_pixel.x>=0:
        var camera_origin: Vector3 = scene.camera.global_position
        var solid_hit: Vector3 = pixel_world(tree,solid_pixel)
        var clear_hit: Vector3 = pixel_world(tree,clear_pixel)
        check(scene.occlusion._sprite_blocks(tree,scene.camera,camera_origin+(solid_hit-camera_origin)*1.5,mask),"finite sight segment detects opaque pixels on actual camera-facing tree plane")
        check(not scene.occlusion._sprite_blocks(tree,scene.camera,camera_origin+(clear_hit-camera_origin)*1.5,mask),"transparent tree cutout space does not count as solid obstruction")
        check(not scene.occlusion._sprite_blocks(tree,scene.camera,camera_origin+(solid_hit-camera_origin)*.5,mask),"tree behind sight segment endpoint does not obscure the character")
    var framing: Dictionary = scene.framing_state()
    check(framing.pitch_degrees >= 13.9 and framing.pitch_degrees <= 14.1 and framing.silhouette_rect[3] >= .22 and framing.silhouette_rect[3] <= .24,"vegetation replacement preserves accepted near-camera framing")
    check(is_equal_approx(scene.player.sprite.pixel_size,.009) and scene.player.sprite.scale.is_equal_approx(Vector3.ONE),"original character size and aspect remain unchanged")
    var report: Dictionary = {"passed":failures.is_empty(),"checks":checks,"failures":failures,"species_counts":counts,"registered_sprites":registered.size(),"live_world_sprites":discovered_sprites.size(),"forbidden_geometry":forbidden_geometry,"loaded_models":loaded_models,"occlusion":occlusion,"framing":framing,"scope":"live scene structure, actual shader texture bindings and alpha-aware visibility; source PNG math, complete route and GPU appearance have separate reports"}
    var file: FileAccess = FileAccess.open(output.path_join("vegetation-runtime-report.json"),FileAccess.WRITE)
    if file == null:
        push_error("Unable to write vegetation-runtime-report.json")
        quit(3)
        return
    file.store_string(JSON.stringify(report,"  ")+"\n")
    print("VEGETATION_RUNTIME_DONE passed=",report.passed," checks=",checks.size()," sprites=",registered.size()," families=",counts.size())
    quit(0 if failures.is_empty() else 1)
