# 场景参数实时调节与完整保存 · r5

林间小村的中文控制台把景深、辉光、环境、云层与其他既有效果放在五个分页中。拖动滑块立即预览；点击「保存参数」后，下一次正常启动恢复整套设置。近景入口仍为 `make forest-close-run`，按 **M** 展开或收起面板。

本页定义 r5 的操作与验证合同。实现和测试均使用独立的 `scene-settings` profile；实际运行结果、AW/VGP 回执和截图应以本轮修订归档为准。本页不将尚未取得的运行、GPU 或人工审阅结果记为通过。

## 使用方法

1. 打开面板，选择「环境」「景深」「Glow」「云与光」或「其他」分页。初次打开保留云与光页，兼容原来的调云操作。
2. 拖动滑块查看即时变化；选中滑块后用左右方向键微调。面板内的数字表示当前预览值。
3. 选择「白天」或「黄昏」，设置数值以及需要的效果开关，再点「保存参数」。保存的是完整场景配置，包含 20 项数值、9 个效果开关和时段。
4. 「读取已保存」放弃尚未保存的预览并还原最近一次存档；「恢复默认」回到默认白天、默认数值及开启状态，之后仍需保存才会替换下次启动配置。

界面显示当前是否存在未保存的更改。调节数值、切换时段或效果、关闭面板、退出场景都不会自动写入个人设置。一个效果关闭时，其数值仍会保留，重新开启后使用同一组参数。面板允许滚动，在 1920×1080 和 1280×720 窗口中均安排独立验证。

鼠标拖动和控件内的方向键用于调参，不同时移动角色。点击场景、使用 WASD 或收起面板后继续行走。既有快捷键保持：**T** 日光／黄昏、**O** 景深、**B** 辉光、**H** 云影、**J** 全局光变、**L** 体积光、**R** 雪山法线、**P** 远景视差、**N** 地面法线、**V** 草木微风。

## 参数范围与实际含义

### 景深

景深使用 Godot 原生相机属性。清晰区跟随角色在相机空间中的深度，角色、镜头移动后仍保持以人物为中心；参数不会移动相机或改变角色比例。

| 参数 | 范围 | 默认 | 含义 |
|---|---|---|---|
| 模糊量 `dof_amount` | 0–0.30 | 0.035 | 近、远两端共用的原生模糊强度 |
| 近景清晰余量 `dof_near_margin` | 0.5–15 m | 5 m | 从角色深度向镜头方向保留的清晰空间 |
| 近景过渡 `dof_near_transition` | 0.1–20 m | 3 m | 近端从清晰到模糊的过渡距离 |
| 远景清晰余量 `dof_far_margin` | 0.5–40 m | 10 m | 从角色深度向远处保留的清晰空间 |
| 远景过渡 `dof_far_transition` | 0.1–40 m | 16 m | 远端从清晰到模糊的过渡距离 |

### 辉光

辉光直接调整已有 `WorldEnvironment` 的 Glow，沿用其混合方式和层级。强度、扩散和阈值具有不同职责，实际影响以画面为准；这些数值不代表屏幕像素按相同比例变亮。

| 参数 | 范围 | 默认 | 含义 |
|---|---|---|---|
| 强度 `glow_intensity` | 0–2 | 0.42 | 辉光结果对画面的贡献 |
| 扩散强度 `glow_strength` | 0–2 | 0.85 | 原生 Glow 扩散强度 |
| 泛光 `glow_bloom` | 0–1 | 0.025 | 基础 Bloom 分量 |
| HDR 阈值 `glow_hdr_threshold` | 0–4 | 0.95 | 进入高亮辉光的亮度门槛 |
| HDR 缩放 `glow_hdr_scale` | 0.1–4 | 1.6 | 超过阈值的高亮辉光响应 |

### 环境、云层与其他效果

