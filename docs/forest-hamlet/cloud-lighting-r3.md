# r3 · 透光云影与原生太阳分配

本轮把云的空间遮挡限制在太阳直射能量的一部分：薄云目标削弱约 **10%**，最厚云最多削弱 **30%**，云外完整透光，边缘连续过渡。这里的百分比针对同一全局光变时刻、同一受光面的太阳直射贡献；环境补光、发光材质、天空反射、体积雾和色调映射仍参与最终画面，因此最终 PNG 的 sRGB 像素不能直接按 90% / 70% 比值验收。

运行实现是 `scripts/forest_hamlet/cloud_lighting.gd` 和 `shaders/forest_hamlet/cloud_occluder.gdshader`。本页记录 r3 实现与测量口径；[r1/r2 云影技术记录](cloud-lighting.md) 和 [不规则全局光照](global-lighting.md) 保留其历史版本，不改写已冻结证据。本轮没有修改雪山原画、背景板、角色比例、相机或植被素材。

## 1. 三个灯节点，两路场景直射光

原 `main_light` 继续作为太阳方向、颜色、总能量和昼夜预设的唯一来源，原 `global_lighting.gd` 仍向它写入总能量。云控制器把源灯的 `sky_mode` 设为 `DirectionalLight3D.SKY_MODE_SKY_ONLY`，让天空仍获得一个完整太阳；两个新增方向光设为 `SKY_MODE_LIGHT_ONLY`，只负责场景光照。

| 节点 / 控制器字段 | `sky_mode` | `light_energy` | 原生阴影投射对象 |
| --- | --- | --- | --- |
| 原太阳 / `sun` | `SKY_MODE_SKY_ONLY`（2） | 权威总能量 `E(t)` | 源灯不参与场景直射 |
| `SunBase70` / `base_sun` | `SKY_MODE_LIGHT_ONLY`（1） | `0.70 × E(t)` | 原有实体，排除云专用层 |
| `SunCloud30` / `cloud_sun` | `SKY_MODE_LIGHT_ONLY`（1） | `0.30 × E(t)` | 原有实体，加云专用层 |

云网格独占第 20 层：`CLOUD_LAYER_MASK = 1 << 19 = 524288`。基础光的 `shadow_caster_mask` 为源灯投影掩码去掉该位；云分支为原有投影位加该位。云网格不会同时留在默认第 1 层，否则它仍可能被基础分支收进阴影图。两个分支保留源灯的 `light_cull_mask`，原有地面、房屋、像素植被和角色继续接收原生光照。

此处必须使用 **`shadow_caster_mask`** 筛选投影者。`light_cull_mask` 筛选受光对象，不能替代投影者掩码。两个分支的 `shadow_opacity` 均为 `1.0`，并复制源灯的阴影开关、偏移、法线偏移、阴影距离、级联设置、pancake、软阴影与角直径等参数。房屋或树木的实体阴影会同时挡住两个分支，因此不会出现以 70% 无阴影补光填亮所有实体阴影的行为。两个独立阴影图在半影采样上不保证逐像素相同，须用实际画面检查其连续性和实体阴影对比。

`sync_sun_lights()` 每次从源灯计算两路能量，不在旧分支能量上继续乘比例。重复调用不会累积变暗。关闭云只隐藏云投影网格，两个实体投影分支保持存在，便于同一灯光结构下做云开关对照。

## 2. 密度、透明覆盖与直射透光率

云网格仍位于世界上空 24 m，宽 220 m，中心 Z 为 −8 m，细分为 32 × 32 个四边形。它使用 `SHADOW_CASTING_SETTING_SHADOWS_ONLY`，不出现在主相机彩色画面中，也不参与碰撞。网格的局部层只允许云分支把它写入原生阴影深度。

密度图沿用固定种子 `20261022` 的原生 FastNoiseLite：256 × 256、单通道 L8、三层 FBM，基础频率 0.016、lacunarity 2.0、gain 0.42。四个平移噪声样本平滑混合为周期场；同步生成避免首帧捕获先于纹理就绪。世界周期为 96 m，风速为 `(0.32, 0.13)` m/s，相位为 `(0.65, 0.0)`。原始密度字节的 SHA-256 会记录在快照中。

