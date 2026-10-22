extends Node3D
## Original forest hamlet effect study; the archived project remains independent.
const Actor = preload("res://scripts/forest_hamlet/actor.gd")
const SceneSettings = preload("res://scripts/forest_hamlet/scene_settings.gd")
const FONT_PATH := "res://assets/ancient-canal/fonts/NotoSansSC.ttf"
## Match the supplied village image: pond in the lower left, houses above.
## Keep the original actor scale; its full silhouette occupies about 13.6% height.
const CAMERA_OFFSET := Vector3(0.0, 12.0, 17.5)
const ACTOR_FOCUS_OFFSET := Vector3(0.0, 0.85, -0.6)
const DEFAULT_FOCUS := Vector3(0.0, 0.85, 1.9)
const CAMERA_FOLLOW_SPEED := 8.0
const CAMERA_FOCUS_BOUNDS := Rect2(-14.0, -13.0, 28.0, 22.0)
var world: Node3D
var backdrop := preload("res://scripts/forest_hamlet/snow_backdrop.gd").new()
var cloud_lighting := preload("res://scripts/forest_hamlet/cloud_lighting.gd").new()
var global_lighting := preload("res://scripts/forest_hamlet/global_lighting.gd").new()
var visibility_guard := preload("res://scripts/forest_hamlet/occlusion.gd").new()
var player: CharacterBody3D
var camera: Camera3D
var environment: Environment
var attributes := CameraAttributesPractical.new()
var main_light: DirectionalLight3D
var sky_material: ProceduralSkyMaterial
var overlay: CanvasLayer
var panel: PanelContainer
var status_label: Label
var exit_confirmation: ConfirmationDialog
var feature_buttons: Dictionary = {}
var time_buttons: Dictionary = {}
# Retain the old property and path: existing cloud preferences migrate on read.
@export var cloud_settings_enabled := true
@export var settings_path := "user://forest-hamlet-clouds.cfg"
var effect_parameters: Dictionary = SceneSettings.default_parameters()
var effect_sliders: Dictionary = {}
var effect_value_labels: Dictionary = {}
var settings_tabs: TabContainer
var setting_scrolls: Dictionary = {}
var _tab_ids: Array[String] = ["environment", "dof", "glow", "clouds", "other"]
var _saved_profile: Dictionary = {}
var _settings_dirty := false
var _settings_ready := false
var _applying_profile := false
# Cloud-only dictionaries remain available to existing tools and captures.
var tuning_sliders: Dictionary = {}
var tuning_value_labels: Dictionary = {}
var tuning_reset_button: Button
var tuning_save_button: Button
var tuning_load_button: Button
var tuning_status_label: Label
var tuning_effect_label: Label
var tuning_scroll: ScrollContainer
var _cloud_tuning_note := "修改即时预览；保存后下次启动自动沿用。"
var _controls_before_tuning := true
var values := {"normals":true, "bloom":true, "dof":true, "wind":true, "backdrop_normals":true, "parallax":true, "clouds":true, "atmosphere":true, "global_light":true}
var time_preset := "day"
var frozen := false
var camera_locked := false
var follow_enabled := true
var camera_focus := DEFAULT_FOCUS
var elapsed := 0.0
var route_running := false
var route_index := 0
var route_elapsed := 0.0
var route_points: Array[Vector3] = [Vector3(-13,.15,1.8), Vector3(0,.15,1.8), Vector3(12,.15,1.8), Vector3(0,.15,1.8), Vector3(0,.15,-10), Vector3(0,.15,1.8)]
var route_result: Dictionary = {}
var route_trajectory: Array = []
var route_sample_clock := 0.0
var capture_counter := 0

