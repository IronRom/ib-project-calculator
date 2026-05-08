# Калькулятор ПИР — UI Kit

High-fidelity recreation of the core product surfaces.

## Screens

1. **Landing** — marketing entry, plan selection, CTA to register
2. **Auth** — sign in / sign up (single screen, toggle)
3. **Dashboard** — list of user's calculation projects
4. **Upload** — drop a ТЗ (technical specification) file
5. **Review** — agreed list of extracted work items, editable
6. **Result** — calculated estimate, ready to export

The `index.html` ties them together as a click-through prototype: start on landing → register → dashboard → upload → review → result. Every interactive element is wired locally (no backend); state lives in React.

## Components

- `Sidebar.jsx` — fixed app navigation
- `Topbar.jsx` — page header with breadcrumb + actions
- `Button.jsx`, `Input.jsx`, `Select.jsx` — primitives
- `Chip.jsx` — status pill
- `WorkItemsTable.jsx` — the heart of the product (editable rows)
- `Stepper.jsx` — multi-step header
- `Uploader.jsx` — drag-and-drop file zone
- `ResultPanel.jsx` — calculation total + export actions

## Substitutions

- Lucide icons inlined as SVG (no CDN dependency in JSX components — kept self-contained).
- All numeric data is fictional but realistic for ПИР projects.
