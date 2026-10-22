# 森林村落：AW / VGP 资源工作流

## 当前云层实时调节 · r4

新增 `cloud-tuning` profile，验证透光对比 **0–80%**（默认 30%）、独立密度 **0–100%**（默认 50%）、中文面板、保存/读取/恢复默认，以及鼠标与方向键的实际操作。该 profile 使用专门的 20 项运行、33 项 GPU 与 58 项像素检查，产生 9 张原始截图；r3 的路线与标定探针继续保留为对应版本的历史证据。

运行标识为 `forest-hamlet-20261022-cloud-tuning-r4`，原生快照为 `cloud-tuning-native-r4`，确认配置及 selection 位于 `art/inputs/forest-hamlet/cloud-tuning-r4/`。AW 原生验证完成，快照包含 **1562 文件、110492897 字节**；delivery export / verify 完成，独立冻结 **68 项来源与证据**。VGP 在同一雪山 Asset 上追加后继 Revision 和 Review Round：

| 字段 | 本轮值 |
|---|---|
| Asset | `52975eea-0437-4f23-96a3-13326f54e762` |
| Revision | `22f17788-3910-4bb3-92ea-c0ba7e376a28` |
| Parent Revision | `03bcb906-33ae-4917-a7fa-8120ac8ae6df` |
| Review Round | `1047b04f-01d0-49ff-a4cd-f6fb13841eec` |
| Previous Round | `0cb738ba-f8d4-486e-8daa-b11be1ddbce5` |
| 状态 | `concept_design` / `pending_review`，技术检查 ready，未创建人工批准或阶段准入 |

实际登记 **70 项逻辑文件、14 个附件**，其中 13 张直接 PNG（3 张主输出、1 张原图、9 张 GPU 图）以及装有其他依赖的确定性 `evidence.zip`。源图片仍按原字节保存；当前和继承的原图引用均保留。

```sh
python3 tools/forest_hamlet/run_cloud_tuning.py test --output build/forest-hamlet/cloud-tuning-r4-final
python3 tools/forest_hamlet/run_cloud_tuning.py capture --output build/forest-hamlet/cloud-tuning-r4-final
make test
python3 tools/forest_hamlet/verify_atmosphere_godot_aw.py --profile cloud-tuning
python3 tools/forest_hamlet/process_atmosphere_aw.py --profile cloud-tuning --extra-evidence docs/forest-hamlet/cloud-tuning-r4.md
python3 tools/forest_hamlet/register_atmosphere_vgp.py --profile cloud-tuning --previous-run-id forest-hamlet-20261022-atmosphere-r3
python3 tools/forest_hamlet/archive_cloud_tuning_evidence.py
```

这些命令记录本次真实生产入口；冻结后改动源码应使用新的 run/snapshot/config/证据路径。实际界面、截图、报告与公开收据见 [r4 修订](revisions/cloud-tuning-r4-20261022/README.md)，参数含义见 [云层实时调节](cloud-tuning-r4.md)。以下各节保留既有版本的制作链与历史计数。

这条制作链复用现有月饰少女，依次保留地面材质与结构模型、HD-2D 植被、雪山远景与动态氛围的来源和验证记录。当前运行资源位于 `assets/forest-hamlet/`。r3 使用新的原生 AW `godot.verify` 运行与源码快照，再执行 `delivery export` / `delivery verify`，最后给既有雪山 Asset 追加 VGP 后继候选。早期 `world.compile` 属于材质和植被颜色加工，本轮不重新绘制或量化雪山颜色图。

## 当前透光云影与氛围 r3 分支（2026-10-22）

当前近景入口为 `make forest-close-run`。画面、最终计数、AW 原生回执、VGP Asset / Revision / 审阅状态和归档身份统一见 [r3 修订记录](revisions/atmosphere-r3-20261022/README.md)。本轮技术验收、原生 AW 验证与交付、VGP 后继登记已完成；VGP 候选技术就绪，仍为 `concept_design / pending_review`。本页说明实际制作与复验协议。