func _ready() -> void:
    world = load("res://scripts/forest_hamlet/world.gd").new()
    world.name = "ForestWorld"
    add_child(world)
    visibility_guard.configure(world.view_occluders)
    camera = Camera3D.new()
    camera.name = "ForestCamera"
    camera.current = true
    camera.near = 0.1
    camera.far = 170.0
    camera.fov = 39.0
    camera.attributes = attributes
    add_child(camera)
    create_lighting()
    player = Actor.new()
    player.position = world.spawn
    player.camera = camera
    add_child(player)
    player.apply_material({"shading_mode":"native", "normals_enabled":true, "normal_strength":0.72, "normal_flip_y":false, "clay":false, "normal_debug":false, "silver_specular":0.7, "light_steps":4.0})
    backdrop.name = "SnowMountainBackdrop"
    add_child(backdrop)
    backdrop.configure(camera, main_light)
    cloud_lighting.name = "CloudLighting"
    add_child(cloud_lighting)
    cloud_lighting.configure(main_light, environment)
    global_lighting.name = "GlobalLightVariation"
    add_child(global_lighting)
    global_lighting.configure(main_light, environment)
    create_hud()
    get_tree().auto_accept_quit = false
    get_tree().root.close_requested.connect(request_quit)
    set_time_preset("day")
    for key in values:
        set_feature(key, values[key])
    update_camera(true)
    backdrop.update_frame()
    _settings_ready = true
    _saved_profile = get_scene_settings()
    # Only a normal main-scene launch reads personal preferences. Script-based
    # tests/captures instantiate children and remain deterministic by default.
    call_deferred("_load_initial_cloud_tuning")
    print("FOREST_HAMLET_READY normals=", not player.normal_definition.is_empty(), " preset=", time_preset)

func _load_initial_cloud_tuning() -> void:
    if cloud_settings_enabled and get_tree().current_scene == self and FileAccess.file_exists(settings_path):
        load_scene_settings()

func set_cloud_contrast(value: float) -> void:
    set_effect_parameter("cloud_contrast", value)

func set_cloud_density(value: float) -> void:
    set_effect_parameter("cloud_density", value)

func reset_cloud_tuning() -> void:
    set_cloud_contrast(0.30)
    set_cloud_density(0.50)
    _cloud_tuning_note = "云层已恢复默认；其他场景参数保持当前设置。"
    _refresh_cloud_tuning()

# Compatibility entry points now persist the complete scene profile.
func save_cloud_tuning() -> bool:
    return save_scene_settings()

func load_cloud_tuning() -> bool:
    return load_scene_settings()

func get_scene_settings() -> Dictionary:
    var parameters := effect_parameters.duplicate(true)
    parameters.cloud_contrast = cloud_lighting.contrast_strength
    parameters.cloud_density = cloud_lighting.cloud_density
    return {"schema_version": SceneSettings.SCHEMA_VERSION, "time_preset": time_preset,
        "features": values.duplicate(true), "parameters": parameters}

func set_effect_parameter(id: String, value: float) -> bool:
    if not SceneSettings.PARAMETER_SPECS.has(id) or not is_finite(value):
        return false
    var spec: Dictionary = SceneSettings.PARAMETER_SPECS[id]
    effect_parameters[id] = clampf(value, float(spec.min), float(spec.max))
    _apply_effect_parameters(id)
    _mark_settings_changed()
    return true

func _apply_effect_parameters(changed_id: String = "") -> void:
    if environment == null or not is_instance_valid(player):
        return
    if changed_id in ["", "cloud_contrast"]:
        cloud_lighting.set_cloud_contrast(effect_parameters.cloud_contrast)
    if changed_id in ["", "cloud_density"]:
        cloud_lighting.set_cloud_density(effect_parameters.cloud_density)
    if changed_id.is_empty() or changed_id.begins_with("glow_"):
        environment.glow_intensity = effect_parameters.glow_intensity
        environment.glow_strength = effect_parameters.glow_strength
        environment.glow_bloom = effect_parameters.glow_bloom
        environment.glow_hdr_threshold = effect_parameters.glow_hdr_threshold
        environment.glow_hdr_scale = effect_parameters.glow_hdr_scale
    if changed_id in ["", "exposure"]:
        environment.tonemap_exposure = effect_parameters.exposure
    if changed_id in ["", "contrast"]:
        environment.adjustment_contrast = effect_parameters.contrast
    if changed_id in ["", "saturation"]:
        environment.adjustment_saturation = effect_parameters.saturation
    if changed_id in ["", "fog_density_scale"]:
        environment.fog_density = (0.0015 if time_preset == "day" else 0.0023) * effect_parameters.fog_density_scale
        environment.volumetric_fog_density = (0.0030 if time_preset == "day" else 0.0038) * effect_parameters.fog_density_scale
    if changed_id in ["", "wind_strength"]:
        world.set_vegetation_wind(effect_parameters.wind_strength if values.wind else 0.0)
    if changed_id in ["", "parallax_strength"]:
        backdrop.parallax_strength = effect_parameters.parallax_strength
        backdrop.update_frame()
    if changed_id in ["", "sun_variation", "ambient_variation"]:
        global_lighting.set_amplitudes(effect_parameters.sun_variation, effect_parameters.ambient_variation)
        cloud_lighting.sync_sun_lights()
    if changed_id.is_empty() or changed_id.begins_with("dof_"):
        update_focus()

