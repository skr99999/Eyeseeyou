const gapMs = 1000;
const sampleInterval = 125;
const alertMs = 1500;
const calibrationMs = 8000;
const poseLabels = {OK: "OK", OPEN_PALM: "张掌", FIST: "握拳"};
const byId = id => document.getElementById(id);

function pointDistance(points, a, b, width, height) {
  return Math.hypot((points[a].x - points[b].x) * width, (points[a].y - points[b].y) * height);
}

export function eyeRatios(points, width, height) {
  if (!points?.length) return null;
  const distance = (a, b) => pointDistance(points, a, b, width, height);
  function eye(a, b, c, d, e, f) {
    const span = distance(a, d);
    return span < 8 ? NaN : (distance(b, f) + distance(c, e)) / (2 * span);
  }
  const ratios = [eye(33,160,158,133,153,144), eye(362,385,387,263,373,380)];
  return ratios.every(Number.isFinite) ? ratios : null;
}

export function handPose(result, width, height) {
  const points = result.landmarks[0];
  const category = result.gestures[0]?.[0];
  if (!points || !category) return "";
  const distance = (a, b) => pointDistance(points, a, b, width, height);
  const scale = distance(0, 9);
  const extended = [12, 16, 20].filter(tip => distance(tip, 0) > 1.18 * distance(tip - 2, 0)).length;
  if (scale && distance(4, 8) < .30 * scale && extended >= 2) return "OK";
  if (category.categoryName === "Open_Palm" && category.score >= .6) return "OPEN_PALM";
  if (category.categoryName === "Closed_Fist" && category.score >= .7) return "FIST";
  return "";
}

export class EyeMonitor {
  thresholds = null;
  samples = [];
  start = 0;
  last = -Infinity;
  closure = null;
  closedFrames = 0;
  alarm = false;

  interrupt() {
    this.last = -Infinity;
    this.samples = [];
    this.closure = null;
    this.closedFrames = 0;
    this.alarm = false;
  }

  update(ratios, now) {
    if (now - this.last > gapMs || !ratios) this.interrupt();
    if (!ratios) return {status: "未取得有效眼部观测，请正视镜头", closureMs: 0};
    this.last = now;
    if (!this.thresholds) {
      if (!this.samples.length) this.start = now;
      this.samples.push(ratios);
      const elapsed = now - this.start;
      if (elapsed < calibrationMs) {
        return {status: `校准中 · 请自然睁眼 ${Math.floor(elapsed / 1000)} / 8 秒`, closureMs: 0};
      }
      this.thresholds = [0, 1].map(eye => {
        const ordered = this.samples.map(sample => sample[eye]).sort((a, b) => a - b);
        return Math.min(.24, Math.max(.12, ordered[Math.floor(ordered.length * .7)] * .58));
      });
      this.samples = [];
      return {status: "校准完成 · 正常", closureMs: 0};
    }
    if (ratios.every((value, eye) => value < this.thresholds[eye])) {
      this.closure ??= now;
      this.closedFrames += 1;
      const elapsed = now - this.closure;
      if (this.closedFrames >= 2 && elapsed >= alertMs) this.alarm = true;
      return {status: "校准完成 · 已取得眼部观测", closureMs: this.alarm ? elapsed : 0};
    }
    // An ambiguous frame cannot extend earlier evidence of continuous closure.
    this.closure = null;
    this.closedFrames = 0;
    this.alarm = false;
    return {status: "校准完成 · 正常", closureMs: 0};
  }
}

export class GestureHold {
  previous = -Infinity;
  firedAt = -Infinity;
  pose = "";
  start = 0;
  frames = 0;
  fired = false;

  update(pose, now) {
    if (pose !== this.pose || now - this.previous > 450) {
      this.start = now;
      this.pose = pose;
      this.frames = 0;
      this.fired = false;
    }
    this.previous = now;
    this.frames += 1;
    if (!pose || this.fired || this.frames < 5 || now - this.start < 900 || now - this.firedAt < 2000) return "";
    this.fired = true;
    this.firedAt = now;
    return pose;
  }
}

const startButton = byId("camera-start");
const stopButton = byId("camera-stop");
const video = byId("camera-preview");
const status = byId("camera-status");
const alert = byId("camera-alert");
const gesture = byId("camera-gesture");
const assets = new URL("./vision-assets/", import.meta.url);
let session = null;
let modelsPromise;

function setStatus(text) {
  if (status.textContent !== text) status.textContent = text;
}

function showEye(result) {
  setStatus(result.status);
  if (result.closureMs && alert.hidden) {
    alert.textContent = `疲劳提醒：持续闭眼 ${(result.closureMs / 1000).toFixed(1)} 秒，建议休息片刻。`;
    alert.hidden = false;
  } else if (!result.closureMs) {
    alert.hidden = true;
    alert.textContent = "";
  }
}

