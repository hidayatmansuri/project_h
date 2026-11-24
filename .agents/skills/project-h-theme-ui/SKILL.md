---
name: project-h-theme-ui
description: >-
  Defines the project-h design system, CSS variables, light/dark theme toggle
  contract, SVG mask-image/currentColor icon theming, home.html template blocks,
  and mobile-first responsive rules. Use this skill when creating or editing
  templates, stylesheets, charts, or UI components in any project-h app.
---

# `project-h` Theme, UI & Responsive Rules

Use this contract for every template and stylesheet in `project-h`. For the complete token table and reusable code snippets, see [references/tokens-and-patterns.md](./references/tokens-and-patterns.md).

## 1. Template Inheritance Contract (`home/templates/home.html`)
Every app template must extend `home.html` and use its 4 blocks:
- `{% block title %}` — page title (`My App | project-h`).
- `{% block extra_css %}` — app-specific `<link rel="stylesheet" href="{% static 'css/<app>.css' %}">`.
- `{% block content %}` — main page content (rendered inside `<main>`).
- `{% block script %}` — always include `{{ block.super }}` before app JS so `dropdown.js`, `theme-toggle.js`, `sidebar.js`, `copyright.js`, and `active.js` stay loaded.

## 2. Theme Tokens & Light/Dark Toggle Contract
- Theme state lives on `<html class="light">` or `<html class="dark">` (persisted in `localStorage.getItem('theme')` and toggled via `#theme-toggle` in `static/js/theme-toggle.js`).
- **Always use CSS variables** from `static/css/home-style.css` (`--bg-color`, `--text-color`, `--button-color`, `--hover-color`, `--warning-color`, `--box-shadow`, `--text-shadow`). Never hardcode light-only or dark-only colors.
- For canvas visuals (e.g., Chart.js), read tokens via `getComputedStyle(document.documentElement)` and attach a `MutationObserver` on `document.documentElement` (`attributeName === 'class'`) to recolor live when the user toggles themes.

## 3. Typography & Icons
- **Global navbar (`.ph-header` / `.home-nav`):** Always keep `Peignot`.
- **App body content:** Use `Gotu` (e.g., `font-family: 'Gotu', sans-serif;` scoped to the app container such as `.cv-app`), loaded via `static/css/fonts.css`.
- **Icons:** Use self-hosted Font Awesome 6.7.2 (`static/vendor/fontawesome/css/all.min.css`, already loaded by `home.html`). Never add external Font Awesome kit scripts, jQuery, or Materialize.
- **SVG Icon/Logo Theming:** For monochrome SVGs that must adapt to Light/Dark themes and hover states, use CSS `mask-image` + `background-color: currentColor` (the `.ph-logo-mark` pattern in `home-style.css`) or inline SVG with `fill="currentColor"`.

## 4. Mobile-First Responsive Breakpoints (Constraint C6)
`project-h` enforces strict mobile-first CSS tiers across all stylesheets:
- **Small (Base):** default styles (`0px – 767px`, no media query).
- **Medium (Tablet):** `@media (min-width: 768px) { ... }`
- **Large (Desktop):** `@media (min-width: 1200px) { ... }`
- **NEVER write `max-width` media queries** in `home-style.css`, `projectauth.css`, or new app stylesheets.

## Verification
Verify theme rules, Constraint C6 (zero `max-width` media queries), and template rendering:
```powershell
D:\project-h\project-env\Scripts\python.exe manage.py check
D:\project-h\project-env\Scripts\python.exe manage.py test projectauth.tests.test_phase6_ui home cv --verbosity=1
```