func _mark_settings_changed() -> void:
    if not _settings_ready or _applying_profile:
        return
    _settings_dirty = get_scene_settings() != _saved_profile
    _cloud_tuning_note = "已实时预览；点击「保存参数」记录全部效果。" if _settings_dirty else "当前参数与已保存设置一致。"
    refresh_hud()

func apply_scene_settings(profile: Dictionary) -> bool:
    # Validate the complete document before touching any live scene property.
    var checked: Dictionary = SceneSettings.normalize_profile(profile)
    if not checked.ok:
        _cloud_tuning_note = "参数格式无效，保留当前效果。"
        refresh_hud()
        return false
    var normalized: Dictionary = checked.profile
    _applying_profile = true
    effect_parameters = normalized.parameters.duplicate(true)
    for id in normalized.features:
        set_feature(id, normalized.features[id])
    set_time_preset(normalized.time_preset)
    _applying_profile = false
    _mark_settings_changed()
    refresh_hud()
    return true

func save_scene_settings() -> bool:
    var profile := get_scene_settings()
    var result: Dictionary = SceneSettings.write_profile(settings_path, profile)
    if result.ok:
        _saved_profile = profile.duplicate(true)
        _settings_dirty = false
        _cloud_tuning_note = "全部参数已保存，下次启动自动恢复。"
    else:
        _cloud_tuning_note = "保存失败（%d）；当前预览和原存档保留。" % result.error_code
    refresh_hud()
    return bool(result.ok)

func load_scene_settings() -> bool:
    var result: Dictionary = SceneSettings.read_profile(settings_path)
    if not result.ok:
        _cloud_tuning_note = "还没有保存的参数。" if result.error_code == ERR_FILE_NOT_FOUND else "参数读取失败，保留当前效果。"
        refresh_hud()
        return false
    if not apply_scene_settings(result.profile):
        return false
    _saved_profile = get_scene_settings()
    _settings_dirty = false
    _cloud_tuning_note = "已沿用旧云层存档；再次保存将包含全部效果。" if result.legacy else "已读取保存的全部场景参数。"
    refresh_hud()
    return true

func reset_scene_settings() -> void:
    apply_scene_settings(SceneSettings.default_profile())
    _cloud_tuning_note = "已恢复全部默认效果；保存后替换之前的设置。"
    _refresh_cloud_tuning()

func create_lighting() -> void:
    # Large cloud penumbras need enough native PCSS samples to stay smooth.
    # This applies only to this running study; project renderer settings stay intact.
    RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_ULTRA)
    environment = Environment.new()
    environment.background_mode = Environment.BG_SKY
    sky_material = ProceduralSkyMaterial.new()
    sky_material.sky_top_color = Color(.21,.38,.49)
    sky_material.sky_horizon_color = Color(.53,.66,.67)
    sky_material.ground_bottom_color = Color(.12,.19,.11)
    sky_material.ground_horizon_color = Color(.53,.66,.67)
    sky_material.sun_angle_max = 4.0
    var sky := Sky.new()
    sky.sky_material = sky_material
    environment.sky = sky
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_sky_contribution = 0.0
    environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
    environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
    environment.tonemap_exposure = 1.0
    environment.ssao_enabled = true
    environment.ssao_radius = 1.0
    environment.ssao_intensity = 1.3
    # Forward+ screen-space reflections ground the pond against its visible
    # stone bank and foliage. Off-screen objects still use the sky fallback.
    environment.ssr_enabled = true
    environment.ssr_max_steps = 64
    environment.glow_enabled = true
    environment.glow_intensity = .42
    environment.glow_strength = .85
    environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
    environment.glow_bloom = .025
    environment.glow_hdr_threshold = .95
    environment.glow_hdr_scale = 1.6
    environment.set_glow_level(0, .0)
    environment.set_glow_level(1, .35)
    environment.set_glow_level(2, .65)
    environment.set_glow_level(3, .25)
    environment.set_glow_level(4, .08)
    environment.adjustment_enabled = true
    environment.adjustment_contrast = 1.06
    environment.adjustment_saturation = .98
    environment.fog_enabled = true
    environment.fog_density = .0015
    environment.fog_light_energy = .7
    environment.fog_sky_affect = .25
    var world_environment := WorldEnvironment.new()
    world_environment.environment = environment
    add_child(world_environment)
    main_light = DirectionalLight3D.new()
    main_light.name = "Sun"
    main_light.shadow_enabled = true
    main_light.directional_shadow_max_distance = 80.0
    main_light.shadow_bias = .035
    main_light.directional_shadow_blend_splits = true
    main_light.light_angular_distance = .65
    add_child(main_light)

