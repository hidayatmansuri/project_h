# `project-h` Design Tokens & UI Patterns

## 1. CSS Theme Tokens (`static/css/home-style.css`)

| Variable | `html.light` | `html.dark` | Usage |
| :--- | :--- | :--- | :--- |
| `--bg-color` | `#D3D9D4` | `#212A31` | Page & card base background, inverted button text |
| `--text-color` | `#212A31` | `#D3D9D4` | Primary text, borders, icons |
| `--button-color` | `#42243C` | `#00D2D3` | Primary accents, active pills, chart primary series |
| `--hover-color` | `#800000` | `#7DE2E2` | Hover states, interactive link highlights |
| `--warning-color` | `#D94E00` | `#FF9F43` | Warnings, secondary chart series, accent highlights |
| `--box-shadow` | `0px 8px 32px 0 rgba(33,42,49,0.5)` | `0 8px 32px 0 rgba(0,0,0,0.6), ...` | `.ph-card` elevation |

## 2. Reusable Utility Classes (`static/css/home-style.css`)
- `.ph-card` — elevated surface with `var(--box-shadow)`, `backdrop-filter: blur(10px)`, and hover lift.
- `.ph-button` — primary button (`background-color: var(--text-color)`, `color: var(--bg-color)`).
- `.ph-hover` — consistent link/icon hover highlight (`var(--hover-color)`).
- `.ph-heading`, `.ph-line`, `.ph-warning`, `.ph-field`, `.ph-label` — standard form and section primitives.

## 3. Theme-Aware SVG Mask Pattern (`.ph-logo-mark`)
Used in `home/templates/home.html` and `static/css/home-style.css` so an external SVG inherits `currentColor` across Light/Dark themes and hover transitions:
```css
.ph-logo-mark {
    display: block;
    width: 1.8rem;
    height: 1.8rem;
    background-color: currentColor;
    -webkit-mask-image: var(--ph-logo-src, url("../images/project_h_transparent.svg"));
    mask-image: var(--ph-logo-src, url("../images/project_h_transparent.svg"));
    -webkit-mask-repeat: no-repeat;
    mask-repeat: no-repeat;
    -webkit-mask-position: center;
    mask-position: center;
    -webkit-mask-size: contain;
    mask-size: contain;
    transition: background-color 0.3s ease-in-out;
}
```

## 4. Chart.js Live Theme Synchronization Pattern (`static/js/cv-charts.js`)
```javascript
function getThemeColors() {
    const styles = getComputedStyle(document.documentElement);
    return {
        textColor: styles.getPropertyValue('--text-color').trim(),
        buttonColor: styles.getPropertyValue('--button-color').trim(),
        warningColor: styles.getPropertyValue('--warning-color').trim(),
    };
}

new MutationObserver((mutations) => {
    if (mutations.some((m) => m.attributeName === 'class')) {
        applyThemeToCharts();
    }
}).observe(document.documentElement, { attributes: true });
```
