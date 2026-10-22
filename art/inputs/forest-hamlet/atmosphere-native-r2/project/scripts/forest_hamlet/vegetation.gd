extends RefCounted
## Manifest-backed HD-2D plants. Pixel aspect and bottom pivots come from the
## produced images; only a uniform world scale varies between placements.
const ROOT := "res://assets/forest-hamlet/vegetation/"
const MANIFEST := ROOT + "manifest.json"
const SURFACE := preload("res://shaders/forest_hamlet/vegetation.gdshader")
const IDS := ["broadleaf_a", "broadleaf_b", "fir", "grass", "fern", "reeds", "flowers_white", "flowers_pink", "window_flowers", "lily_pad"]
var assets: Dictionary = {}
var materials: Dictionary = {}
var textures: Dictionary = {}
var alpha_masks: Dictionary = {}
var wind_clock := 0.0
var wind_strength := 0.06
var normals_enabled := true

func configure() -> void:
    assert(FileAccess.file_exists(MANIFEST), "Missing produced vegetation manifest")
    var decoded: Variant = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST))
    assert(decoded is Dictionary, "Invalid vegetation manifest")
    var manifest: Dictionary = decoded
    assert(manifest.get("normal_convention", "") == "OpenGL", "Vegetation normals must use OpenGL tangent +Y")
    for record in manifest.get("assets", []):
        var id := String(record.id)
        assert(id in IDS and not assets.has(id), "Unknown or duplicate vegetation asset: " + id)
        assets[id] = record
        var color_path := ROOT + String(record.color)
        var normal_path := ROOT + String(record.normal)
        var color := load(color_path) as Texture2D
        var normal := load(normal_path) as Texture2D
        assert(color != null and normal != null, "Missing vegetation image pair: " + id)
        assert(color.get_size() == normal.get_size(), "Vegetation color/normal canvas mismatch: " + id)
        assert(color.get_width() == int(record.size_px[0]) and color.get_height() == int(record.size_px[1]), "Vegetation manifest canvas mismatch: " + id)
        var alpha_image := color.get_image()
        if alpha_image.is_compressed():
            var error := alpha_image.decompress()
            assert(error == OK, "Unable to read vegetation cutout alpha: " + id)
        var mask := BitMap.new()
        mask.create_from_image_alpha(alpha_image, 0.5)
        alpha_masks[id] = mask
        textures[id] = color
        var material := ShaderMaterial.new()
        material.shader = SURFACE
        material.set_shader_parameter("color_texture", color)
        material.set_shader_parameter("normal_texture", normal)
        material.set_shader_parameter("pivot_v", float(record.pivot_px[1]) / float(record.size_px[1]))
        material.set_shader_parameter("normal_strength", 0.65)
        material.set_shader_parameter("use_normals", normals_enabled)
        material.set_shader_parameter("wind_strength", wind_strength)
        material.set_shader_parameter("wind_clock", wind_clock)
        materials[id] = material
    assert(assets.size() == IDS.size(), "All ten vegetation families are required")

func material(id: String) -> ShaderMaterial:
    assert(materials.has(id), "Unknown vegetation material: " + id)
    return materials[id] as ShaderMaterial

func create(id: String, uniform_scale := 1.0, wind_phase := 0.0) -> Sprite3D:
    assert(assets.has(id), "Unknown vegetation asset: " + id)
    var record: Dictionary = assets[id]
    var canvas := Vector2(float(record.size_px[0]), float(record.size_px[1]))
    var pivot := Vector2(float(record.pivot_px[0]), float(record.pivot_px[1]))
    var visible := Rect2(float(record.visible_rect_px[0]), float(record.visible_rect_px[1]), float(record.visible_rect_px[2]), float(record.visible_rect_px[3]))
    assert(visible.size.y > 0.0 and float(record.height_m) > 0.0, "Vegetation needs a visible silhouette and physical height")
    var sprite := Sprite3D.new()
    sprite.texture = textures[id]
    sprite.material_override = material(id)
    sprite.pixel_size = float(record.height_m) / visible.size.y
    sprite.offset = Vector2(canvas.x * 0.5 - pivot.x, pivot.y - canvas.y * 0.5)
    sprite.scale = Vector3.ONE * uniform_scale
    sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED
    sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    sprite.alpha_scissor_threshold = 0.5
    sprite.shaded = true
    sprite.double_sided = true
    sprite.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
    # The GPU rotates the full plane, including pitch. A conservative spherical
    # local box prevents the upright Sprite3D bounds culling that rotated plane.
    var extent := Vector2(maxf(pivot.x, canvas.x - pivot.x), maxf(pivot.y, canvas.y - pivot.y))
    var radius := extent.length() * sprite.pixel_size + 0.1
    sprite.custom_aabb = AABB(Vector3(-radius, -radius, -radius), Vector3.ONE * radius * 2.0)
    sprite.set_instance_shader_parameter("wind_phase", wind_phase)
    sprite.set_instance_shader_parameter("wind_weight", float(record.get("wind_weight", 1.0)))
    sprite.set_meta("asset_id", id)
    sprite.set_meta("color_path", ROOT + String(record.color))
    sprite.set_meta("normal_path", ROOT + String(record.normal))
    sprite.set_meta("pivot_px", pivot)
    sprite.set_meta("visible_rect_px", visible)
    sprite.set_meta("alpha_bitmap", alpha_masks[id])
    sprite.set_meta("wind_phase", wind_phase)
    sprite.set_meta("wind_weight", float(record.get("wind_weight", 1.0)))
    return sprite

func set_normals(enabled: bool) -> void:
    normals_enabled = enabled
    for value in materials.values():
        var surface := value as ShaderMaterial
        surface.set_shader_parameter("use_normals", enabled)

func set_wind_strength(strength: float) -> void:
    wind_strength = strength
    for value in materials.values():
        var surface := value as ShaderMaterial
        surface.set_shader_parameter("wind_strength", strength)

func tick(delta: float) -> void:
    # Existing scene controls and capture scripts address foliage_material.
    # It is the real broadleaf material; propagate its setting to every family.
    var requested := float(material("broadleaf_a").get_shader_parameter("wind_strength"))
    if not is_equal_approx(requested, wind_strength):
        set_wind_strength(requested)
    wind_clock += maxf(delta, 0.0)
    for value in materials.values():
        var surface := value as ShaderMaterial
        surface.set_shader_parameter("wind_clock", wind_clock)

func snapshot() -> Dictionary:
    return {"families":assets.keys(), "family_count":assets.size(), "normal_convention":"OpenGL", "normals_enabled":normals_enabled, "wind_strength":wind_strength, "wind_clock":wind_clock, "rendering":"camera-facing Sprite3D color + tangent normal cutouts"}
