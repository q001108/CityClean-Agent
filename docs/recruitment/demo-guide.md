# 演示视频说明

`docs/media/cityclean-demo.mp4` 是已有 `cityclean-demo.webm` 的 H.264 转码版本，画面来自实际运行的工作台，73.32 秒，无声，已直接内嵌中文阶段字幕。投递包将 MP4 放在根目录 `03-demo.mp4`，可用系统播放器或离线 HTML 首页播放，不依赖播放器加载外挂字幕。

原始录屏为 1366 × 768；成片在下方增加 108 像素字幕区，输出 1366 × 876，保持原操作画面完整。阶段标题与一句说明同步切换，持续标注“合成数据 · 规则模式”。

演示条件：固定种子 `20260925`，30 个候选点、4 辆车、每车 1600 升、治理预算 10 个点；无天地图 Key，无实时模型调用，使用规则研判和合成运营数据。

画面依次展示：

1. 合成风险点、资源约束与规则研判。
2. OR-Tools 生成路线，独立 Verifier 校验，10 个任务被分配。
3. CitySim 启动并推进至 08:05。
4. 封闭 `SE-002-F` 后触发重规划，查看封闭路段和更新后的路线。

视频展示固定成功案例；其他种子或资源约束下可能不可行。它不展示实时 DeepSeek 推理、真实运营数据或真实城市导航。视频中的调度和重规划结果由后端生成。

原始 WebM、三张阶段截图与本视频一同保留在源码的 `docs/media/`。投递版的文件摘要和精确源码提交见根目录 `manifest.json`。

## 字幕与复现

字幕内容及时段定义在 `docs/media/cityclean-demo-captions.json`，配套 UTF-8 字幕时间轴为 `cityclean-demo.zh-CN.srt`；投递包另附 `03-demo.zh-CN.srt` 便于编辑。

10 个字幕时段覆盖项目介绍、场景准备、规则研判、调度优化、独立校验、执行仿真、时间推进、道路封闭、动态重规划与能力边界。整片不添加配音，不将规则模式描述成真实模型调用。

如需修改字幕，编辑 JSON 后在项目根目录运行以下命令。FFmpeg 需要支持 `drawtext`、`libx264`，字体需要支持中文；它们仅用于视频编辑，不属于应用启动依赖。

```powershell
conda activate langchain1.2
python scripts/render_demo_subtitles.py --ffmpeg ffmpeg --font "C:/Windows/Fonts/msyh.ttc"
```

如果 FFmpeg 不在 PATH 中，将 `--ffmpeg` 参数改为本机可执行文件路径。脚本始终使用原始 WebM 作为输入，完成渲染后替换 MP4 并重写 SRT，不在压缩后的 MP4 上重复叠加字幕。
