# EyeSeeYou Edge · 可回放的端侧专注 Agent

[![离线回归测试](https://github.com/skr99999/eyeseeyou-edge/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/skr99999/eyeseeyou-edge/actions/workflows/test.yml) · Python 3.10+ · [MIT](LICENSE)

### Windows 桌面版

[下载 Windows x64 安装包（0.2.0）](https://github.com/skr99999/eyeseeyou-edge/releases/download/v0.2.0/EyeSeeYou-Edge-0.2.0-Windows-x64.msi)。双击 MSI 完成安装，从开始菜单打开 **EyeSeeYou Edge**。安装包包含 Python 和图形界面，可离线使用。

- **学习与专注**：输入“背单词 20 分钟”，预览分段计划，点“确认开始”。支持暂停、继续、结束与分段加时。关闭应用会保存进度，重新打开后由你确认继续。
- **观测回放**：载入内置示例或自己的 JSONL，生成 HTML 报告并在浏览器中打开。学习进度保存在当前用户的 `%LOCALAPPDATA%\EyeSeeYou Edge`，报告位置由你选择。桌面版使用手动专注计时和日志回放，不调用摄像头。

开发运行使用 `python -m eyeseeyou_edge.desktop`（需要 Tk）。在 64 位 Windows、CPython 3.13 的虚拟环境中执行 `python -m pip install cx-Freeze==8.7.4` 和 `python windows/build_msi.py bdist_msi` 可重新构建安装包，产物位于 `windows/dist/`。

EyeSeeYou Edge 把团队 A210 学习助手的判断过程搬到了普通电脑上。给它一段带时间戳的眼口观测，就能逐帧查出哪一帧触发了疲劳提醒、哪一帧撤回。专注会话也能回放，从生成学习计划，到离席暂停、回座后由用户确认继续。

*Replay an edge agent’s alerts and focus sessions locally, using timestamped observations and Python’s standard library.*

![同一段合成输入，第 24 秒重新睁眼。旧版沿用失效观测之前的样本，按 40% 闭眼占比发出提醒；修复后重新建立窗口，首帧闭眼占比为 0%，没有提醒。](docs/tracking-replay.png)

**改一条规则，会让用户多收到哪一次提醒？** 运行 `python examples/check_alerts.py` 即可核对三段固定输入的全部提醒与撤回时间。另一个实验用五种采样率复现了“已经睁眼才开始提醒”的边界问题。[查看各版实测对照、复现命令和同类项目](docs/replay-evaluation.md)

## 复现图中的误报

在仓库根目录用 Python 3.10 或更高版本生成离线报告：

```sh
python -m eyeseeyou_edge examples/tracking_loss.jsonl --report tracking.html
```

双击打开 `tracking.html`。报告列出 23 帧，10 至 23 秒的眼部观测连续显示“无法判断”，第 24 秒恢复睁眼，整段发出提醒 0 次。选中“只看发出或撤回提醒的帧”可以筛选动作。换用 `examples/fatigue.jsonl` 便能看到一对提醒和撤回，分别出现在 12500 和 13250 毫秒。报告可离线转发，其中包括输入文件名、逐帧时间和判断结果。

需要逐行 JSON 输出时，直接运行：

```sh
python -m eyeseeyou_edge examples/tracking_loss.jsonl
```

看最后一行的 `t_ms=24000`。摄像头在第 10 至 23 秒每秒都送来一帧，但眼睛一直无法辨认。旧版把失去跟踪前后的 **5 个有效样本**拼成了一个足够长的窗口，其中 2 个被判闭眼，导致睁眼时反而发出提醒。现在，距离上一次有效眼部观测超过 1 秒就重建窗口。这一帧输出 `state="NORMAL"`、`perclos=0.0`、`action=null`。[原始输入](examples/tracking_loss.jsonl) · [修复前源码](https://github.com/skr99999/eyeseeyou-edge/tree/a543e174a959b70225dc04dd01142ccce0801164) · [回归测试和持续有效观测的对照组](tests/test_evidence_gap.py)

## 回放疲劳提醒与专注会话

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

在仓库根目录运行 `python -m pip install .` 后，其他 Python 项目可以直接逐帧读取判断结果。安装时 pip 会准备构建工具；包的运行依赖均来自标准库。也可以提前运行 `python -m pip wheel --no-deps -w dist .`，将生成的 wheel 带到另一台电脑离线安装。

```python
from eyeseeyou_edge.replay import replay

with open("observations.jsonl", "rb") as observations:
    for frame in replay(observations):
        if frame["action"]:
            print(frame["t_ms"], frame["action"])
```

将自己的观测文件命名为 `observations.jsonl`，或使用仓库的 `examples/fatigue.jsonl`。安装后用一条命令试跑[独立接入示例](examples/check_session.py)：

```sh
python -I examples/check_session.py examples/fatigue.jsonl
```

它汇总每次发出、撤回提醒的输入时间戳。在这份样例中各发生一次，分别是 12500 和 13250 毫秒。示例来自一次模拟第三方接入：开发者角色只阅读公开 README，在新虚拟环境中编写调用程序。

**错误处理。** Python 的 `replay()` 是惰性迭代器。遇到坏行时会抛出含行号的 `ValueError`，此前的帧可能已经交给调用方。需要整场统计时，请在迭代全部成功后再输出。独立示例演示了如何补上文件路径并返回退出码。

每行一个 UTF-8 JSON 对象，五个字段均为必填。下面是一帧有效观测，以及随后一次明确的缺面。完整可运行输入见 [合成样本](examples/fatigue.jsonl)。

```jsonl
{"t_ms":0,"face_found":true,"eye_state":"OPEN","ear":0.30,"mar":0.10}
{"t_ms":100,"face_found":false,"eye_state":"UNCERTAIN","ear":null,"mar":null}
```

- `t_ms` 是严格递增的非负整数毫秒。内部以首帧为时间原点。
- `eye_state` 可选 `OPEN`、`CLOSED`、`UNCERTAIN`。`ear` 和 `mar` 是眼睛、嘴部的纵横比。有脸时应为非负有限数，缺面时填 `null` 并将眼部状态标为 `UNCERTAIN`。
- 输入只接收这五个字段。有观测但未检测到人脸时，请显式记录缺面。相邻观测间隔超过 1 秒时，恢复首帧重新开始累计闭眼和张嘴时长，并重建闭眼占比窗口。间隔恰好 1 秒仍允许连续计时。采集端可按实际采样间隔设置 `fatigue.max_observation_gap_seconds`。
- 每行结果含判断理由 `reasons`、当前风险标志 `alarm` 和动作 `action`。命令行回放会打印这些判断。格式错误时，命令行指出文件、行号并以状态码 2 退出，之前的有效行已经输出。

运行 `python -m eyeseeyou_edge examples/camera_gap.jsonl` 可复现一次断流：9.0 秒和 9.2 秒观测到闭眼，下一帧在 12.5 秒到达。该帧的 `eye_closed_seconds` 为 0，`action` 为 `null`。

## 开源范围与复现

| 能力 | 本仓库提供的实现 |
| --- | --- |
| 疲劳判断 | 保留 A210 时间规则、校准和状态模型。缺面或断流会打断连续闭眼计时；持续失去有效眼部观测会重建闭眼占比窗口。字段 `perclos` 是滑窗中有效样本的闭眼占比，宜在稳定采样率下比较。 |
| 学习计划与行动 | 根据目标及时长在本地拆分子任务；校验确认后的计划，再交给专注状态机执行。可回放离席与恢复。 |
| 板端视觉与语言模型 | 暑期系统有摄像头、板端视觉推理和可选的外部语言服务。本仓从观测输入开始运行，计划默认使用本地模板。 |

### 怎样读这些结果

| 要核对的问题 | 可复现的结果 |
| --- | --- |
| 摄像头直接断流，恢复首帧会怎样？ | 相隔 3.3 秒后恢复，闭眼计时从 0 开始。持续收到闭眼观测后仍会在 1.5 秒触发提醒。[输入](examples/camera_gap.jsonl) · [续接帧与断言](tests/test_evidence_gap.py) |
| 排除了失效帧，会漏掉闭眼占比提醒吗？ | 对照序列每 200 毫秒采一帧，多次短闭眼始终低于长闭眼阈值。第 23 秒，闭眼占比规则独立触发提醒。[对照测试](tests/test_evidence_gap.py) |
| 回座会直接扣减剩余时间吗？ | 回座后保持 1169 秒，用户确认后恢复，下一秒才降到 1168 秒。[会话示例](examples/away_return.py) |

上述结果来自合成观测，验证从观测到动作的规则。真人使用时的误提醒次数、漏提醒次数、A210 现场帧率和功耗仍待实测。文献中也有按眼睑闭合**时间**和独立警觉性任务做对照的实验；复用这里的样本占比时，请同时记录采样间隔、无效帧和判定口径。[PERCLOS 原始实验](https://doi.org/10.1016/j.ijpsycho.2011.09.012)

首页把输入和动作放在同一条时间线上，参考了 [Rerun 的时间序列回放](https://github.com/rerun-io/rerun)。单独展示跟踪状态的做法可对照 [OpenFace 的输出字段](https://github.com/TadasBaltrusaitis/OpenFace/wiki/Output-Format)。按使用场景交代评测条件与局限的写法参考了 [Model Cards for Model Reporting](https://research.google/pubs/model-cards-for-model-reporting/)。

## 开发与许可

决策逻辑在 [fatigue.py](eyeseeyou_edge/fatigue.py) 和 [focus.py](eyeseeyou_edge/focus.py)，计划生成与确认在 [plan.py](eyeseeyou_edge/plan.py)。报告误提醒时，请给出最短的合成 JSONL、预期动作和实际输出，便于在测试中复现。

原项目由 EyeSeeYou 团队开发，成员见 [AUTHORS.txt](AUTHORS.txt)。源码沿用 [MIT License](LICENSE)。各模块与暑期版本的关系见 [来源与第三方说明](THIRD_PARTY_NOTICES.md)。
