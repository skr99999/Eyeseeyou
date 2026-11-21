from copy import deepcopy
import unittest

from eyeseeyou_edge.plan import confirm_plan, preview_plan


class OfflinePlanTests(unittest.TestCase):
    def test_preview_and_explicit_confirmation(self):
        preview = preview_plan("我想用十五分钟背英语单词")
        self.assertEqual(preview["task"], "背英语单词")
        self.assertEqual(preview["total_seconds"], 900)
        self.assertEqual(preview["subtasks"][0]["label"], "词汇学习")
        self.assertEqual(len(preview["subtasks"]), 3)
        self.assertNotIn("command", preview)
        for value in (False, None, 1, "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                confirm_plan(preview, confirmed=value)
        command = confirm_plan(preview, confirmed=True)
        self.assertEqual(command["command"], "start_focus")
        self.assertEqual(command["payload"], {
            "current_task": preview["task"],
            "duration_seconds": 900,
            "plan": preview,
        })
        self.assertIsNot(command["payload"]["plan"], preview)

    def test_duration_boundaries_and_allocation(self):
        examples = {
            "1分钟背英语": (60, 1),
            "4.99分钟背英语": (299, 1),
            "5分钟背英语": (300, 2),
            "15分钟做题": (900, 3),
            "14.99分钟做题": (899, 2),
            "0.5 hour 写作": (1800, 4),
            "半个小时复习": (1800, 4),
            "一百零五分钟做题": (6300, 4),
            "3小时复习": (10800, 4),
            "复习电路": (2400, 4),
        }
        for goal, (seconds, count) in examples.items():
            with self.subTest(goal=goal):
                plan = preview_plan(goal)
                self.assertEqual(plan["total_seconds"], seconds)
                self.assertEqual(len(plan["subtasks"]), count)
                self.assertGreater(min(item["seconds"] for item in plan["subtasks"]), 0)
                self.assertEqual(sum(item["seconds"] for item in plan["subtasks"]), seconds)
                confirm_plan(plan, confirmed=True)

    def test_english_goal_removes_duration_connector(self):
        plan = preview_plan("review chapter 2 for 20 minutes")
        self.assertEqual(plan["task"], "review chapter 2")
        self.assertEqual(plan["total_seconds"], 1200)

    def test_invalid_goals(self):
        for goal in (None, "  ", "3分钟", "零分钟做题", "-1 min 做题", "半分钟做题", "负一小时做题", "− 1 min 做题",
                     "180.01分钟做题", "四小时做题", "一千分钟做题", "2小时10分钟做题", "一个半小时复习", "1小时半读书",
                     "学" * 101, "学" * 301):
            with self.subTest(goal=goal), self.assertRaises(ValueError):
                preview_plan(goal)

    def test_invalid_plan_payloads(self):
        preview = preview_plan("5分钟做题")
        malformed = [
            [],
            {**preview, "task": True},
            {**preview, "total_seconds": 300.0},
            {**preview, "total_seconds": 301},
            {**preview, "total_seconds": 10801},
            {**preview, "subtasks": preview["subtasks"][:1]},
        ]
        for field, value in (("label", ""), ("seconds", True), ("seconds", 0), ("kind", "unknown")):
            altered = deepcopy(preview)
            altered["subtasks"][0][field] = value
            malformed.append(altered)
        for plan in malformed:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                confirm_plan(plan, confirmed=True)
