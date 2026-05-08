# Handoff: Калькулятор ПИР — Web App

## Overview

This package contains the design for **Калькулятор ПИР** — an AI-powered cost calculator for проектно-изыскательные работы (ПИР) used by construction-engineering firms. Users register, buy a subscription, upload a technical specification (ТЗ), let an AI agent extract work items, review/edit the list, run a calculation against reference books (СБЦ-2020), and export an XLSX estimate.

## About the design files

The HTML/JSX files in this bundle are **design references** created as a click-through prototype, not production code to copy directly. Recreate them in the target codebase's environment (React + the team's component library / state management / styling solution) following its existing patterns. If no codebase exists yet, the prototype is structured as React components with a global token CSS file — that's a reasonable starting stack (Next.js / Vite + plain CSS variables, or Tailwind with the tokens mapped into `theme.extend`).

## Fidelity

**High-fidelity.** Final colors, typography, spacing, copy, and interactions. Recreate pixel-perfect using the codebase's existing libraries and patterns. The token file `colors_and_type.css` is the source of truth — port its CSS custom properties into the target system.

## Screens / Views

The prototype is a single SPA with route state in React (`route` string). Six screens, two zones:

**Public zone** (no chrome):
1. **Landing** (`route='landing'`) — sticky nav (64px, blur), hero on blueprint grid, "how it works" 4-step grid, 3-tier pricing, footer.
2. **Auth** (`route='auth'`) — single 440px card centered on grid background, toggles between sign-in and sign-up.

**App zone** (sidebar 240px + main column with topbar 56px):
3. **Dashboard** (`route='dashboard'`) — search/filter row, 4 KPI cards, projects table (8 columns).
4. **Upload** (`route='upload'`) — Stepper (4 steps, current=0), project meta card, drag-drop zone OR processing card with 5-stage progress.
5. **Review** (`route='review'`) — Stepper (current=1), title + run-calculation CTA, warning banner, editable items table (8 columns: №/Код/Раздел/Наименование/Ед/Кол-во/Точность/actions).
6. **Result** (`route='result'`) — Stepper (current=3), header with chip + export buttons, hero total panel (gradient, 4-column breakdown), detail table with footer total.

For exact layout, components, copy, and dimensions, **read the JSX source files** — they're declarative and ~100-300 lines each.

## Interactions & behavior

- **Navigation:** route is a single string in App-level state. Sidebar nav switches between dashboard / upload. Topbar "← Все проекты" returns to dashboard.
- **Landing CTA / sign-in** → auth. Auth submit → dashboard.
- **Dashboard "Новый расчёт"** → upload. Click any project row → result.
- **Upload:** drag-drop OR click "Выбрать файл" starts a fake 100% progress (interval, +4% / 90ms), advancing through 5 named stages. On completion → review.
- **Review:**
  - Double-click any row name OR click ⚙ icon → inline edit
  - 🗑 → remove row
  - "Добавить позицию" → append new row in edit mode
  - "Запустить расчёт" → result
- **Result:** "← К списку проектов" → dashboard. Download buttons are stubbed.
- **Hover:** surface goes one step lighter (`--bg-hover`) OR border one step stronger — never both. No size or shadow change.
- **Focus:** always `box-shadow: var(--shadow-focus)` (3px blue glow). Required for accessibility.
- **Motion:** 90ms hover, 160ms default, 260ms layout. `cubic-bezier(0.2, 0.7, 0.2, 1)` for entries. No bounces, no springs.

## State management

App-level: `route` (string). Use whatever the codebase prefers (React Router, file-based routes, Zustand, plain useState).

Per-screen local state:
- **Auth:** `mode` ('signin'|'signup'), `email`, `password`, `company`.
- **Upload:** `file`, `progress` (0-100), `stage` (0-4), `drag` (boolean).
- **Review:** `items` (array of `{id, code, section, name, unit, qty, confidence}`), `editId` (id|null).

Data fetching: every list/total in this prototype is hardcoded mock data. Replace with real API calls — confirmed shapes are visible in the JSX (`SAMPLE_PROJECTS`, `INITIAL_ITEMS`, `RESULT_ROWS`).

