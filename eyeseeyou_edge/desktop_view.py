"""Native desktop widgets using the A210 dashboard palette and layout."""

import tkinter as tk
from tkinter import ttk


INK, MUTED, BLUE, TEAL = "#1e293b", "#52677d", "#2563eb", "#087e91"
SKY, PAPER, NIGHT = "#b9dafa", "#ffffff", "#0b1928"
FONT = "Microsoft YaHei UI"


def label(parent, text="", size=10, color=INK, bold=False, **options):
    return tk.Label(parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
                    fg=color, bg=parent.cget("bg"), anchor="w", justify="left", **options)


def card(parent, row, column, span=1):
    shell = tk.Canvas(parent, bg=SKY, highlightthickness=0, width=1, height=1)
    shell.grid(row=row, column=column, columnspan=span, sticky="nsew", padx=5, pady=5)
    body = tk.Frame(shell, bg=PAPER)
    panel = shell.create_window(16, 15, window=body, anchor="nw")

    def fit(event):
        w, h, r = event.width, event.height, 15
        shell.delete("surface")
        shell.create_polygon(r,0,w-r,0,w,0,w,r,w,h-r,w,h,w-r,h,r,h,0,h,0,h-r,0,r,0,0,
                             fill=PAPER, smooth=True, tags="surface")
        shell.tag_lower("surface")
        shell.itemconfigure(panel, width=max(1, w-32), height=max(1, h-30))
    shell.bind("<Configure>", fit)
    return body


def brand(parent):
    icon = tk.Canvas(parent, width=57, height=45, bg=PAPER, highlightthickness=0)
    icon.pack(side="left", padx=(0, 10))
    icon.create_polygon(4,22,15,8,28,6,41,8,52,22,41,36,28,38,15,36,
                        smooth=True, fill=PAPER, outline=BLUE, width=2)
    icon.create_oval(19,13,37,31, outline=BLUE, width=2)
    icon.create_oval(25,19,31,25, outline="", fill=TEAL)
    for x, y, dx, dy in [(2,3,1,1),(54,3,-1,1),(2,41,1,-1),(54,41,-1,-1)]:
        icon.create_line(x+7*dx,y,x,y,x,y+7*dy, fill=TEAL, width=2)
    word = tk.Frame(parent, bg=PAPER)
    word.pack(side="left")
    label(word, "EyeSeeYou", 20, bold=True).pack(anchor="w")
    label(word, "疲劳监测与专注管理 Agent", 9, MUTED).pack(anchor="w")


class ReplayView:
    def __init__(self, chart, state):
        self.live = False
        self.rows = []
        self.plot = tk.Canvas(chart, bg=NIGHT, bd=0, highlightthickness=0, height=120)
        self.plot.pack(fill="both", expand=True, pady=(8, 5))
        self.plot.bind("<Configure>", lambda _: self.draw())
        self.slider = ttk.Scale(chart, from_=0, to=1, command=self.draw)
        self.slider.pack(fill="x")
        self.position = label(chart, color=MUTED)
        self.position.pack(anchor="w")
        self.state = label(state, "—", 19, bold=True)
        self.state.pack(anchor="w", pady=(10, 0))
        self.reason = label(state, color=MUTED, wraplength=210)
        self.reason.pack(anchor="w", pady=(0, 10))
        tiles = tk.Frame(state, bg=PAPER)
        tiles.pack(fill="x")
        self.metrics = []
        for i, name in enumerate(("闭眼占比", "连续闭眼", "累计眨眼", "风险分数")):
            col = i % 2
            tiles.columnconfigure(col, weight=1, uniform="tile")
            tile = tk.Frame(tiles, bg="#f0f6fc", padx=9, pady=5)
            tile.grid(row=i//2, column=col, sticky="nsew", padx=2, pady=2)
            label(tile, name, 9, MUTED).pack(anchor="w")
            value = label(tile, "—", 15, bold=True)
            value.pack(anchor="w")
            self.metrics.append(value)

    def load(self, rows):
        self.rows = rows
        chosen = next((i for i, row in enumerate(rows) if row["action"] == "request_fatigue_alert"), 0)
        self.slider.configure(to=max(1, len(rows)-1), state="normal" if len(rows)>1 else "disabled")
        self.slider.set(chosen)
        self.draw()

    def draw(self, *_):
        if self.live or not self.rows:
            return
        index = min(round(self.slider.get()), len(self.rows)-1)
        row = self.rows[index]
        self.position.configure(text=f"第 {index+1} / {len(self.rows)} 帧     ·     {row['t_ms']/1000:g} 秒")
        self.state.configure(text=row["state"], fg="#ae432c" if row["alarm"] else TEAL)
        reason = "、".join(row["reasons"]) or ("眼部观测有效" if row["eye_sample_valid"] else "缺少有效眼部观测")
        self.reason.configure(text=reason)
        values = (f"{row['perclos']:.0%}", f"{row['eye_closed_seconds']:g} s",
                  str(row['blinks_total']), f"{row['risk_score']:.2f}")
        for widget, value in zip(self.metrics, values):
            widget.configure(text=value)
        plot = self.plot
        plot.delete("all")
        w, h = plot.winfo_width(), plot.winfo_height()
        if w < 55 or h < 65:
            return
        left, right, top, bottom = 33, w-17, 35, h-23
        start, end = self.rows[0]["t_ms"], self.rows[-1]["t_ms"]
        peak = max(1, max(item["eye_closed_seconds"] for item in self.rows))
        plot.create_text(12,14,anchor="w",text="连续闭眼时长  /  秒",fill="#d5eafa",font=(FONT,9))
        for ratio in (0, .5, 1):
            y = bottom-ratio*(bottom-top)
            plot.create_line(left,y,right,y,fill="#294056")
            plot.create_text(left-5,y,anchor="e",text=f"{ratio*peak:.1f}",fill="#92aac0",font=("Segoe UI",8))
        for i, item in enumerate(self.rows):
            x = left+(right-left)*(item["t_ms"]-start)/max(1,end-start)
            if i == index:
                plot.create_line(x,top,x,bottom,fill="#ffbd65",dash=(3,3))
            if item["eye_sample_valid"]:
                y = bottom-(bottom-top)*item["eye_closed_seconds"]/peak
                color = "#ffbd65" if i == index else "#5ed9e0"
                plot.create_line(x,bottom,x,y,fill=color,width=2)
                plot.create_oval(x-2,y-2,x+2,y+2,fill=color,outline="")
        for x, stamp, anchor in ((left,start,"w"),(right,end,"e")):
            plot.create_text(x,h-10,anchor=anchor,text=f"{stamp/1000:g} s",fill="#92aac0",font=("Segoe UI",8))
