const get = id => document.getElementById(id);
const key = "eyeseeyou-mobile-v1";
let state = {plan: null, active: null, history: []};
try {
  const saved = localStorage.getItem(key);
  if (saved) state = JSON.parse(saved);
} catch {
  get("empty-history").textContent = "本机存储当前不可用。";
}

function save() {
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch {
    get("empty-history").hidden = false;
    get("empty-history").textContent = "保存失败，请检查浏览器的存储权限或剩余空间。";
  }
}

const general = [
  ["专注完成"], ["核心学习", "快速回顾"],
  ["知识梳理", "练习巩固", "总结复盘"], ["概念复习", "例题讲解", "独立练习", "总结复盘"],
];
const vocabulary = [
  ["集中背诵"], ["集中记忆", "快速复习"],
  ["词汇学习", "回忆测试", "错词复盘"], ["新词预览", "集中记忆", "回忆测试", "错词复盘"],
];
const weights = [[100], [80, 20], [35, 50, 15], [25, 25, 37.5, 12.5]];

function previewPlan(task, minutes) {
  const index = [5, 15, 30].filter(threshold => minutes >= threshold).length;
  const labels = (/单词|词汇|背词|vocab/i.test(task) ? vocabulary : general)[index];
  const exact = weights[index].map(weight => minutes * weight / 100);
  const units = exact.map(Math.floor);
  const extra = minutes - units.reduce((sum, unit) => sum + unit, 0);
  const order = exact.map((_, i) => i).sort((a, b) => (exact[b] - units[b]) - (exact[a] - units[a]));
  for (const i of order.slice(0, extra)) units[i] += 1;
  return {task, minutes, steps: labels.map((label, i) => ({label, minutes: units[i]}))};
}

function renderPlan() {
  const {plan, active} = state;
  get("plan-status").hidden = !plan;
  get("plan-steps").hidden = !plan;
  get("plan-status").textContent = plan ? `${plan.task} · ${plan.minutes} 分钟` : "";
  get("plan-steps").replaceChildren(...(plan?.steps || []).map(step => {
    const item = document.createElement("li");
    item.textContent = `${step.label} · ${step.minutes} 分钟`;
    return item;
  }));
  for (const id of ["goal", "minutes", "preview"]) get(id).disabled = Boolean(active);
}

function renderHistory() {
  get("empty-history").hidden = state.history.length > 0;
  get("history").replaceChildren(...state.history.map(record => {
    const item = document.createElement("li");
    const date = new Date(record.time).toLocaleString("zh-CN", {dateStyle: "short", timeStyle: "short"});
    item.textContent = `${record.task} · ${formatTime(record.elapsed)} · ${record.done ? "已完成" : "提前结束"} · ${date}`;
    return item;
  }));
}

function formatTime(seconds) {
  return [Math.floor(seconds / 60), seconds % 60].map(value => String(value).padStart(2, "0")).join(":");
}

function remaining(active, now = Date.now()) {
  return active.endAt === null ? active.remaining : Math.max(0, active.endAt - now);
}

function finish(now = Date.now()) {
  const {active} = state;
  const left = remaining(active, now);
  const total = active.plan.minutes * 60000;
  state.history.unshift({
    task: active.plan.task,
    time: left === 0 && active.endAt !== null ? active.endAt : now,
    elapsed: Math.max(0, Math.floor((total - left) / 1000)),
    done: left === 0,
  });
  state.active = null;
  renderHistory();
  save();
  renderPlan();
}

function renderTimer() {
  if (state.active && remaining(state.active) === 0) finish();
  const {active, plan} = state;
  const running = active && active.endAt !== null;
  const seconds = active ? Math.ceil(remaining(active) / 1000) : (plan?.minutes || Number(get("minutes").value) || 20) * 60;
  get("clock").textContent = formatTime(seconds);
  get("current-task").textContent = active?.plan.task || plan?.task || "准备开始";
  let status = plan ? "计划已就绪" : "预览学习计划后即可开始";
  if (active) {
    let elapsed = active.plan.minutes * 60 - seconds;
    const step = active.plan.steps.find(item => {
      elapsed -= item.minutes * 60;
      return elapsed < 0;
    });
    status = `${running ? "进行中" : "已暂停"} · ${step?.label || active.plan.task}`;
  }
  if (get("timer-status").textContent !== status) get("timer-status").textContent = status;
  get("timer-toggle").textContent = running ? "暂停" : active ? "继续专注" : "开始专注";
  get("timer-toggle").disabled = !plan;
  get("timer-end").hidden = !active;
}

get("plan-form").addEventListener("submit", event => {
  event.preventDefault();
  if (state.active) return;
  const goal = get("goal");
  const task = goal.value.trim();
  if (!task) {
    goal.setCustomValidity("请输入学习目标");
    goal.reportValidity();
    return;
  }
  state.plan = previewPlan(task, Number(get("minutes").value));
  save();
  renderPlan();
  renderTimer();
});

get("goal").addEventListener("input", () => get("goal").setCustomValidity(""));
get("minutes").addEventListener("input", renderTimer);

