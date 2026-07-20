import assert from "node:assert/strict";
import test from "node:test";

import { createPrintController } from "../web/static/app.mjs";

function response({ ok = true, status = 200, json, blob } = {}) {
  return { ok, status, json: async () => json, blob: async () => blob };
}

function makeUi() {
  return {
    form: {},
    preview: { src: "old-preview", hidden: false },
    printButton: { disabled: false },
    status: { textContent: "", dataset: {} },
  };
}

test("preview sends CSRF-protected form data and keeps the old image on error", async () => {
  const ui = makeUi();
  const calls = [];
  const controller = createPrintController({
    ...ui,
    formDataFactory: () => "form-data",
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url === "/csrf-token") return response({ json: { csrf_token: "token" } });
      return response({ ok: false, status: 400, json: { error: "Bad source" } });
    },
    createObjectURL: () => "new-preview",
  });

  await controller.preview();

  assert.equal(ui.preview.src, "old-preview");
  assert.equal(ui.status.textContent, "Bad source");
  assert.deepEqual(calls[1], {
    url: "/preview",
    options: {
      method: "POST",
      body: "form-data",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": "token" },
    },
  });
});

test("print disables the button and polls until the job is terminal", async () => {
  const ui = makeUi();
  const calls = [];
  const timers = [];
  const controller = createPrintController({
    ...ui,
    formDataFactory: () => "form-data",
    setTimeoutImpl: (callback, delay) => timers.push({ callback, delay }),
    fetchImpl: async (url) => {
      calls.push(url);
      if (url === "/csrf-token") return response({ json: { csrf_token: "token" } });
      if (url === "/print") return response({ status: 202, json: { job_id: "job-7" } });
      return response({ json: { state: "complete", error: null } });
    },
  });

  await controller.print();
  assert.equal(ui.printButton.disabled, true);
  assert.equal(ui.status.textContent, "Preparing print job…");
  assert.deepEqual(timers, [{ callback: timers[0].callback, delay: 500 }]);

  await timers[0].callback();
  assert.deepEqual(calls, ["/csrf-token", "/print", "/jobs/job-7"]);
  assert.equal(ui.printButton.disabled, false);
  assert.equal(ui.status.textContent, "Print complete.");
});

test("print submits explicit boolean settings", async () => {
  const ui = makeUi();
  const body = { values: {}, set(name, value) { this.values[name] = value; } };
  const controller = createPrintController({
    ...ui,
    dither: { checked: true },
    bold: { checked: false },
    formDataFactory: () => body,
    setTimeoutImpl: () => {},
    fetchImpl: async (url) => {
      if (url === "/csrf-token") return response({ json: { csrf_token: "token" } });
      return response({ status: 202, json: { job_id: "job-1" } });
    },
  });

  await controller.print();
  assert.deepEqual(body.values, { dither: "true", bold: "false" });
});
