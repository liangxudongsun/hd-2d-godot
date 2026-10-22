# 云层实时调节 · r4

在 `scenes/forest_hamlet_close.tscn` 的中文控制台中，玩家可以实时调整云层的透光对比与密度。按 **M** 展开或收起面板；运行命令为 `make forest-close-run`。

## 操作与数值

| 控件 | 范围 | 默认 | 实际作用 |
|---|---|---|---|
| 透光对比 · 最大遮光 | 0–80% | 30% | 调整最厚云层对太阳直射光的最大削弱比例。0% 无云影明暗差；80% 时厚云保留 20% 直射光。 |
| 云层密度 | 0–100% | 50% | 改变平滑云场的覆盖和厚薄分布。0% 无云，50% 沿用默认分布，100% 满布厚云。 |
| 保存参数 | — | — | 保存这两个参数，下次正常启动场景时自动读取。 |
| 读取已保存 | — | — | 放弃当前预览值，恢复最近一次保存的参数。 |
| 恢复默认 | — | — | 恢复 30% 最大遮光和 50% 密度；若要将默认值作为下次启动设置，随后点击保存。 |

滑块拖动后即时生效，无须重启。选中滑块后可用左右方向键微调，每步 1 个百分点。拖动和方向键调节不会同时移动角色；点击场景、按 WASD 或收起面板即可继续行走。面板在 1920×1080 和 1280×720 中均可使用，较矮窗口中下部效果开关可滚动查看。

**透光对比显示的是遮光量，越大则云下越暗。** 在默认 30% 上限下，薄云目标削弱约 10%，厚云削弱 30%。薄云的代表强度保持为最大值的三分之一；将最大遮光设为 80% 时，薄云代表值约为 26.7%。云边缘连续过渡到零遮光。

这两个控件只负责云的遮光。独立全局光变 **J**、云影开关 **H**、体积光 **L**、辉光 **B** 和日光／黄昏 **T** 继续可用。想单独观察云影对比时，可以先用 J 暂时关闭全局光变。

## 渲染与默认兼容

源太阳仍然拥有总能量、颜色、方向和天空贡献。两路同向原生方向光按 `1 − 最大遮光` 与 `最大遮光` 分配场景直射能量：默认仍为 70/30，最大值为 20/80，零对比为 100/0。仅云敏感分支接收独占云层的 alpha hash 投影；两路都保留普通房屋、植物和角色的实体阴影。

密度改变固定种子平滑噪声的偏置 `2 × (density − 0.5)`，不更换随机种子，不增加新的高频图案。默认 0.5 的偏置为零。连续边缘和薄厚曲线继续使用既有实现；零对比时显式保护零除法。

80% 是**云对太阳直射的最大削弱量**，不代表经过环境补光、材质反射、体积散射和色调映射后的游戏像素必然降低 80%。新截图用于验证实际画面变化；此前 r3 的专用透光探针仍作为其对应默认参数的历史测量证据。

旧的 `set_uniform_attenuation()` 是专门验证 0–30% 的标定接口，开启时固定使用旧 70/30 分支并绕过用户参数，退出后恢复用户调节。普通游戏面板始终使用自然云场。快照中 `base70`、`cloud30` 是兼容旧报告的字段名，实际比例以 `base_ratio`、`cloud_ratio` 和当前能量为准。

## 设置与验证隔离

设置保存于场景专用的 `user://forest-hamlet-clouds.cfg`。文件使用带版本的 ConfigFile 格式，先写临时文件再重命名；读取时验证数值类型和有限性。失败会在面板中显示，并保留当前预览值。

自动读取仅在场景作为 `SceneTree.current_scene` 正常启动时发生。脚本式测试和 GPU 截图将场景作为子节点实例化，因此不读取个人偏好；新的定向测试还明确设置 `cloud_settings_enabled = false`，保存和读取仅使用独立的 build 测试文件。

验证入口：

```sh
python3 tools/forest_hamlet/run_cloud_tuning.py test --output build/forest-hamlet/cloud-tuning-r4-final
python3 tools/forest_hamlet/run_cloud_tuning.py capture --output build/forest-hamlet/cloud-tuning-r4-final
make test
python3 tools/forest_hamlet/verify_atmosphere_godot_aw.py --profile cloud-tuning
python3 tools/forest_hamlet/process_atmosphere_aw.py --profile cloud-tuning
python3 tools/forest_hamlet/register_atmosphere_vgp.py --profile cloud-tuning --previous-run-id forest-hamlet-20261022-atmosphere-r3
```

当前源码在 `scripts/forest_hamlet/scene.gd`、`scripts/forest_hamlet/cloud_lighting.gd` 与 `shaders/forest_hamlet/cloud_occluder.gdshader`。本轮采用独立的 AW/VGP cloud-tuning profile 和新运行标识，不覆盖已完成的 r3 来源链与证据。技术测试不代替用户对视觉效果的判断。
