import assert from "node:assert/strict";
import test from "node:test";

import { createPrintController, createTemplateController } from "../web/static/app.mjs";
import { CUSTOM_TEMPLATE_ID, TEMPLATES, getTemplate } from "../web/static/templates.mjs";

function response({ ok = true, status = 200, json, blob } = {}) {
  return { ok, status, json: async () => json, blob: async () => blob };
}

function makeUi() {
  return {
    form: {},
    preview: { src: "old-preview", hidden: false },
    printButton: { disabled: false },
    status: { textContent: "", dataset: {}, classList: { toggle() {} } },
  };
}

function templateButton(id) {
  return {
    id,
    dataset: { template: id },
    ariaPressed: "false",
    listeners: {},
    addEventListener(type, callback) { this.listeners[type] = callback; },
    click() { this.listeners.click?.(); },
  };
}

function makeTemplateUi() {
  const sourceImage = { checked: true };
  const sourceText = { checked: false };
  const textInput = { value: "Keep this text" };
  const fontSize = { value: "18" };
  const alignment = { value: "right" };
  const bold = { checked: false };
  const imageControl = { disabled: false };
  const textControl = { disabled: true };
  const buttons = [
    templateButton(CUSTOM_TEMPLATE_ID),
    ...TEMPLATES.map((template) => templateButton(template.id)),
  ];
  let showSourceCalls = 0;
  let scheduleCalls = 0;
  return {
    sourceImage, sourceText, textInput, fontSize, alignment, bold, templateButtons: buttons,
    description: { textContent: "" },
    imageControl, textControl,
    showSource() {
      showSourceCalls += 1;
      imageControl.disabled = !sourceImage.checked;
      textControl.disabled = sourceImage.checked;
    },
    schedulePreview() { scheduleCalls += 1; },
    showSourceCalls: () => showSourceCalls,
    scheduleCalls: () => scheduleCalls,
  };
}

test("template definitions expose the approved editable presets", () => {
  assert.equal(CUSTOM_TEMPLATE_ID, "custom");
  assert.deepEqual(TEMPLATES, [
    { id: "checklist", text: "CHECKLIST\n[ ] First task\n[ ] Second task\n[ ] Done", fontSize: 24, alignment: "left", bold: true, description: "A short list you can finish." },
    { id: "todo-label", text: "TO DO\nWhat needs doing?", fontSize: 32, alignment: "center", bold: true, description: "A bold label for one task." },
    { id: "tiny-note", text: "A tiny note for you.", fontSize: 24, alignment: "left", bold: false, description: "A small note with room for your words." },
    { id: "surprise-card", text: "SURPRISE!\nYou are doing great.", fontSize: 28, alignment: "center", bold: true, description: "A cheerful mini-card." },
  ]);
  assert.equal(getTemplate("tiny-note"), TEMPLATES[2]);
  assert.equal(getTemplate("missing"), undefined);
});

test("each preset switches to text, applies fields, and schedules one preview", () => {
  for (const template of TEMPLATES) {
    const ui = makeTemplateUi();
    createTemplateController(ui);
    ui.templateButtons.find((button) => button.id === template.id).click();

    assert.equal(ui.sourceImage.checked, false, template.id);
    assert.equal(ui.sourceText.checked, true, template.id);
    assert.equal(ui.showSourceCalls(), 1, template.id);
    assert.equal(ui.imageControl.disabled, true, template.id);
    assert.equal(ui.textControl.disabled, false, template.id);
    assert.equal(ui.textInput.value, template.text, template.id);
    assert.equal(ui.fontSize.value, String(template.fontSize), template.id);
    assert.equal(ui.alignment.value, template.alignment, template.id);
    assert.equal(ui.bold.checked, template.bold, template.id);
    assert.equal(ui.description.textContent, template.description, template.id);
    assert.equal(ui.scheduleCalls(), 1, template.id);
    for (const button of ui.templateButtons) assert.equal(button.ariaPressed, String(button.id === template.id), `${template.id}: ${button.id}`);
  }
});

test("Custom preserves the current source and values without scheduling a preview", () => {
  const ui = makeTemplateUi();
  ui.sourceImage.checked = false;
  ui.sourceText.checked = true;
  ui.textInput.value = "An edited note";
  ui.fontSize.value = "27";
  ui.alignment.value = "center";
  ui.bold.checked = true;
  createTemplateController(ui);

  ui.templateButtons.find((button) => button.id === CUSTOM_TEMPLATE_ID).click();

  assert.equal(ui.sourceImage.checked, false);
  assert.equal(ui.sourceText.checked, true);
  assert.equal(ui.textInput.value, "An edited note");
  assert.equal(ui.fontSize.value, "27");
  assert.equal(ui.alignment.value, "center");
  assert.equal(ui.bold.checked, true);
  assert.equal(ui.showSourceCalls(), 0);
  assert.equal(ui.scheduleCalls(), 0);
  assert.equal(ui.description.textContent, "Custom text");
  for (const button of ui.templateButtons) assert.equal(button.ariaPressed, String(button.id === CUSTOM_TEMPLATE_ID));
});

