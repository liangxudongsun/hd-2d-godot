# 林间小村 · R2 秋色 HD-2D 植被

> 已在 Godot Forward+ 实机完成本轮接入和验证。颜色/法线素材、两种场景入口、最终景深与物理游览均已复验；VGP 候选已登记，等待美术审阅。

## 修改缘由与范围

用户拒绝 R1 绿色初稿，指出其呈现为低分辨率设计，未达到期望的精致像素风格。R2 按新提供的[秋色植被参考图](../../../../art/inputs/forest-hamlet/vegetation-r2/source/user-vegetation-reference.png)重画，以清楚的叶簇、秋红与金黄亮部、深冷阴影和有层次的枝干组织画面。参考图用于风格判断，保留在制作来源中；R1 不作为本轮美术接受结果。

林间小村的全部植物改用面向屏幕的二维颜色图与逐像素法线图：**10 类、20 张配对图、218 个植物 Sprite3D，其中 67 棵树**。月饰少女原颜色、四方向 108 帧动画、法线、脚底锚点与统一比例保持，**345 份原角色资源未变更**。近景保留 **14° 俯角、39° FOV、`pixel_size = 0.009`**；四方向动画轮廓并集的投影高度为屏高 **23.2449%**，脚底位于屏高 **62.691%**。并集高度覆盖所有动画帧，不表示每帧可见像素同高。渲染器继续使用现有 **Forward+**。

| 植被位置 | 运行资产 ID |
|---|---|
| 阔叶树、冷杉 | `broadleaf_a`、`broadleaf_b`、`fir` |
| 草丛、蕨类、池岸芦苇 | `grass`、`fern`、`reeds` |
| 白花、粉花花床 | `flowers_white`、`flowers_pink` |
| 三栋房屋的六组窗花 | `window_flowers` |
| 池面睡莲 | `lily_pad` |

运行场景不加载三维树木、草丛、球形花朵或圆柱睡莲。房屋源模型移除 24 个植物节点后导出为 `cottage_without_plants.glb`，由三栋房屋复用；保留木花箱和门把手，再以 Sprite3D 放置六组窗花。旧植被模型和含植物的原房屋只保留为历史制作来源，不在运行场景中加载。

## 工程结构与实现

- [运行清单](../../../../assets/forest-hamlet/vegetation/manifest.json)：记录十类颜色/法线对、画布尺寸、可见范围、根部像素、物理高度和散列。尺寸由清单决定；`pixel_size = height_m / visible_height_px`，实例仅作统一缩放。
- [植被工厂](../../../../scripts/forest_hamlet/vegetation.gd)与[场景装配](../../../../scripts/forest_hamlet/world.gd)：创建并登记实际 Sprite3D；结构 GLB 仅限房屋、围栏、石头、灯、长椅和招牌。
- [专用着色器](../../../../shaders/forest_hamlet/vegetation.gdshader)：颜色、法线同 UV、nearest 采样和 alpha cutout；可见与阴影 pass 使用同一主相机 billboard。风摆只变形顶点，根部保持固定，两张图一起移动。
- [遮挡保护](../../../../scripts/forest_hamlet/occlusion.gd)：根据当前 billboard 平面、像素根部与风偏移计算视线交点，再查询 alpha 掩码；透明边缘和树冠孔洞不直接当作实体矩形。进入/离开采用不同边缘余量，遮住角色的树渐隐，离开后恢复。

法线采用 OpenGL 切线空间：X 向右、Y 向上、Z 朝观察者。依据可编辑形体标注独立生成并归一化向量，不把颜色亮度直接当高度。颜色与法线画布及 alpha 必须一致；法线作为线性数据保留，不进入颜色调色板。着色器从 RG 重建正 Z，兼容仅存 RG 的法线压缩格式。

首轮近景中，远处树冠受景深影响过强。最终候选仅将远景起点从角色视深 `+6 m` 改为 **`+10 m`**，过渡从 `7 m` 改为 **`16 m`**，最大模糊量从 `0.10` 降至 **`0.035`**；近景边界、相机位置/角度/FOV 和人物参数保持。首轮证据与调整前源码独立保存在 `build/forest-hamlet/vegetation-r2-before-focus`，新参数的完整 GPU、近景运行与工程检查均已通过。

## 启动与检查

在项目根目录执行：

```sh
make forest-close-run
make test
python3 tools/forest_hamlet/run.py test-vegetation --output build/forest-hamlet/vegetation-r2-final
python3 tools/forest_hamlet/run.py capture-vegetation --output build/forest-hamlet/vegetation-r2-final
```

