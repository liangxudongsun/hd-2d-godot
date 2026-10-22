# 林间小村 · 透光云影与氛围 r3

2026-10-22。本轮按“薄云约削弱 10%、最厚云只削弱 30%，避免大块黑投影”的要求，完成透光云影、真实 GPU 复验、AW 原生验证与交付、VGP 后继候选登记。雪山、角色、近机位、HD-2D 植被及独立不规则全局光变继续保留。

**技术验收全部通过；VGP 候选为 `ready=true`、`issues=[]`，处于 `concept_design / pending_review`。** 这表示候选可审阅，没有生成用户美术批准或后续阶段准入。运行入口仍为项目根目录执行 `make forest-close-run`；完整操作见 [场景说明](../../README.md#运行)，制作命令见 [AW / VGP 工作流](../../pipeline.md)。

## 当前画面

![r3 日光：雪山与自然透光云影](close-day-clouds-natural.png)

![r3 黄昏：暖光、实体阴影与灯具光晕](close-dusk-atmosphere.png)

直接比较：[云关闭](close-day-clouds-off.png)、[强制薄云](close-day-clouds-thin.png)、[强制厚云](close-day-clouds-thick.png)、[自然密度](close-day-clouds-natural.png)。这些是游戏场景的真实 1920×1080 GPU 输出，未修改像素或以生成图替代。

## 这次修改的实际范围

原太阳继续提供方向、颜色、总能量和单一天空太阳。新增两个同向原生方向光获得总能量的 70% / 30%；70% 分支仅排除云专用投影层，30% 分支接收云的 alpha hash 覆盖。两个分支都保留房屋、树木和角色的实体阴影，`shadow_opacity` 均为 1。云体厚薄与边缘平滑变化，完整太阳总能量不会被二值云平面一起挡住。

H 切换云层空间遮挡，J 保留独立的多尺度时间噪声全局光变。全局模块继续调节源太阳与环境补光，再由云控制器从当前源能量分配两路场景光；重复同步不累乘。L / B 分别控制原生体积雾与 Glow，T 切换日光 / 黄昏。10% / 30% 是同一全局时刻下云自身对太阳直射的削弱比例；环境光、雾、反射和色调映射也影响最终游戏画面。

实现与测量方法见冻结的 [r3 云透光技术记录](../../cloud-lighting-r3.md)。其中先行原型结果保留原文；本页登记同一方案在最终运行快照上的复验，未改写原型历史或 r2 技术文档。

## 最终验收

| 检查 | 本轮实际结果 | 报告 |
| --- | --- | --- |
| 雪山及氛围资源 | **15 项通过** | [资源检查](atmosphere-assets-report.json) |
| 原生运行合同 | **58 项通过**，25.142 秒 | [运行检查](atmosphere-runtime-report.json) |
| 场景 GPU 捕获 | **47 项通过**，18 张 1920×1080 PNG | [捕获状态](atmosphere-gpu-report.json) |
| 场景像素分析 | **80 项通过** | [像素检查](atmosphere-gpu-pixel-report.json) |
| 专用透光 GPU 捕获 | **24 项通过**，8 张 1024×768 PNG | [探针捕获](cloud-transmission/cloud-transmission-capture.json) |
| 专用透光像素分析 | **67 项通过** | [透光估计与分布](cloud-transmission/cloud-transmission-pixel-report.json) |
| 真实角色路线 | **6/6 路点完成，22.45 秒** | [路线及逐时刻采样](atmosphere-gpu-report.json) |
| 既有资源 | **48 项通过** | [既有资源检查](assets-report.json) |
| 植被资源 / 运行 | **126 / 28 项通过** | [植被资源](vegetation-assets-report.json) / [植被运行](vegetation-runtime-report.json) |
| 近景 / 总览运行 | **27 / 81 项通过** | [近景](close-runtime-report.json) / [总览](runtime-report.json) |
| 项目共用功能 | **`make test` 通过**，11.131 秒 | [测试回执](make-test-report.json) |
| AW 原生 `godot.verify` | **completed，58 项**，37.26 秒 | [原生验证摘要](aw-godot-summary.json) / [原生运行合同](aw-godot-runtime-report.json) |

实际 GPU 为 **NVIDIA GeForce RTX 4070 SUPER**，渲染方式为 **Forward+**。最终场景捕获和透光探针均正常退出，退出码为 0；捕获耗时分别为 65.611 秒和 6.746 秒。先前 Wayland 捕获试次的退出异常记录保留，最终捕获采用工程已验证的 X11 路径。捕获或测试耗时不作为游戏帧率。

两组最终图像与像素报告绑定同一 [运行文件指纹](runtime-fingerprint.json)：

```text
853768f01c2a9d3402e57d0c69bb15c1fe771d6eee9c2202c7c8d43337619017
```

## 透光比例：实际测量与误差边界

透光探针使用固定灰色 Lambert 接收面、固定太阳方向和一个实体遮挡块。环境补光、天空反射、雾、Glow、自动曝光及其他相关后期关闭，色调映射为 `LINEAR`、曝光为 1。原始输出是 8-bit PNG；分析逐通道执行标准 sRGB 逆变换，扣除零太阳暗场，再对同一接收面像素求线性亮度和的比值。半能量控制检验该方法的线性关系。**结果是经校准的 PNG 线性估计，不是原生 HDR 缓冲读回。**

| 测量区域 / 控制 | 透光估计 | 解释 |
| --- | ---: | --- |
| 薄云 `upper_left` | **0.89632635** | 平均削弱约 10.37% |
| 薄云 `center` | **0.89692456** | 平均削弱约 10.31% |
| 薄云 `lower_left` | **0.89609746** | 平均削弱约 10.39% |
| 厚云，三个区域一致 | **0.69725654** | 8-bit 量化区间 **[0.68249407, 0.71205134]** 包含结构目标 0.70 |
| 半太阳能量校准 | **0.49215860** | 通过预先设定的 0.50 ± 0.015；量化区间也包含 0.50 |
| 同 shader 强制透明云 | **1.0** | 与关闭云一致 |
| 自然云场分块范围 | **0.70091546–1.0** | 保留厚云、薄云和云外的空间变化 |
| 实体遮挡块的影区 / 完整受光区亮度比 | **0.0** | 无环境补光的专用探针中，实体阴影仍由两个分支共同保留 |

三个薄云 ROI 各包含 49,152 个像素，其 32×32 像素分块均值标准差为 **0.00606928–0.00730708**，约 0.61–0.73 个百分点；逐像素标准差为 0.02294–0.02533。冻结状态的薄云重复 PNG 与首次 PNG 的 SHA-256 相同。以上支持区域平均透光目标与这次静态重复稳定性，单像素仍存在 alpha hash 覆盖起伏，不据此承诺放大观察或任意运动下完全无颗粒。

厚云估计值按实际量化区间解释，不把 0.69725654 改写成精确 0.70，也不将其直接判为真实直射超过 30% 的削弱。量化区间按各通道 ±0.5 码值传播；固定精度的详细统计和预先设定的容差见 [最终透光分析](cloud-transmission/cloud-transmission-pixel-report.json)。本次最终各比例与先行原型相同。

### 八张原始探针图

| 控制 | 原图 |
| --- | --- |
| 暗场 / 完整太阳 / 半能量 | [零太阳](cloud-transmission/cloud-direct-dark.png) · [完整太阳且云关闭](cloud-transmission/cloud-direct-clear.png) · [半能量校准](cloud-transmission/cloud-direct-half-calibration.png) |
| 透明云 / 薄云 / 重复薄云 | [同 shader 透明云](cloud-transmission/cloud-direct-uniform-clear.png) · [薄云](cloud-transmission/cloud-direct-thin.png) · [冻结重复薄云](cloud-transmission/cloud-direct-thin-repeat.png) |
| 厚云 / 自然密度 | [厚云](cloud-transmission/cloud-direct-thick.png) · [自然云](cloud-transmission/cloud-direct-natural.png) |

## 游戏场景里的可见效果

以下图像差异是最终游戏 PNG 的平均绝对 RGB 码值差，范围单位为 0–255；它们用于确认实际渲染贡献，不能当作太阳直射透光百分比。各功能使用独立对照，云影对照固定全局时钟到 t=0，全局强弱对照关闭云，雪山法线方向探针关闭全局光变。

| 功能 | 本轮实际读回 |
| --- | --- |
| 云影随时间移动 | 全景 t=0 / t=24 秒平均差约 **4.058**；地面、房屋、植被区域均有空间变化 |
| 薄云 / 厚云游戏画面 | 平均差约 **6.799**；自然云 / 云关闭平均差约 **7.317** |
| 全局强 / 弱光 | 57 秒与 84 秒画面平均差约 **8.730**，约 **91.93%** 像素超过 2 级变化阈值 |
| 全局关闭 / 中性 t=0 | 平均差约 **0.023**，超过 2 级阈值的像素为 **0** |
| 雪山法线与左右光方向 | 法线开启时方向差约 **2.284**；法线关闭为 **0** |
| 原生 Glow | 平均差约 **0.578**，**17,312** 个像素超过 2 级阈值 |
| 原生体积雾 | 平均差约 **5.925**，约 **83.69%** 像素超过 2 级阈值 |
| 实际行走中的远景视差 | 可用 `main_snow_ridge` 雪脊地标预测横移 **−96.5705 px**，实测 **−97 px**；局部匹配灰度误差约 **0.828** |

独立全局光变仍使用种子 `20261022`。本轮 0–90 秒、每秒一次采样的太阳倍率为 **0.91607898–1.12100458**，环境倍率为 **0.94412806–1.06875133**；太阳最弱 / 最强分别为 57 / 84 秒，t=0 两路倍率均为 1。太阳 ±18%、环境 ±10% 是硬边界，不是该时间窗口必达峰值。参数、状态和每个接收面数据见 [场景像素报告](atmosphere-gpu-pixel-report.json)。

视差匹配只采用报告标为可用的雪脊地标。靠近边界或被场景遮挡、匹配误差过大的其他候选地标没有计作有效测量；相机和角色通过真实路线移动，没有用仅改变参数代替画面证据。

### 十八张场景对照

| 对照组 | 原图 |
| --- | --- |
| 云影移动与关闭 | [t=0](close-day-clouds-a.png) · [t=24 秒](close-day-clouds-b.png) · [云关闭](close-day-clouds-off.png) |
| 本轮薄厚与自然密度 | [薄云](close-day-clouds-thin.png) · [厚云](close-day-clouds-thick.png) · [自然云](close-day-clouds-natural.png) |
| 昼夜、雾与 Glow | [黄昏](close-dusk-atmosphere.png) · [Glow 关闭](close-day-glow-off.png) · [体积雾关闭](close-day-atmosphere-off.png) |
| 全局光变 | [弱光](close-day-global-weak.png) · [强光](close-day-global-strong.png) · [全局变化关闭](close-day-global-off.png) |
| 真实左右行走 | [左侧路点](close-route-left.png) · [右侧路点](close-route-right.png) |
| 雪山法线方向 | [左光 / 法线开](snow-left-normals-on.png) · [左光 / 法线关](snow-left-normals-off.png) · [右光 / 法线开](snow-right-normals-on.png) · [右光 / 法线关](snow-right-normals-off.png) |

## 相机、角色与资产保持

近机位实际俯角约 **14°**、FOV **39°**，角色 `pixel_size = 0.009`，完整动画轮廓占画高 **23.24485%**。月饰少女四方向、每方向 27 帧，共 108 帧；345 个原文件继续按摘要核对。植被仍是 **218 个颜色图 + 法线图 Sprite3D**，没有重新引入立体植物模型。具体保留结果见 [资源保持记录](preserved-resources.json) 与上述回归报告。

雪山依旧是一块完整远景板，与村庄产生相对视差，未拆出多张独立山层。1983×793 原画与运行颜色 PNG 逐字节一致，源 SHA-256 为：

```text
fa11b07fc545379570c1a86f8f5c70a5d5fe01c38aa4ffd2306ad6c5d381ce8c
```

20 个低频山体面来自手工标注，天空与薄雾保持平法线；原画已有明暗仍保留，动态法线只作温和重光照。见 [背景 manifest](backdrop-manifest.json) 与 [原画 / 法线来源](source-normal-provenance.json)。本轮没有修改相机、角色、植物素材或雪山原色来取得云影测试通过。

## AW 原生运行与交付

| 身份 / 状态 | 本轮值 |
| --- | --- |
| 逻辑 run | `forest-hamlet-20261022-atmosphere-r3` |
| 原生源码 snapshot | `atmosphere-native-r3` |
| `godot.verify` | **completed，58 项检查** |
| 不可变源码快照 | **1556 文件、110438597 字节** |
| `delivery export` / `delivery verify` | **completed** |
| Delivery ID | `delivery-0da408cb09664effc932c786ed0fe4ba5c61d175356a4444cc25909842d8585f` |
| 工程独立来源 / 证据闭包 | **82 项**，与原生 delivery 的选定文件集合分开记录 |

AW 在不可变项目副本中运行指定的无窗口 GDScript 合同。交付链从这个已完成的原生运行中选择原色、法线、区域三张运行 PNG，及选定源码、配方与原生运行证据，导出并校验确切 ZIP。声明的 GPU 捕获和分析工具源码随来源保留，但 **18+8 张实际 GPU 图与其像素分析由工程独立执行**；不把这些画面归为 AW 渲染，也不把技术法线或原画绘制归为 AW 自动生成。

原生回执和对应关系：

- [AW 总摘要](aw-summary.json) · [独立冻结输入](independent-frozen-inputs.json)
- [Godot 摘要](aw-godot-summary.json) · [原生回执](aw-godot-receipt.json) · [配方](aw-godot-recipe.json) · [源码快照](aw-godot-snapshot.json) · [运行检查](aw-godot-runtime-report.json)
- [交付 manifest](aw-delivery-manifest.json) · [技术记录](aw-delivery-technical.json) · [校验回执](aw-delivery-verification.json) · [选定文件](aw-delivery-selection.json) · [来源映射](aw-delivery-source-map.json)

早期地面材质和植被颜色的 `world.compile` 来源继续保留，其职责不混入这次云影、雪山原色或外部 GPU 捕获。原生运行身份与输入已经冻结；后续修改应使用新 run / snapshot，而非覆盖本轮证据。

## VGP 后继候选与实际附件

| 身份 / 状态 | 本轮值 |
| --- | --- |
| VGP run | `forest-hamlet-20261022-atmosphere-r3` |
| 前一运行 | `forest-hamlet-20261022-atmosphere-r2-review2` |
| 复用 Asset | `52975eea-0437-4f23-96a3-13326f54e762` |
| 新 Revision | `03bcb906-33ae-4917-a7fa-8120ac8ae6df` |
| 新审阅 Round | `0cb738ba-f8d4-486e-8daa-b11be1ddbce5` |
| 技术检查 | **`ready=true`，`issues=[]`** |
| 阶段 / 状态 | **`concept_design / pending_review`** |
| 实际附件 | **31 个 = 30 个直接 PNG + 1 个 `evidence.zip`** |
| 完整逻辑来源 | **84 项 = 30 项直接文件 + 54 项打包依赖** |

驱动核验既有雪山 Asset 和前一 Revision，建立父稿关系并提交后继审阅轮次；没有创建重复 Asset，没有生成美术决定或后续阶段入库。实际直接附件包括原画、三张主输出和全部 26 张 GPU PNG。其余 54 项依赖装入确定性 ZIP，全部逻辑来源仍按 SHA-256 保留。

原生后继候选保留当前原图与显式父稿的原图来源引用，源图本次实际附件仍只有一个。归档的 ingest 回执投影保留 `parent_revision_ids`、`original_references` 和 `member_original_references`，逐条对应来源摘要、字节数与角色；继承引用不重复计作新附件。

ZIP 使用固定条目顺序、1980-01-01 时间戳、0644 文件权限和 `ZIP_STORED`，包内索引绑定每个成员的来源、字节数和 SHA-256。工程逐成员验证 ZIP；原生 VGP 返回的实际附件名、摘要、字节数又与传输声明逐项核对。这里区分逻辑来源数与实际附件数，不把 84 项描述成服务器接收了 84 个直接附件。

- [VGP 摘要](vgp-summary.json) · [技术检查](vgp-check.json) · [完整逻辑冻结集合](vgp-frozen-files.json)
- [实际传输清单](vgp-transport-files.json) · [打包依赖映射](vgp-packed-dependencies.json) · [服务器附件核验](vgp-server-verification.json)
- [原生 ingest 回执的安全投影](vgp-ingest-receipt.json) · [ZIP 内部依赖索引](vgp-dependency-index.json)

公开文档保存安全投影与摘要，不复制包含本地服务句柄的完整原生回应。实际 `evidence.zip` 保留在工程 VGP 运行的 `transport/evidence.zip`；这里的索引和归档校验记录其来源与确切 SHA-256，不声称服务器自动审阅了 ZIP 内部所有内容。

## 归档与历史

[validation.json](validation.json) 是本目录的归档总索引，**实际归档核验已通过**，自动归档 **63 个证据文件：26 张 PNG + 37 份 JSON**；加本 README 共 64 个文件。索引关联 18 张场景 PNG、`cloud-transmission/` 内的八张探针、运行指纹、各项报告、原生 AW 与 VGP 身份，以及实际附件、合法父稿原图引用和 ZIP 成员核验。原始 PNG 不做缩放、重新编码或改色。完整运行条件以各实际 JSON 为准。

先行原型、失败捕获试次和本轮最终证据各自保留。原 [r2 全局光变](../atmosphere-r2-20261022/README.md)、[r1 云影与雪山](../atmosphere-r1-20261022/README.md) 及 [秋色植被](../vegetation-r2-20261022/README.md) 记录不覆盖；旧计数与回执保持其原版本含义。