设纹理线性采样得到的密度为 `d`。自然模式下的实际 shader 使用两个 `smoothstep`：

```text
edge = smoothstep(mask_cutoff - mask_edge_width, mask_cutoff, d)
body = smoothstep(mask_cutoff, mask_cutoff + mask_body_width, d)
attenuation = edge × mix(0.10, 0.30, body)
ALPHA = clamp(attenuation / 0.30, 0, 1)
```

默认 `mask_cutoff = 0.515`、`mask_edge_width = 0.12`、`mask_body_width = 0.18`：

| 密度区间 | 目标太阳直射削弱 | 云分支中的含义 |
| --- | --- | --- |
| ≤ 0.395 | 0% | 云外，零阻挡 |
| 0.395–0.515 | 平滑 0–10% | 云边缘进入薄云 |
| 0.515–0.695 | 平滑 10–30% | 薄云变为厚云 |
| ≥ 0.695 | 30% | 完全遮住云分支 |

如果过滤后的云分支阻挡覆盖率为 `a`，直接受光面的总太阳透过率为：

```text
T_sun = 0.70 + 0.30 × (1 − a) = 1 − 0.30 × a
```

因此薄云目标 `ALPHA = 1/3` 对应预计 `T_sun ≈ 0.90`；厚云 `ALPHA = 1` 对应 `T_sun = 0.70`。天空、环境补光和源灯总能量不参与这个空间遮罩。独立全局光变仍可改变 `E(t)`；它与云本身的削弱比例是两项独立效果。

shader 写入 `ALPHA_HASH_SCALE` 以使用原生 alpha hash 投影路径，不使用普通 alpha blend，也不再把密度阈值变成整个太阳的二值遮挡。`alpha_hash_scale = 1.0` 只控制抖动图案尺度；透光率由 `ALPHA` 和 70% / 30% 能量分配共同决定。它没有额外逐帧随机种子。

**薄云约 90% 是区域平均透光目标；先行原型已测得三个区域约 89.61%–89.69%，详见末节。** 本轮使用固定线性色调映射的 8-bit PNG，经标准 sRGB 逆变换估计线性亮度，并以半能量控制检验该方法；不读取原生 HDR 缓冲。Alpha hash 对单个阴影深度样本实行二值保留 / 丢弃；半影和阴影过滤后才得到覆盖均值。某个像素仍可能偏离 90%，不能仅凭 uniform 值声称已达到目标或没有颗粒。当前保留场景已有的 `SHADOW_QUALITY_SOFT_ULTRA` 和 0.65° 太阳角直径，最终质量以自然密度画面、固定接收面测试及移动观察为准。

## 3. 接口与更新顺序

初始化方式沿用原接口：

```gdscript
var clouds = preload("res://scripts/forest_hamlet/cloud_lighting.gd").new()
add_child(clouds)
clouds.configure(main_light, environment)
clouds.set_preset("day")
clouds.set_enabled(true)
```

| 方法 | 行为 |
| --- | --- |
| `configure(sunlight, world_environment)` | 建立密度纹理、云投影网格和两个灯分支，应用当前参数 |
| `sync_sun_lights()` | 读取源灯，立即同步两分支方向、颜色、能量、受光 / 投影掩码和阴影 / 体积雾参数 |
| `set_enabled(value)` | 只切换云投影网格可见性，并同步灯光；保留两个实体投影分支 |
| `set_atmosphere_enabled(value)` | 独立切换原生体积雾 |
| `set_motion_enabled(value)` | 控制 `tick()` 是否推进云时钟 |
| `set_time(seconds)` | 将非负云时钟立即写入 shader，不依赖全局 shader `TIME` |
| `tick(delta)` | 允许运动时推进云时钟；控制器没有独立 `_process()` |
| `set_preset("day" / "dusk")` | 更新体积雾参数与源灯体积雾系数，再同步分支；无效名称返回 `false` |
| `set_pattern(cutoff, span_m, velocity)` | 更新密度阈值、周期和风速；分别限制在 0.05–0.95、24–192 m、速度长度 ≤ 3 m/s |
| `set_uniform_attenuation(value)` | 测试用：在同一实际 shader 内覆盖空间密度所得的衰减 |
| `cloud_ray_sample(world_point, seconds = -1)` | 给出投影射线与云平面的交点及 CPU 密度 / 目标覆盖诊断 |
| `snapshot()` | 返回当前状态、密度配置、两分支实际原生灯属性及射线诊断 |

