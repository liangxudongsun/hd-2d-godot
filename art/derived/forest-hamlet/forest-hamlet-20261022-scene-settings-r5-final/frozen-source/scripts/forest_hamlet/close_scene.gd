extends "res://scripts/forest_hamlet/scene.gd"
## Independent close reference camera. The shared village, original traveler
## scale and full camera-facing billboard are inherited without replacement.
const CLOSE_CAMERA_OFFSET := Vector3(0.0, 3.084504, 12.371271)
const CLOSE_FOCUS_OFFSET := Vector3(0.0, 1.0, -0.6)
const CLOSE_DEFAULT_FOCUS := Vector3(0.0, 1.15, 1.9)
var occlusion := preload("res://scripts/forest_hamlet/occlusion.gd").new()

func _ready() -> void:
    super._ready()
    player.facing = 0
    player.update_animation()
    occlusion.configure(world.view_occluders)
    camera.fov = 39.0
    update_camera(true)

func update_camera(snap := false, delta := 1.0 / 60.0) -> void:
    if camera_locked:
        return
    var desired := CLOSE_DEFAULT_FOCUS
    if follow_enabled and is_instance_valid(player):
        desired.x = clampf(player.position.x + CLOSE_FOCUS_OFFSET.x, CAMERA_FOCUS_BOUNDS.position.x, CAMERA_FOCUS_BOUNDS.end.x)
        desired.y = player.position.y + CLOSE_FOCUS_OFFSET.y
        desired.z = clampf(player.position.z + CLOSE_FOCUS_OFFSET.z, CAMERA_FOCUS_BOUNDS.position.y, CAMERA_FOCUS_BOUNDS.end.y)
    var weight := 1.0 - exp(-CAMERA_FOLLOW_SPEED * maxf(delta, 0.0))
    camera_focus = desired if snap else camera_focus.lerp(desired, weight)
    camera.position = camera_focus + CLOSE_CAMERA_OFFSET
    camera.look_at(camera_focus, Vector3.UP)
    update_focus()
    occlusion.update(camera, player, delta, snap)

func framing_state() -> Dictionary:
    var state := super.framing_state()
    state["camera_offset_length"] = CLOSE_CAMERA_OFFSET.length()
    state["profile"] = "close_reference"
    return state

func snapshot_state() -> Dictionary:
    var state := super.snapshot_state()
    state["occlusion"] = occlusion.snapshot()
    return state