func set_time_preset(id: String) -> bool:
    if id not in ["day", "dusk"]:
        return false
    time_preset = id
    if id == "day":
        main_light.rotation_degrees = Vector3(-53,-42,0)
        main_light.light_color = Color(1.0,.95,.86)
        main_light.light_energy = 1.45
        environment.ambient_light_color = Color(.43,.56,.65)
        environment.ambient_light_energy = .55
        environment.fog_light_color = Color(.42,.57,.57)
        environment.fog_density = .0015
        sky_material.sky_top_color = Color(.21,.38,.49)
        sky_material.sky_horizon_color = Color(.53,.66,.67)
    else:
        main_light.rotation_degrees = Vector3(-24,-62,0)
        main_light.light_color = Color(1.0,.66,.43)
        main_light.light_energy = 1.15
        environment.ambient_light_color = Color(.37,.47,.68)
        environment.ambient_light_energy = .40
        environment.fog_light_color = Color(.25,.34,.46)
        environment.fog_density = .0023
        sky_material.sky_top_color = Color(.16,.24,.40)
        sky_material.sky_horizon_color = Color(.65,.46,.31)
    backdrop.set_preset(id)
    cloud_lighting.set_preset(id)
    global_lighting.set_preset(id)
    cloud_lighting.sync_sun_lights()
    sky_material.ground_horizon_color = sky_material.sky_horizon_color
    for lamp in world.lamps:
        lamp.visible = id == "dusk"
    for material in world.lamp_glass_materials:
        material.emission_energy_multiplier = 4.0 if id == "dusk" else .3
    # Presets provide color and base lighting; personal strengths survive them.
    _apply_effect_parameters()
    _mark_settings_changed()
    refresh_hud()
    return true

func set_feature(id: String, enabled: bool) -> bool:
    if not values.has(id):
        return false
    values[id] = enabled
    match id:
        "normals": world.ground_material.set_shader_parameter("use_normals",enabled)
        "bloom": environment.glow_enabled = enabled
        "dof":
            attributes.dof_blur_far_enabled = enabled
            attributes.dof_blur_near_enabled = enabled
        "wind": world.set_vegetation_wind(effect_parameters.wind_strength if enabled else 0.0)
        "backdrop_normals": backdrop.set_normals(enabled)
        "parallax": backdrop.set_parallax(enabled)
        "clouds": cloud_lighting.set_enabled(enabled)
        "atmosphere": cloud_lighting.set_atmosphere_enabled(enabled)
        "global_light": global_lighting.set_enabled(enabled)
    cloud_lighting.sync_sun_lights()
    _mark_settings_changed()
    refresh_hud()
    return true

func update_camera(snap := false, delta := 1.0 / 60.0) -> void:
    if camera_locked:
        return
    var desired := DEFAULT_FOCUS
    if follow_enabled and is_instance_valid(player):
        desired.x = clampf(player.position.x + ACTOR_FOCUS_OFFSET.x, CAMERA_FOCUS_BOUNDS.position.x, CAMERA_FOCUS_BOUNDS.end.x)
        desired.z = clampf(player.position.z + ACTOR_FOCUS_OFFSET.z, CAMERA_FOCUS_BOUNDS.position.y, CAMERA_FOCUS_BOUNDS.end.y)
    var weight := 1.0 - exp(-CAMERA_FOLLOW_SPEED * maxf(delta, 0.0))
    camera_focus = desired if snap else camera_focus.lerp(desired, weight)
    camera.position = camera_focus + CAMERA_OFFSET
    camera.look_at(camera_focus,Vector3.UP)
    update_focus()
    visibility_guard.update(camera,player,delta,snap)

