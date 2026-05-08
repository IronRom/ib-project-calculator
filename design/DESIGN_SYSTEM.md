# ИС·ПИР — Design System

**Brand:** Интеллектуальное Строительство (Intelligent Construction)
**Product:** Калькулятор ПИР — AI-powered cost calculator for проектно-изыскательные работы (design and survey works)
**Mood:** технологичный и строгий (technological and strict)

---

## Product context

Калькулятор ПИР is a B2B SaaS tool for construction-engineering firms. The core flow:

1. **Регистрация** — user creates an account
2. **Подписка** — buys a subscription tier
3. **Загрузка ТЗ** — uploads a technical specification document (PDF / DOCX)
4. **AI-извлечение** — an AI agent parses the ТЗ and extracts a list of named work items (наименования работ)
5. **Согласование** — the user reviews the extracted list, and can edit / add / delete rows
6. **Расчёт** — the user runs the calculation; the agent uses internal reference books (справочники — most likely СБЦ / Sprawocniki Bazovych Cen and similar normative pricing tables) to compute the ПИР cost
7. **Экспорт** — the system outputs a calculation file (most likely XLSX, possibly PDF)

The audience is professional: главные инженеры проекта (chief project engineers), сметчики (estimators), руководители ПИР-отделов. They are technical, used to GOST documents, AutoCAD, GrandSmeta, and similar industry tools. The interface should feel like an instrument — precise, dense with data when needed, no decorative noise.

## Sources provided

None. No codebase, Figma, screenshots, or brand guide were attached. The system below is designed from the brief alone, biased toward the **dark engineering** direction (deep navy + electric blue) chosen as default. Every decision is documented so it can be challenged.

⚠️ **Substitutions flagged for replacement when real assets arrive:**
- **Fonts** — using IBM Plex Sans + IBM Plex Mono via Google Fonts. If you have brand fonts, drop the `.woff2` files into `fonts/` and replace the `@import` in `colors_and_type.css`.
- **Logo / wordmark** — `assets/logo-wordmark-*.svg` and `assets/mark.svg` are placeholder marks I designed to communicate the engineering tone. Replace with the official mark.
- **Iconography** — Lucide via CDN. If you have a custom icon set, drop SVGs into `assets/icons/` and update `ICONOGRAPHY` below.
- **Imagery** — no photography copied in. The system uses pure UI surfaces, blueprint grids, and data visualization rather than photos.

---

## Index

| File / Folder | Purpose |
|---|---|
| `README.md` | This file — full system documentation |
| `SKILL.md` | Agent Skill manifest (cross-compatible with Claude Code) |
| `colors_and_type.css` | All design tokens as CSS custom properties — import this in any HTML output |
| `fonts/` | Webfont references (currently CDN-loaded; replace when real fonts arrive) |
| `assets/` | Logos, marks, background tiles, illustrations |
| `assets/icons/` | Local icon SVGs (none yet — Lucide is loaded from CDN) |
| `preview/` | Design System tab preview cards (registered assets) |
| `ui_kits/calculator/` | UI kit for the Калькулятор ПИР product — landing page + full app flow |

---

## Content fundamentals

The product is professional engineering software. Copy is **formal, terse, accurate**.

### Tone

- **Formal Russian — «Вы»** form. Always. This is B2B software for engineers; familiarity is not appropriate.
- **Technically precise.** Use correct industry terminology: «проектно-изыскательные работы», «техническое задание», «справочник базовых цен», «локальная смета». Don't soften jargon — the audience expects it.
- **Neutral and instrumental.** No marketing exclamation points, no «Привет!», no friendly emoji. The interface is an instrument; the copy is a manual.
- **Direct.** Say what the system did, what the user must do, what will happen. Never editorialize.

### Casing

- **Sentence case** for all UI labels: `Загрузить техническое задание`, not `Загрузить Техническое Задание`.
- **UPPERCASE** reserved for: section overlines (`ШАГ 02`), single short status pills (`ГОТОВО`), and the wordmark.
- Buttons in sentence case, infinitive verb-first: `Запустить расчёт`, `Сохранить и продолжить`, `Скачать XLSX`.

### Examples

