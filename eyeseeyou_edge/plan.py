"""Adapted from EyeSeeYou v2.0 src/a210_fatigue_agent/{qwen,agent}.py under MIT."""

from decimal import Decimal
import re


_DURATION = re.compile(
    r"(?P<number>(?:[+＋\-−－负負]\s*)?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+|半|[零〇一二两三四五六七八九十百千]+))\s*"
    r"(?P<unit>(?:个)?小时|(?:個)?小時|分钟|分鐘|分|min(?:ute)?s?(?![a-z])|h(?:ours?)?(?![a-z]))",
    re.IGNORECASE,
)
_DIGITS = dict(zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
_KINDS = {"concept_review", "example", "practice", "summary"}
_WEIGHTS = ((100,), (80, 20), (35, 50, 15), (25, 25, 37.5, 12.5))
_GENERAL = (
    (("专注完成", "practice"),),
    (("核心学习", "concept_review"), ("快速回顾", "summary")),
    (("知识梳理", "concept_review"), ("练习巩固", "practice"), ("总结复盘", "summary")),
    (("概念复习", "concept_review"), ("例题讲解", "example"),
     ("独立练习", "practice"), ("总结复盘", "summary")),
)
_VOCABULARY = (
    (("集中背诵", "practice"),),
    (("集中记忆", "concept_review"), ("快速复习", "summary")),
    (("词汇学习", "concept_review"), ("回忆测试", "practice"), ("错词复盘", "summary")),
    (("新词预览", "concept_review"), ("集中记忆", "example"),
     ("回忆测试", "practice"), ("错词复盘", "summary")),
)


def _number(value: str) -> Decimal:
    sign = -1 if value.startswith(("-", "−", "－", "负", "負")) else 1
    value = value.lstrip("+＋-−－负負").strip()
    if value == "半":
        return sign * Decimal("0.5")
    if value.isascii():
        return sign * Decimal(value)
    if "千" in value:
        raise ValueError("时长必须在 1 到 180 分钟之间")
    match = re.fullmatch(
        r"(?:(?P<hundred>[一二两三四五六七八九])?百(?:[零〇])?)?"
        r"(?:(?P<ten>[一二两三四五六七八九])?十)?(?P<one>[零〇一二两三四五六七八九])?",
        value,
    )
    if match is None:
        raise ValueError("无法识别中文时长")
    return Decimal(sign * (
        (_DIGITS.get(match["hundred"], 1) * 100 if "百" in value else 0)
        + (_DIGITS.get(match["ten"], 1) * 10 if "十" in value else 0)
        + _DIGITS.get(match["one"], 0)
    ))


def _subtask_count(seconds: int) -> int:
    return 1 + sum(seconds >= threshold for threshold in (300, 900, 1800))


def preview_plan(goal: str) -> dict:
    """Convert a goal to a plan without emitting a command or changing state."""
    if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 300:
        raise ValueError("学习目标需包含 1 到 300 个字符")
    goal = goal.strip()
    # shortcut: one duration expression per goal, extend the parser for compound durations.
    matches = list(_DURATION.finditer(goal))
    if len(matches) > 1:
        raise ValueError("请用一个时长描述学习目标")
    total_seconds = 2400
    if matches:
        duration = matches[0]
        before = goal[:duration.start()]
        after = goal[duration.end():]
        unit = duration["unit"].lower()
        compound_prefix = duration["number"] == "半" and re.search(
            r"[0-9一二两三四五六七八九十百千]\s*[个個]?\s*$", before
        )
        compound_suffix = "小" in unit and re.match(r"\s*半", after)
        if compound_prefix or compound_suffix:
            raise ValueError("请把复合时长写成分钟，如 90 分钟")
        seconds = _number(duration["number"]) * (3600 if unit.startswith("h") or "小" in unit else 60)
        if not 60 <= seconds <= 10800:
            raise ValueError("时长必须在 1 到 180 分钟之间")
        total_seconds = round(seconds)

    task = goal
    if matches:
        task = re.sub(r"\bfor\s+$", "", before, flags=re.IGNORECASE) + " " + after
    task = re.sub(r"^(?:(?:我想|我要|打算|准备|需要|计划|请|帮我|给我|用|花)\s*)+", "", task)
    task = " ".join(task.split()).strip(" ，,。.!！?？；;：:")
    if not 1 <= len(task) <= 100:
        raise ValueError("请提供 1 到 100 个字符的具体学习任务")

    count = _subtask_count(total_seconds)
    templates = _VOCABULARY if any(
        word in task.lower() for word in ("单词", "词汇", "背词", "vocab")
    ) else _GENERAL
    unit = 60 if total_seconds % 60 == 0 else 1
    total_units = total_seconds // unit
    exact = [total_units * weight / 100 for weight in _WEIGHTS[count - 1]]
    allocated = [int(units) for units in exact]
    order = sorted(range(count), key=lambda i: exact[i] - allocated[i], reverse=True)
    for index in order[:total_units - sum(allocated)]:
        allocated[index] += 1
    return {
        "task": task,
        "total_seconds": total_seconds,
        "subtasks": [
            {"label": label, "kind": kind, "seconds": units * unit}
            for (label, kind), units in zip(templates[count - 1], allocated)
        ],
    }


def confirm_plan(plan: dict, *, confirmed: bool) -> dict:
    """Validate a preview and build the payload for the start_focus command."""
    if confirmed is not True:
        raise ValueError("请显式确认后再开始专注")
    if not isinstance(plan, dict):
        raise ValueError("计划格式错误")
    task = plan.get("task")
    duration = plan.get("total_seconds")
    subtasks = plan.get("subtasks")
    if not isinstance(task, str) or not 1 <= len(task.strip()) <= 100:
        raise ValueError("计划任务无效")
    if type(duration) is not int or not 60 <= duration <= 10800:
        raise ValueError("总时长必须是 60 到 10800 的整数秒")
    if not isinstance(subtasks, list) or len(subtasks) != _subtask_count(duration):
        raise ValueError("子任务数量与总时长不匹配")
    checked = []
    for item in subtasks:
        if not isinstance(item, dict):
            raise ValueError("子任务格式错误")
        label, kind, seconds = item.get("label"), item.get("kind"), item.get("seconds")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
            raise ValueError("子任务名称无效")
        if not isinstance(kind, str) or kind not in _KINDS or type(seconds) is not int or seconds <= 0:
            raise ValueError("子任务类别或时长无效")
        checked.append({"label": label.strip(), "kind": kind, "seconds": seconds})
    if sum(item["seconds"] for item in checked) != duration:
        raise ValueError("子任务时长总和必须等于计划总时长")
    task = task.strip()
    return {
        "command": "start_focus",
        "payload": {
            "current_task": task,
            "duration_seconds": duration,
            "plan": {"task": task, "total_seconds": duration, "subtasks": checked},
        },
    }