## Design tokens

All tokens live in `colors_and_type.css`. Import wholesale or port to the target system. Highlights:

**Color (semantic, dark-default):**
- `--bg-app: #05080D` · `--bg-surface: #0A0E15` · `--bg-elevated: #0F141C` · `--bg-raised: #161D27` · `--bg-hover: #1E2632`
- `--fg-1: #E8ECF1` (primary) · `--fg-2: #C5CCD6` · `--fg-3: #8A95A4` · `--fg-4: #5A6675` (disabled)
- `--border-subtle: #2A3340` · `--border-default: #3B4654` · `--border-strong: #5A6675`
- `--accent: #1F5FE8` (Signal Blue 500) · hover `#3672F0` · pressed `#1850CC`
- `--accent-tint: rgba(31, 95, 232, 0.12)` for selected rows / chip backgrounds
- Status: `--success-400 #22C55E`, `--warning-400 #F59E0B`, `--danger-400 #EF4444`
- A `.theme-light` opt-in class is included.

**Typography:** IBM Plex Sans (UI) + IBM Plex Mono (numbers, codes, IDs — always with `font-variant-numeric: tabular-nums`). Replace with brand fonts when available.

**Spacing:** 4px base. `--space-1 4` → `--space-2 8` → 12 → 16 → 20 → 24 → 32 → 40 → 48 → 64 → 80 → 96.

**Radius:** xs 2 / sm 4 / **md 6 (default)** / lg 8 (cards) / xl 12 (modals) / 2xl 16 / full 999.

**Shadows:** Almost invisible on dark. Use surface stacking + 1px borders for depth. The only meaningful shadow is `--shadow-focus: 0 0 0 3px rgba(31, 95, 232, 0.32)`.

**Numeric data:** always `font-family: var(--font-mono); font-variant-numeric: tabular-nums;` so columns align.

**Copy & casing:** Russian, formal «вы». Sentence case for all UI labels. UPPERCASE only for overlines + the wordmark. Currency: `2 384 500 ₽` with non-breaking spaces. Dates: `07.05.2026` in tables, `7 мая 2026` in copy. Units: `м²`, `км`, `шт.`, `чел.-час`. **No emoji anywhere.**

## Assets

- `assets/logo-wordmark-dark.svg`, `logo-wordmark-light.svg`, `mark.svg` — **placeholder logo** I designed. Replace with the real brand mark when available.
- `assets/grid-tile.svg` — seamless 80×80 CAD-grid background. Use only on hero / marketing surfaces.
- **Icons:** Lucide (1.5px stroke, sizes 14/16/20/24, color: currentColor). The prototype inlines them in `Icons.jsx`; in the target codebase use `lucide-react` (or equivalent) directly.
- No photography, no decorative illustrations. Imagery is data: tables, charts, schematic diagrams.

## Files

- `colors_and_type.css` — design tokens (port wholesale)
- `assets/` — logos, icons, grid tile
- `ui_kits/calculator/`
  - `index.html` — clickable prototype entry
  - `Icons.jsx` — Lucide icon set inlined
  - `Primitives.jsx` — Button, Input, Select, Chip, Stepper
  - `Chrome.jsx` — Sidebar, Topbar
  - `LandingScreen.jsx`, `AuthScreen.jsx`, `DashboardScreen.jsx`, `UploadScreen.jsx`, `ReviewScreen.jsx`, `ResultScreen.jsx`
  - `README.md` — kit-level notes

The full design system documentation (`README.md` at the project root of the original bundle) has more on content tone, visual foundations, and iconography rules — treat it as the design system spec.

## Open items / substitutions to flag with the design owner

- Logo is a placeholder
- Fonts use IBM Plex Sans/Mono via Google Fonts CDN — swap for brand fonts when provided
- Reference book codes (СБЦ-XX.XX), pricing tiers, and project numbers are plausible but fictional
- Confirm Russian terminology with a domain expert before shipping
