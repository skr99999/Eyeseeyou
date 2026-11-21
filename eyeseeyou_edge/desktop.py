"""Local study planner, focus timer and observation replay desktop application."""

from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from math import ceil
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .database import Database
from .desktop_view import BLUE, INK, MUTED, PAPER, SKY, TEAL, ReplayView, brand, card, label
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
        root.geometry(f"{min(1140, root.winfo_screenwidth()-45)}x{min(585, root.winfo_screenheight()-85)}")
        root.minsize(885, 550)
        root.configure(bg=SKY)
        root.option_add("*Font", "{Microsoft YaHei UI} 10")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", padding=(8, 5), background="#eff5fc", foreground=INK, borderwidth=1,
                        bordercolor="#d5e1ed", lightcolor="#eff5fc", darkcolor="#eff5fc")
        style.map("TButton", background=[("active", "#deebfc")])
        style.configure("Primary.TButton", background=BLUE, foreground=PAPER,
                        lightcolor=BLUE, darkcolor=BLUE, bordercolor=BLUE)
        style.map("Primary.TButton", background=[("active", "#1d4ed8")])
        style.configure("Horizontal.TScale", troughcolor="#e3edf6", background="#8db9e8",
                        bordercolor="#d4e4f4", lightcolor="#cce0f5", darkcolor="#8db9e8")
        style.configure("Horizontal.TProgressbar", background=BLUE, troughcolor="#e3edf6",
                        borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
        head = tk.Frame(root, bg=PAPER, padx=20, pady=10)
        head.pack(fill="x")
        brand(head)
        session = tk.Frame(head, bg=PAPER)
        session.pack(side="left", padx=(35, 12))
        self.session_state = label(session, "专注会话", 9, MUTED)
        self.session_state.pack(anchor="w")
        self.timer = label(session, size=25, color="#b66b09", bold=True)
        self.timer.configure(font=("Consolas", 26, "bold"))
        self.timer.pack(anchor="w")
        self.primary = ttk.Button(head, command=self.advance, style="Primary.TButton")
        self.primary.pack(side="left", padx=3)
        self.extend = ttk.Button(head, text="本段加时", command=lambda: self.command(
            "resolve_segment", {"completed": False, "source": "desktop"}))
        self.end = ttk.Button(head, text="结束专注", command=self.stop)
        self.end.pack(side="left", padx=3)
        label(head, "Windows  ·  离线桌面版", 9, TEAL).pack(side="right")

        board = tk.Frame(root, bg=SKY)
        board.pack(fill="both", expand=True, padx=9, pady=8)
        for i, weight in enumerate((40, 26, 34)):
            board.columnconfigure(i, weight=weight, uniform="panels")
        board.rowconfigure(0, weight=1)
        board.rowconfigure(1, minsize=110)
        chart, state, study = (card(board, 0, i) for i in range(3))
        label(chart, "观测回放", 16, bold=True).pack(anchor="w")
        self.filename = label(chart, "请选择观测日志", 9, MUTED)
        self.filename.pack(anchor="w")
        label(state, "疲劳状态", 16, bold=True).pack(anchor="w")
        label(state, "所选回放帧", 9, MUTED).pack(anchor="w")
        self.replay_view = ReplayView(chart, state)
        files = tk.Frame(chart, bg=PAPER)
        files.pack(anchor="w", pady=(7, 0))
        ttk.Button(files, text="打开日志…", command=self.choose_source).pack(side="left")
        assets = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        self.demo = assets / "examples" / "fatigue.jsonl"
        if self.demo.is_file():
            ttk.Button(files, text="内置样例", command=lambda: self.select(self.demo)).pack(side="left", padx=6)

        label(study, "学习助理", 16, bold=True).pack(anchor="w")
        label(study, "学习目标与时长", 9, MUTED).pack(anchor="w", pady=(6, 3))
        self.goal = tk.StringVar(value=self.focus.current.current_task or "背单词 20 分钟")
        self.entry = ttk.Entry(study, textvariable=self.goal)
        self.entry.pack(fill="x", ipady=4)
        self.entry.bind("<Return>", lambda _: self.advance())
        self.goal.trace_add("write", self.invalidate_preview)
        self.status = label(study, color=MUTED, wraplength=225)
        self.status.pack(anchor="w", pady=8)
        self.steps = tk.Frame(study, bg=PAPER)
        self.steps.pack(fill="x")
        self.shown_steps = None
        self.progress = ttk.Progressbar(study, maximum=100)

        history = card(board, 1, 0)
        label(history, "回放事件", 14, bold=True).pack(anchor="w")
        self.events = tk.Frame(history, bg=PAPER)
        self.events.pack(anchor="w", pady=(3, 0))
        report = card(board, 1, 1, 2)
        buttons = tk.Frame(report, bg=PAPER)
        buttons.pack(side="right", padx=(15, 0))
        self.export = ttk.Button(buttons, text="生成 HTML 报告…", command=self.save_report, state="disabled")
        self.export.pack(side="left", padx=5)
        self.open_report = ttk.Button(buttons, text="打开报告", state="disabled", command=self.open_html)
        self.open_report.pack(side="left")
        label(report, "回放报告", 15, bold=True).pack(anchor="w")
        self.message = label(report, color=MUTED, wraplength=285)
        self.message.pack(anchor="w")
        if self.demo.is_file():
            self.select(self.demo)
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
        elapsed = s.duration_seconds - s.remaining_seconds if active else 0
        steps = tuple((item["label"], round(item["seconds"])) for item in plan["subtasks"]) if plan else ()
        current = -1
        if active:
            boundary = 0
            for i, (_, duration) in enumerate(steps):
                boundary += duration
                if elapsed < boundary or s.segment_review_index == i:
                    current = i
                    break
        if (steps, current) != self.shown_steps:
            self.shown_steps = steps, current
            for widget in self.steps.winfo_children():
                widget.destroy()
            for i, (name, duration) in enumerate(steps):
                bg = "#dfedff" if i == current else "#f2f6fb"
                row = tk.Frame(self.steps, bg=bg, padx=8, pady=3, highlightthickness=1,
                               highlightbackground=BLUE if i == current else "#e5edf3")
                row.pack(fill="x", pady=2)
                badge = label(row, str(i+1), 9, PAPER, bold=True, padx=4)
                badge.configure(bg=BLUE)
                badge.pack(side="left", padx=(0, 8))
                label(row, name, bold=(i == current)).pack(side="left")
                minutes, sec = divmod(duration, 60)
                label(row, f"{minutes}:{sec:02d}", 10, MUTED).pack(side="right")
        if active and s.duration_seconds:
            self.progress.configure(value=100*elapsed/s.duration_seconds)
            self.progress.pack(fill="x", pady=(8, 0))
        else:
            self.progress.pack_forget()
        states = {"RUNNING": "进行中", "PAUSED": "已暂停", "AWAY": "离席", "COMPLETED": "已完成"}
        self.session_state.configure(text="专注会话  ·  " + states.get(s.state, "待开始"))
        seconds = ceil(s.remaining_seconds) if active else plan["total_seconds"] if plan else 0
        self.timer.configure(text=f"{int(seconds) // 60:02}:{int(seconds) % 60:02}")
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
        try:
            with source.open("rb") as stream:
                rows = list(islice(replay(stream), 241))
        except (OSError, ValueError) as error:
            messagebox.showerror("观测回放", str(error), parent=self.root)
            return
        self.source, self.report = source, None
        prefix = "内置样例" if source == self.demo else "本地日志"
        self.filename.configure(text=f"{prefix}  ·  {source.name}")
        self.replay_view.load(rows[:240])
        for widget in self.events.winfo_children():
            widget.destroy()
        events = [(i, row) for i, row in enumerate(rows[:240]) if row["action"]]
        for i, row in events[-2:]:
            action = "发出提醒" if row["action"] == "request_fatigue_alert" else "撤回提醒"
            ttk.Button(self.events, text=f"{row['t_ms']/1000:g}s  {action}",
                       command=lambda n=i: self.replay_view.slider.set(n)).pack(side="left", padx=(0, 5))
        if not events:
            label(self.events, "预览范围内没有提醒事件", 9, MUTED).pack()
        self.export.configure(state="normal")
        self.open_report.configure(state="disabled")
        self.message.configure(text="已预览前 240 帧，导出报告可查看完整日志。" if len(rows) > 240
                               else f"{source.name}  ·  共 {len(rows)} 帧，可导出逐帧判断和提醒记录。")

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
        if self.job is None:
            return
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
