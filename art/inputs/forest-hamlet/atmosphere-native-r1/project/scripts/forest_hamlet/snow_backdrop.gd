extends Node3D
## One complete distant snow plate with restrained, directional normal relighting.
## The camera and player scale remain owned by the existing scene. This module
## follows camera Y/Z while retaining a controlled amount of relative X motion.

const ASSET_ROOT := "res://assets/forest-hamlet/backdrop/"
const SHADER_PATH := "res://shaders/forest_hamlet/snow_backdrop.gdshader"
const DEPTH := 135.0
const MIN_WIDTH := 255.0
const PARALLAX_STRENGTH := 0.35
const PEAK_SCREEN_X := 0.505
const PEAK_SCREEN_Y := -0.015
const LANDMARKS := [
    {"id":"main_peak", "uv":Vector2(0.620, 0.288)},
    {"id":"main_snow_ridge", "uv":Vector2(0.629, 0.330)},
    {"id":"left_shoulder", "uv":Vector2(0.586, 0.365)},
    {"id":"left_peak", "uv":Vector2(0.171, 0.388)},
    {"id":"right_ridge", "uv":Vector2(0.806, 0.424)}
]

var camera: Camera3D
var sun: DirectionalLight3D
var board: MeshInstance3D
var material: ShaderMaterial
var manifest: Dictionary = {}
var normals_enabled := true
var parallax_enabled := true
var preset := "day"
var elapsed := 0.0
var parallax_strength := PARALLAX_STRENGTH
var _reference_x := 0.0
var _source_size := Vector2(1983.0, 793.0)
var _board_size := Vector2(230.0, 130.0)
var _source_world_height := 92.0
var _source_vertical_offset := 22.0
var _source_horizontal_offset := 0.0
var _visible_size := Vector2.ZERO
var _viewport_size := Vector2.ZERO
var _local_light_direction := Vector3(0.0, 0.0, 1.0)

func configure(view_camera: Camera3D, main_sun: DirectionalLight3D) -> void:
    camera = view_camera
    sun = main_sun
    _reference_x = camera.global_position.x
    if is_instance_valid(board):
        update_frame()
        return
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ASSET_ROOT + "manifest.json"))
    assert(parsed is Dictionary, "Snow backdrop manifest is missing or invalid")
    manifest = parsed
    var dimensions: Array = manifest["dimensions"]
    _source_size = Vector2(float(dimensions[0]), float(dimensions[1]))
    material = ShaderMaterial.new()
    material.shader = load(SHADER_PATH)
    material.set_shader_parameter("color_texture", load(ASSET_ROOT + "color.png"))
    material.set_shader_parameter("normal_texture", load(ASSET_ROOT + "normal.png"))
    material.set_shader_parameter("region_texture", load(ASSET_ROOT + "regions.png"))
    material.set_shader_parameter("normal_strength", float(manifest.get("normal_strength", 0.8)))
    board = MeshInstance3D.new()
    board.name = "DistantSnowPlate"
    board.mesh = QuadMesh.new()
    board.material_override = material
    board.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    board.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
    board.ignore_occlusion_culling = true
    add_child(board)
    set_normals(normals_enabled)
    set_preset(preset)
    update_frame()

func tick(delta: float) -> void:
    elapsed += maxf(delta, 0.0)
    update_frame()

func update_frame() -> void:
    if not is_instance_valid(camera) or not is_instance_valid(board):
        return
    _viewport_size = camera.get_viewport().get_visible_rect().size
    if _viewport_size.x <= 0.0 or _viewport_size.y <= 0.0:
        _viewport_size = Vector2(1920.0, 1080.0)
    var vertical_extent := 2.0 * DEPTH * tan(deg_to_rad(camera.fov) * 0.5)
    var aspect := _viewport_size.x / _viewport_size.y
    _visible_size = Vector2(vertical_extent * aspect, vertical_extent)
    # Physical quad covers the full view and horizontal follow envelope. The
    # approved image keeps its aspect ratio inside it; a calm edge fog color
    # extends below the original art where existing terrain normally occludes it.
    _board_size = Vector2(maxf(MIN_WIDTH, _visible_size.x + 50.0), maxf(130.0, _visible_size.y * 1.30))
    _source_world_height = _board_size.x * _source_size.y / _source_size.x
    _source_vertical_offset = (0.5 - PEAK_SCREEN_Y) * _visible_size.y - (0.5 - 0.288) * _source_world_height
    _source_horizontal_offset = (PEAK_SCREEN_X - 0.5) * _visible_size.x - (0.620 - 0.5) * _board_size.x
    var quad := board.mesh as QuadMesh
    quad.size = _board_size
    var follow_lag := (_reference_x - camera.global_position.x) * parallax_strength if parallax_enabled else 0.0
    var view_basis := camera.global_basis.orthonormalized()
    board.global_transform = Transform3D(view_basis, camera.global_position - view_basis.z * DEPTH + view_basis.x * follow_lag)
    material.set_shader_parameter("source_uv_scale", Vector2(1.0, _board_size.y / _source_world_height))
    material.set_shader_parameter("source_uv_offset", Vector2(-_source_horizontal_offset / _board_size.x, _source_vertical_offset / _source_world_height))
    if is_instance_valid(sun):
        _local_light_direction = (view_basis.inverse() * sun.global_basis.z).normalized()
        material.set_shader_parameter("sun_direction_local", _local_light_direction)
        material.set_shader_parameter("sun_color", sun.light_color)

