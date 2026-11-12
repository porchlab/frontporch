(() => {
  "use strict";
  const scanner = document.querySelector("[data-phone-scanner]");
  if (scanner) {
    const video = scanner.querySelector("video");
    const message = scanner.querySelector("[data-scan-message]");
    const stopButton = scanner.querySelector("[data-scan-stop]");
    let controls = null;
    let generation = 0;
    function stop() {
      generation += 1;
      if (controls) controls.stop();
      controls = null;
      if (video.srcObject) video.srcObject.getTracks().forEach(track => track.stop());
      video.srcObject = null;
      video.hidden = true;
      stopButton.hidden = true;
    }
    stopButton.addEventListener("click", stop);
    window.addEventListener("pagehide", stop);
    document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
    scanner.querySelectorAll("[data-scan]").forEach(button => button.addEventListener("click", async () => {
      stop();
      const request = generation;
      const field = button.dataset.scan;
      if (!navigator.mediaDevices?.getUserMedia || !window.ZXingBrowser) {
        message.textContent = "Camera scanning isn't available here. Enter the label details in the fields below.";
        return;
      }
      message.textContent = `Point the camera at the barcode labelled ${field === "mac" ? "MAC" : "S/N"}.`;
      video.hidden = false;
      stopButton.hidden = false;
      try {
        const reader = new window.ZXingBrowser.BrowserMultiFormatReader();
        const current = await reader.decodeFromConstraints({audio: false, video: {facingMode: {ideal: "environment"}}}, video, result => {
          if (!result || request !== generation) return;
          const text = result.getText().trim().replace(/^(MAC|S\/N|SN)\s*[:=]?\s*/i, "").toUpperCase();
          const value = field === "mac" ? text.replace(/[:-]/g, "") : text;
          if (!(field === "mac" ? /^[A-F0-9]{12}$/ : /^[A-Z0-9]{8,64}$/).test(value)) return;
          if (field === "serial" && /^[A-F0-9]{12}$/.test(value)) return;
          document.getElementById(`id_${field}`).value = value;
          document.getElementById(`id_${field}`).focus();
          message.textContent = `${field === "mac" ? "MAC" : "S/N"} filled in. Check it against the printed label before registering.`;
          stop();
        });
        if (request !== generation) current.stop();
        else controls = current;
      } catch (_) {
        if (request !== generation) return;
        stop();
        message.textContent = "We couldn't open the camera. Allow camera access or enter the label details below.";
      }
    }));
    document.getElementById("phone-registration").addEventListener("submit", stop);
  }
  const progress = document.querySelector("[data-phone-progress]");
  if (!progress || progress.dataset.finished === "true") return;
  const el = name => progress.querySelector(`[data-progress-${name}]`);
  let timer;
  let stopped = false;
  async function refresh() {
    if (document.hidden || stopped) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(progress.dataset.phoneProgress, {credentials: "same-origin", cache: "no-store", signal: controller.signal});
      if (!response.ok || !response.headers.get("Content-Type")?.includes("application/json")) throw new Error("refresh failed");
      const data = await response.json();
      el("title").textContent = data.title;
      el("message").textContent = data.message;
      el("working").hidden = data.finished;
      el("firmware").hidden = !data.firmware;
      el("firmware").querySelector("span").textContent = data.firmware;
      el("downloaded").hidden = !data.downloaded || data.state === "ready";
      el("extension").textContent = data.extension;
      el("ready").hidden = data.state !== "ready";
      el("check").hidden = !data.check_allowed;
      el("reset").hidden = !data.reset_confirmation;
      el("deregistered").hidden = !data.deregistered;
      el("deregister").hidden = !data.can_deregister;
      el("instructions").hidden = data.removing;
      el("stale").hidden = true;
      stopped = data.finished;
    } catch (_) { el("stale").hidden = false; }
    finally { clearTimeout(timeout); if (!stopped) timer = setTimeout(refresh, 10000); }
  }
  document.addEventListener("visibilitychange", () => { clearTimeout(timer); if (!document.hidden) refresh(); });
  window.addEventListener("pagehide", () => { stopped = true; clearTimeout(timer); });
  timer = setTimeout(refresh, 5000);
})();
