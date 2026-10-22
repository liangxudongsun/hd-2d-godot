extends RefCounted
## Close-camera character protection. Sprite tests intersect the rendered
## camera-facing plane and its alpha silhouette, including the current wind
## shear; transparent image margins and canopy holes are not solid boxes.
const ENTER_MARGIN := 0.08
const LEAVE_MARGIN := 0.20
const FADE_SPEED := 6.0
const SAMPLE_HEIGHTS := [0.12, 1.0, 1.95]
const SAMPLE_SIDES := [-0.52, 0.0, 0.52]
var _trees: Array[Dictionary] = []
var _mask_cache: Dictionary = {}
var _mesh_count := 0
var _sprite_count := 0
var _geometry_count := 0

func configure(roots: Array) -> void:
    for entry in _trees:
        for geometry in entry.geometry:
            if is_instance_valid(geometry):
                geometry.transparency = 0.0
    _trees.clear()
    _mask_cache.clear()
    _mesh_count = 0
    _sprite_count = 0
    _geometry_count = 0
    for root in roots:
        if not is_instance_valid(root) or not root is Node3D:
            continue
        var geometry: Array[GeometryInstance3D] = []
        _collect_geometry(root, geometry)
        if geometry.is_empty():
            continue
        var sprites: Array[Dictionary] = []
        var meshes: Array[Dictionary] = []
        for visual in geometry:
            visual.transparency = 0.0
            if visual is Sprite3D:
                var sprite := visual as Sprite3D
                if sprite.texture == null:
                    continue
                var bitmap := _source_mask(sprite)
                var scale: Vector3 = sprite.global_basis.get_scale()
                var pixels_per_meter := 1.0 / maxf(0.00001, sprite.pixel_size * minf(scale.x, scale.y))
                var enter_radius := ceili(ENTER_MARGIN * pixels_per_meter)
                var leave_radius := ceili(LEAVE_MARGIN * pixels_per_meter)
                sprites.append({"sprite":sprite, "enter_mask":_expanded_mask(sprite, bitmap, enter_radius), "leave_mask":_expanded_mask(sprite, bitmap, leave_radius)})
                _sprite_count += 1
            elif visual is MeshInstance3D:
                var mesh := visual as MeshInstance3D
                if mesh.mesh != null:
                    meshes.append({"mesh":mesh, "bounds":mesh.global_transform * mesh.get_aabb()})
                    _mesh_count += 1
        _trees.append({"name":str(root.name), "geometry":geometry, "sprites":sprites, "meshes":meshes, "occluding":false, "transparency":0.0})
        _geometry_count += geometry.size()

func _collect_geometry(node: Node, geometry: Array[GeometryInstance3D]) -> void:
    if node is Sprite3D or node is MeshInstance3D:
        geometry.append(node as GeometryInstance3D)
    for child in node.get_children():
        _collect_geometry(child, geometry)

func _source_mask(sprite: Sprite3D) -> BitMap:
    if sprite.has_meta("alpha_bitmap"):
        return sprite.get_meta("alpha_bitmap") as BitMap
    var source := sprite.texture.get_image()
    if source.is_compressed():
        var error := source.decompress()
        assert(error == OK, "Unable to inspect sprite alpha for occlusion")
    var bitmap := BitMap.new()
    bitmap.create_from_image_alpha(source, 0.5)
    return bitmap

func _expanded_mask(sprite: Sprite3D, source: BitMap, radius: int) -> BitMap:
    var key := str(sprite.texture.get_instance_id()) + ":" + str(radius)
    if not _mask_cache.has(key):
        var expanded := source.duplicate() as BitMap
        expanded.grow_mask(radius, Rect2i(Vector2i.ZERO, expanded.get_size()))
        _mask_cache[key] = expanded
    return _mask_cache[key] as BitMap

func _pivot(sprite: Sprite3D) -> Vector2:
    if sprite.has_meta("pivot_px"):
        return sprite.get_meta("pivot_px") as Vector2
    var size := sprite.texture.get_size()
    return Vector2(size.x * 0.5 - sprite.offset.x, size.y * 0.5 + sprite.offset.y)

func _wind_sway(sprite: Sprite3D) -> float:
    var surface := sprite.material_override as ShaderMaterial
    if surface == null or not sprite.has_meta("wind_weight"):
        return 0.0
    var strength := float(surface.get_shader_parameter("wind_strength"))
    var clock := float(surface.get_shader_parameter("wind_clock"))
    var phase := float(sprite.get_meta("wind_phase", 0.0))
    var weight := float(sprite.get_meta("wind_weight", 1.0))
    return sin(clock * 1.25 + phase) * strength * weight

