# 云影与体积光

`scripts/forest_hamlet/cloud_lighting.gd` 在世界上空 24 m 创建一个 220 m 宽、仅投影的水平网格。它不加入可行走世界、不参与碰撞，也不替换任何植物或角色资源。网格细分为 32 × 32 个四边形，用于减轻巨大三角形在级联阴影边缘的裁切问题。

固定种子 `20261022` 的 FastNoiseLite 生成一次 256 × 256 单通道周期云遮罩；三层低频 FBM 以及四角平滑混合避免滚动接缝。遮罩仅决定哪些高空片元写入太阳的原生阴影深度。云控制器自身不改变太阳或环境补光能量，云影差异跟随世界位置、物体高度和太阳方向，模型、地面、像素植被、角色均由原生渲染器接收遮挡。半影使用已有 DirectionalLight3D 的 PCSS / PCF。这里模拟太阳直射的空间云遮挡。r2 的 `global_lighting.gd` 另以固定种子时间噪声调节原生太阳与环境补光能量，两种变化独立控制；详见 [不规则全局光照](global-lighting.md)。此云模块不实现空间变化的烘焙环境光或完整大气散射。

## 接口

```gdscript
var cloud_lighting = preload("res://scripts/forest_hamlet/cloud_lighting.gd").new()
add_child(cloud_lighting)
cloud_lighting.configure(main_light, environment)
cloud_lighting.set_preset("day")
cloud_lighting.set_enabled(true)
cloud_lighting.set_atmosphere_enabled(true)
```

场景每帧调用 `tick(delta)`；场景冻结时停止调用即可。`set_motion_enabled(false)` 也可冻结独立云时钟。`set_time(seconds)` 精确设置遮罩相位，不依赖全局 shader `TIME`，适用于固定时刻的 GPU A/B 验证。`set_pattern(cutoff, span_m, velocity)` 可调整云覆盖阈值、世界尺度与风速，该调用自身不改变太阳能量。`snapshot()` 返回可重建参数、原始遮罩 SHA-256、环境雾状态及 CPU 射线诊断；诊断不代替 GPU 图像验收。

`set_atmosphere_enabled` 独立控制原生体积雾；日光 / 黄昏密度分别为 0.0030 / 0.0038，计算范围 78 m，短历史混合降低移动拖影。既有非体积远雾可以继续使用。Glow 由主场景统一拥有，云影模块不覆盖 Glow 设置。

## 验收边界

云影对照拍摄同一相机与角色状态的云时钟 t = 0、t = 24 s 和关闭云遮挡三个画面，关闭草木风 / 水面动画，并把独立全局光变固定到 t=0（两路能量倍率为 1）以隔离差异；体积雾开关单独比较。地面、屋面与像素树应有可测空间变化，角色帧、比例、相机、太阳与环境能量在这组 A/B 中保持一致。全局光变另在关闭云影后采集强 / 弱 / 关闭三图，其变化不能替代云影的空间证据。

日光环境补光基值为 0.55；全局光变启用后，由独立模块在该基值的 0.90–1.10 倍硬边界内变化，实际采样范围以引擎报告为准。云图相位为 `(0.65, 0.0)`、世界周期 96 m、移动速度 `(0.32, 0.13)` m/s。出生点位于云间漏光区域；云影随时间经过人物和房屋。方向光软阴影采用 `SHADOW_QUALITY_SOFT_ULTRA`，降低大半影中的采样颗粒；太阳角直径仍为 0.65°。

[云影初版 r1 验收](revisions/atmosphere-r1-20261022/README.md) 已完成真实 Forward+ GPU 验证：地面、房屋和植被均有空间变化，固定机位的 0 / 24 秒对照能测得云影位移，体积雾与 Glow 分别有独立像素差异；该版保存 12 张截图并通过 41 项像素检查。当前 [r2 验收](revisions/atmosphere-r2-20261022/README.md) 已通过 **15 项资源、47 项运行、26 项 GPU、65 项像素检查**；完整捕获为 **15 张 PNG**，真实路线 **6/6 路点、22.45 秒**。新增全局光变三图在关闭云影后独立比较；原云影、体积雾和 Glow 对照把全局倍率固定为 1，继续验证各自的空间与像素贡献。画面审美仍由用户审阅。

## 官方参考

- [GeometryInstance3D · Shadows Only](https://docs.godotengine.org/en/stable/classes/class_geometryinstance3d.html)：仅显示网格投影。
- [DirectionalLight3D](https://docs.godotengine.org/en/stable/classes/class_directionallight3d.html)：光线沿节点的 −Z 方向传播，级联阴影和 pancake 属性。
- [Spatial shader](https://docs.godotengine.org/en/stable/tutorials/shaders/shader_reference/spatial_shader.html)：原生空间材质与 discard 深度遮罩。
- [Volumetric fog](https://docs.godotengine.org/en/stable/tutorials/3d/volumetric_fog.html)：Forward+ 体积雾、光照与时间重投影。
