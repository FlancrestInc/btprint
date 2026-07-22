# Editable Print Templates Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four editable local print templates to the Win31 CTP500 web app.

**Architecture:** A small browser module owns template definitions and selection. The existing app module applies template values to current Text controls, then uses the same preview and print flow.

**Tech Stack:** Flask templates, vanilla ES modules, existing Node and Python tests.

---

### Task 1: Add template data and controller behavior

**Files:**
- Create: `web/static/templates.mjs`
- Modify: `web/static/app.mjs`
- Modify: `tests/web_app_ui.test.mjs`

- [ ] Write failing Node tests for the exact keys `checklist`, `todo-label`,
  `tiny-note`, and `surprise-card` plus Custom; each preset's visible
  description and selected `aria-pressed` state; preset source
  switching and field application; Custom preserving every current text field
  and the current source; exactly one call to the real preview scheduler per
  preset click; and no form submit or print call.
- [ ] Run `node --test tests/web_app_ui.test.mjs` and confirm failure.
- [ ] Export template definitions and lookup helpers. Add a template controller
  that applies presets with `.value`, `textContent`, `aria-pressed`, and exactly
  one existing debounced preview call.
- [ ] Run the Node test again and confirm it passes.
- [ ] Commit: `Add editable print templates`

### Task 2: Add the Win31 template panel

**Files:**
- Modify: `web/templates/index.html`
- Modify: `web/static/app.css`
- Modify: `tests/test_webapp.py`

- [ ] Write a failing page-contract test for the five type-button IDs, selected
  description, and Win31 panel classes. Assert every template control renders
  `type="button"`.
- [ ] Run `python3 -m unittest tests.test_webapp` and confirm failure.
- [ ] Add or retain a Node regression test that selects Image, supplies a
  file, schedules a preview, and submits a print without any template code
  changing that existing image workflow.
- [ ] Add the panel above the source picker using type-button controls and
  `aria-pressed`; wire it to the template controller without changing existing
  input IDs, form names, CSRF, or print controls.
- [ ] Run Python and Node tests and confirm they pass.
- [ ] Commit: `Add Win31 template picker`

### Task 3: Verify and document the feature

**Files:**
- Modify: `README.md`

- [ ] Document templates as editable local presets and state that they use the
  normal preview and print flow.
- [ ] Run `python3 -m unittest discover -s tests`,
  `node --test tests/web_app_ui.test.mjs`, and `git diff --check`.
- [ ] Manually select each template, edit it, confirm preview updates, and print
  one template.
- [ ] Commit: `Document editable print templates`