| 参数 | 范围 | 默认 | 含义 |
|---|---|---|---|
| 曝光 `exposure` | 0.25–2.5 | 1 | 色调映射曝光 |
| 画面对比 `contrast` | 0.5–1.5 | 1.06 | 全画面的颜色对比，不等同于云的最大遮光 |
| 饱和度 `saturation` | 0–1.5 | 0.98 | 全画面颜色饱和度 |
| 云层透光对比 `cloud_contrast` | 0–80% | 30% | 最厚云层对太阳直射光的最大削弱量 |
| 云层密度 `cloud_density` | 0–100% | 50% | 自然云场的覆盖和厚薄分布 |
| 草木风力 `wind_strength` | 0–0.16 | 0.06 | 已有植被风动强度 |
| 远景视差 `parallax_strength` | 0–1 | 0.35 | 已有整块雪山背景的视差强度 |
| 雾密度倍率 `fog_density_scale` | 0–3 | 1 | 日光／黄昏基础雾及体积雾密度的倍率 |
| 太阳波动 `sun_variation` | 0–50% | 18% | 独立全局光变的太阳能量振幅上限 |
| 环境光波动 `ambient_variation` | 0–30% | 10% | 独立全局光变的环境补光振幅上限 |

日光／黄昏会改变各自基础灯光和雾色，保留已经调好的效果数值。全局光变继续沿用既有种子和时间相位，振幅是理论边界，并不表示每个周期必达极值。关闭全局光变后恢复时段基础能量；重新开启使用保存的振幅。云层 30% 默认遮光仍对应薄云约 10%、厚云 30% 的既有行为；80% 最大遮光仍保留至少 20% 太阳直射光。

## 保存格式与旧配置迁移

设置继续使用 `user://forest-hamlet-clouds.cfg`。r5 增加 `[scene] schema_version=2`，时段保存在 `[scene]`，九个开关保存在 `[features]`，其余数值保存在 `[effects]`；原 `[clouds] schema_version=1`、`max_attenuation`、`density` 保留，兼容旧的云参数读取方式。

只有 `[clouds]` 的旧配置在读取时补入其他效果的显式默认值。原来保存的 **0.7 透光对比、0.48 密度**会继续作为 70%／48% 使用，不按新滑块步长重新量化。读取迁移不改写旧文件；下一次点击保存才写出含全部效果的新版配置。

读取先验证整份配置，再一次性应用。未知字段、错误类型、非有限数值、不支持的版本或缺少必要的云参数都会拒绝整份加载，并保留当前画面。合法的有限数值按范围夹取；新增可选字段缺失时使用显式默认值。保存使用同目录临时文件和原子重命名；失败会显示提示并保留原存档和当前预览。

正常启动仅在该场景为 `SceneTree.current_scene` 且 `cloud_settings_enabled` 开启时自动读取。脚本式测试与 GPU 捕获设置独立输出路径，关闭个人设置自动读取；自动恢复测试使用隔离的测试配置和新的场景实例。生产验证不应写入、迁移或重置真实个人存档。

## 运行接口与兼容边界

`scene_settings.gd` 负责默认值、范围、整份校验与文件读写，不接触节点或渲染器；`settings_panel.gd` 构建中文分页控件。`scene.gd` 负责把完整配置应用到已有相机、环境、云层、全局光变、植被和背景；提供 `get_scene_settings()`、`apply_scene_settings()`、`set_effect_parameter()`、`save_scene_settings()`、`load_scene_settings()` 和 `reset_scene_settings()`。

既有 `set_time_preset()`、`set_feature()`、云层 setter、`save_cloud_tuning()`、`load_cloud_tuning()`、`reset_cloud_tuning()` 以及旧快照字段保留。云层专用重置仍只重置两项云参数；完整重置使用新的场景接口。人物位置、路线进度、动画相位和镜头跟随状态不属于本次持久化参数。

## 独立验证与 AW / VGP 来源链

