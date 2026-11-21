# EyeSeeYou Edge · 可回放的端侧专注 Agent

一次正常眨眼、摄像头丢了人脸、持续闭眼，应该引发三种不同的处理。EyeSeeYou Edge 从团队在 A210 开发板上做的学习助手中抽出决策代码，让开发者把一段观测重新喂给 Agent，逐帧查出它为什么提醒、何时撤回，以及哪些动作需要用户确认。

**A replayable edge agent for focus sessions and fatigue alerts.** Run the original A210 decision logic on timestamped observations. Inspect every alert locally with Python, synthetic data and no API key.

## 两分钟运行

下载本仓库 ZIP 后解压，或用 Git 克隆，在仓库根目录打开终端。需要 Python 3.10 或更高版本。运行依赖均在 Python 标准库内。

```sh
python -m eyeseeyou_edge examples/fatigue.jsonl
python -m eyeseeyou_edge.session "背单词 20 分钟"
python -m eyeseeyou_edge.session "背单词 20 分钟" --confirm
python -m examples.away_return
python -B -m unittest discover -s tests -v
```

在第一条命令的输出中，直接查找以下几个毫秒时间戳。输入只有 20 条合成观测，复现时无需摄像头、模型文件或云账号。

| 时间戳 | 可以验证什么 |
| ---: | --- |
| 8000 | 完成初始校准，进入 `NORMAL` |
| 9400 | 短闭眼记作一次眨眼，`alarm` 为 `false` |
| 10200 | 眼部分类不确定，`eye_sample_valid` 为 `false`，该帧不计入闭眼比例 |
| 12500 | 连续闭眼达到 1.5 秒，发出一次 `request_fatigue_alert` |
| 13250 | 睁眼得到确认，发出 `clear_fatigue_alert` |

第二条命令把 20 分钟分成词汇学习 7 分钟、回忆测试 10 分钟、错词复盘 3 分钟。第三条带上用户确认，原版专注状态机才会产生 `focus_started` 并进入 `RUNNING`。这个命令在内存 SQLite 中演示启动过程，关闭进程即结束。第四条把一次离席、回座和主动确认放进同一场会话，可以观察回座后什么时候恢复计时。

## 如何接自己的观测

每行一个 UTF-8 JSON 对象，五个字段均为必填。下面是一帧有效观测，以及随后一次明确的缺面。完整可运行输入见 [合成样本](examples/fatigue.jsonl)。

```jsonl
{"t_ms":0,"face_found":true,"eye_state":"OPEN","ear":0.30,"mar":0.10}
{"t_ms":100,"face_found":false,"eye_state":"UNCERTAIN","ear":null,"mar":null}
```

- `t_ms` 是严格递增的非负整数毫秒。内部以首帧为时间原点。
- `eye_state` 可选 `OPEN`、`CLOSED`、`UNCERTAIN`。`ear` 和 `mar` 是眼睛、嘴部的纵横比。有脸时应为非负有限数，缺面时填 `null` 并将眼部状态标为 `UNCERTAIN`。
- 输入边界只接收这五个字段。请在采集端将模型输出转换为该格式，并显式记录缺面。仅省略丢失的帧会留下时间空洞，无法判断这段时间内人的状态。
- 每行结果含判断理由 `reasons`、当前风险标志 `alarm` 和动作 `action`。动作描述可供上层程序消费，回放自身只打印结果。格式错误时会指出文件、行号并以状态码 2 退出，之前的有效行已经输出。

## 开源范围与复现

| 能力 | 本仓库提供的实现 |
| --- | --- |
| 疲劳判断 | 原 A210 时间规则、校准和状态模型，外加缺面时中断连续闭眼证据的修正。PERCLOS 在这里按滑窗中有效样本的闭眼占比计算，比较实验应使用稳定采样率。 |
| 学习计划与行动 | 根据目标及时长在本地拆分子任务；校验确认后的计划，再交给专注状态机执行。可回放离席与恢复。 |
| 板端视觉与语言模型 | 暑期系统有摄像头、板端视觉推理和可选的外部语言服务。本仓从观测输入开始运行，计划默认使用本地模板。 |

回放验证的是给定输入下的决策。真人疲劳识别准确率、现场帧率和耗电都需要另外测量。项目面向学习辅助与软件实验。

## 开发与许可

决策逻辑在 [fatigue.py](eyeseeyou_edge/fatigue.py) 和 [focus.py](eyeseeyou_edge/focus.py)，计划生成与确认在 [plan.py](eyeseeyou_edge/plan.py)。报告误提醒时，请给出最短的合成 JSONL、预期动作和实际输出，便于在测试中复现。

原项目由 EyeSeeYou 团队开发，成员见 [AUTHORS.txt](AUTHORS.txt)。源码沿用 [MIT License](LICENSE)。各模块与暑期版本的关系见 [来源与第三方说明](THIRD_PARTY_NOTICES.md)。
