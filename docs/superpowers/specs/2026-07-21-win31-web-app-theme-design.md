# Win31 Local Print App Theme Design

## Goal

Apply the existing Flancrest Win31 design system to the local CTP500 print web
app while keeping the baby-blue page background as its desktop workspace.

## Source and ownership

Vendor only `@flancrestinc/win31-core@0.1.0` as
`web/static/win31/win31-core.css`, copied from
`/home/ryan/projects/style/packages/core/dist/index.css`. The core artifact
already embeds the shared tokens and Win31 theme, so a separate token file would
duplicate CSS. Record the package, version, source path, and SHA-256 in
`web/static/win31/win31-core.provenance.json`. Application CSS may add only
local layout rules and the baby-blue canvas override. The app does not load
theme assets from a network or require Node at runtime.

## Visual structure

- The document uses `data-ds-theme="win31"`.
- The page background is baby blue, replacing the Win31 teal canvas token only
  for this app.
- A `.ds-window` encloses the app, with a `.ds-titlebar` for the CTP500 title
  and printer target.
- The settings section and receipt preview use Win31 panel, sunken-panel,
  field, control, button, and status classes.
- The receipt preview remains a white monochrome image. Its print geometry and
  JavaScript behavior do not change.

## Class mapping

- `<html>` gets `data-ds-theme="win31"`; `<body>` remains the baby-blue
  workspace.
- The existing main shell gains `ds-app-shell`; its child application container
  becomes `ds-window`.
- The header becomes `ds-titlebar`; the existing target output remains visible
  inside it.
- Settings and preview sections become `ds-panel`; the preview frame becomes
  `ds-panel--sunken`.
- Each label/control pair uses `ds-field` plus `ds-control`; file, radio, and
  checkbox controls retain their native types and existing names/IDs.
- The source fieldset and legend remain semantic, with Win31 layout classes only.
- The Advanced `<details>` and `<summary>` remain native controls.
- The Print button gains `ds-button ds-button--primary`.
- The live status retains `role="status" aria-live="polite"` and gains
  `ds-status`; JavaScript adds/removes `ds-status--success` and
  `ds-status--error` alongside its existing data state.

## Markup and behavior

Keep all current element IDs, form names, ARIA behavior, CSRF requests,
preview generation, print polling, and advanced settings intact. Preserve
same-origin/CSRF rejection, request shapes, printer-target input sync, advanced
MAC containment, 384-pixel preview sizing, and pixelated image rendering.
Update classes and surrounding semantic structure only. The editable printer
address stays in the Advanced details control; the title bar continues to
display the synced non-editable target address.

## Validation

Add page-contract assertions for the local vendored stylesheet, theme attribute,
provenance metadata, and primary shared component classes. Keep the existing
CSRF, request, polling, target-sync, advanced-settings, and pixel-preview tests.
Add browser assertions that no network stylesheet is used, the 384-pixel
preview stays white/monochrome, and mocked preview/print interactions still
work. Run the Python application tests, JavaScript controller tests, and a
local browser page check. Manually verify keyboard focus, radio controls,
details/summary, file input, submit, and live status announcements; check
contrast for the baby-blue workspace, titlebar target, disabled button, and
success/error statuses.
