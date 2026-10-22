extends "res://scripts/ancient_canal/actor.gd"
## Scene-local input and billboard adapter. Original color, normal, silver and
## timing data stay in the shared traveler; the physical feet/collider stay put.

func _ready() -> void:
    super._ready()
    surface.set_shader_parameter("camera_facing_billboard",true)

func apply_material(values: Dictionary) -> void:
    super.apply_material(values)
    if surface != null:
        surface.set_shader_parameter("camera_facing_billboard",true)

func motion_direction() -> Vector3:
    if not controls_enabled:
        return Vector3.ZERO
    if scripted_input:
        var direction := scripted_direction.limit_length(1.0)
        return Vector3(direction.x, 0.0, direction.y)
    if Input.is_key_pressed(KEY_CTRL) or Input.is_key_pressed(KEY_ALT) or Input.is_key_pressed(KEY_META):
        return Vector3.ZERO
    var axis := Vector2(
        float(Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT)) - float(Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT)),
        float(Input.is_physical_key_pressed(KEY_S) or Input.is_physical_key_pressed(KEY_DOWN)) - float(Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP)))
    if not is_instance_valid(camera):
        return Vector3(axis.x, 0.0, axis.y).limit_length(1.0)
    var right := camera.global_basis.x
    var back := camera.global_basis.z
    right.y = 0.0
    back.y = 0.0
    return (right.normalized() * axis.x + back.normalized() * axis.y).limit_length(1.0)
