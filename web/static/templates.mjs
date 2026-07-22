export const CUSTOM_TEMPLATE_ID = "custom";

export const TEMPLATES = [
  {
    id: "checklist",
    title: "Checklist",
    text: "CHECKLIST\n[ ] First task\n[ ] Second task\n[ ] Done",
    fontSize: 24,
    alignment: "left",
    bold: true,
    description: "A short list you can finish.",
  },
  {
    id: "todo-label",
    title: "To-do label",
    text: "TO DO\nWhat needs doing?",
    fontSize: 32,
    alignment: "center",
    bold: true,
    description: "A bold label for one task.",
  },
  {
    id: "tiny-note",
    title: "Tiny note card",
    text: "A tiny note for you.",
    fontSize: 24,
    alignment: "left",
    bold: false,
    description: "A small note with room for your words.",
  },
  {
    id: "surprise-card",
    title: "Surprise mini-card",
    text: "SURPRISE!\nYou are doing great.",
    fontSize: 28,
    alignment: "center",
    bold: true,
    description: "A cheerful mini-card.",
  },
];

export function getTemplate(id) {
  return TEMPLATES.find((template) => template.id === id);
}