func update_focus() -> void:
    # DoF distances are view-space depth, not radial distance. A full billboard
    # occupies one depth plane, so this protects the entire original silhouette.
    var focus_distance := -camera.to_local(player.global_position).z
    attributes.dof_blur_near_distance = maxf(1.0,focus_distance - float(effect_parameters.dof_near_margin))
    attributes.dof_blur_near_transition = effect_parameters.dof_near_transition
    # Fine vegetation clusters remain readable through the middle forest rows;
    # a longer, gentler falloff separates distant planes without erasing pixels.
    attributes.dof_blur_far_distance = focus_distance + float(effect_parameters.dof_far_margin)
    attributes.dof_blur_far_transition = effect_parameters.dof_far_transition
    attributes.dof_blur_amount = effect_parameters.dof_amount

func _process(delta: float) -> void:
    if not frozen:
        elapsed += delta
        update_camera(false, delta)
        cloud_lighting.tick(delta)
        global_lighting.tick(delta)
        backdrop.tick(delta)
    # Keep both native lighting branches in sync, including frozen GPU probes.
    cloud_lighting.sync_sun_lights()
    backdrop.update_frame()
    refresh_hud()

func _physics_process(delta: float) -> void:
    if not route_running or frozen:
        return
    route_elapsed += delta
    route_sample_clock += delta
    if route_sample_clock >= .2:
        route_sample_clock = 0.0
        route_trajectory.append([snappedf(route_elapsed,.001),player.position.x,player.position.y,player.position.z,route_index])
    if route_elapsed > 110.0 or player.position.y < -1.0:
        stop_route("failed")
        return
    var remaining := route_points[route_index] - player.position
    if Vector2(remaining.x,remaining.z).length() < .25:
        route_index += 1
        if route_index >= route_points.size():
            stop_route("completed")
            return
        remaining = route_points[route_index] - player.position
    player.scripted_direction = Vector2(remaining.x,remaining.z).normalized()

func _input(event: InputEvent) -> void:
    # Mouse drags and arrow-key edits must not also walk the character. Clicking
    # outside the panel releases slider focus; hiding the panel does likewise.
    if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT and is_instance_valid(panel) and not panel.get_global_rect().has_point(event.position):
        _release_tuning_focus()

func _release_tuning_focus() -> void:
    var focus := get_viewport().gui_get_focus_owner()
    if focus != null and effect_sliders.values().has(focus):
        focus.release_focus()

func _on_tuning_focus_entered() -> void:
    if route_running:
        stop_route()
    _controls_before_tuning = player.controls_enabled
    player.controls_enabled = false

func _on_tuning_focus_exited() -> void:
    if is_instance_valid(player):
        player.controls_enabled = _controls_before_tuning

func set_control_panel_visible(value: bool) -> void:
    panel.visible = value
    if not value:
        _release_tuning_focus()

func start_route() -> void:
    _release_tuning_focus()
    route_running = true
    route_index = 0
    route_elapsed = 0.0
    route_sample_clock = 0.0
    route_trajectory.clear()
    route_result = {}
    player.controls_enabled = true
    player.scripted_input = true
    player.scripted_direction = Vector2.ZERO
    refresh_hud()

func stop_route(reason := "cancelled") -> void:
    route_running = false
    player.scripted_input = false
    player.scripted_direction = Vector2.ZERO
    route_result = {"status":reason,"completed":reason=="completed","waypoints":route_index,"total_waypoints":route_points.size(),"elapsed_seconds":route_elapsed,"samples":route_trajectory.duplicate(true),"position":[player.position.x,player.position.y,player.position.z]}
    refresh_hud()

func _unhandled_input(event: InputEvent) -> void:
    if not event is InputEventKey or not event.pressed or event.echo:
        return
    if event.ctrl_pressed or event.alt_pressed or event.meta_pressed or event.shift_pressed:
        return
    var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
    if key in [KEY_W,KEY_A,KEY_S,KEY_D,KEY_UP,KEY_LEFT,KEY_DOWN,KEY_RIGHT]:
        _release_tuning_focus()
        if route_running:
            stop_route()
        return
    match key:
        KEY_T: set_time_preset("dusk" if time_preset=="day" else "day")
        KEY_N: set_feature("normals",not values.normals)
        KEY_B: set_feature("bloom",not values.bloom)
        KEY_O: set_feature("dof",not values.dof)
        KEY_V: set_feature("wind",not values.wind)
        KEY_P: set_feature("parallax",not values.parallax)
        KEY_R: set_feature("backdrop_normals",not values.backdrop_normals)
        KEY_H: set_feature("clouds",not values.clouds)
        KEY_L: set_feature("atmosphere",not values.atmosphere)
        KEY_J: set_feature("global_light",not values.global_light)
        KEY_G:
            if route_running: stop_route()
            else: start_route()
        KEY_M: set_control_panel_visible(not panel.visible)
        KEY_K: capture_frame()
        KEY_ESCAPE:
            if route_running: stop_route()
            elif exit_confirmation.visible: exit_confirmation.hide()
            elif panel.visible: set_control_panel_visible(false)
            else: request_quit()
        _: return
    get_viewport().set_input_as_handled()

