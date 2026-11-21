"""Write a standalone HTML view of the regular replay output."""

from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile


HEADER = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>EyeSeeYou Edge · 回放报告</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5ef;color:#183b30;font:16px/1.5 Inter,"Microsoft YaHei",sans-serif}
main{max-width:1140px;padding:clamp(16px,4vw,54px);margin:auto;display:flex;flex-direction:column}
header{order:-2;background:#153b31;color:#f4f6ea;border-radius:14px;padding:28px 32px}
header p{margin:0;color:#b9d6c7}h1{margin:4px 0 8px;font-size:clamp(24px,4vw,38px)}
.summary{order:-1;padding:14px 0;border-bottom:1px solid #bacbc0;font-variant-numeric:tabular-nums}
label{align-self:flex-start;margin:14px 0;cursor:pointer}input{accent-color:#245a45}
.frames{overflow-x:auto;background:white;border:1px solid #c4d1c7;border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:14px;white-space:nowrap;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #dee6df}th{background:#e3ece3}
.request_fatigue_alert{background:#fff0d7}.clear_fatigue_alert{background:#dff4e8}
label:has(input:checked) ~ .frames tbody tr:not(.request_fatigue_alert):not(.clear_fatigue_alert){display:none}
</style><main><header><p>EyeSeeYou Edge</p><h1>观测与提醒回放</h1>"""

TABLE = """</header><label><input type="checkbox"> 只看发出或撤回提醒的帧</label>
<div class="frames" tabindex="0" role="region" aria-label="逐帧回放"><table><thead><tr>
<th>时间戳 (ms)</th><th>距前帧</th><th>眼部观测</th><th>状态</th><th>连续闭眼</th>
<th>闭眼占比</th><th>动作</th><th>判断理由</th></tr></thead><tbody>
"""

ACTIONS = {"request_fatigue_alert": "发出提醒", "clear_fatigue_alert": "撤回提醒"}


def write_report(path, source_name, decisions):
    # Replace a previous report only after the entire input has passed validation.
    temp = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    pending = Path(temp.name)
    try:
        with temp:
            temp.write(HEADER + f"<p>{escape(source_name)}</p>" + TABLE)
            previous_ms = None
            frame = 0
            counts = dict.fromkeys(ACTIONS, 0)
            for frame, row in enumerate(decisions, 1):
                t_ms = row["t_ms"]
                interval = "—" if previous_ms is None else f"{t_ms - previous_ms} ms"
                previous_ms = t_ms
                action = row["action"]
                if action:
                    counts[action] += 1
                eye = {"OPEN": "睁眼", "CLOSED": "闭眼", "UNCERTAIN": "无法判断"}[row["eye_state"]]
                cells = (t_ms, interval, eye, row["state"], f"{row['eye_closed_seconds']:g} s",
                         f"{row['perclos']:.2%}", ACTIONS.get(action, "—"), "、".join(row["reasons"]) or "—")
                temp.write(f'<tr id="t-{t_ms}" class="{action or ""}">' +
                           "".join(f"<td>{escape(str(cell))}</td>" for cell in cells) + "</tr>\n")
            temp.write(f'</tbody></table></div><p class="summary">{frame} 帧 · '
                       f'发出提醒 {counts["request_fatigue_alert"]} 次 · 撤回提醒 {counts["clear_fatigue_alert"]} 次'
                       '</p></main></html>')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
