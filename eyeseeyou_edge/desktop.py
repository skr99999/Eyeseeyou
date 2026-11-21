"""Local study planner, focus timer and observation replay desktop application."""

from concurrent.futures import ThreadPoolExecutor
from math import ceil
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .database import Database
from .focus import FocusSessionController
from .plan import confirm_plan, preview_plan
from .replay import replay
from .report import write_report


def export_report(source, target):
    if target.exists() and target.samefile(source):
        raise ValueError("请选择与输入日志不同的报告文件。")
    with source.open("rb") as stream:
        write_report(target, source.name, replay(stream))


class Desktop:
    def __init__(self, root, database):
        self.root = root
        self.db = database
        self.focus = FocusSessionController({}, database)
        self.plan = self.focus.current.plan
        self.source = self.report = self.job = None
        self.worker = ThreadPoolExecutor(max_workers=1)
        root.title("EyeSeeYou Edge")
        root.geometry("730x570")
        root.minsize(630, 520)
        root.option_add("*Font", "{Microsoft YaHei UI} 10")
        style = ttk.Style(root)
        style.configure("TButton", padding=(10, 5))
        style.configure("Timer.TLabel", foreground="#155548", font=("Consolas", 34, "bold"))
        head = tk.Frame(root, bg="#173e35", padx=22, pady=12)
        head.pack(fill="x")
        tk.Label(head, text="EyeSeeYou Edge", fg="white", bg="#173e35",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tabs = ttk.Notebook(root)
        tabs.pack(fill="both", expand=True, padx=16, pady=12)
        study, logs = ttk.Frame(tabs, padding=16), ttk.Frame(tabs, padding=16)
        tabs.add(study, text="学习与专注")
        tabs.add(logs, text="观测回放")
        ttk.Label(study, text="学习目标与时长").pack(anchor="w")
        self.goal = tk.StringVar(value=self.focus.current.current_task or "背单词 20 分钟")
        self.entry = ttk.Entry(study, textvariable=self.goal)
        self.entry.pack(fill="x", pady=(4, 8))
        self.goal.trace_add("write", self.invalidate_preview)
        self.outline = ttk.Label(study, justify="left", wraplength=550)
        self.outline.pack(anchor="w")
        self.timer = ttk.Label(study, style="Timer.TLabel")
        self.timer.pack(anchor="w", pady=(10, 0))
        self.status = ttk.Label(study, wraplength=550)
        self.status.pack(anchor="w", pady=(0, 10))
        actions = ttk.Frame(study)
        actions.pack(fill="x")
        self.primary = ttk.Button(actions, command=self.advance)
        self.primary.pack(side="left")
        self.extend = ttk.Button(actions, text="本段加时", command=lambda: self.command(
            "resolve_segment", {"completed": False, "source": "desktop"}))
        self.end = ttk.Button(actions, text="结束本次专注", command=self.stop)
        self.end.pack(side="right")
        ttk.Label(logs, text="打开观测日志，查看每一帧的判断与提醒。", wraplength=540).pack(anchor="w")
        files = ttk.Frame(logs)
        files.pack(fill="x", pady=10)
        ttk.Button(files, text="选择 JSONL 日志…", command=self.choose_source).pack(side="left")
        assets = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        demo = assets / "examples" / "fatigue.jsonl"
        if demo.is_file():
            ttk.Button(files, text="载入疲劳提醒示例", command=lambda: self.select(demo)).pack(side="left", padx=6)
        self.filename = ttk.Label(logs, text="尚未选择日志", wraplength=550)
        self.filename.pack(anchor="w", pady=8)
        self.export = ttk.Button(logs, text="生成 HTML 报告…", command=self.save_report, state="disabled")
        self.export.pack(anchor="w", pady=5)
        self.message = ttk.Label(logs, wraplength=550)
        self.message.pack(anchor="w", pady=6)
        self.open_report = ttk.Button(logs, text="打开报告", state="disabled", command=self.open_html)
        self.open_report.pack(anchor="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    def invalidate_preview(self, *_):
        self.plan = None
        self.render()

    def command(self, name, payload=None):
        self.focus.update(None)
        self.focus.command(name, payload)
        if self.focus.current.state in {"STOPPED", "COMPLETED"}:
            self.plan = None
        self.render()

    def advance(self):
        s = self.focus.current
        if s.segment_review_ready and s.state == "PAUSED":
            self.command("resolve_segment", {"completed": True, "source": "desktop"})
        elif s.state == "RUNNING":
            self.command("pause_focus")
        elif s.state == "PAUSED":
            self.command("resume_focus")
        elif self.plan is None:
            try:
                self.plan = preview_plan(self.goal.get())
            except ValueError as error:
                messagebox.showerror("学习目标", str(error), parent=self.root)
                return
            self.render()
        else:
            request = confirm_plan(self.plan, confirmed=True)
            self.command(request["command"], request["payload"])

    def stop(self):
        if messagebox.askyesno("结束专注", "现在结束本次学习计划？", parent=self.root):
            self.command("stop_focus")

    def render(self):
        s = self.focus.current
        active = s.state in {"RUNNING", "PAUSED", "AWAY"}
        plan = s.plan if active else self.plan
        outline = "\n".join(f"{i}. {item['label']}    {item['seconds'] // 60} 分 {item['seconds'] % 60:02} 秒"
                            for i, item in enumerate(plan["subtasks"], 1)) if plan else ""
        self.outline.configure(text=outline)
        seconds = ceil(s.remaining_seconds) if active else plan["total_seconds"] if plan else 0
        self.timer.configure(text=f"{seconds // 60:02}:{seconds % 60:02}")
        self.entry.configure(state="disabled" if active else "normal")
        self.end.configure(state="normal" if active else "disabled")
        if s.segment_review_ready and active:
            title, detail = "本段已完成", s.last_action
            self.extend.pack(side="left", padx=6)
        else:
            self.extend.pack_forget()
            if active:
                title = "暂停" if s.state == "RUNNING" else "继续专注"
                detail = s.current_task + " · " + s.last_action
            elif plan:
                title, detail = "确认开始", "计划已生成，确认后开始计时。"
            else:
                title, detail = "预览计划", "输入目标和时长后预览学习计划。"
                if s.state == "COMPLETED":
                    detail = "本次计划已完成。可以输入下一个学习目标。"
        self.primary.configure(text=title)
        self.status.configure(text=detail)

    def tick(self):
        self.focus.update(None)
        self.render()
        self.root.after(400, self.tick)

    def choose_source(self):
        name = filedialog.askopenfilename(parent=self.root, filetypes=[("观测日志", "*.jsonl"), ("全部文件", "*")])
        if name:
            self.select(Path(name))

    def select(self, source):
        if self.job is not None:
            return
        self.source, self.report = source, None
        self.filename.configure(text=source.name)
        self.export.configure(state="normal")
        self.open_report.configure(state="disabled")
        self.message.configure(text="")

    def save_report(self):
        name = filedialog.asksaveasfilename(parent=self.root, initialfile=self.source.stem + ".html",
                                             defaultextension=".html", filetypes=[("HTML 报告", "*.html")])
        if not name:
            return
        self.export.configure(state="disabled")
        self.open_report.configure(state="disabled")
        self.message.configure(text="正在生成报告…")
        self.report = Path(name)
        self.job = self.worker.submit(export_report, self.source, self.report)
        self.root.after(100, self.check_export)

    def check_export(self):
        if not self.job.done():
            self.root.after(100, self.check_export)
            return
        try:
            self.job.result()
        except (OSError, ValueError) as error:
            self.report = None
            self.message.configure(text=f"生成失败：{error}")
        else:
            self.message.configure(text=f"已保存到 {self.report}")
            self.open_report.configure(state="normal")
        finally:
            self.job = None
            self.export.configure(state="normal")

    def open_html(self):
        webbrowser.open(self.report.resolve().as_uri())

    def close(self):
        if self.job is not None:
            messagebox.showinfo("观测回放", "报告正在生成，请稍后关闭。", parent=self.root)
            return
        self.focus.update(None)
        self.focus.checkpoint(force=True)
        self.worker.shutdown(wait=False)
        self.root.destroy()


def main():
    root = tk.Tk()
    data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local/share") / "EyeSeeYou Edge"
    data.mkdir(parents=True, exist_ok=True)
    lock = (data / "desktop.lock").open("a+b")
    try:
        if sys.platform == "win32":
            import msvcrt
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                messagebox.showinfo("EyeSeeYou Edge", "已有一个学习窗口正在运行。", parent=root)
                root.destroy()
                return
        database = Database(data / "sessions.sqlite")
        try:
            Desktop(root, database)
            root.mainloop()
        finally:
            database.conn.close()
    finally:
        lock.close()


if __name__ == "__main__":
    main()
