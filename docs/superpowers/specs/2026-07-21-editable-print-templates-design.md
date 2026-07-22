# Editable Print Templates Design

## Goal

Add a small, local set of editable print templates to the CTP500 web app. The
templates make quick practical and playful receipts without changing the proven
preview, calibration, CSRF, or print transport paths.

## Scope

The first release provides four built-in text templates:

- Checklist
- To-do label
- Tiny note card
- Surprise mini-card

`Custom` remains the default. Image printing remains unchanged.

## Data and behavior

`web/static/templates.mjs` exports `TEMPLATES`, `getTemplate(id)`, and
`CUSTOM_TEMPLATE_ID`. Each definition has a stable ID, title, short description,
default text, font size, alignment, and bold value. All built-ins must fit the
existing renderer limits. The initial values are:

- `checklist`: `CHECKLIST\n[ ] First task\n[ ] Second task\n[ ] Done`, 24px,
  left, bold; description `A short list you can finish.`
- `todo-label`: `TO DO\nWhat needs doing?`, 32px, center, bold; description
  `A bold label for one task.`
- `tiny-note`: `A tiny note for you.`, 24px, left, not bold; description
  `A small note with room for your words.`
- `surprise-card`: `SURPRISE!\nYou are doing great.`, 28px, center, bold;
  description `A cheerful mini-card.`

Selecting a template sets the Text radio, runs the existing source
visibility/disable logic, applies every field, and schedules exactly one
debounced preview. Selecting `Custom` makes `template-custom` the sole pressed
button, preserves all current form values, and does not switch source. User edits keep the current
template selected: templates are editable presets, not saved documents. Edits
exist only in the current form; they are not saved, renamed, or sent as template
data to the server. Selecting a template never sends a print job.

## Interface

Add a Win31 panel above the source selector. It contains `Custom` and the four
template buttons, with IDs `template-custom`, `template-checklist`,
`template-todo-label`, `template-tiny-note`, and `template-surprise-card`.
Every template button is `<button type="button">`; none may submit the print
form. The selected button has pressed state and `aria-pressed`. The panel also
displays the selected template description with `textContent`; Custom shows
`Custom text`. Template text is written with `.value`, never `innerHTML`.
Existing text controls remain the editor for all template content; no
drag-and-drop canvas or template-specific print route is added.

## Safety and validation

Templates use only local static text. Their values flow through the existing
text renderer, source validation, CSRF-protected preview, and print endpoints.
Existing text length and rendered-height limits still apply.

## Testing

Add JavaScript tests for template lookup, each built-in value, source switching,
image-control disablement, FormData fields, exactly one preview schedule,
Custom preservation of all text settings, and selected-state behavior after
edits. Verify template buttons do not submit or print. Keep existing tests for
CSRF, preview/print request shape, job polling, image source behavior, and
Win31 page structure. Add one page integration test proving Image remains the
initial source and its print flow is unchanged. Manual acceptance is selecting
each template, editing it, confirming the preview changes, and printing one
template.