完整证据集合为 **18 张 1920×1080 场景图 + 8 张 1024×768 透光探针**。场景图包括日光 / 黄昏、云影移动 / 关闭、Glow / 体积雾关闭、左右真实行走、左右光方向下雪山法线开关、云关闭条件下全局强 / 弱 / 关闭，以及新增薄云 / 厚云 / 自然密度三图。透光探针使用固定灰色接收面与实体遮挡块，通过独立控制估计云的实际削弱比例；两组最终证据绑定同一个运行文件指纹。[r2 全局光变初版](revisions/atmosphere-r2-20261022/README.md) 和 [r1 云影初版](revisions/atmosphere-r1-20261022/README.md) 保留为历史。

### 原画、技术数据与镜头

雪山原画为 `art/inputs/forest-hamlet/snow-r1/source/snow-master.png`，1983×793，SHA-256 为 `fa11b07fc545379570c1a86f8f5c70a5d5fe01c38aa4ffd2306ad6c5d381ce8c`。运行时 `assets/forest-hamlet/backdrop/color.png` 与该源画逐字节一致。`normal-rig.json` 手工标注 10 个山体的 20 个大片面；`prepare_snow_backdrop.py` 据此生成技术法线、区域图和 manifest，天空与下部雾保持平法线。法线没有从颜色明暗反推高程，原画已有的绘制光照也不会被技术法线消除。见 [雪山技术记录](../../art/inputs/forest-hamlet/snow-r1/technical-notes.md)。

背景是一块保持原长宽比的完整远景板，成组雪脊位于中央树冠开口，角色横向行走产生村庄与远景之间的相对视差。图内山层未拆成独立移动素材。默认近机位、角色设计与素材配置沿用 14° / 39° FOV、23.24485% 完整动画画高占比、218 个植物精灵和 345 个原角色文件，最终完整性和镜头回归以 r3 报告为准。

### 云的空间透光与独立全局能量

r3 原太阳仅作为权威总能量 / 天空来源，新增两个同向原生场景方向光，分别获得总能量的 70% / 30%。基础分支通过 `shadow_caster_mask` 排除云专用层；云分支包括该层；两路都保留房屋、树木和角色的实体阴影。云 shader 把自然密度平滑转换为 0–30% 总直射削弱，云体薄处约 10%、厚处 30%，边缘从 0 平滑进入。Alpha hash 提供云分支的部分覆盖，真实原生阴影过滤形成平均透光；不再用一块二值遮挡挡住全部太阳。