function loadModels() {
  if (!modelsPromise) modelsPromise = (async () => {
    const {FilesetResolver, FaceLandmarker, GestureRecognizer} = await import(new URL("vision_bundle.js", assets));
    const files = await FilesetResolver.forVisionTasks(new URL("wasm/", assets).href.replace(/\/$/, ""));
    const options = name => ({
      baseOptions: {modelAssetPath: new URL(name + ".task", assets).href, delegate: "CPU"},
      runningMode: "VIDEO",
    });
    const face = await FaceLandmarker.createFromOptions(files, options("face_landmarker"));
    try {
      const hand = await GestureRecognizer.createFromOptions(files, options("gesture_recognizer"));
      return {face, hand};
    } catch (error) {
      face.close();
      throw error;
    }
  })().catch(error => {
    modelsPromise = null;
    throw error;
  });
  return modelsPromise;
}

function stopCamera(message = "摄像头已关闭") {
  const current = session;
  if (!current) return;
  session = null;
  clearTimeout(current.request);
  current.stream?.getTracks().forEach(track => track.stop());
  video.srcObject = null;
  video.hidden = true;
  startButton.hidden = false;
  stopButton.hidden = true;
  gesture.hidden = true;
  showEye({status: message, closureMs: 0});
}

function tick(current, models) {
  if (current !== session) return;
  current.request = setTimeout(() => tick(current, models), sampleInterval);
  const now = performance.now();
  const canSample = !current.stream.getVideoTracks()[0].muted &&
    video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.currentTime !== current.videoTime;
  if (!canSample) {
    if (now - current.lastSample > gapMs) {
      current.eyes.interrupt();
      current.hold.update("", now);
      showEye({status: "摄像头暂未送来新画面", closureMs: 0});
    }
    return;
  }
  current.videoTime = video.currentTime;
  current.lastSample = now;
  try {
    const {videoWidth: width, videoHeight: height} = video;
    const face = models.face.detectForVideo(video, now);
    showEye(current.eyes.update(eyeRatios(face.faceLandmarks[0], width, height), now));
    const pose = current.hold.update(handPose(models.hand.recognizeForVideo(video, now), width, height), now);
    if (pose) {
      const handled = !document.dispatchEvent(new CustomEvent("eyeseeyou:gesture", {detail: pose, cancelable: true}));
      gesture.textContent = handled ? `${poseLabels[pose]}手势已控制计时` :
        pose === "OK" ? "识别到 OK，请先预览计划或查看正在运行的计时" : `识别到${poseLabels[pose]}，当前计时状态无需操作`;
      gesture.hidden = false;
    }
  } catch (error) {
    console.error("Camera inference error", error);
    stopCamera("实时识别中断，请重新开启摄像头");
  }
}

async function startCamera() {
  if (session) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("实时摄像头需要从 HTTPS 页面或 Android 安装包开启");
    return;
  }
  const current = {eyes: new EyeMonitor(), hold: new GestureHold(), lastSample: -Infinity, videoTime: -1};
  session = current;
  startButton.hidden = true;
  stopButton.hidden = false;
  setStatus("正在请求摄像头权限…");
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {facingMode: {ideal: "user"}, width: {ideal: 640}, height: {ideal: 480}, frameRate: {ideal: 24}},
    });
  } catch (error) {
    if (current === session) {
      stopCamera(error.name === "NotAllowedError" ? "未获摄像头权限，请在浏览器或系统设置里允许后重试" :
        "无法开启摄像头，请检查设备是否可用");
    }
    return;
  }
  if (current !== session) {
    stream.getTracks().forEach(track => track.stop());
    return;
  }
  current.stream = stream;
  stream.getVideoTracks()[0].addEventListener("ended", () => {
    if (current === session) stopCamera("摄像头已断开，请重新开启");
  });
  video.srcObject = stream;
  video.hidden = false;
  setStatus("正在初始化本机识别模型…");
  try {
    const [models] = await Promise.all([loadModels(), video.play()]);
    if (current === session) {
      setStatus("请正视镜头，自然睁眼约 8 秒");
      tick(current, models);
    }
  } catch (error) {
    if (current === session) {
      console.error("Camera initialization error", error);
      stopCamera("无法初始化本机识别，请确认模型已加载，然后重试");
    }
  }
}

startButton.addEventListener("click", startCamera);
stopButton.addEventListener("click", () => stopCamera());
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopCamera("切到后台时已关闭摄像头");
});
window.addEventListener("pagehide", () => stopCamera());
document.addEventListener("eyeseeyou:background", () => stopCamera("切到后台时已关闭摄像头"));