func create_hud() -> void:
    overlay = CanvasLayer.new()
    add_child(overlay)
    var root_control := Control.new()
    root_control.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root_control.mouse_filter = Control.MOUSE_FILTER_IGNORE
    if ResourceLoader.exists(FONT_PATH):
        var theme := Theme.new()
        theme.default_font = load(FONT_PATH)
        theme.default_font_size = 18
        root_control.theme = theme
    overlay.add_child(root_control)
    var title := Label.new()
    title.text = "林间小村  ·  HD-2D 场景范例"
    title.position = Vector2(30,24)
    title.add_theme_font_size_override("font_size",28)
    title.add_theme_color_override("font_shadow_color",Color(0,0,0,.85))
    title.add_theme_constant_override("shadow_offset_x",2)
    title.add_theme_constant_override("shadow_offset_y",2)
    root_control.add_child(title)
    var hints := Label.new()
    hints.text = "WASD / 方向键 移动    M 控制台    G 自动游览    T 日光 / 黄昏    K 截图"
    hints.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
    hints.position = Vector2(30,-44)
    hints.add_theme_color_override("font_shadow_color",Color.BLACK)
    hints.add_theme_constant_override("shadow_offset_x",2)
    hints.add_theme_constant_override("shadow_offset_y",2)
    root_control.add_child(hints)
    preload("res://scripts/forest_hamlet/settings_panel.gd").build(self, root_control)
    exit_confirmation = ConfirmationDialog.new()
    exit_confirmation.title = "退出场景"
    exit_confirmation.dialog_text = "要退出林间小村吗？"
    exit_confirmation.confirmed.connect(func(): get_tree().quit())
    root_control.add_child(exit_confirmation)
    get_viewport().size_changed.connect(_layout_control_panel)
    _layout_control_panel()
    _refresh_cloud_tuning()

func select_settings_tab(id: String) -> bool:
    var index := _tab_ids.find(id)
    if index < 0 or not is_instance_valid(settings_tabs):
        return false
    _release_tuning_focus()
    settings_tabs.current_tab = index
    return true

func _layout_control_panel() -> void:
    if not is_instance_valid(panel):
        return
    var viewport_size := get_viewport().get_visible_rect().size
    var width := minf(470.0, maxf(280.0, viewport_size.x - 48.0))
    panel.position = Vector2(maxf(12.0,viewport_size.x - width - 24.0),80.0)
    panel.size = Vector2(width,maxf(240.0,minf(760.0,viewport_size.y - 148.0)))

func _refresh_cloud_tuning() -> void:
    if effect_sliders.is_empty():
        return
    for id in effect_sliders:
        var value: float = effect_parameters[id]
        if id == "cloud_contrast":
            value = cloud_lighting.contrast_strength
        elif id == "cloud_density":
            value = cloud_lighting.cloud_density
        var scale := 100.0 if id in ["cloud_contrast", "cloud_density"] else 1.0
        effect_sliders[id].set_value_no_signal(value * scale)
        effect_value_labels[id].text = preload("res://scripts/forest_hamlet/settings_panel.gd").value_text(id, value)
    var contrast := float(cloud_lighting.contrast_strength)
    if is_instance_valid(tuning_effect_label):
        tuning_effect_label.text = ("薄云遮光 %.1f%% · 厚云遮光 %d%%\n厚云保留 %d%% 直射光" % [contrast * 100.0 / 3.0,roundi(contrast * 100.0),roundi((1.0 - contrast) * 100.0)]) if values.clouds else "云影已关闭；开启后沿用当前参数。"
    if is_instance_valid(tuning_status_label):
        tuning_status_label.text = ("● 未保存 · " if _settings_dirty else "") + _cloud_tuning_note
        tuning_status_label.add_theme_color_override("font_color", Color(.93,.85,.55) if _settings_dirty else Color(.72,.81,.76))