场景一帧中的必要顺序为：先更新独立全局光变的源灯总能量，再调用 `sync_sun_lights()`，然后提交渲染。场景冻结时停止各时钟的 `tick()`，但仍调用 `sync_sun_lights()`；这样测试可以在冻结画面中修改源灯方向或总能量，并立即更新真实分支。昼夜预设和功能开关修改结束后也需要同步，避免只更新源灯或出现一帧延迟。

`set_time()` 修改的是云时钟；全局光变拥有自己的独立时钟。云 `set_time()` 本身不推进、重置或改变全局能量。`set_uniform_attenuation()` 返回 `void`，任意负值恢复自然密度；非负值限制在 `[0, 0.30]`，并立即写入材质：

```gdscript
clouds.set_uniform_attenuation(-1.0) # 自然密度
clouds.set_uniform_attenuation(0.0)  # 同几何 / 同 shader，全透明云层
clouds.set_uniform_attenuation(0.1)  # 同原生阴影路径，强制薄云
clouds.set_uniform_attenuation(0.3)  # 同原生阴影路径，强制厚云
```

均匀模式仍可读到原始噪声密度用于诊断，但实际 `attenuation` 由该 uniform 覆盖。它没有替换受光材质、叠加屏幕遮罩或处理捕获图像。

## 4. 全局光变、天空、雾与 Glow

日光太阳 / 环境补光基值仍为 1.45 / 0.55，黄昏为 1.15 / 0.40。`global_lighting.gd` 继续独立控制源灯和环境补光；云控制器读取已经变化的总太阳能量再分配，始终满足 `base_sun.light_energy + cloud_sun.light_energy = sun.light_energy`，仅有浮点误差。云网格的隐藏和均匀测试覆盖不会修改该总量。

源灯使用 `SKY_MODE_SKY_ONLY`，保留完整太阳能量与唯一的天空太阳；新增两个分支使用 `SKY_MODE_LIGHT_ONLY`，避免天空同时叠出两个太阳贡献。源灯原有的阴影配置保留为两分支的配置来源，但它自身只供天空使用。

体积雾沿用原预设：日光 / 黄昏密度 0.0030 / 0.0038，长度 78 m，各向异性 0.48，时间重投影混合 0.65。源灯的 `light_volumetric_fog_energy` 日光 / 黄昏分别为 3.2 / 4.2，两分支原样复制该系数。该参数本身乘在 `light_energy` 上，所以不会再额外乘 0.70 / 0.30，以免二次分配。体积雾通过两个真实场景光及其阴影获得透光变化；该光照效果仍须 GPU 场景对照检验。

Glow 由主场景拥有，r3 云控制器不覆盖其参数。远景雪山继续使用既有的法线重光照方案，其原画字节、背景构图、单板相对视差和材质没有在本轮改动。r3 不声称实现多层散射云或空间变化的烘焙环境光。

## 5. 可检查状态

`snapshot().light_split` 包含 `source`、`base70`、`cloud30` 三个节点快照，每项记录实际 `energy`、`sky_mode`、`shadow_caster_mask`、`light_cull_mask`、`shadow_enabled`、`shadow_opacity`、`volumetric_fog_energy`、颜色、方向、角直径、阴影模式 / 距离和可见性。

汇总字段为 `source_total_energy`、`total_direct_energy`、`energy_sum_error`、`cloud_layer_mask`、`ordinary_caster_mask`、`base_ratio`、`cloud_ratio`、`source_is_sky_only` 和 `real_scene_light_count`。最后一项表示两路场景直射光；它不把天空源灯计为第三路场景日光。

顶层还记录 `uniform_attenuation`、`attenuation_range = [0, 0.30]`、`cloud_body_attenuation_range = [0.10, 0.30]`、`direct_transmittance_bounds = [0.70, 1]`、`caster_layers`、`alpha_hash_scale`、密度参数、种子、时钟、mask SHA-256 和雾密度。这些是配置与结构诊断，不是像素测量结果。