| Bad | Good |
|---|---|
| «Привет! 👋 Давайте загрузим ваше ТЗ» | «Загрузите техническое задание» |
| «Ой, что-то пошло не так 😕» | «Не удалось обработать файл. Проверьте формат: PDF или DOCX, до 50 МБ.» |
| «Класс! Расчёт готов!» | «Расчёт завершён. 47 позиций, итого 2 384 500 ₽.» |
| «Удалить элемент?» | «Удалить позицию из расчёта?» |
| «Поздравляем с подпиской!» | «Подписка активирована. Лимит — 10 расчётов в месяц.» |

### Numbers, units, dates

- Currency: `2 384 500 ₽` — non-breaking spaces between thousands, ruble glyph after.
- Dates: `07.05.2026` (Russian DD.MM.YYYY) in dense tables; `7 мая 2026` in long-form copy.
- Units: `м²`, `км`, `шт.`, `чел.-час` — always with proper symbols and a non-breaking space (`50 м²`).
- Numeric data is **mono, tabular** so columns align: `font-family: var(--font-mono); font-variant-numeric: tabular-nums;`

### Emoji

**No.** Not in UI labels, not in toasts, not in marketing. The only graphical accents are icons (Lucide) and the brand mark.

---

## Visual foundations

### Mood

Dark engineering. Imagine the interface lives next to AutoCAD and GrandSmeta — same tonal register, but built in 2026. Crisp hairlines. Tabular numbers. Generous use of monospace for codes and quantities. Almost no shadows; depth comes from layered surfaces and 1px borders. Color is rationed: a single signal blue for actions, neutral steel for chrome, and the rest of the palette only when status demands it.

### Color

- **Surfaces are deep navy** (`--ink-1000` → `--ink-700`). Pure black is avoided; pure white is reserved for the optional light "blueprint" theme.
- **Foreground hierarchy is strict.** `--fg-1` (highest contrast) for primary text, `--fg-2` for body, `--fg-3` for placeholder/captions, `--fg-4` for disabled. Never color text just to add visual interest.
- **Accent is one color** — Signal Blue (`--blue-500` `#1F5FE8`). It marks the single most important action on a screen. Multiple blue CTAs in one viewport is a smell.
- **Status colors are functional, not decorative**: success/warning/danger only ever appear when the data IS that status. A green icon never decorates a generic checkbox.
- **Data viz palette** (`--data-1` through `--data-6`) is reserved for charts. UI elements never pick from it.

### Typography

- **IBM Plex Sans** for everything UI (display, body, labels). Industrial, slightly mechanical, unmistakably technical without being cold.
- **IBM Plex Mono** for: numbers in tables, currency totals, IDs / codes / project numbers, file paths, anything copy-pasted from a system. Use `font-variant-numeric: tabular-nums` everywhere numeric.
- **No display fonts, no serifs, no script.** Variety comes from weight (400/500/600/700) and size, never from a second sans family.
- **Tight tracking on display** (`--tracking-tight`), normal on body, **wide on overline** (`--tracking-wide`) — that's the only place letterspacing changes.

### Backgrounds

- App background: solid `--bg-app`. No gradients on the canvas.
- **Hero / marketing surfaces** may use `assets/grid-tile.svg` — a subtle CAD-grid tile at 8% opacity. This is the brand's only allowed background pattern.
- No photography. No hand-drawn illustrations. No mesh gradients. No noise textures.
- **Imagery, when needed,** is data: tables, charts, schematic diagrams, blueprint-style line art. The product visualizes engineering work; it does not picture buildings.

### Borders & dividers

- **1px borders are the primary depth signal.** `--border-subtle` between rows, `--border-default` around cards, `--border-strong` for emphasized cells.
- Border radius is **restrained**: `--radius-md` (6px) for buttons and inputs, `--radius-lg` (8px) for cards, `--radius-xl` (12px) for modals/sheets. No fully-pill buttons, no `--radius-2xl` on small elements.
- Tables use **square cells** (`--radius-none` on inner cells, `--radius-md` on the outer table only).

### Shadows / elevation