get("timer-toggle").addEventListener("click", () => {
  const now = Date.now();
  const {active, plan} = state;
  if (active && remaining(active, now) === 0) {
    finish(now);
  } else if (!active) {
    state.active = {plan, endAt: now + plan.minutes * 60000, remaining: null};
  } else if (active.endAt !== null) {
    active.remaining = remaining(active, now);
    active.endAt = null;
  } else {
    active.endAt = now + active.remaining;
    active.remaining = null;
  }
  save();
  renderPlan();
  renderTimer();
});

get("timer-end").addEventListener("click", () => {
  if (state.active) finish();
  renderTimer();
});

document.addEventListener("eyeseeyou:gesture", event => {
  renderTimer();
  const {active, plan} = state;
  const running = active && active.endAt !== null;
  const pose = event.detail;
  if (pose === "OK" && plan && !running || pose === "OPEN_PALM" && running) {
    get("timer-toggle").click();
    event.preventDefault();
  } else if (pose === "FIST" && active) {
    get("timer-end").click();
    event.preventDefault();
  }
});


const stateNames = {
  NORMAL: "正常", CALIBRATING: "校准中", FATIGUE: "疲劳提醒",
  RECOVERING: "恢复中", NO_FACE: "未检测到人脸", UNCERTAIN: "眼部观测不确定",
};
const actions = {request_fatigue_alert: "发出提醒", clear_fatigue_alert: "撤回提醒"};
let frames = [];
let playTimer = null;

function renderFrame() {
  const index = Number(get("frame").value);
  const row = frames[index];
  get("position").textContent = `第 ${index + 1} / ${frames.length} 帧 · ${row.t_ms / 1000} 秒`;
  const reason = row.reasons.join("、") || (row.eye_sample_valid ? "眼部观测有效" : "缺少有效眼部观测");
  get("result").textContent = `${stateNames[row.state] || row.state} · ${reason}`;
  get("result").style.color = row.alarm ? "#ae432c" : "#087084";
  get("perclos").textContent = `${Math.round(row.perclos * 100)}%`;
  get("closed").textContent = `${row.eye_closed_seconds} 秒`;
  get("blinks").textContent = row.blinks_total;
  get("risk").textContent = row.risk_score.toFixed(2);

  const canvas = get("chart");
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const x = frame => 14 + frame.t_ms / frames.at(-1).t_ms * (width - 28);
  const y = rate => height - 18 - rate * (height - 36);
  context.clearRect(0, 0, width, height);
  context.lineWidth = 2;
  context.strokeStyle = "#355069";
  context.beginPath();
  for (const rate of [0, .5, 1]) {
    context.moveTo(14, y(rate));
    context.lineTo(width - 14, y(rate));
  }
  context.stroke();
  context.lineWidth = 4;
  context.strokeStyle = "#7dd3fc";
  context.beginPath();
  frames.forEach((frame, i) => {
    if (i === 0) context.moveTo(x(frame), y(frame.perclos));
    else context.lineTo(x(frame), y(frame.perclos));
  });
  context.stroke();
  context.fillStyle = row.alarm ? "#fda18b" : "#fff";
  context.beginPath();
  context.arc(x(row), y(row.perclos), 7, 0, Math.PI * 2);
  context.fill();
}

function stopReplay() {
  clearTimeout(playTimer);
  playTimer = null;
  get("play").textContent = "播放";
}

function advanceReplay() {
  const slider = get("frame");
  const index = Number(slider.value);
  if (index === frames.length - 1) {
    stopReplay();
    return;
  }
  playTimer = setTimeout(() => {
    slider.value = index + 1;
    renderFrame();
    advanceReplay();
  }, frames[index + 1].t_ms - frames[index].t_ms);
}

function selectReplay() {
  stopReplay();
  frames = REPLAY_DATA[get("sample").value];
  const slider = get("frame");
  const firstAlert = frames.findIndex(row => row.action === "request_fatigue_alert");
  slider.max = frames.length - 1;
  slider.value = Math.max(firstAlert, 0);
  const buttons = [];
  frames.forEach((row, i) => {
    if (!actions[row.action]) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = `${row.t_ms / 1000}s ${actions[row.action]}`;
    button.addEventListener("click", () => {
      stopReplay();
      slider.value = i;
      renderFrame();
    });
    buttons.push(button);
  });
  get("events").replaceChildren(...buttons);
  renderFrame();
}

get("sample").addEventListener("change", selectReplay);
get("frame").addEventListener("input", () => {
  stopReplay();
  renderFrame();
});
get("play").addEventListener("click", () => {
  if (playTimer !== null) {
    stopReplay();
    return;
  }
  const slider = get("frame");
  if (slider.value === slider.max) slider.value = 0;
  renderFrame();
  get("play").textContent = "暂停回放";
  advanceReplay();
});

if (state.plan) {
  get("goal").value = state.plan.task;
  get("minutes").value = state.plan.minutes;
}
renderHistory();
renderPlan();
renderTimer();
selectReplay();
setInterval(renderTimer, 250);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopReplay();
  else renderTimer();
});
window.addEventListener("pageshow", renderTimer);

if ("serviceWorker" in navigator && window.isSecureContext &&
    /^https?:$/.test(location.protocol) && location.hostname !== "appassets.androidplatform.net") {
  navigator.serviceWorker.register("./sw.js").catch(error => console.warn("离线缓存初始化失败", error));
}