两条检查命令将本轮报告与截图写入同一目录；完整 GPU 检查包含实际物理游览，不加 `--no-route`。`test-vegetation` 包含植被与近景运行检查，工程级 `make test` 仍需单独执行。

`WASD / 方向键` 移动，`G` 开始/停止自动游览，`T` 切换日光/黄昏，`V` 切换草木微风，`B` 切换辉光，`O` 切换景深，`M` 显示/隐藏控制台，`K` 截图。移动键会取消自动游览。`Esc` 优先停止游览，再关闭已打开的退出确认框或控制台；没有这些状态时显示退出确认。现有 `N` 只控制地面法线；植被法线由 `world.set_vegetation_normals(enabled)` 和专用 GPU 对照检查独立控制。

## AW / VGP 来源与验收状态

实际成功的 AW 运行 ID 为 **`forest-hamlet-20261022-vegetation-r2-paired`**，输入准备目录仍为 `vegetation-r2-canvas`：

```sh
python3 tools/forest_hamlet/process_vegetation_aw.py \
  --run-id forest-hamlet-20261022-vegetation-r2-paired \
  --preparation art/inputs/forest-hamlet/vegetation-r2-canvas/preparation.json \
  --recipe art/inputs/forest-hamlet/vegetation-r2-canvas/vegetation-paired.recipe.yaml
```

前置尝试出现过画布尺寸、透明 `preview.ground`、spec 路径及 ground 图像触碰槽位边界问题，对应失败记录保留。最终运行修正成对画布和资源路径，使用独立不透明预览地面；该预览图不参与游戏场景。

AW `world.compile` 正式加工十张颜色图，十张独立线性法线经配对检查后接入，共二十张运行图。详见[制作摘要](../../../../art/derived/forest-hamlet/forest-hamlet-20261022-vegetation-r2-paired/vegetation-summary.json)与[生产入口](../../../../assets/forest-hamlet/vegetation-production.json)。VGP 最终运行为 `forest-hamlet-20261022-vegetation-r2-review`，二十个主输出的实际检查为 **ready、issues=[]**。原有项目、场景分类与审阅 Case 继续复用，候选保持 `concept_design / pending_review`。详见 [VGP 摘要](vgp-summary.json) 与 [原生检查](vgp-check.json)。

| VGP 身份 | 标识 |
|---|---|
| Asset | `a64415f5-d8fe-413c-ac8d-7a20f74ccbdd` |
| Revision | `6dcd4a7a-3384-497f-8687-a1cb59b50500` |
| Review round | `cca9b78c-9745-4792-872a-302754b1ded1` |

首次 ingest 的成员 ID 含下划线，原生验证拒绝后保留失败请求；修正合法 ID，并用新运行身份复用已创建 Asset，未创建重复资产。

## 验证证据与画面

以下为调整景深后的最终结果；截图与报告均保存在本目录，并核对捕获时与归档时的运行文件指纹。

| 证据 | 已完成结果 |
|---|---|
| [植被源图与法线](vegetation-assets-report.json) | 126 项 passed；十类图的尺寸、alpha、向量与来源检查 |
| [植被运行结构](vegetation-runtime-report.json) | 28 项 passed；218 个 Sprite3D、67 棵树、纹理绑定与无旧植物几何 |
| [近景运行检查](close-runtime-report.json) | 27 项 passed；角色构图、遮挡恢复与真实物理移动 |
| [全景运行检查](runtime-report.json) | 61 项 passed |
| [原资源检查](assets-report.json) | 345 份原角色资源未变更 |
| [真实 GPU 采集](vegetation-gpu-report.json) | 11 张截图、10 类植物、六点物理路线通过；路线 22.45 秒 |
| [GPU 像素回读](vegetation-gpu-pixel-report.json) | 45 项 passed；法线开关与对称光向比较 |
| [工程 `make test`](make-test-report.json) | passed，退出码 0 |
| [最终运行指纹](runtime-fingerprint.json) | `0134f75cb8452176e2fde2c160713fe76dc9f30c0e2df088abf8085ce52b249d` |

画面入口：[默认近景](close-normals-on.png) · [右侧路线近树](close-route-right.png) · [日光全景](overview-day.png) · [黄昏近景](close-dusk.png)。图像来自最终 1920×1080 实机渲染。

历史截图与报告保留原有含义，本轮证据独立归档。GPU 检查固定颜色与几何，对比法线开关及对称光向的实际像素结果，用于检验法线是否参与受光；是否达到用户期望的像素美术质量，仍以本轮实际画面审阅为准。

归档时会再次核对运行指纹、全部截图摘要、AW 输出字节、VGP 冻结文件和原生检查；[验证汇总](validation.json) 与 [颜色/法线来源](source-normal-provenance.json) 记录对应身份。