func set_normals(enabled: bool) -> void:
    normals_enabled = enabled
    if is_instance_valid(material):
        material.set_shader_parameter("use_normals", enabled)

func set_parallax(enabled: bool) -> void:
    parallax_enabled = enabled
    update_frame()

func set_preset(id: String) -> bool:
    if id not in ["day", "dusk"]:
        return false
    preset = id
    if is_instance_valid(material):
        material.set_shader_parameter("preset_tint", Color(1.0, 1.0, 1.0) if id == "day" else Color(1.0, 0.92, 0.91))
        material.set_shader_parameter("brightness", 0.93 if id == "day" else 0.86)
    update_frame()
    return true

func landmark_world(uv: Vector2) -> Vector3:
    if not is_instance_valid(board):
        return Vector3.ZERO
    return board.to_global(Vector3((uv.x - 0.5) * _board_size.x + _source_horizontal_offset, (0.5 - uv.y) * _source_world_height + _source_vertical_offset, 0.0))

func snapshot() -> Dictionary:
    if not is_instance_valid(board) or not is_instance_valid(camera):
        return {"ready":false}
    var projected: Array = []
    for point in LANDMARKS:
        var uv: Vector2 = point["uv"]
        var location := landmark_world(uv)
        var screen := camera.unproject_position(location)
        projected.append({
            "id":point["id"], "uv":[uv.x, uv.y],
            "world":[location.x, location.y, location.z],
            "projected_pixels":[screen.x, screen.y],
            "projected_normalized":[screen.x / _viewport_size.x, screen.y / _viewport_size.y],
            "in_frame":Rect2(Vector2.ZERO, _viewport_size).has_point(screen)
        })
    var corners: Array = []
    var minimum := Vector2(INF, INF)
    var maximum := Vector2(-INF, -INF)
    for point in [Vector2(-0.5,-0.5), Vector2(0.5,-0.5), Vector2(0.5,0.5), Vector2(-0.5,0.5)]:
        var location := board.to_global(Vector3(point.x * _board_size.x, point.y * _board_size.y, 0.0))
        var projected_corner := camera.unproject_position(location)
        minimum = minimum.min(projected_corner)
        maximum = maximum.max(projected_corner)
        corners.append([projected_corner.x, projected_corner.y])
    var overscan := [-minimum.x, -minimum.y, maximum.x - _viewport_size.x, maximum.y - _viewport_size.y]
    var coverage_ok := minimum.x <= 0.0 and minimum.y <= 0.0 and maximum.x >= _viewport_size.x and maximum.y >= _viewport_size.y
    return {
        "ready":true, "geometry_count":1, "independent_color_layers":1,
        "parallax_kind":"single_distant_board", "parallax_enabled":parallax_enabled,
        "parallax_strength":parallax_strength, "normals_enabled":normals_enabled,
        "lighting_method":"dynamic_tangent_normal_relighting", "preset":preset,
        "source_sha256":manifest.get("source_sha256", ""),
        "source_dimensions":[_source_size.x, _source_size.y],
        "source_color_byte_identical":manifest.get("validation", {}).get("checks", {}).get("approved_color_byte_identical", false),
        "normal_geometric_facets":manifest.get("geometric_facets", 0),
        "normal_map":ASSET_ROOT + "normal.png", "normal_strength":manifest.get("normal_strength", 0.8),
        "local_light_direction":[_local_light_direction.x, _local_light_direction.y, _local_light_direction.z],
        "view_depth":DEPTH, "within_camera_far":DEPTH < camera.far,
        "board_size":[_board_size.x, _board_size.y],
        "source_world_height":_source_world_height, "source_vertical_offset":_source_vertical_offset,
        "source_horizontal_offset":_source_horizontal_offset, "peak_screen_target":[PEAK_SCREEN_X, PEAK_SCREEN_Y],
        "reference_camera_x":_reference_x, "camera_x":camera.global_position.x,
        "viewport_coverage_ok":coverage_ok, "overscan_margin_px":overscan,
        "projected_quad_corners":corners, "landmarks":projected,
        "cast_shadow":board.cast_shadow, "elapsed":elapsed
    }