func billboard_bounds(sprite: Sprite3D, camera: Camera3D) -> AABB:
    var canvas := sprite.texture.get_size()
    var visible := Rect2(Vector2.ZERO, canvas)
    if sprite.has_meta("visible_rect_px"):
        visible = sprite.get_meta("visible_rect_px") as Rect2
    var pivot := _pivot(sprite)
    var scale: Vector3 = sprite.global_basis.get_scale()
    var right := camera.global_basis.x.normalized()
    var up := camera.global_basis.y.normalized()
    var sway := _wind_sway(sprite)
    var bounds := AABB()
    var initialized := false
    for point in [visible.position, Vector2(visible.end.x, visible.position.y), visible.end, Vector2(visible.position.x, visible.end.y)]:
        var x: float = (point.x - pivot.x) * sprite.pixel_size + sway * ((pivot.y - point.y) / canvas.y)
        var y: float = (pivot.y - point.y) * sprite.pixel_size
        var world_point: Vector3 = sprite.global_position + right * x * scale.x + up * y * scale.y
        if initialized:
            bounds = bounds.expand(world_point)
        else:
            bounds = AABB(world_point, Vector3.ZERO)
            initialized = true
    return bounds.grow(0.005)

func _sprite_blocks(sprite: Sprite3D, camera: Camera3D, target: Vector3, mask: BitMap) -> bool:
    var origin := camera.global_position
    var segment := target - origin
    var normal := camera.global_basis.z.normalized()
    var denominator := normal.dot(segment)
    if absf(denominator) < 0.000001:
        return false
    var distance := normal.dot(sprite.global_position - origin) / denominator
    # A tree behind the character or behind the camera is never an occluder.
    if distance <= 0.0 or distance >= 1.0:
        return false
    var hit := origin + segment * distance - sprite.global_position
    var scale: Vector3 = sprite.global_basis.get_scale()
    var pivot := _pivot(sprite)
    var pixel_y := pivot.y - hit.dot(camera.global_basis.y.normalized()) / maxf(0.00001, sprite.pixel_size * scale.y)
    var local_x := hit.dot(camera.global_basis.x.normalized()) / maxf(0.00001, scale.x)
    var shear := _wind_sway(sprite) * ((pivot.y - pixel_y) / float(sprite.texture.get_height()))
    var pixel_x := pivot.x + (local_x - shear) / sprite.pixel_size
    var pixel := Vector2i(floori(pixel_x), floori(pixel_y))
    var size := mask.get_size()
    if pixel.x < 0 or pixel.y < 0 or pixel.x >= size.x or pixel.y >= size.y:
        return false
    return mask.get_bitv(pixel)

func update(camera: Camera3D, player: Node3D, delta: float, immediate := false) -> void:
    if not is_instance_valid(camera) or not is_instance_valid(player):
        return
    var feet := player.global_position
    var actor_sprite := player.get("sprite") as Node3D
    if is_instance_valid(actor_sprite):
        feet = actor_sprite.global_position
    var up := camera.global_basis.y.normalized()
    var right := camera.global_basis.x.normalized()
    var targets: Array[Vector3] = []
    for height in SAMPLE_HEIGHTS:
        for side in SAMPLE_SIDES:
            targets.append(feet + up * height + right * side)
    var origin := camera.global_position
    var step := FADE_SPEED * maxf(delta, 0.0)
    for entry in _trees:
        var margin := LEAVE_MARGIN if entry.occluding else ENTER_MARGIN
        var blocked := false
        for item in entry.sprites:
            var sprite := item.sprite as Sprite3D
            if not is_instance_valid(sprite):
                continue
            var bounds := billboard_bounds(sprite, camera).grow(margin)
            var mask: BitMap = item.leave_mask if entry.occluding else item.enter_mask
            for target in targets:
                if bounds.intersects_segment(origin, target) != null and _sprite_blocks(sprite, camera, target, mask):
                    blocked = true
                    break
            if blocked:
                break
        if not blocked:
            for item in entry.meshes:
                var bounds: AABB = item.bounds.grow(margin)
                for target in targets:
                    if bounds.intersects_segment(origin, target) != null:
                        blocked = true
                        break
                if blocked:
                    break
        entry.occluding = blocked
        var target_transparency := 1.0 if blocked else 0.0
        var value := target_transparency if immediate else move_toward(float(entry.transparency), target_transparency, step)
        entry.transparency = value
        for visual in entry.geometry:
            if is_instance_valid(visual):
                visual.transparency = value

func snapshot() -> Dictionary:
    var faded_names: Array[String] = []
    var occluding_count := 0
    var details: Array[Dictionary] = []
    for entry in _trees:
        if entry.occluding:
            occluding_count += 1
        if float(entry.transparency) > 0.0001:
            faded_names.append(entry.name)
        if entry.occluding or float(entry.transparency) > 0.0001:
            details.append({"name":entry.name, "occluding":entry.occluding, "transparency":entry.transparency, "geometry_count":entry.geometry.size(), "sprite_count":entry.sprites.size(), "mesh_count":entry.meshes.size()})
    return {"mode":"billboard_alpha_aware", "faded_trees":faded_names.size(), "occluding_trees":occluding_count, "registered_trees":_trees.size(), "faded_names":faded_names, "geometry_count":_geometry_count, "sprite_count":_sprite_count, "mesh_count":_mesh_count, "details":details}
