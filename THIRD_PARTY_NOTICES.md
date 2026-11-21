# 来源与第三方说明

Windows 桌面安装包另外包含 CPython、Tcl/Tk、cx_Freeze 启动组件和 Microsoft Visual C++ 运行库。随包许可见安装目录的 `licenses`、`share` 及 cx_Freeze 版权说明。第三方组件沿用各自的许可。桌面版的计划、计时和回放调度来自本仓的公开实现。

本仓库源自 EyeSeeYou 团队的 A210 v2.0 比赛提交版。原件的 LICENSE 与 AUTHORS.txt 随仓保留。原作者见 [AUTHORS.txt](AUTHORS.txt)。

| 当前文件 | 由来 |
| --- | --- |
| `models.py`、`database.py` | 沿用原版 `src/a210_fatigue_agent/` 下同名团队源码。 |
| `focus.py` | 源自同目录的专注状态机。桌面移植增加无视觉输入的手动计时，结束会话时清除待确认的分段状态。 |
| `fatigue.py` | 基于同目录原文件，补充断流时的计时重置、失去有效眼部观测时的窗口重建，以及等待确认睁眼期间的闭眼计时处理。 |
| `plan.py` | 参考原 `qwen.py`、`agent.py` 的本地任务模板、时长分配和确认流程，独立为可测试接口。 |
| `replay_config.json` | 从暑期运行配置选取疲劳判断、眼状态确认、告警冷却所需参数，并增加断流判定间隔。 |
| 命令行入口、示例、回归测试与持续集成配置 | 为公开复现整理；示例观测为合成数据。 |

离线回放和计时核心只使用 Python 标准库。Windows 实时摄像头模式使用 OpenCV 和 MediaPipe。完整安装包包含构建时下载的 Google Face Landmarker 和 Gesture Recognizer 模型，第 1 版 float16 文件及其校验值列于 `windows/prepare_camera_models.py`。相关组件按其上游条款提供，随包许可位于 `licenses`。[Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker) · [Gesture Recognizer](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer)

原板端的 TORQ SDK、板端可执行文件、模型权重、字体、前端库、真人影像及部署配置均未随本仓分发。项目 MIT 许可的范围以随仓源码和文档为准。

Android APK 同时包含 Google MediaPipe Tasks Vision 0.10.32 的 JavaScript/WASM（SIMD 和非 SIMD）、Face Landmarker 与 Gesture Recognizer 的 float16 第 1 版。安装包内的 `assets/vision-assets/LICENSE-mediapipe.txt` 随附 MediaPipe Apache-2.0 许可及上游第三方说明。源码仓库通过 [固定版本下载脚本](mobile/prepare_vision_assets.py) 复现这些文件，脚本记录来源与 SHA-256。构建时将 npm 的 `vision_bundle.mjs` 原字节保存为 `vision_bundle.js`。[MediaPipe Web 源码和模型来源](https://github.com/google-ai-edge/mediapipe/tree/master/mediapipe/tasks/web/vision) · [npm 包](https://www.npmjs.com/package/@mediapipe/tasks-vision/v/0.10.32) · [模型许可上游说明](https://github.com/google-ai-edge/mediapipe-samples/issues/407)
