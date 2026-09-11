/**
 * R4.2/R8.3 client-side capture quality pre-check: plain local heuristics only,
 * no network call, no LLM. Two checks run against a downsampled canvas frame:
 *
 *  - blur: Laplacian-variance estimate on grayscale pixel data (R8.3's own
 *    example heuristic). Low variance -> too soft to plausibly read printed
 *    text/bubbles.
 *  - "is a page with a QR plausibly in frame": a real client-side QR decode
 *    via jsQR (vendor/jsQR.js — R8.3 explicitly names this library as an
 *    acceptable local heuristic, unlike an LLM call). A hand-rolled
 *    finder-pattern heuristic was tried first and calibrated against real
 *    corpus photos (docs/PROGRESS.md); it proved unreliable — both missing
 *    real, rotated QR codes at low downsample resolution *and* firing on
 *    dense printed content with no QR at all once resolution was raised
 *    enough to see the real one. A real decode attempt doesn't have either
 *    failure mode and is what R8.3 recommends, so it replaced the heuristic.
 *    "Plausibly in frame" == jsQR actually decodes something. This is a
 *    stricter, more honest signal than a plausibility guess — the tradeoff
 *    is it can't tell "no page" apart from "page present but QR occluded /
 *    still out of focus at the module level"; both correctly fail the check
 *    and prompt a retake, which is the right UX outcome either way.
 *
 * Threshold constants below are a documented judgement call, calibrated
 * against real camera-shaped frames (a real dev-server capture session
 * using Chromium's fake camera device fed from actual corpus photos — see
 * docs/PROGRESS.md) rather than guessed blind. They're overridable via the
 * `opts` params for future tuning against more corpus data.
 *
 * Dual CommonJS/browser module: works via a plain <script> tag (exposes
 * `window.QualityCheck`, and expects `window.jsQR` from vendor/jsQR.js to
 * already be loaded) and via `require()` from Node test files (pulls in
 * vendor/jsQR.js itself via a relative `require`), with no build step either
 * way.
 */
(function (global) {
  "use strict";

  var jsQRImpl = typeof module !== "undefined" && module.exports ? require("./vendor/jsQR.js") : global.jsQR;

  function toGrayscale(data, width, height) {
    const gray = new Float64Array(width * height);
    for (let i = 0, p = 0; p < gray.length; i += 4, p++) {
      gray[p] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    }
    return gray;
  }

  function laplacianVariance(data, width, height) {
    const gray = toGrayscale(data, width, height);
    if (width < 3 || height < 3) return 0;

    let n = 0;
    let mean = 0;
    let m2 = 0; // Welford's online variance — avoids buffering every value
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const idx = y * width + x;
        const value = 4 * gray[idx] - gray[idx - 1] - gray[idx + 1] - gray[idx - width] - gray[idx + width];
        n++;
        const delta = value - mean;
        mean += delta / n;
        m2 += delta * (value - mean);
      }
    }
    return n > 0 ? m2 / n : 0;
  }

  // Calibrated against the real dev-server capture session (docs/PROGRESS.md):
  // sharp real corpus photos measured ~500-900 on this scale; this threshold
  // sits comfortably below that with margin, not against a blurred synthetic.
  const BLUR_VARIANCE_THRESHOLD = 60;

  function isBlurry(data, width, height, threshold) {
    const t = threshold == null ? BLUR_VARIANCE_THRESHOLD : threshold;
    return laplacianVariance(data, width, height) < t;
  }

  function qrPlausible(data, width, height) {
    if (typeof jsQRImpl !== "function" || width < 15 || height < 15) return false;
    try {
      return !!jsQRImpl(data, width, height);
    } catch (e) {
      // jsQR throws on some malformed/edge-case buffers rather than
      // returning null — treat that the same as "no QR found".
      return false;
    }
  }

  /**
   * Run both checks on one downsampled RGBA canvas frame.
   * @param {Uint8ClampedArray|number[]} data - RGBA pixel bytes (canvas ImageData.data)
   * @param {number} width
   * @param {number} height
   * @param {{blurThreshold?: number}} [opts]
   */
  function checkFrame(data, width, height, opts) {
    const blurry = isBlurry(data, width, height, opts && opts.blurThreshold);
    const hasPageQr = qrPlausible(data, width, height);
    return { ok: !blurry && hasPageQr, blurry: blurry, hasPageQr: hasPageQr };
  }

  const api = {
    toGrayscale: toGrayscale,
    laplacianVariance: laplacianVariance,
    isBlurry: isBlurry,
    qrPlausible: qrPlausible,
    checkFrame: checkFrame,
    BLUR_VARIANCE_THRESHOLD: BLUR_VARIANCE_THRESHOLD,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    global.QualityCheck = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
