extends RefCounted
## Runtime controls only. Values, persistence and lighting belong to the scene.
const Settings = preload("res://scripts/forest_hamlet/scene_settings.gd")
const ACCENT := Color(0.93, 0.85, 0.55)
const MUTED := Color(0.72, 0.81, 0.76)

static func build(scene: Node3D, parent: Control) -> void:
    var panel := PanelContainer.new()
    panel.name = "SceneEffectsPanel"
    var style := StyleBoxFlat.new()
    style.bg_color = Color(0.035, 0.065, 0.05, 0.95)
    style.content_margin_left = 16
    style.content_margin_right = 16
    style.content_margin_top = 12
    style.content_margin_bottom = 12
    style.set_corner_radius_all(8)
    panel.add_theme_stylebox_override("panel", style)
    parent.add_child(panel)
    scene.panel = panel
    var stack := VBoxContainer.new()
    stack.add_theme_constant_override("separation", 8)
    panel.add_child(stack)
    var heading := HBoxContainer.new()
    stack.add_child(heading)
    var title := Label.new()
    title.text = "场景调节"
    title.add_theme_font_size_override("font_size", 24)
    title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    heading.add_child(title)
    _action(heading, "收起 M", scene.set_control_panel_visible.bind(false))
    _note(stack, "拖动即时生效 · 点击场景或按 WASD 继续行走")
    var time_row := HBoxContainer.new()
    time_row.add_theme_constant_override("separation", 8)
    stack.add_child(time_row)
    for pair in [["day", "白天"], ["dusk", "黄昏"]]:
        var button := _action(time_row, pair[1], scene.set_time_preset.bind(pair[0]))
        button.toggle_mode = true
        scene.time_buttons[pair[0]] = button
    _action(time_row, "自动漫游 G", func():
        if scene.route_running:
            scene.stop_route()
        else:
            scene.start_route())
    var tabs := TabContainer.new()
    tabs.name = "EffectCategories"
    tabs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
    tabs.get_tab_bar().focus_mode = Control.FOCUS_NONE
    tabs.get_tab_bar().add_theme_font_size_override("font_size", 16)
    tabs.tab_changed.connect(func(_index: int): scene._release_tuning_focus())
    stack.add_child(tabs)
    scene.settings_tabs = tabs
    var pages: Dictionary = {}
    for pair in [["environment", "环境"], ["dof", "景深"], ["glow", "Glow"], ["clouds", "云与光"], ["other", "其他"]]:
        var scroll := ScrollContainer.new()
        scroll.name = pair[1]
        scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
        scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
        scroll.follow_focus = true
        tabs.add_child(scroll)
        var margin := MarginContainer.new()
        margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        margin.add_theme_constant_override("margin_left", 8)
        margin.add_theme_constant_override("margin_right", 10)
        margin.add_theme_constant_override("margin_top", 10)
        margin.add_theme_constant_override("margin_bottom", 10)
        scroll.add_child(margin)
        var content := VBoxContainer.new()
        content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        content.add_theme_constant_override("separation", 8)
        margin.add_child(content)
        pages[pair[0]] = content
        scene.setting_scrolls[pair[0]] = scroll
    scene.tuning_scroll = scene.setting_scrolls.clouds

    var environment_page: VBoxContainer = pages.environment
    _note(environment_page, "白天与黄昏会同时改变太阳、天空和灯火。\n下方强度在切换时段后继续保留。")
    _slider(scene, environment_page, "exposure", "曝光", "画面的整体明亮程度。")
    _slider(scene, environment_page, "contrast", "对比度", "调整明暗层次，不改变云层透光比例。")
    _slider(scene, environment_page, "saturation", "色彩饱和度", "0 为灰度，1 为原始色彩强度。")
    _feature(scene, environment_page, "atmosphere", "体积光  L")
    _slider(scene, environment_page, "fog_density_scale", "雾浓度", "相对白天或黄昏原有雾量的倍数；同时调节远景雾和体积雾。")

    var dof_page: VBoxContainer = pages.dof
    _feature(scene, dof_page, "dof", "启用景深  O")
    _note(dof_page, "焦点始终跟随角色。缩小清晰范围会加强空间分层，角色保持清晰。")
    _slider(scene, dof_page, "dof_amount", "模糊强度", "整体景深模糊量；0 为清晰。")
    _slider(scene, dof_page, "dof_near_margin", "角色前方清晰范围", "角色向镜头方向保留清晰的距离；数值越小，前景越容易模糊。")
    _slider(scene, dof_page, "dof_near_transition", "前景柔化过渡", "由清晰到模糊的过渡距离；数值越大，变化越柔和。")
    _slider(scene, dof_page, "dof_far_margin", "角色后方清晰范围", "角色后方保留清晰的距离；数值越小，中远景越容易模糊。")
    _slider(scene, dof_page, "dof_far_transition", "远景柔化过渡", "远景由清晰到模糊的过渡距离。")

    var glow_page: VBoxContainer = pages.glow
    _feature(scene, glow_page, "bloom", "启用 Glow 光晕  B")
    _note(glow_page, "降低高光门槛会让更多亮部泛光；黄昏时可以观察灯火边缘。")
    _slider(scene, glow_page, "glow_intensity", "光晕亮度", "光晕加入画面时的整体强度。")
    _slider(scene, glow_page, "glow_strength", "扩散强度", "控制发光区域向周围扩散的强度。")
    _slider(scene, glow_page, "glow_bloom", "暗部泛光", "让较暗的区域也参与泛光；增大会形成整体柔光。")
    _slider(scene, glow_page, "glow_hdr_threshold", "高光门槛", "数值越低，参与泛光的明亮区域越多。")
    _slider(scene, glow_page, "glow_hdr_scale", "高光增益", "超过高光门槛部分的泛光增益。")

    var cloud_page: VBoxContainer = pages.clouds
    _feature(scene, cloud_page, "clouds", "流动云影  H")
    _slider(scene, cloud_page, "cloud_contrast", "透光对比 · 最大遮光", "厚云最多削弱的直射光比例；薄云约为它的三分之一。")
    var cloud_hint := _note(cloud_page, "")
    cloud_hint.add_theme_color_override("font_color", ACCENT)
    scene.tuning_effect_label = cloud_hint
    _slider(scene, cloud_page, "cloud_density", "云层密度", "0% 无云，50% 为原有分布，100% 满布。")
    _note(cloud_page, "0% 无云 · 50% 默认分布 · 100% 满布")
    cloud_page.add_child(HSeparator.new())
    _feature(scene, cloud_page, "global_light", "独立全局光变  J")
    _note(cloud_page, "平滑、不规则地改变日光与环境光，独立于云的遮挡。")
    _slider(scene, cloud_page, "sun_variation", "日光变化幅度", "日光基准亮度上下浮动的最大比例；0 停止此通道变化。")
    _slider(scene, cloud_page, "ambient_variation", "环境光变化幅度", "环境光基准亮度上下浮动的最大比例。")

    var other_page: VBoxContainer = pages.other
    _feature(scene, other_page, "wind", "草木微风  V")
    _slider(scene, other_page, "wind_strength", "草木摆动幅度", "控制图像植被的风动位移。")
    _feature(scene, other_page, "parallax", "远景视差  P")
    _slider(scene, other_page, "parallax_strength", "远景视差强度", "角色横向行走时，雪山背景与近景之间的相对位移。")
    _feature(scene, other_page, "backdrop_normals", "雪山法线光照  R")
    _feature(scene, other_page, "normals", "地面法线光照  N")
    _note(other_page, "开关和滑块数值会一起保存。关闭效果后，数值保留供下次开启。")
    var status := _note(other_page, "")
    scene.status_label = status

    # Save/load/reset never scroll away, even in a 720p window.
    stack.add_child(HSeparator.new())
    var actions := HBoxContainer.new()
    actions.add_theme_constant_override("separation", 8)
    stack.add_child(actions)
    scene.tuning_save_button = _action(actions, "保存参数", scene.save_scene_settings)
    scene.tuning_load_button = _action(actions, "读取已保存", scene.load_scene_settings)
    scene.tuning_reset_button = _action(actions, "恢复默认", scene.reset_scene_settings)
    scene.tuning_reset_button.tooltip_text = "恢复全部默认效果；只有再次保存才会替换存档。"
    scene.tuning_status_label = _note(stack, "")
    scene.tuning_status_label.custom_minimum_size.y = 40
    # Keep cloud controls in the initial view for existing users and tooling.
    tabs.current_tab = scene._tab_ids.find("clouds")