`cloud_ray_sample()` 的 `requested_attenuation` 是密度或 uniform 给出的目标；`effective_attenuation` 在云关闭或射线未命中平面时为 0；`branch_blocked_coverage` 等于有效削弱除以 0.30；`expected_direct_transmittance` 等于 1 减有效削弱。保留的 `blocked` 字段现在仅表示存在非零云削弱，不能理解为完全遮光。

## 6. 实测方法与性能边界

透光比例使用实际 Forward+ GPU、固定相机、灰色 Lambert 接收面和一个实体遮挡块测试。专用测量场景关闭独立全局光变，使用 `TONE_MAPPER_LINEAR`、`tonemap_exposure = 1.0`、相机曝光倍率 1.0，并关闭自动曝光、环境补光、天空补光、反射贡献、常规雾、体积雾、Glow、SSAO、SSIL、SSR、GI 和颜色调整。受测区域预先确定，避开实体阴影、黑场及输出裁切；保留另一个实体阴影区域单独验收。

捕获保留八张未经改写的原始 8-bit PNG：零太阳暗场、完整太阳且云关闭、半太阳能量校准、同 shader 强制 0、强制薄云 0.10、冻结状态的薄云重复捕获、强制厚云 0.30，以及自然密度。只有暗场和半能量校准改变源太阳总能量；其余六张的总能量均为 1.0，且保持同一分支结构、方向、材质和机位。

**测量输出是经校准的 PNG 线性估计，不是原生 HDR 辐亮度读回。** 将每个通道的码值除以 255 得到 `s`，按标准 sRGB 逆变换计算：

```text
linear(s) = s / 12.92                         当 s ≤ 0.04045
linear(s) = ((s + 0.055) / 1.055) ^ 2.4      其他情况
Y = 0.2126 × R_linear + 0.7152 × G_linear + 0.0722 × B_linear
T_estimate = sum(Y_sample − Y_dark) / sum(Y_clear − Y_dark)
```

分子与分母使用相同接收面像素，先逆变换每通道、扣除实际零太阳暗场，再求区域和的比值。半太阳能量控制的估计结果应接近 0.50，验证该捕获链在所用亮度范围内具有预期线性关系；脚本预设允许误差为 0.015。半能量校准未通过时，不据此宣布薄 / 厚云透光比例通过。

量化误差按每个 8-bit 码值的 `±0.5` 四舍五入区间处理：先分别逆变换其上下界，再把样本、暗场和完整太阳基线的界限传播到比值。报告中的 `quantization_interval` 是该舍入模型下的保守估计区间，不包含一切潜在渲染或空间采样误差。厚云 0.70 目标必须落在实际量化区间内；不通过扩大厚云误差阈值来隐藏与 30% 上限的冲突。薄云均值的预设空间覆盖容差为 0.02，另报告逐像素分布、32 × 32 像素分块均值和标准差；冻结薄云的重复读回均值差须不大于 0.005。

普通游戏场景 PNG 继续用于自然云影、审美和空间一致性对照；它含有环境光、雾、Glow 等效果，不能直接套用上述专用测量场景的亮度比值。

薄云除均值外还需检查空间分布、低分位和颗粒；厚云需检查其直射削弱没有超过 30% 的结构目标。实体遮挡块用于验证两分支仍产生实体阴影，避免以弱化房屋 / 树影换取较亮云影。自然云模式需要在固定全局倍率下比较不同云时钟，并检查地面、屋面、人物、树冠和镜头移动中的噪点；环境雾和 Glow 继续使用独立对照。

本实现增加第二个真实方向光阴影分支，普通实体将参与两套原生太阳阴影计算。当前优先保留两个分支相同的实体阴影设置，没有以减少分级或降低阴影质量提前抵消成本。额外的阴影渲染和过滤会增加开销，具体帧时必须实际量测；本页不根据光源数量推算帧率，也不把运行检查耗时当作游戏帧率。

## 官方 API 依据

