/**
 * Unit tests for the R4.2 client-side capture quality pre-check
 * (app/web/static/web/quality_check.js). Pure heuristics, no DOM/browser
 * needed — run with the Node built-in test runner:
 *
 *   node --test
 *
 * The "sharp, passes" fixture (tests/js/fixtures/qr_frame.{rgba,json}) is a
 * real, jsQR-decodable QR code composited with a checkerboard block (real
 * qrcode+Pillow output, not a hand-drawn pattern) — see fixtures/qr_frame.json
 * and scripts note in docs/PROGRESS.md for how it was generated. The
 * "blurred, fails" case is produced *by this test*, by box-blurring that
 * same fixture, so the pass/fail behavior is demonstrated running against
 * one consistent frame, not asserted by inspection or precomputed offline.
 *
 * Threshold calibration against *real camera-shaped* frames (not just this
 * synthetic fixture) was done separately with a real corpus photo pushed
 * through a real dev server via Chromium's fake camera device — see
 * docs/PROGRESS.md for that session's findings, including why the QR check
 * uses jsQR (vendor/jsQR.js) rather than a hand-rolled heuristic.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const QualityCheck = require("../../app/web/static/web/quality_check.js");

const FIXTURES_DIR = path.join(__dirname, "fixtures");

function loadFixture(name) {
  const meta = JSON.parse(fs.readFileSync(path.join(FIXTURES_DIR, `${name}.json`), "utf8"));
  const raw = fs.readFileSync(path.join(FIXTURES_DIR, `${name}.rgba`));
  const data = new Uint8ClampedArray(raw.buffer, raw.byteOffset, raw.byteLength);
  return { data, width: meta.width, height: meta.height };
}

function boxBlur(data, width, height, radius) {
  const out = new Uint8ClampedArray(data.length);
  const tmp = new Float64Array(data.length);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      for (let c = 0; c < 3; c++) {
        let sum = 0;
        let n = 0;
        for (let k = -radius; k <= radius; k++) {
          const sx = Math.min(width - 1, Math.max(0, x + k));
          sum += data[(y * width + sx) * 4 + c];
          n++;
        }
        tmp[(y * width + x) * 4 + c] = sum / n;
      }
    }
  }
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      for (let c = 0; c < 3; c++) {
        let sum = 0;
        let n = 0;
        for (let k = -radius; k <= radius; k++) {
          const sy = Math.min(height - 1, Math.max(0, y + k));
          sum += tmp[(sy * width + x) * 4 + c];
          n++;
        }
        out[(y * width + x) * 4 + c] = sum / n;
      }
      out[(y * width + x) * 4 + 3] = 255;
    }
  }
  return out;
}

test("laplacianVariance is zero on a flat, featureless frame", () => {
  const width = 20;
  const height = 20;
  const flat = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < flat.length; i += 4) {
    flat[i] = flat[i + 1] = flat[i + 2] = 200;
    flat[i + 3] = 255;
  }
  assert.equal(QualityCheck.laplacianVariance(flat, width, height), 0);
});

test("sharp frame with a real embedded QR code passes both checks", () => {
  const { data, width, height } = loadFixture("qr_frame");
  const result = QualityCheck.checkFrame(data, width, height);

  assert.equal(result.blurry, false, "expected the checkerboard/QR frame to read as sharp");
  assert.equal(result.hasPageQr, true, "expected jsQR to decode the embedded QR code");
  assert.equal(result.ok, true);
});

test("heavily blurred version of the same frame fails the quality check", () => {
  const { data: sharp, width, height } = loadFixture("qr_frame");
  const blurred = boxBlur(sharp, width, height, 6);

  const sharpVariance = QualityCheck.laplacianVariance(sharp, width, height);
  const blurredVariance = QualityCheck.laplacianVariance(blurred, width, height);
  assert.ok(
    blurredVariance < sharpVariance,
    `expected blur to reduce Laplacian variance (${blurredVariance} vs ${sharpVariance})`
  );

  const result = QualityCheck.checkFrame(blurred, width, height);
  assert.equal(result.blurry, true, "expected the smeared frame to read as blurry");
  assert.equal(result.ok, false);
});

test("a blank uniform frame has no plausible QR (nothing for jsQR to decode)", () => {
  const width = 200;
  const height = 200;
  const blank = new Uint8ClampedArray(width * height * 4).fill(255);
  assert.equal(QualityCheck.qrPlausible(blank, width, height), false);
});

test("qrPlausible declines to run on frames too small to hold a finder pattern", () => {
  const { data } = loadFixture("qr_frame");
  assert.equal(QualityCheck.qrPlausible(data.slice(0, 10 * 10 * 4), 10, 10), false);
});