原 `global_lighting.gd` 保留，以种子 **20261022** 的多尺度平滑时间噪声分别改变源太阳和环境补光。太阳倍率硬边界仍为 **0.82–1.18**、环境为 **0.90–1.10**，并非必达峰值。r3 在全局模块更新后分配两路能量，保证能量和等于源太阳，重复同步不累乘。云 H、全局变化 J、体积雾 L、Glow B 独立；T 切换日光 / 黄昏。见 [透光云影 r3](cloud-lighting-r3.md)、[沿用的全局光照](global-lighting.md) 和 [全部操作](README.md#运行)。

### 测量与来源边界

专用探针关闭环境补光、天空反射、雾、Glow、自动曝光和其他相关后期效果，使用 `TONE_MAPPER_LINEAR`、曝光 1。保留暗场、完整能量、半能量校准、透明云、薄云、重复薄云、厚云和自然密度八张 PNG，先对每通道做标准 sRGB 逆变换、扣除零太阳基线，再计算相同接收面像素的线性亮度比。它是**经校准的 8-bit PNG 线性估计**，不是原生 HDR 缓冲读回。半能量控制检查线性关系，量化区间按 ±0.5 码值传播；薄云另保留逐像素及 32×32 分块的覆盖分布。

最终快照已按相同方案重新捕获，透光探针 **24 项捕获检查 / 67 项像素检查通过**，与先行原型结果一致：三个薄云区域约 0.8961–0.8969 透光；厚云约 0.69725654，其 [0.68249407, 0.71205134] 量化区间包含 0.70；半能量约 0.49215860；自然密度分块约 0.70091546–1.0；实体阴影亮度比为 0。冻结的技术文档保留先行原型记录，最终结果由 [r3 修订记录](revisions/atmosphere-r3-20261022/README.md) 的真实报告证明，不改写先行历史。

| 阶段 | 实际职责与证据 |
|---|---|
| 工程准备与实际 GPU | 生成技术贴图、核验运行资源、执行实际游戏捕获和透光探针；形成 18+8 PNG、像素分析、真实路线和运行指纹 |
| AW 原生 `godot.verify` | 本轮已 **completed，58 项检查**；新源码快照为 **1556 文件、110438597 字节**，耗时 37.26 秒。它对不可变项目副本执行指定无窗口 GDScript 运行合同；快照也包含捕获 / 分析工具源码，但 AW 不因此被记作这些 GPU 工具的执行者 |
| AW `delivery export` / `delivery verify` | 已 **completed**。从已完成原生运行中选择原色 / 法线 / 区域三张运行 PNG、原生回执、配方、运行报告及选定源码，导出并校验确切交付 ZIP |
| 工程独立证据冻结 | 已冻结 **82 项**原画、法线标注、源码、技术文档、完整 GPU 图像与分析报告，逐文件记录 SHA-256；与原生 AW 交付选择分开记录 |
| VGP 后继候选 | 已核验既有雪山 Asset 与父 Revision 并追加候选 / 审阅轮次。**31 个实际附件覆盖 84 项逻辑来源**；技术 `ready=true`、`issues=[]`，保持 `concept_design / pending_review` |
| 归档核验 | **已通过，63 个证据文件 = 26 PNG + 37 JSON**。实际核对最终运行指纹、各图摘要、原生 AW 回执、VGP 附件、父稿原图引用及 ZIP 内部依赖映射；加修订 README 后共 64 个文件 |

技术检查、AW 校验或 VGP 的 `ready` 不产生用户美术批准。驱动不调用 `review.decide`，也不创建后续阶段准入。最终实际状态以 [r3 修订记录](revisions/atmosphere-r3-20261022/README.md) 为准。

本轮 **15 项资源 / 58 项运行 / 47 项场景 GPU / 80 项场景像素检查全部通过**，透光探针另为 **24 / 67 项**。18 张场景 PNG 与八张探针完整保留，真实路线 **6/6 路点、22.45 秒**。运行合同耗时 25.142 秒；既有资源 48 项、植被资源 / 运行 126 / 28 项、近景 27 项、总览 **81 项**均通过，`make test` 通过且耗时 11.131 秒。总览 81 是本轮实际计数，与下方历史 r2 的 77 项分开记录。测试及捕获耗时不作为游戏帧率。

### VGP 实际附件与 evidence.zip 协议

VGP 接收的是一个有界的实际附件列表。本轮驱动保留完整逻辑来源集合，按同一个源文件路径去重，不因为附件数量限制删去验证工具、报告、原画或截图。原画、三张主输出及全部 26 张 GPU PNG 作为独立附件，便于直接审阅；其余依赖作为一个 `evidence.zip` 附件提交。实际 `ingest` 为 **31 个附件：30 个直接 PNG + 1 个 ZIP**；逻辑来源共 **84 项：30 项直接文件 + 54 项打包依赖**。驱动在提交前检查实际附件数为 1–64，并逐项核对服务器回执。

`evidence.zip` 对同一运行身份和相同输入采用固定顺序、固定 1980-01-01 时间戳、Unix 普通文件 0644 权限与 `ZIP_STORED`。包内 `index.json` 记录直接附件与打包依赖的来源、别名、字节数和 SHA-256；依赖位于 `dependencies/`。工程在提交前逐条读取 ZIP，核对目录、唯一性、索引字节和每个成员的摘要与大小。

| 清单 | 用途 |
|---|---|
| `vgp/atmosphere.frozen-files.json` | 全部逻辑来源及逐文件冻结副本，不因打包而缩减 |
| `vgp/packed-dependencies.json` | 逻辑依赖到 ZIP 成员的精确映射及容器身份 |
| `vgp/transport-files.json` | 真正传给 `vgp ingest --file` 的直接 PNG 与 ZIP 附件列表 |
| `vgp/transport-server-verification.json` | 原生 VGP 返回的实际附件名、SHA-256、字节数与声明逐项一致的核验 |

VGP 直接核验 ZIP 附件的身份；工程另外验证 ZIP 内部每个成员，不声称服务器已自动解释或审阅包内所有内容。`bundle_file_count` 指真实附件数，`logical_file_count` 指全部逻辑来源数，二者不混写。主图、原图与 GPU PNG 仍为直接附件，打包只改变其余依赖的传输形式。

后继候选同时保留当前原图与显式父稿的原图来源引用；这类继承引用不增加实际上传附件数。归档保留父 Revision 关系及各来源引用的摘要、字节数和角色，原画本次仍只上传一个直接附件。

### 当前交付登记与归档命令

以下记录本轮已完成的 r3 生产入口。原生验证、AW 交付与 VGP 使用同一个逻辑 run，分别写入各自子目录；snapshot 使用独立身份。现有 run 与证据已经冻结，相同输入可核验或恢复；后续源文件、工具、导入内容或证据变化时分配新 run / snapshot 和输出目录。确切交付 / 候选身份见 [r3 修订记录](revisions/atmosphere-r3-20261022/README.md)，不覆盖本轮或 r2 冻结记录。

首先完成技术准备、资源 / 运行检查与完整 GPU 捕获。完整 `capture` 自动把八张探针放入 `cloud-transmission/`，再执行两组分析；`--preview` 和 `--no-route` 都不能作为最终完整证据。

```sh
build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/prepare_snow_backdrop.py
build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/run_atmosphere.py assets --output build/forest-hamlet/atmosphere-r3-final
build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/run_atmosphere.py test --output build/forest-hamlet/atmosphere-r3-final
build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/run_atmosphere.py capture --output build/forest-hamlet/atmosphere-r3-final
make test
```

原生验证使用新 r3 配置、run 和 snapshot。只在构建本轮不可变源快照时执行；之后交付复用已经完成的原生回执，不能把后来变化的源目录写回旧快照。

```sh
build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/verify_atmosphere_godot_aw.py \
  --run-id forest-hamlet-20261022-atmosphere-r3 \
  --snapshot-id atmosphere-native-r3 \
  --config art/inputs/forest-hamlet/atmosphere-r3/workbench-project.yaml

build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/process_atmosphere_aw.py \
  --run-id forest-hamlet-20261022-atmosphere-r3 \
  --evidence-dir build/forest-hamlet/atmosphere-r3-final \
  --native-godot-summary art/derived/forest-hamlet/forest-hamlet-20261022-atmosphere-r3/native-godot/summary.json \
  --config art/inputs/forest-hamlet/atmosphere-r3/workbench-project.yaml

build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/register_atmosphere_vgp.py \
  --run-id forest-hamlet-20261022-atmosphere-r3 \
  --aw-run-id forest-hamlet-20261022-atmosphere-r3 \
  --previous-run-id forest-hamlet-20261022-atmosphere-r2-review2

build/forest-hamlet/validation-env/bin/python tools/forest_hamlet/archive_atmosphere_evidence.py \
  --capture build/forest-hamlet/atmosphere-r3-final \
  --aw-run-id forest-hamlet-20261022-atmosphere-r3 \
  --vgp-run-id forest-hamlet-20261022-atmosphere-r3 \
  --output docs/forest-hamlet/revisions/atmosphere-r3-20261022
```

`process_atmosphere_aw.py` 自动纳入冻结的 `cloud-lighting-r3.md`、沿用的 `global-lighting.md` 和已声明的完整证据，不需要把主 README 加入冻结链。VGP 的 `--previous-run-id` 会读取前次真实回执，核验已有 Asset / Revision 并设置 `parent_revision_ids` 与前一审阅轮次，因此不能与恢复失败首次登记所用的 `--existing-asset-id` 同时传入。新的逻辑候选仍属于原雪山 Asset，不创建重复资源。

归档的补充回归报告使用 `--extra-report NAME.json=PATH`，实际文件路径沿用 r3 修订记录。归档目标已存在时只可核对同一份冻结证据；新的制作或复核应使用新的输出目录与运行身份。驱动不会安装软件、启动服务、改写原用户批准或自动发布。

最终报告入口为：

```text
build/forest-hamlet/atmosphere-r3-final/atmosphere-assets-report.json
build/forest-hamlet/atmosphere-r3-final/atmosphere-runtime-report.json
build/forest-hamlet/atmosphere-r3-final/atmosphere-gpu-report.json
build/forest-hamlet/atmosphere-r3-final/atmosphere-gpu-pixel-report.json
build/forest-hamlet/atmosphere-r3-final/cloud-transmission/cloud-transmission-capture.json
build/forest-hamlet/atmosphere-r3-final/cloud-transmission/cloud-transmission-pixel-report.json
```

### 已归档 r2 与 r1 历史

[r2 全局光变初版](revisions/atmosphere-r2-20261022/README.md) 的 **15 / 47 / 26 / 65 项资源、运行、GPU、像素检查**全部通过，保存 **15 张 PNG**，真实路线 **6/6 路点、22.45 秒**。当时既有资源 48 项、植被资源 / 运行 126 / 28 项、近景 27 项、总览 77 项通过，`make test` 用时 8.946 秒。原生 AW `godot.verify` completed，47 项检查，快照 **1549 文件、110349949 字节**；AW 交付 / 校验已完成，VGP 技术 `ready=true`、状态 `pending_review`。完整身份与回执保留在 r2 归档，不把这些数字列为 r3 最终验收结果。

r2 的固定种子 0–90 秒实测太阳倍率约 **0.9161–1.1210**（57 秒最弱、84 秒最强），环境约 **0.9441–1.0688**；强 / 弱 GPU 平均绝对 RGB 差约 **8.727**，约 **91.93%** 像素超过 2 级阈值，关闭后对中性 t=0 的平均差约 **0.081**。雪山法线左右光差约 **2.284 / 0**（开启 / 关闭），主雪脊实测位移 **−97 px**。这些数据保留其 r2 测量范围；全局变化模块虽继续沿用，最终 r3 图像仍按本轮指纹重新验收。

r2 原生快照冻结后，Godot 导入曾新增 `global_lighting.gd.uid`，当时完整源目录因此成为 1550 文件，原有 1549 文件保持。旧快照与 UID 均保留；r3 使用新 snapshot 重新收集源码和验证工具，不能覆盖旧快照来制造旧 run 可重跑的假象。

[r1 云影初版](revisions/atmosphere-r1-20261022/README.md) 的 **15 / 34 / 20 / 41 项检查**、12 张 PNG、6/6 路点及项目回归曾全部通过。其主雪脊位移预测 −96.5705 px、实测 −97 px、灰度误差约 0.827。这些历史记录不替代 r3 云透光的独立测量，测试运行耗时也不作为游戏帧率。

## 既有秋色植被分支（2026-10-22）

当前所有植物已改为面向屏幕的二维颜色/法线图。详见 [植被修订与验证](revisions/vegetation-r2-20261022/README.md)。这一分支保留既有地面材质和结构模型来源，新增十类植物原稿、逐形体法线标注和配准校验：

- 输入：`art/inputs/forest-hamlet/vegetation-r2/`；合法透明画布与新版法线：`vegetation-r2-canvas/`。画布补边保留原像素，不拉伸植被。
- AW：`forest-hamlet-20261022-vegetation-r2-paired`，配方 `vegetation-paired.recipe.yaml`，正式 `world.compile` 加工颜色，独立法线不做颜色量化。十对图逐像素核对 alpha 后才复制到运行目录。
- VGP：`forest-hamlet-20261022-vegetation-r2-review`，复用既有 Project / 场景分类 / Case，登记 `forest-hamlet-vegetation-sprites` 的二十张主输出。候选自动检查为 ready、issues=[]，当前为 `concept_design` 待审。
- 房屋来源：`build_cottage_without_plants.py` 从原房屋删去 24 个植物节点，保留门把手与木花箱；运行时三次复用该结构模型，窗花另用精灵。该 GLB 作为本轮植被候选的场景接入证据保存。
- Godot：`vegetation.gd`、专用植物 shader、alpha 掩码遮挡保护、`test-vegetation` 与 `capture-vegetation`。最终图像、路线、运行文件指纹均独立归档。

前置 AW 配方与 VGP 请求失败均保留原记录；修正后使用新的运行身份，没有覆盖冻结输入。以下 1–6 节保留地面材质和最初模型生产链的历史说明；其中运行身份、计数与候选状态属于当时版本。

## 1. 原稿与确定性输入准备

原始材质母图：`art/inputs/forest-hamlet/material-atlas.png`，1254×1254，SHA-256 为 `fea6c0c48d91eed01d0f77a181994700d2f813124b6c37a0542c1e178a450f26`。图中四个 627×627 象限依次为草地、暖土、木板和苔石。

```sh
python3 tools/forest_hamlet/prepare_materials.py
```

输入准备将每个象限最近邻缩为 32×32，再用水平／垂直镜像组成 64×64 周期图，确保两组相对边逐像素相同。不会对角落作模糊混合。镜像重复仍可能在大面积铺设时可见，最终应以场景画面判断。

脚本同时输出有透明槽边的 2×2 输入图集和固定色板。色板每种材质最多选 16 个代表色，合并为共享的 64 色来源色板，每个代表色均吸附到原稿实际存在的 RGB 值；最终颜色映射由 AW 执行。原图不覆盖。`prepared-pixel-r2/preparation.json` 固定裁切、算法、尺寸、色板和摘要。

## 2. 官方 AW 编译

```sh
python3 tools/forest_hamlet/process_materials_aw.py
```

驱动使用当前安装的 `aw`，不从相邻源码仓库导入实现，不安装依赖或启动服务。输入规格为 `art/inputs/forest-hamlet/workbench-project.yaml`，执行配方为 `materials.pixel-r2.recipe.yaml`，正式调用为 `workflow validate world.compile`、`workflow run world.compile --bypass-rectify`。

AW 冻结输入与实现指纹，执行固定色板映射、尺寸和可见尺度检查，并输出图集目录及原生 `run.json`。现有 AW scene-sheet v1 的 ground 分支固定为 64×32 菱形，因此四个方形表面材质使用受支持的 prop 画布分支；配方中另有一个满足 catalog 契约的预览地块，该预览地块不接入三维场景。

默认运行目录为 `art/derived/workbench/world/forest-hamlet-20261022-pixel-r2/`。独立摘要与驱动回执位于 `art/derived/forest-hamlet/forest-hamlet-20261022-pixel-r2/`。只有官方运行状态为 completed，且输出满足 64×64、不透明、相对边相等、像素属于固定原稿色板，驱动才把官方 PNG 的原字节复制到：

- `assets/forest-hamlet/textures/grass.png`
- `assets/forest-hamlet/textures/earth.png`
- `assets/forest-hamlet/textures/wood.png`
- `assets/forest-hamlet/textures/stone.png`

原生回执与摘要各自保留，摘要不能替代 AW 原生证据。该步骤为 CPU 材质编译；Godot 的实际 GPU 画面、操控和场景验证由本场景的验收工具单独记录。

## 3. Blender 模型与角色复用

在最终 AW 材质生成后运行项目的 `tools/forest_hamlet/build_assets.py`，保留 `art/inputs/forest-hamlet/blender/*.blend` 与导出的 `assets/forest-hamlet/models/*.glb`。`blender/manifest.json` 记录固定 seed、坐标转换和每个 GLB 摘要。材质字节变化后需要重新导出使用内嵌材质的 GLB。

模型包含 cottage、broadleaf、fir、fence、rock、lamp、bench、sign 和 grass 九件组件。几何由项目脚本制作，AW 负责其材质的加工。角色仍由既有 crescent-traveler 资源提供；月饰少女颜色帧、法线和银饰蒙版的复用摘要由场景来源记录保存。

## 4. VGP 候选、场景分类与审阅

完成最终材质和模型后执行：

```sh
python3 tools/forest_hamlet/register_vgp.py \
  --run-id forest-hamlet-20261022-pixel-r2 \
  --previous-run-id forest-hamlet-20261022-r2 \
  --aw-run-id forest-hamlet-20261022-pixel-r2
```

驱动使用真实 VGP CLI 的 `project files register`，将本工程登记为资源 Project；项目候选和工作状态位于项目 `.vgp`。它创建两个稳定逻辑资源：`forest-hamlet-surfaces` 的四图主输出组，以及 `forest-hamlet-model-kit` 的九模型主输出组。每组明确保留原稿、完整类型目标和外部制作报告，读取 `asset.revision.check`，关联森林村落场景分类，再创建并提交候选审批批次。

首次登记使用 `concept_design` 阶段。材料已经经过技术加工，不等于取得 VGP 的前阶段批准；`specification_processed` 和 `engine_ready` 必须引用真实的前阶段决定及父稿，不能用标签、游戏中已有文件或 Agent 自行补写的批准代替。此驱动不调用 `review.decide`，不生成阶段入库，也不自动改变用户的美术决定。

本轮最终 Project、Asset、Revision、Case 和场景分类身份保存在 `art/derived/forest-hamlet/forest-hamlet-20261022-pixel-r2/vgp/summary.json`。本版复用既有 Project、Case 与两个稳定 Asset，以 `forest-hamlet-20261022-r2` 为父稿追加资源候选和审阅轮次。两个候选技术检查均为 ready、issues=[]，仍为 concept_design 待审；未创建美术批准或阶段入库。r1、r2 的配方、运行记录和候选历史全部保留。

运行时新增的世界坐标道具 shader 与主相机 billboard 属于 Godot 实现；AW 证据只证明四张材质加工，VGP 候选记录四张输出和九个内嵌新版材质的模型。它们不能代替实际 GPU 画面。该 pixel-r2 版本的 GPU、角色比例与路线证据位于 `docs/forest-hamlet/revisions/pixel-r2-20261022/`；当前版本见上方雪山与氛围分支。

## 5. 重试与后续修改

AW 运行目录已存在时使用原始冻结输入恢复；源图、配方、实现或参数改变时改用新的 `--run-id`，保留旧证据。VGP 驱动为每个变更保存确切请求与幂等键，并固定文件摘要；素材变化时同样使用新 `--run-id`，配合 `--previous-run-id` 读取并核验原 Project / Asset / Revision / Case 后追加后继候选，不覆盖旧稿件。本版使用 `--run-id forest-hamlet-20261022-pixel-r2 --previous-run-id forest-hamlet-20261022-r2 --aw-run-id forest-hamlet-20261022-pixel-r2`。它不会提升权限、伪造身份、删除历史或对外发布资源。

## 6. 保存新一轮画面证据

使用独立输出目录，避免覆盖先前的截图与报告：

```sh
python3 tools/forest_hamlet/run.py capture --output build/forest-hamlet/capture-next
python3 tools/forest_hamlet/archive_evidence.py \
  --capture build/forest-hamlet/capture-next \
  --aw-run-id forest-hamlet-20261022-pixel-r2 \
  --vgp-run-id forest-hamlet-20261022-pixel-r2 \
  --shared-test build/forest-hamlet/logs/make-test-reviewed.json \
  --output docs/forest-hamlet/revisions/next-review
```

归档会核对运行文件指纹、截图摘要、AW 输出与 VGP 冻结文件；实际运行文件在 GPU 捕获后发生变化会拒绝归档。每次修改后应先重新执行运行检查和 `make test`，并提供该次测试的状态记录。