static func _action(parent: HBoxContainer, title: String, action: Callable) -> Button:
    var button := Button.new()
    button.text = title
    button.focus_mode = Control.FOCUS_NONE
    button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    button.add_theme_font_size_override("font_size", 16)
    button.pressed.connect(action)
    parent.add_child(button)
    return button

static func _note(parent: VBoxContainer, title: String) -> Label:
    var label := Label.new()
    label.text = title
    label.add_theme_font_size_override("font_size", 14)
    label.add_theme_color_override("font_color", MUTED)
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    parent.add_child(label)
    return label

static func _feature(scene: Node3D, parent: VBoxContainer, id: String, title: String) -> void:
    var toggle := CheckButton.new()
    toggle.name = id.to_pascal_case() + "Enabled"
    toggle.text = title
    toggle.focus_mode = Control.FOCUS_NONE
    toggle.add_theme_font_size_override("font_size", 16)
    toggle.button_pressed = scene.values[id]
    toggle.toggled.connect(func(enabled: bool): scene.set_feature(id, enabled))
    parent.add_child(toggle)
    scene.feature_buttons[id] = toggle

static func _slider(scene: Node3D, parent: VBoxContainer, id: String, title: String, hint: String) -> void:
    var row := HBoxContainer.new()
    parent.add_child(row)
    var label := Label.new()
    label.text = title
    label.tooltip_text = hint
    label.add_theme_font_size_override("font_size", 16)
    label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    row.add_child(label)
    var value_label := Label.new()
    value_label.custom_minimum_size.x = 72
    value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    value_label.add_theme_font_size_override("font_size", 16)
    value_label.add_theme_color_override("font_color", ACCENT)
    row.add_child(value_label)
    var slider := HSlider.new()
    slider.name = id.to_pascal_case()
    var spec: Dictionary = Settings.PARAMETER_SPECS[id]
    var scale := 100.0 if id in ["cloud_contrast", "cloud_density"] else 1.0
    slider.min_value = float(spec.min) * scale
    slider.max_value = float(spec.max) * scale
    slider.step = float(spec.step) * scale
    slider.custom_minimum_size = Vector2(160, 28)
    slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    slider.tick_count = 5
    slider.ticks_on_borders = true
    slider.tooltip_text = hint
    slider.focus_entered.connect(scene._on_tuning_focus_entered)
    slider.focus_exited.connect(scene._on_tuning_focus_exited)
    slider.value_changed.connect(func(value: float): scene.set_effect_parameter(id, value / scale))
    parent.add_child(slider)
    scene.effect_sliders[id] = slider
    scene.effect_value_labels[id] = value_label
    if id in ["cloud_contrast", "cloud_density"]:
        var legacy := "contrast" if id == "cloud_contrast" else "density"
        scene.tuning_sliders[legacy] = slider
        scene.tuning_value_labels[legacy] = value_label

static func value_text(id: String, value: float) -> String:
    if id in ["cloud_contrast", "cloud_density", "parallax_strength"]:
        return "%d%%" % roundi(value * 100.0)
    if id in ["sun_variation", "ambient_variation"]:
        return "±%d%%" % roundi(value * 100.0)
    if id == "dof_amount":
        return "%.1f%%" % (value * 100.0)
    if id.begins_with("dof_"):
        return "%.1f m" % value
    if id == "wind_strength":
        return "%.1f cm" % (value * 100.0)
    if id in ["glow_bloom"]:
        return "%.3f" % value
    if id in ["exposure", "fog_density_scale"]:
        return "%.2f ×" % value
    return "%.2f" % value
