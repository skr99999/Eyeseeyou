(() => {
  const dialog = document.getElementById("guide");
  const openButton = document.getElementById("guide-open");
  const closeButton = document.getElementById("guide-close");
  const next = document.getElementById("guide-next");
  const previous = document.getElementById("guide-previous");
  const replay = dialog.querySelector(".guide-replay");
  replay.insertAdjacentHTML("beforebegin", `
    <div class="guide-scene guide-camera" data-guide-scene hidden>
      <div class="guide-demo">
        <div class="guide-demo-label">摄像头 · 疲劳提醒</div>
        <div class="guide-camera-strip">
          <div class="guide-camera-card">
            <span class="guide-camera-symbol">📷</span><b>允许相机</b><span>开启摄像头</span>
          </div>
          <div class="guide-camera-card">
            <span class="guide-camera-symbol">🙂</span><b>自然睁眼</b><span>正视约 8 秒</span>
          </div>
          <div class="guide-camera-card">
            <span class="guide-camera-symbol">😌</span><b>持续闭眼</b><span>达到 1.5 秒提醒</span>
          </div>
        </div>
      </div>
    </div>
    <div class="guide-scene guide-gestures" data-guide-scene hidden>
      <div class="guide-demo">
        <div class="guide-demo-label">摄像头 · 手势控制</div>
        <div class="guide-camera-strip">
          <div class="guide-camera-card">
            <span class="guide-camera-symbol">👌</span><b>OK</b><span>开始或继续</span>
          </div>
          <div class="guide-camera-card">
            <span class="guide-camera-symbol">✋</span><b>张掌</b><span>暂停</span>
          </div>
          <div class="guide-camera-card">
            <span class="guide-camera-symbol">✊</span><b>握拳</b><span>结束并保存</span>
          </div>
        </div>
      </div>
    </div>
  `);
  const scenes = [...dialog.querySelectorAll("[data-guide-scene]")];
  const steps = [
    ["安排一次学习", "在「学习助理」填写目标和时长，点「预览计划」查看分配到每个步骤的时间。"],
    ["按自己的节奏专注", "点「开始专注」启动计时。中途可以暂停并继续，点「结束并保存」可留下本次记录。"],
    ["开启摄像头并校准", "点「开启摄像头」并允许访问。自然睁眼正视镜头约 8 秒进行校准。之后连续闭眼达到 1.5 秒时，页面会显示提醒。"],
    ["试试三种手势", "先预览计划，再把一只手完整放进画面。手势保持约 1 秒。OK 开始或继续，张掌暂停，握拳结束并保存。"],
    ["看看提醒如何触发", "在「样例回放」选择一段记录，拖动进度条，或点提醒时刻跳到对应的观测帧。"],
  ];
  const hiddenKey = "eyeseeyou-guide-disabled";
  const shownKey = "eyeseeyou-guide-shown";
  let index = 0;

  function render() {
    scenes.forEach((scene, position) => { scene.hidden = position !== index; });
    document.getElementById("guide-progress").textContent = `使用教学 · ${index + 1} / ${steps.length}`;
    document.getElementById("guide-title").textContent = steps[index][0];
    document.getElementById("guide-detail").textContent = steps[index][1];
    previous.disabled = index === 0;
    next.textContent = index === steps.length - 1 ? "完成" : "下一步";
  }

  function show() {
    index = 0;
    render();
    dialog.showModal();
    try { sessionStorage.setItem(shownKey, "1"); } catch {}
  }

  const frames = REPLAY_DATA.fatigue;
  const point = frame => [12 + frame.t_ms / frames[frames.length - 1].t_ms * 228, 59 - frame.perclos * 38];
  document.getElementById("guide-curve").setAttribute("points", frames.map(frame => point(frame).join(",")).join(" "));
  for (const [marker, action] of [["alert", "request_fatigue_alert"], ["clear", "clear_fatigue_alert"]]) {
    const [x, y] = point(frames.find(frame => frame.action === action));
    const circle = document.getElementById(`guide-${marker}-marker`);
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
  }

  openButton.addEventListener("click", show);
  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => openButton.focus({preventScroll: true}));
  previous.addEventListener("click", () => {
    index -= 1;
    render();
    if (previous.disabled) next.focus();
  });
  next.addEventListener("click", () => {
    if (index === steps.length - 1) dialog.close();
    else {
      index += 1;
      render();
    }
  });
  document.getElementById("guide-disable").addEventListener("click", () => {
    try {
      localStorage.setItem(hiddenKey, "1");
      dialog.close();
    } catch {
      document.getElementById("guide-detail").textContent = "浏览器无法保存此设置。仍可关闭本次教学。";
    }
  });

  let autoShow = true;
  try { autoShow = !localStorage.getItem(hiddenKey) && !sessionStorage.getItem(shownKey); } catch {}
  if (autoShow) show();
})();
