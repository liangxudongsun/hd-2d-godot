# 林间小村 · HD-2D 场景范例

入口：`scenes/forest_hamlet.tscn`。这是可实际行走的独立 Godot 场景，复用项目已有的月饰少女，将暖土路、森林木屋、石岸池塘、像素材质和三维光影组合为一个范例。

视觉参考为 [用户提供的 Bilibili 视频](https://www.bilibili.com/video/BV1TFjz6eEK7/) 中约 **00:13 的森林村落镜头**：暖土路、低矮木屋、密集树林、花坛和前景池塘。视频页面标注包含 AI 生成内容；本工程依据可见画面制作自己的几何、材质和渲染效果，不将视频帧作为游戏贴图，也不声称取得原视频的模型、工程或精确渲染参数。

## 运行

在项目根目录执行：

```sh
make forest-run
```

也可以在 Godot 编辑器中打开 `scenes/forest_hamlet.tscn` 后按 F6。原项目默认入口仍为江南河街。直接运行这个范例只需要现有 Godot 与图形桌面，不需要启动 AW、VGP 或 Blender。

| 操作 | 功能 |
|---|---|
| WASD / 方向键 | 行走；输入会接管自动游览 |
| T | 日光 / 黄昏 |
| G | 沿六个路点自动游览，使用真实角色移动与碰撞 |
| M | 打开 / 收起中文效果控制台 |
| N | 地面法线开关 |
| B | 辉光开关 |
| O | 景深开关 |
| V | 植物微风开关 |
| K | 保存当前截图，界面显示位置 |
| Esc | 先取消游览或关闭面板；退出需确认 |

F8 / F9 留给编辑器停止 / 暂停。场景输入通过独立角色适配器处理，不修改共用 InputMap。

## 画面与场景组成

![日光全景](captures/day-overview.png)

![黄昏全景](captures/dusk-overview.png)

地面由真实可碰撞网格承载。世界坐标材质把草地和土路连续混合，路缘带有小尺度不规则变化；草地的大色块优先于颗粒，避免与角色争夺注意。地面微法线是独立编写的解析表面信号，没有从颜色图明暗反推固定阴影。

木屋有完整墙体、三角山墙、屋檐、独立木瓦层、屋脊、窗框、侧窗、台阶、烟囱和花箱。树林由阔叶树与针叶树组成，多排深度、不同缩放和转向形成遮挡；树冠使用不规则小叶簇，按材质合并网格以控制绘制次数。栅栏、石块、路灯、长椅、月纹路牌和草簇均有原创 Blender 来源。

池塘使用独立水面、石岸与岸边碰撞。水面包含蓝绿深浅色、动态法线、不规则短波和局部闪光，并使用 Forward+ 屏幕空间反射。屏幕外对象不在 SSR 可反射范围内；水面仍有天空反射回退。闪光包含美术编写的信号，不应将其误记为完整物理水模拟。

光照提供日光与黄昏两组设置。暖色太阳、冷色环境光、实际投影、接触遮蔽、轻雾和景深构成空间层次。景深焦点保护角色所在区域，原角色逐帧法线与银饰材质继续参与受光。

## 角色与资产来源

- 月饰少女沿用原四方向、每方向 27 帧，共 **108 帧**。颜色、法线、银饰蒙版与相关定义的 **345 个原文件**以 SHA-256 基线核验，未被本轮制作覆盖。
- 新增 **4 张 256×256 材质**：草地、土路、木板、苔石。原始 ImageGen 母图与完整提示词保留；工具没有提供可记录的模型版本与 seed，来源记录明确为 null。
- 新增 **9 个模型组件**：cottage、broadleaf、fir、fence、rock、lamp、bench、sign、grass。固定几何 seed 为 20261022；每个模型另记录派生 seed、Blender 版本、生成器摘要、内嵌材质摘要和 GLB 摘要。
- 原创几何保留 `.blend` 与生成脚本。固定几何 seed 便于重现结构；不同 Blender 版本和文件元数据仍可能造成二进制编码差异。

详细步骤见 [AW / VGP 工作流](pipeline.md)。AW 实际执行 `world.compile`；Blender 生成模型；VGP 保存资源候选、来源、类型目标和待审批次。这三类事实分别记录。

## 验证与证据

最终状态与计数见 [验证摘要](evidence/validation.json)。已执行的验证覆盖：

1. 原始母图、AW 官方输出与运行副本摘要；贴图尺寸、透明度；角色原文件不可变性；九个模型的来源和 GLB 格式。
2. 无窗口真实移动、动画帧序、四方向法线、效果开关独立性、池塘阻挡、路线取消与六路点完成。
3. 实际硬件 Forward+ GPU 渲染的 1920×1080 截图，包含日光、黄昏、角色特写、控制台、路线节点，以及地面法线 / 景深 / 辉光对照。
4. 对照截图冻结角色物理、场景更新、风与水流，使用静态天空。GPU 报告记录每张图的状态、摘要和视口绘制计数。
5. 原项目 `make test` 共用功能回归。

证据入口：

- [运行检查](evidence/runtime-report.json)
- [GPU 检查与截图状态](evidence/gpu-report.json)
- [实际捕获对应的运行文件指纹](evidence/runtime-fingerprint.json)
- [AW 材质处理摘要](evidence/materials-summary.json)
- [VGP 候选与审批身份](evidence/vgp-summary.json)
- [角色特写](captures/crescent-traveler-close.png)
- [中文控制台](captures/controls.png)
- [地面法线开启](captures/ground-detail-normals-on.png) / [关闭](captures/ground-detail-normals-off.png)
- [黄昏路灯辉光开启](captures/dusk-glow-on.png) / [关闭](captures/dusk-glow-off.png)

日景的辉光处理很克制，整幅开关差异低于本报告的 2 级 RGB 变化阈值；黄昏路灯的对照记录了局部可测差异。材质法线和景深的对照也分别保存，避免把每个开关都描述成明显的全屏效果。

这些检查确认工程行为和实际渲染。与参考的美术相似程度仍需结合截图判断；技术检查不会自动创建用户美术批准或 VGP 的后续阶段入库。

## 重建命令

```sh
python3 tools/forest_hamlet/prepare_materials.py
python3 tools/forest_hamlet/process_materials_aw.py
make forest-models
make forest-import
make forest-test
python3 tools/forest_hamlet/run.py capture --output build/forest-hamlet/capture-new
make test
```

`GODOT` / `BLENDER` 可以指定已安装的程序；命令不会安装软件或启动服务。完整捕获会执行真实行走路线。只在调整静态画面时可添加 `--no-route`，这种捕获不会作为完整路线证据。

修改源图、配方或加工规则时，为 AW 使用新的 `--run-id`，保留既有原生记录；修改 VGP 候选资源时同样使用新的运行身份并复用原 Asset。不要覆盖已经冻结的请求来绕过版本检查。

## 文件位置

| 路径 | 内容 |
|---|---|
| `scenes/forest_hamlet.tscn` | 场景入口 |
| `scripts/forest_hamlet/` | 场景、世界组装与角色输入适配 |
| `shaders/forest_hamlet/` | 草土混合、水面和植物风动 |
| `assets/forest-hamlet/` | 运行时四种材质与九个 GLB |
| `art/inputs/forest-hamlet/` | 原图、提示词、配方、复用基线、可编辑模型 |
| `art/derived/workbench/world/` | AW 未修改的原生执行记录 |
| `art/derived/forest-hamlet/` | 加工摘要与 VGP 驱动回执 |
| `.vgp/` | 原生 VGP 项目资源与历史 |
| `tools/forest_hamlet/` | 准备、加工、模型、登记、运行与捕获工具 |
| `tests/forest_hamlet/` | 场景运行检查 |

含本机路径的原生工作流记录在当前工程内保留，并排除于 git；可携带的相对路径摘要和最终画面在本目录。`build/` 保存过程日志及迭代捕获。本轮没有提交或推送代码。

范例聚焦视频中森林村落这一种环境；房屋室内、战斗、四季变化和任务系统不在此场景中。