func refresh_hud() -> void:
    if not is_instance_valid(status_label):
        return
    status_label.text = "月饰少女 · 原四方向动画 / 逐帧法线" + ("    游览 %d / %d" % [route_index+1,route_points.size()] if route_running else "    可随时行走与比较效果")
    for id in feature_buttons:
        feature_buttons[id].set_pressed_no_signal(values[id])
    for id in time_buttons:
        time_buttons[id].set_pressed_no_signal(id == time_preset)
    _refresh_cloud_tuning()

func request_quit() -> void:
    if route_running:
        stop_route()
    exit_confirmation.popup_centered(Vector2i(440,160))

func capture_frame() -> void:
    if DisplayServer.get_name() == "headless":
        return
    capture_counter += 1
    var destination := "user://forest-hamlet-captures"
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(destination))
    await RenderingServer.frame_post_draw
    var filename := "%s/%s-%d-%02d.png" % [destination,time_preset,Time.get_unix_time_from_system(),capture_counter]
    var error := get_viewport().get_texture().get_image().save_png(filename)
    status_label.text = "截图：" + ProjectSettings.globalize_path(filename) if error == OK else "截图保存失败：" + str(error)
    print("FOREST_SCREENSHOT ",filename," error=",error)

func framing_state() -> Dictionary:
    var viewport_size := camera.get_viewport().get_visible_rect().size
    # The union of the original 108 visible frames, independently measured in
    # the source pipeline. Project its corners using the intended full billboard.
    var pixels := Rect2(66.0, 14.0, 123.0, 227.0)
    var pivot := Vector2(128.0, 240.0)
    var screen_min := Vector2(INF, INF)
    var screen_max := Vector2(-INF, -INF)
    var sprite_scale: Vector3 = player.sprite.global_basis.get_scale()
    for point in [pixels.position, Vector2(pixels.end.x, pixels.position.y), pixels.end, Vector2(pixels.position.x, pixels.end.y)]:
        var local_pixel: Vector2 = point - pivot
        var position_3d: Vector3 = player.sprite.global_position + camera.global_basis.x * local_pixel.x * player.sprite.pixel_size * sprite_scale.x - camera.global_basis.y * local_pixel.y * player.sprite.pixel_size * sprite_scale.y
        var screen := camera.unproject_position(position_3d)
        screen_min = screen_min.min(screen)
        screen_max = screen_max.max(screen)
    var rect := Rect2(screen_min, screen_max - screen_min)
    var foot := camera.unproject_position(player.global_position) / viewport_size
    var depth := -camera.to_local(player.global_position).z
    return {"silhouette_rect":[rect.position.x / viewport_size.x, rect.position.y / viewport_size.y, rect.size.x / viewport_size.x, rect.size.y / viewport_size.y], "foot":[foot.x,foot.y], "view_depth":depth, "dof_near":attributes.dof_blur_near_distance, "dof_far":attributes.dof_blur_far_distance, "in_frame":Rect2(Vector2(12,12),viewport_size - Vector2(24,24)).encloses(rect), "camera_offset_length":CAMERA_OFFSET.length(), "fov":camera.fov, "pitch_degrees":-camera.rotation_degrees.x, "pixel_size":player.sprite.pixel_size}

func snapshot_state() -> Dictionary:
    return {"preset":time_preset,"features":values.duplicate(true),"player":[player.position.x,player.position.y,player.position.z],"camera":[camera.position.x,camera.position.y,camera.position.z],"normal_directions":player.normal_atlases.size(),"original_color_directions":player.color_atlases.size(),"route_running":route_running,"route_index":route_index,"framing":framing_state(),"tree_visibility":visibility_guard.snapshot(),"backdrop":backdrop.snapshot(),"clouds":cloud_lighting.snapshot(),"global_light":global_lighting.snapshot(),"glow":{"enabled":environment.glow_enabled,"intensity":environment.glow_intensity,"strength":environment.glow_strength,"threshold":environment.glow_hdr_threshold,"bloom":environment.glow_bloom,"hdr_scale":environment.glow_hdr_scale},"scene_settings":get_scene_settings(),"settings_dirty":_settings_dirty,"dof":{"amount":attributes.dof_blur_amount,"near_transition":attributes.dof_blur_near_transition,"far_transition":attributes.dof_blur_far_transition}}
