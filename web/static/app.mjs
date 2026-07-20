const TERMINAL_STATES = new Set(["complete", "failed"]);

function errorMessage(response, fallback) {
  return response.json().then((body) => body?.error || fallback).catch(() => fallback);
}

export function createPrintController({
  form,
  preview,
  printButton,
  status,
  dither,
  bold,
  fetchImpl = fetch,
  formDataFactory = (target) => new FormData(target),
  createObjectURL = URL.createObjectURL,
  revokeObjectURL = URL.revokeObjectURL,
  setTimeoutImpl = setTimeout,
}) {
  let csrfToken;
  let previewUrl;
  let previewTimer;

  const setStatus = (message, kind = "info") => {
    status.textContent = message;
    status.dataset.kind = kind;
  };

  async function token() {
    if (csrfToken) return csrfToken;
    const response = await fetchImpl("/csrf-token", { credentials: "same-origin" });
    if (!response.ok) throw new Error(await errorMessage(response, "Could not prepare local request."));
    ({ csrf_token: csrfToken } = await response.json());
    return csrfToken;
  }

  async function post(path) {
    const csrf = await token();
    const body = formDataFactory(form);
    if (typeof body.set === "function") {
      body.set("dither", String(Boolean(dither?.checked)));
      body.set("bold", String(Boolean(bold?.checked)));
    }
    return fetchImpl(path, {
      method: "POST", body, credentials: "same-origin", headers: { "X-CSRF-Token": csrf },
    });
  }

  async function previewReceipt() {
    try {
      setStatus("Preparing preview…");
      const response = await post("/preview");
      if (!response.ok) throw new Error(await errorMessage(response, "Could not prepare preview."));
      const nextUrl = createObjectURL(await response.blob());
      preview.src = nextUrl;
      preview.hidden = false;
      if (previewUrl) revokeObjectURL(previewUrl);
      previewUrl = nextUrl;
      setStatus("Preview ready.", "success");
    } catch (error) {
      setStatus(error.message || "Could not prepare preview.", "error");
    }
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeoutImpl(previewReceipt, 250);
  }

  async function poll(jobId) {
    try {
      const response = await fetchImpl(`/jobs/${jobId}`, { credentials: "same-origin" });
      if (!response.ok) throw new Error(await errorMessage(response, "Could not check print job."));
      const job = await response.json();
      if (!TERMINAL_STATES.has(job.state)) {
        setStatus(job.state === "printing" ? "Printing receipt…" : "Preparing print job…");
        setTimeoutImpl(() => poll(jobId), 500);
        return;
      }
      printButton.disabled = false;
      setStatus(job.state === "complete" ? "Print complete." : (job.error || "Print failed."), job.state === "complete" ? "success" : "error");
    } catch (error) {
      printButton.disabled = false;
      setStatus(error.message || "Could not check print job.", "error");
    }
  }

  async function printReceipt() {
    printButton.disabled = true;
    try {
      const response = await post("/print");
      if (!response.ok) throw new Error(await errorMessage(response, "Could not start print job."));
      const { job_id: jobId } = await response.json();
      setStatus("Preparing print job…");
      setTimeoutImpl(() => poll(jobId), 500);
    } catch (error) {
      printButton.disabled = false;
      setStatus(error.message || "Could not start print job.", "error");
    }
  }

  return { preview: previewReceipt, schedulePreview, print: printReceipt };
}

function boot() {
  const form = document.querySelector("#print-form");
  if (!form) return;
  const imageControls = document.querySelector("#image-controls");
  const textControls = document.querySelector("#text-controls");
  const imageFile = document.querySelector("#image-file");
  const imageFilename = document.querySelector("#image-filename");
  const sourceImage = document.querySelector("#source-image");
  const controller = createPrintController({ form, preview: document.querySelector("#preview"), printButton: document.querySelector("#print-button"), status: document.querySelector("#status"), dither: document.querySelector("#dither"), bold: document.querySelector("#bold") });

  const showSource = () => {
    const isImage = sourceImage.checked;
    imageControls.hidden = !isImage;
    textControls.hidden = isImage;
    imageControls.querySelectorAll("input, select, textarea").forEach((control) => { control.disabled = !isImage; });
    textControls.querySelectorAll("input, select, textarea").forEach((control) => { control.disabled = isImage; });
  };
  form.addEventListener("change", (event) => {
    if (event.target.name === "source_type") showSource();
    if (event.target === imageFile) imageFilename.textContent = imageFile.files[0]?.name || "No file selected";
    controller.schedulePreview();
  });
  form.addEventListener("input", controller.schedulePreview);
  form.addEventListener("submit", (event) => { event.preventDefault(); controller.print(); });
  showSource();
}

if (typeof document !== "undefined") boot();