| 标识 | r5 值 |
|---|---|
| Profile | `scene-settings` |
| Run | `forest-hamlet-20261022-scene-settings-r5-final` |
| Native snapshot | `scene-settings-native-r5-final` |
| 配置 | `art/inputs/forest-hamlet/scene-settings-r5/workbench-project.yaml` |
| 技术证据目录 | `build/forest-hamlet/scene-settings-r5-final` |
| 前一运行 | `forest-hamlet-20261022-cloud-tuning-r4` |
| 修订归档目录 | `docs/forest-hamlet/revisions/scene-settings-r5-20261022` |

首次原生尝试 `forest-hamlet-20261022-scene-settings-r5` 的 Godot 测试已通过 89 项检查，但测试入口当时只识别 `--forest-output=`，没有识别 AW 传入的 `--output=`。报告因此写到默认目录，AW `godot.verify` 在收集指定制品时找不到报告并判定运行失败；这次尝试不记作 AW 完成或交付通过。该失败运行和 `scene-settings-native-r5` 快照完整保留。后续测试入口同时支持两种输出参数，使用上表新的 `-final` 运行与快照身份重新验证，不修补旧回执、旧快照或放宽制品要求。

执行顺序：

```sh
make forest-scene-settings-test
make forest-scene-settings-capture
make test
# 把这次 make test 的真实退出状态和耗时保存为证据目录的 make-test-report.json。
make forest-scene-settings-aw
make forest-scene-settings-vgp
make forest-scene-settings-archive
```

等价的工作流命令为：

```sh
python3 tools/forest_hamlet/verify_atmosphere_godot_aw.py --profile scene-settings
python3 tools/forest_hamlet/process_atmosphere_aw.py --profile scene-settings
python3 tools/forest_hamlet/register_atmosphere_vgp.py --profile scene-settings --previous-run-id forest-hamlet-20261022-cloud-tuning-r4
python3 tools/forest_hamlet/archive_cloud_tuning_evidence.py --profile scene-settings
```

新合同要求三份专用报告和 **15 张原始 PNG**：景深关闭／加强、辉光关闭／加强、黄昏保存／新实例恢复、五个 1080p 分页面板、720p 景深与辉光面板及鼠标输入后画面。GPU 捕获在独立 SubViewport 中创建新实例，再通过「读取已保存」证明完整画面恢复；真正的根场景 `current_scene` 自动读取由无窗口合同单独验证。报告必须绑定同一个 `runtime-fingerprint.json` 和 `source-fingerprint.json`；后者还绑定测试、捕获、像素分析、运行器和 AW/VGP/归档驱动的真实源码字节。像素报告必须逐张绑定原始 GPU PNG，不能用旧截图或未执行的断言代替。`test` 必须先于同目录的 `capture`，运行器会拒绝使用不同来源指纹的先前运行报告。

新 profile 还把当前 `assets/**` 的完整文件集合、SHA-256 和字节数与 r4 原生快照逐项比较，验证原角色帧、法线、蒙版、房屋模型、地面、植被和雪山图片没有变化。原雪山母图仍使用既有固定摘要核验。比较使用不可变 r4 快照，并通过 r4 原生摘要记录绑定其身份；不会要求旧代码在修改后的工作树重新通过原来的源码指纹。

AW 原生 `godot.verify` 在新的不可变快照中执行专用无窗口运行合同，`delivery export` / `delivery verify` 选择和验证实际冻结输入。外部 GPU 截图与像素分析由工程独立执行并冻结，不能表述为 AW 渲染或 AW 完成 GPU 审阅。VGP 只为既有雪山 Asset 追加 r4 后继候选与审阅轮次；状态保持 `concept_design / pending_review`，不创建人工决定或阶段准入。

所有 r4 及更早快照、证据与审批历史保留。r5 无窗口运行合同记录自己的六路点物理路线回归结果；本轮 15 张截图集中于 UI、效果和保存恢复，没有重跑旧 GPU 路线截图组或云透光标定。源码或证据冻结后若再次变化，必须使用新的运行与快照身份。技术检查通过与用户视觉批准分别记录。
