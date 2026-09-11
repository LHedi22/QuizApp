/**
 * R4.1(a)/R4.2/R4.3 — in-browser camera capture for the single-photo scan
 * upload page. Feeds a captured, quality-checked still into the *existing*
 * `SubmissionPhotoUploadForm` file input via a hidden-input + DataTransfer
 * swap, then submits that same form natively — the server never sees a
 * difference between a camera capture and a file-picker upload (no second
 * upload code path).
 *
 * Wired up from a <script data-form-id="..." data-file-input-id="..."
 * data-health-url="..."> tag; see submission_upload.html.
 */
(function () {
  "use strict";

  var scriptEl = document.currentScript;

  // Calibrated against real corpus photos run through the dev server with a
  // fake camera device (docs/PROGRESS.md): jsQR needs real pixel density on
  // the printed QR to decode it, not just overall image sharpness — a QR
  // occupying ~11% of the sheet's width failed to decode below ~700px of
  // downsampled frame width even on a perfectly sharp photo. 1000px keeps a
  // safety margin above that floor while still being cheap for a one-shot
  // (not per-video-frame) capture-time check.
  var DOWNSAMPLE_WIDTH = 1000;
  var HEALTH_CHECK_INTERVAL_MS = 20000;
  var HEALTH_CHECK_TIMEOUT_MS = 4000;

  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  function setupCameraCapture(script) {
    var fileInput = document.getElementById(script.dataset.fileInputId);
    var form = document.getElementById(script.dataset.formId);
    var healthUrl = script.dataset.healthUrl;

    var cameraCapture = document.getElementById("camera-capture");
    var startBtn = document.getElementById("camera-start-btn");
    var shotBtn = document.getElementById("camera-shot-btn");
    var cancelBtn = document.getElementById("camera-cancel-btn");
    var useBtn = document.getElementById("camera-use-btn");
    var retakeBtn = document.getElementById("camera-retake-btn");
    var liveBox = document.getElementById("camera-live");
    var reviewBox = document.getElementById("camera-review");
    var video = document.getElementById("camera-video");
    var stillCanvas = document.getElementById("camera-still-canvas");
    var workCanvas = document.getElementById("camera-capture-canvas");
    var qualityMsg = document.getElementById("camera-quality-msg");
    var statusMsg = document.getElementById("camera-status");
    var banner = document.getElementById("camera-banner");

    if (!fileInput || !form || !cameraCapture || !startBtn) return;

    var supportsCamera = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    if (!supportsCamera) {
      // Graceful degradation: no broken UI, no dead capture button — just
      // fall back to the file picker that's already on the page.
      cameraCapture.hidden = true;
      return;
    }

    var stream = null;
    var reachable = true;

    function setBanner(message) {
      if (!message) {
        banner.hidden = true;
        banner.textContent = "";
        return;
      }
      banner.hidden = false;
      banner.textContent = message;
    }

    function setStatus(message, kind) {
      if (!message) {
        statusMsg.hidden = true;
        statusMsg.textContent = "";
        statusMsg.className = "camera-status";
        return;
      }
      statusMsg.hidden = false;
      statusMsg.textContent = message;
      statusMsg.className = "camera-status " + (kind || "");
    }

    function stopStream() {
      if (stream) {
        stream.getTracks().forEach(function (t) {
          t.stop();
        });
        stream = null;
      }
      video.srcObject = null;
    }

    function resetToIdle() {
      liveBox.hidden = true;
      reviewBox.hidden = true;
      startBtn.hidden = false;
      qualityMsg.textContent = "";
      qualityMsg.className = "camera-quality-msg";
    }

    function updateAvailability() {
      var offline = !navigator.onLine;
      var message = null;
      if (offline) {
        message = "You're offline — camera capture is disabled until connectivity returns.";
      } else if (!reachable) {
        message =
          "Can't reach the server right now — camera capture is disabled. " +
          "File upload may still work once the server is back.";
      }
      setBanner(message);
      var disable = offline || !reachable;
      startBtn.disabled = disable;
      // Don't yank an already-captured still out from under the professor on a
      // connectivity blip — only reclaim the live preview, never the review step.
      if (disable && stream && !liveBox.hidden) {
        stopStream();
        resetToIdle();
      }
    }

    function checkHealth() {
      if (!navigator.onLine) {
        reachable = false;
        updateAvailability();
        return;
      }
      var timedOut = false;
      var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      var timer = controller
        ? setTimeout(function () {
            timedOut = true;
            controller.abort();
          }, HEALTH_CHECK_TIMEOUT_MS)
        : null;
      fetch(healthUrl, { cache: "no-store", signal: controller ? controller.signal : undefined })
        .then(function (resp) {
          if (timer) clearTimeout(timer);
          reachable = resp.ok;
          updateAvailability();
        })
        .catch(function () {
          if (timer) clearTimeout(timer);
          reachable = false;
          updateAvailability();
        });
      void timedOut;
    }

    window.addEventListener("online", checkHealth);
    window.addEventListener("offline", updateAvailability);
    checkHealth();
    setInterval(checkHealth, HEALTH_CHECK_INTERVAL_MS);

    function startCamera() {
      var constraints = { video: { facingMode: { ideal: "environment" } }, audio: false };
      navigator.mediaDevices
        .getUserMedia(constraints)
        .catch(function () {
          // Fall back to any camera if the rear-camera preference can't be honored.
          return navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        })
        .then(function (mediaStream) {
          setStatus(null);
          stream = mediaStream;
          video.srcObject = stream;
          startBtn.hidden = true;
          liveBox.hidden = false;
          reviewBox.hidden = true;
        })
        .catch(function () {
          // No camera, permission denied, etc. — degrade to file picker only.
          setStatus("Couldn't access the camera — use the file picker below instead.", "error");
          startBtn.disabled = true;
        });
    }

    function cancelCamera() {
      stopStream();
      resetToIdle();
    }

    function capture() {
      var vw = video.videoWidth;
      var vh = video.videoHeight;
      if (!vw || !vh) return;

      stillCanvas.width = vw;
      stillCanvas.height = vh;
      stillCanvas.getContext("2d").drawImage(video, 0, 0, vw, vh);

      var scale = Math.min(1, DOWNSAMPLE_WIDTH / vw);
      var dw = Math.max(1, Math.round(vw * scale));
      var dh = Math.max(1, Math.round(vh * scale));
      workCanvas.width = dw;
      workCanvas.height = dh;
      var wctx = workCanvas.getContext("2d");
      wctx.drawImage(video, 0, 0, dw, dh);
      var imageData = wctx.getImageData(0, 0, dw, dh);

      var result = window.QualityCheck.checkFrame(imageData.data, dw, dh);

      liveBox.hidden = true;
      reviewBox.hidden = false;

      if (!result.ok) {
        var reasons = [];
        if (result.blurry) reasons.push("too blurry to read reliably");
        if (!result.hasPageQr) reasons.push("no page/QR code plausibly in frame");
        qualityMsg.textContent = "Retake — " + reasons.join(" and ") + ".";
        qualityMsg.className = "camera-quality-msg fail";
        useBtn.hidden = true;
      } else {
        qualityMsg.textContent = "Looks good — sharp, and a page/QR is plausibly in frame.";
        qualityMsg.className = "camera-quality-msg ok";
        useBtn.hidden = false;
      }
    }

    function retake() {
      reviewBox.hidden = true;
      useBtn.hidden = true;
      if (stream) {
        liveBox.hidden = false;
      } else {
        startCamera();
      }
    }

    function useCaptured() {
      stillCanvas.toBlob(
        function (blob) {
          if (!blob) {
            setStatus("Couldn't prepare the photo — please retake.", "error");
            return;
          }
          if (!navigator.onLine || !reachable) {
            // Never silently drop it (R4.3): keep the reviewed still on screen
            // so "Use this photo" can simply be clicked again once reachable.
            setStatus("Not submitted — you're offline or the server is unreachable. Retry when back online.", "error");
            return;
          }
          var file = new File([blob], "camera-capture.jpg", { type: "image/jpeg" });
          var dt = new DataTransfer();
          dt.items.add(file);
          fileInput.files = dt.files;
          stopStream();
          setStatus(null);
          if (form.requestSubmit) {
            form.requestSubmit();
          } else {
            form.submit();
          }
        },
        "image/jpeg",
        0.92
      );
    }

    startBtn.addEventListener("click", startCamera);
    cancelBtn.addEventListener("click", cancelCamera);
    shotBtn.addEventListener("click", capture);
    retakeBtn.addEventListener("click", retake);
    useBtn.addEventListener("click", useCaptured);
  }

  onReady(function () {
    if (scriptEl) setupCameraCapture(scriptEl);
  });
})();