- Drop shadows are **almost invisible** on dark — they don't read. Use layered surfaces instead: a card is `--bg-elevated`, a popover is `--bg-raised`, hover is `--bg-hover`.
- The only meaningful shadow is **focus** (`--shadow-focus`, the 3px blue glow) — accessibility-critical, must not be removed.
- A 1px top inner-highlight (`inset 0 1px 0 rgba(255,255,255,0.04)`) is acceptable on raised surfaces to pop them off the canvas.

### Hover & press

- **Hover** = surface goes one step lighter (`--bg-hover`) OR border goes one step stronger. Never both at once. No size change, no shadow change.
- **Press** = surface darkens by one step (return to `--bg-surface` from `--bg-elevated`), and translates `transform: translateY(0.5px)`. Subtle.
- **Disabled** = `opacity: 0.45`, `cursor: not-allowed`. No grayscale filter.
- **Focus** = always visible, always `--shadow-focus`. Never remove the outline.

### Motion

- **Fast and unobtrusive.** `--duration-1` (90ms) for hover, `--duration-2` (160ms) for default, `--duration-3` (260ms) for layout shifts. Page transitions cap at `--duration-4` (420ms).
- **Easing is `--ease-out`** for entries, `--ease-in-out` for transforms. **No bounces, no springs, no overshoots.** This is engineering software.
- **Loaders are linear or stepped progress bars**, never pulsing dots or bouncing balls. AI processing shows percentage and an estimated step indicator (`Шаг 2 из 5: извлечение позиций`).

### Layout rules

- **12-column grid** at 1280/1440/1920 breakpoints, 24px gutter, 80px outer margin on the marketing site.
- **App is a fixed sidebar (240px) + flexible main**. Sidebar can collapse to icon-rail (56px). No floating navigation.
- **Tables fill width**; they don't sit in narrow columns. A calculation has 12 columns; we show 12 columns.
- **Modals are top-anchored** at 12vh (not centered), max-width 640px, with a clear primary action on the right.

### Transparency & blur

- **Transparency is rare.** Used only for: overlay scrims (`--bg-overlay`), accent tints on selected rows (`--accent-tint`), and the one focus glow.
- **Backdrop blur is forbidden** in app chrome. It's expensive, it muddles data, and it doesn't belong in an instrument. The marketing site may use one `backdrop-filter: blur(12px)` on its sticky nav, and only there.

### Cards

- Background `--bg-elevated`, `--hairline` border, `--radius-lg` corners, `--shadow-1` (almost invisible on dark).
- Padding: `--space-6` (24px) for content cards; `--space-4` for compact list cards.
- A card never gets a colored left border. Status is communicated via a **chip** (`Status` component) inside the card header.

---

## Iconography

- **Lucide Icons** via CDN: `https://unpkg.com/lucide@latest`
- **Stroke weight: 1.5px** (Lucide default). Never mix stroke weights.
- **Size scale: 14 / 16 / 20 / 24 px**. 16px is default (matches body text x-height). Always whole numbers, never fractional sizes.
- **Color is `currentColor`** — icons inherit the surrounding text color. They become accent-colored only inside an accent-colored element (a primary button, a selected nav item).
- **No emoji.** Anywhere. Status is communicated by Lucide icons (`CheckCircle2`, `AlertTriangle`, `XCircle`, `Info`).
- **No bitmap icons.** SVG only.
- **Custom domain icons** (e.g. for ПИР document types: ТЗ, смета, ведомость объёмов) live in `assets/icons/` and follow the same line/stroke conventions. Currently empty — flag if you want me to draw a starter set; otherwise we'll substitute Lucide's `FileText`, `Calculator`, `ListChecks`.

### Substitutions flagged

- The brand has no icon set of its own. Lucide is the substitution. If you have a custom icon system, drop SVGs into `assets/icons/`.

---

## How to use this system

In any HTML file in this project (or downstream), include the tokens:

```html
<link rel="stylesheet" href="/colors_and_type.css">
```

Then use semantic tokens (not raw palette) in your CSS:

```css
.card {
  background: var(--bg-elevated);
  color: var(--fg-1);
  border: var(--hairline);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
}
```

For numbers, totals, and codes — always reach for the mono utility:

```html
<span class="t-mono">2 384 500 ₽</span>
```
