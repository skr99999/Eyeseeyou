# 同一段观测，哪一版会提醒？

适用对象是维护学习助手的开发者。改动闭眼阈值、丢帧处理或恢复逻辑时，可以先固定输入，比较用户会在何时收到提醒，再决定是否合并。这里所有输入均为合成数据，时间来自记录本身。

## 三段固定输入的历史对照

每次运行使用当前仓库的同一组输入与预期动作。检查器先核对输出的帧数、顺序和时间戳，再逐项比较所有发出及撤回动作。多一次、少一次或时间不同，都会返回失败。固定样例里毫秒级时间可直接比对。

| 规则版本 | 短眨眼后持续闭眼 · 20 帧 | 摄像头断流 · 8 帧 | 眼部跟踪失效 · 23 帧 | 符合预期的场景 |
| --- | --- | --- | --- | --- |
| [首次公开版](https://github.com/skr99999/eyeseeyou-edge/tree/4ea41c3) | 12.50 秒提醒，13.25 秒撤回 | 12.50 秒多发一次 | 24.00 秒多发一次 | 1/3 |
| [断流修复版](https://github.com/skr99999/eyeseeyou-edge/tree/a543e17) | 同上 | 全程无动作 | 24.00 秒多发一次 | 2/3 |
| [跟踪失效修复版](https://github.com/skr99999/eyeseeyou-edge/tree/2db49a7) | 同上 | 全程无动作 | 全程无动作 | 3/3 |

在当前仓库根目录运行。第二条命令把旧代码放到新的相邻目录，第三条应报告两处不符并以状态码 1 退出。Unix、Windows 使用相同的 Python 命令。

```sh
python examples/check_alerts.py
git worktree add --detach ../eye-initial 4ea41c3
python examples/check_alerts.py --engine-dir ../eye-initial
```

## 把采样率当作实验变量

三段样例都通过之后，我们另外构造了一个边界实验。从第 10 秒开始闭眼，分别持续 1.40、1.49 和 2.00 秒。校准、阈值、采样起点和其他输入固定，只改变采样率。每条轨迹都有明确的闭眼起止时间。运行下列命令可查看 15 组动作及其对应的原始眼部状态。

```sh
python -m examples.sampling_sweep
```

| 设定的闭眼时长 | [上一版](https://github.com/skr99999/eyeseeyou-edge/tree/d92078d) | 本次修复 |
| --- | --- | --- |
| 1.40 秒 | 5 种采样率均无提醒 | 5 种均无提醒 |
| 1.49 秒 | 5 种均在首个睁眼帧发出提醒 | 5 种均无提醒 |
| 2.00 秒 | 5 种均在闭眼期间提醒，随后撤回 | 5 种均在闭眼期间提醒，随后撤回 |

原规则要求连续两帧睁眼才确认恢复。第一帧已经给出睁眼观测，计时器却继续增加，有时刚好越过 1.50 秒阈值。修复保留两帧确认机制，在等待确认时将连续闭眼时长停在上一帧。对于 2.00 秒对照，5、10、20、25、50 Hz 的提醒时间依次是 11.60、11.50、11.50、11.52、11.50 秒。这些是采样时间戳；进程耗时需单独测量。若两次采样之间短暂闭眼又睁眼，输入本身可能完全缺少这次事件。

## 这个问题和哪些开源项目相似？

| 项目或方法 | 借鉴的做法 | 在这里如何使用 |
| --- | --- | --- |
| [LearnOpenCV 疲劳检测](https://github.com/spmallick/learnopencv/blob/master/Driver-Drowsiness-detection-using-Mediapipe-in-Python/drowsy_detection.py) | 从图像估算眼部纵横比，结合持续时间决定何时响铃 | 同属视觉提醒任务。EyeSeeYou 的公开入口从已有观测开始，能单独排查决策层。 |
| [openpilot process replay](https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/test/process_replay/README.md) | 用同一日志片段重跑进程，与参考输出比较 | 把相同输入交给不同版本，列出发生变化的动作和时间点。 |
| [Prometheus 规则测试](https://github.com/prometheus/prometheus/blob/main/docs/configuration/unit_testing_rules.md) | 在给定时刻写明预期告警，也可写明应当没有告警 | 同时检查应该提醒、应该撤回和全程安静三种预期。 |
| [Numenta Anomaly Benchmark](https://github.com/numenta/NAB) | 为事件标注时间窗口，评分考虑误报与漏报 | 未来遇到只能标出大致起止时间的人工标注，可改用事件窗口匹配；当前固定回放仍按精确时间判定。 |

从计算问题看，这是**不完整观测下的时序事件监测**。每帧只给出局部信息，提醒取决于一段历史。跟踪失效和缺帧会改变可以支持的判断。对具体输入逐步检查时间规则，与流式运行时验证研究中的问题相近。本项目采用 Python 状态机和具体轨迹测试，覆盖范围由公开的样例决定。[Runtime Verification for Timed Event Streams with Partial Information](https://link.springer.com/chapter/10.1007/978-3-030-32079-9_16)

## 怎样解读结果

三段历史回放专门选取了已知故障和一个正例；采样实验使用固定的观测相位与规则生成眼部状态。它们可以证明这些输入上的行为，也适合作为改代码后的回归检查。推断真实学习场景中的每小时误提醒次数，需要独立记录、明确标注与观察时长。下一步仅靠软件也可扩展到采样相位偏移、抖动和连续丢帧，保留每个失败输入供复查。