- [Godot 4.7 · Light3D](https://docs.godotengine.org/en/4.7/classes/class_light3d.html)：`shadow_caster_mask`、受光掩码、阴影不透明度和体积雾能量系数。
- [Godot 4.7 · DirectionalLight3D](https://docs.godotengine.org/en/4.7/classes/class_directionallight3d.html)：`sky_mode`、方向与级联阴影配置。
- [Godot 4.7 · StandardMaterial3D](https://docs.godotengine.org/en/4.7/tutorials/3d/standard_material_3d.html)：alpha hash 的覆盖方式与投影支持，普通 alpha blend 的限制。
- [Godot 4.7 · Spatial shaders](https://docs.godotengine.org/en/4.7/tutorials/shaders/shader_reference/spatial_shader.html)：`ALPHA`、`ALPHA_HASH_SCALE` 与原生光照输入。
- [Godot 4.7 · Volumetric fog](https://docs.godotengine.org/en/4.7/tutorials/3d/volumetric_fog.html)：Forward+ 体积光、原生灯光和阴影交互。

## 本轮先行原型实测与最终复验登记

本节冻结已完成的先行原型测量，不预先宣布最终交付快照通过。原型实际使用 **NVIDIA GeForce RTX 4070 SUPER、Forward+、1024 × 768**，保留八张原始 PNG；捕获的 **24 项检查**及独立像素分析的 **67 项检查**均通过。两个 JSON 报告的 `passed` 均为 `true`，没有失败项。上述代码 / shader SHA-256 已记录在捕获报告，数据来自实际原生云阴影，CPU 密度诊断不作为这些比例的来源。

薄云三个预先定义的接收面区域，每个包含 49,152 像素，测得：

| 区域 | 平均透光估计 | 平均削弱估计 | 32 × 32 像素分块均值的标准差 |
| --- | ---: | ---: | ---: |
| `upper_left` | 0.89632635（89.63%） | 10.37% | 0.00730708 |
| `center` | 0.89692456（89.69%） | 10.31% | 0.00669401 |
| `lower_left` | 0.89609746（89.61%） | 10.39% | 0.00606928 |

三个区域的冻结薄云重复捕获与首次捕获具有相同测量值。分块标准差约为 0.61–0.73 个百分点；逐像素标准差约为 0.02294–0.02533，说明细尺度覆盖仍有起伏。该结果支持薄云的区域平均目标和当前静态重复稳定性，**不承诺单个像素都只削弱 10%，也不以原图静帧结果承诺放大观察或任意移动镜头下完全无颗粒**。

厚云三个区域的透光估计均为 **0.69725654**。按实际 8-bit 码值传播的量化区间为 **[0.68249407, 0.71205134]**，包含结构目标 **0.70**。该读数应按量化范围解释，不能把 0.69725654 强行改写成精确 0.70000000，也不能据这一点估计把厚云描述为已证实超出 30% 的实际遮光。

半太阳能量控制测得 **0.49215860**，在预先设定的 0.50 ± 0.015 范围内；其量化区间 **[0.48066285, 0.50344670]** 也包含 0.50。强制透明云层的透光估计为 **1.0**，与关闭云一致。自然密度网格分块的透光估计范围为 **0.70091546–1.0**，保留厚云到云外的空间变化。实体遮挡块的阴影区域与完整受光区域亮度比为 **0.0**，证明这个无环境补光的测试中，两个场景灯分支仍共同保留实体遮挡。

集成的先行检查也已完成：r3 云模块、shader 与场景同步在原生 Godot 4.7.2 环境中通过原有 **47 项运行合同**，未出现解析错误，该次检查耗时 **26.38 秒**。该合同计数是先行集成结果，不等同于最终 r3 扩展验收总数，也不作为帧率数据。

### 最终交付快照的同方案复验

最终 runner 将以同一运行快照重新采集场景对照和八张透光控制，沿用上述预设阈值。最终复验结果另行登记在以下稳定路径，由对应报告决定通过状态；本页的先行原型结果不替代最终报告：

```text
build/forest-hamlet/atmosphere-r3-final/cloud-transmission/
    cloud-transmission-capture.json
    cloud-transmission-pixel-report.json
    cloud-direct-dark.png
    cloud-direct-clear.png
    cloud-direct-half-calibration.png
    cloud-direct-uniform-clear.png
    cloud-direct-thin.png
    cloud-direct-thin-repeat.png
    cloud-direct-thick.png
    cloud-direct-natural.png
```

本页不预填最终资源 / 运行 / 场景 GPU / 像素计数、路线结果或 AW / VGP 状态；这些交付事实与最终快照、报告和归档回执一起记录，避免把先行原型或 r2 历史证据当作本轮最终交付通过。
