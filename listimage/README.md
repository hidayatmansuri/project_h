# ListImage: Image to SVG Vector Feature Documentation

The `listimage` application provides professional background removal, 2000x2000 pure white canvas rendering, and a pure vector **Image to SVG** converter.

---

## 🌟 Key Features

1. **Dual-Engine Vectorization**:
   - Primary: `vtracer` binary vectorizer for high-performance spline and polygon tracing.
   - Fallback: Built-in OpenCV Bézier spline contour vectorizer (Catmull-Rom cubic Bézier tangent matching) that guarantees 100% operation on restricted operating systems (e.g. Windows WDAC / SAC environments).

2. **Resolution Independence**:
   - Generates pure vector paths only. No embedded rasters (`<image>`), no CSS classes, no filters, no scripts, and no foreignObject.
   - Enforces exact `viewBox` aspect matching, `preserveAspectRatio="xMidYMid meet"`, and `shape-rendering="geometricPrecision"`.
   - Normalizes input capped at `LISTIMAGE_SVG_MAX_TRACE_PX` (2000 px) and applies 2x Lanczos upscaling on small images (<800 px) for smooth curve generation.
   - Centering option: "Square 1:1 canvas" centers the vector subject in a square viewBox with 5% padding.

3. **Three Colour Modes**:
   - **Monochrome**: Single user-chosen color (default `#000000`).
     - *Silhouette*: Traces foreground alpha boundary.
     - *Detail*: Extracts internal shape and line luminance features via threshold slider.
   - **Hybrid**: Chosen swatches retain their extracted color; all other parts become a single monochrome base color.
   - **Full Colour**: Quantized 2 to 16 color palette generated via OpenCV K-Means clustering.

4. **Live Colour Editing UI**:
   - Every path element carries `data-palette-index`.
   - **Click-to-Pick**: Clicking any shape in the SVG preview automatically selects its swatch in the palette toolbar.
   - **Custom Colours**: Color pickers live-update `<path>` fill attributes directly in the preview DOM with zero latency.
   - **Quick Actions**: Set any swatch to the monochrome color or remove it completely (transparent).
   - **Undo History**: Stack-based undo mechanism for restoring previous color states.
   - **Reset**: Instantly reverts all swatches to original extracted colors.
   - **Near-White Removal**: Automatically strips near-white background or reflection fills (RGB $\ge 245$).

5. **Cutting Machine Support**:
   - "Non-overlapping shapes" option (`hierarchical='cutout'`) produces disjoint vector pieces suitable for vinyl cutters, Cricut, and Silhouette machines. Default stacked mode overlaps layers for clean print registration.

6. **Cooperative Cancellation & Cleanup**:
   - Responsive cancel button at every step that stops background processing between stages and prunes database and workspace rows.
   - Post-download automatic server cleanup redirects to `listimage:index`.

---

## ⚙️ Configuration Settings

Add or customize these settings in `project_h/settings.py`:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `LISTIMAGE_SVG_MAX_TRACE_PX` | `2000` | Maximum dimension (longest side) for vector source input before downscaling. |
| `LISTIMAGE_SVG_MAX_BYTES` | `3145728` (3 MB) | File size threshold triggering an advisory warning in the UI recommending lower color counts or simpler presets. |
| `LISTIMAGE_MAX_AGE_MINUTES` | `60` | Age threshold used by `cleanup_listimage` to purge stale temporary jobs. |

---

## 🎛️ Quality Presets

| Preset | Filter Speckle | Color Precision | Layer Difference | Corner Angle | Length Threshold | Splice Angle | Precision |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Simple** | 16 px | 4 | 24 | 60° | 6.0 | 45° | 2 |
| **Balanced** (Default) | 4 px | 6 | 16 | 50° | 4.0 | 45° | 4 |
| **Detailed** | 1 px | 8 | 8 | 30° | 2.0 | 40° | 6 |

---

## 🔗 Endpoints & URLs

| URL Pattern | View Function | Method | Description |
| :--- | :--- | :---: | :--- |
| `svg/` | `svg_start` | GET / POST | SVG upload start page & file ingestion |
| `svg/from-job/<uuid>/` | `svg_from_raster` | POST | Entry Point 10(b): Creates new SVG job from existing cutout |
| `svg/<uuid>/options/` | `svg_options` | GET | Interactive wizard, options controls, and SVG preview |
| `svg/<uuid>/render/` | `svg_render` | POST | Submits parameters and queues background tracing worker |
| `svg/<uuid>/status/` | `job_status` | GET | Shared polling endpoint returning progress, stats, and URLs |
| `svg/<uuid>/preview.svg` | `svg_preview` | GET | Serves `image/svg+xml` with `X-Content-Type-Options: nosniff` |
| `svg/<uuid>/download/` | `svg_download` | GET | Serves attachment blob as `listimage-<short-id>.svg` |
| `svg/<uuid>/recolor/` | `svg_recolor` | POST | Synchronizes live palette modifications to disk before save |
| `svg/<uuid>/cancel/` | `svg_cancel` | POST | Deletes files and DB row; redirects to `listimage:index` |
| `cleanup/<uuid>/` | `cleanup_job` | POST | Shared post-download cleanup endpoint |

---

## 🧹 Maintenance & Pruning

Run the cleanup management command periodically via cron or task scheduler:

```bash
# Prune all expired jobs older than 60 minutes (raster and SVG)
python manage.py cleanup_listimage --max-age-minutes=60

# Prune only expired SVG jobs
python manage.py cleanup_listimage --kind=svg --max-age-minutes=60

# Perform a dry-run without deleting files or DB rows
python manage.py cleanup_listimage --dry-run
```