test("template clicks do not submit a form or call print", () => {
  const ui = makeTemplateUi();
  let submitCalls = 0;
  let printCalls = 0;
  const form = { submit() { submitCalls += 1; } };
  const print = () => { printCalls += 1; };
  createTemplateController({ ...ui, form, print });

  ui.templateButtons.find((button) => button.id === "checklist").click();
  ui.templateButtons.find((button) => button.id === CUSTOM_TEMPLATE_ID).click();

  assert.equal(submitCalls, 0);
  assert.equal(printCalls, 0);
});

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

test("boot mirrors the printer address into the header target", async () => {
  const originalDocument = globalThis.document;
  const originalFetch = globalThis.fetch;
  const input = { value: "20:DC:8B:CD:CA:C0", addEventListener(type, callback) { this.oninput = callback; } };
  const target = { textContent: "" };
  const form = { addEventListener() {} };
  const controls = {
    "#print-form": form, "#printer-address": input, "#printer-target": target,
    "#image-controls": { hidden: false, querySelectorAll: () => [] },
    "#text-controls": { hidden: true, querySelectorAll: () => [] },
    "#image-file": { files: [] }, "#image-filename": { textContent: "" },
    "#source-image": { checked: true }, "#preview": {}, "#print-button": {},
    "#status": { dataset: {} }, "#dither": { checked: false }, "#bold": { checked: false },
  };
  globalThis.document = { querySelector: (selector) => controls[selector] };
  globalThis.fetch = async () => response();
  await import(`../web/static/app.mjs?boot=${Date.now()}`);

  assert.equal(target.textContent, "20:DC:8B:CD:CA:C0");
  input.value = "AA:BB:CC:DD:EE:FF";
  input.oninput();
  assert.equal(target.textContent, "AA:BB:CC:DD:EE:FF");
  globalThis.document = originalDocument;
  globalThis.fetch = originalFetch;
});

test("boot keeps the image workflow working and leaves Image selected for Custom", async () => {
  const originalDocument = globalThis.document;
  const originalFetch = globalThis.fetch;
  const originalFormData = globalThis.FormData;
  const originalSetTimeout = globalThis.setTimeout;
  const timers = [];
  const calls = [];
  const listeners = {};
  const input = { value: "20:DC:8B:CD:CA:C0", addEventListener(type, callback) { this[type] = callback; } };
  const imageFile = { files: [{ name: "photo.png" }] };
  const sourceImage = { checked: true };
  const sourceText = { checked: false };
  const customButton = templateButton(CUSTOM_TEMPLATE_ID);
  const form = { addEventListener(type, callback) { listeners[type] = callback; } };
  const controls = {
    "#print-form": form, "#printer-address": input, "#printer-target": { textContent: "" },
    "#image-controls": { hidden: false, querySelectorAll: () => [{ disabled: false }] },
    "#text-controls": { hidden: true, querySelectorAll: () => [{ disabled: true }] },
    "#image-file": imageFile, "#image-filename": { textContent: "No file selected" },
    "#source-image": sourceImage, "#source-text": sourceText,
    "#preview": { hidden: true }, "#print-button": { disabled: false },
    "#status": { textContent: "", dataset: {}, classList: { toggle() {} } },
    "#dither": { checked: false }, "#bold": { checked: false },
    "#template-description": { textContent: "" }, "#text-input": { value: "" },
    "#font-size": { value: "24" }, "#alignment": { value: "left" },
  };
  try {
    globalThis.document = {
      querySelector: (selector) => controls[selector],
      querySelectorAll: (selector) => (selector === "[data-template]" ? [customButton] : []),
    };
    globalThis.FormData = class { set() {} };
    globalThis.setTimeout = (callback, delay) => { timers.push({ callback, delay }); return timers.length; };
    globalThis.fetch = async (url) => {
      calls.push(url);
      if (url === "/csrf-token") return response({ json: { csrf_token: "token" } });
      if (url === "/preview") return response({ blob: "preview" });
      if (url === "/print") return response({ status: 202, json: { job_id: "job-1" } });
      return response({ json: { state: "complete" } });
    };
    await import(`../web/static/app.mjs?image-workflow=${Date.now()}`);

    listeners.change({ target: imageFile });
    assert.equal(controls["#image-filename"].textContent, "photo.png");
    assert.deepEqual(timers.map(({ delay }) => delay), [250]);
    await timers[0].callback();
    assert.deepEqual(calls, ["/csrf-token", "/preview"]);

    listeners.submit({ preventDefault() {} });
    await Promise.resolve();
    await Promise.resolve();
    assert.deepEqual(calls, ["/csrf-token", "/preview", "/print"]);
    customButton.click();
    assert.equal(sourceImage.checked, true);
    assert.equal(sourceText.checked, false);
    assert.equal(controls["#template-description"].textContent, "Custom text");
  } finally {
    globalThis.document = originalDocument;
    globalThis.fetch = originalFetch;
    globalThis.FormData = originalFormData;
    globalThis.setTimeout = originalSetTimeout;
  }
});
