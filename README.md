# Project H (Personal Dashboard & Tools)

![Project Banner/Screenshot](placeholders/banner.png) <!-- Add a screenshot of your main page here -->

A comprehensive personal Django web application featuring a suite of useful daily tools and a professional portfolio. Built with Django, PostgreSQL, and styled for a modern user experience.

## ✨ Features

The project is divided into several dedicated applications:

*   **🏠 Home:** The landing page and central hub.
*   **📄 CV/Portfolio (`cv`):** A professional digital resume showcasing skills, experience, and projects.
*   **🔐 Password Generator (`passgen`):** A secure tool to generate strong, random passwords based on user-defined criteria.
*   **⚡ Utility Tracker (`utilitytracker`):** A comprehensive dashboard to track electricity and gas meter readings, log top-ups, and visualize usage data over time with interactive charts.
*   **🎨 Colour Shades (`shades`):** An interactive colour palette explorer from #000000 to #FFFFFF with instant copy micro-interactions.
*   **📝 Document Editor (`docedit`):** A document editor for old scanned books and diverse documents. Features OCR with fuzzy character detection, automated font matching (system fonts, free Google Font downloads, and nearest match alternatives), Windows system font installation, live split-pane editing, and same-extension file exports.
*   **🪄 ListImage Object Isolator & SVG Vectorizer (`listimage`):** Upload product images, automatically remove backgrounds using neural networks (`isnet-general-use`, `birefnet-general`, `u2netp`), center subjects with exact 10 px padding on a pure white 2000x2000 canvas, or convert main subjects/logos to pure resolution-independent SVG vector paths (dual-engine: `vtracer` with OpenCV Bézier spline fallback). Features Monochrome (Silhouette and Detail), Hybrid, and 2–16 Full Colour modes, non-overlapping shapes for cutting machines (Cricut/Silhouette), 1:1 square canvas framing, live client-side swatch recoloring with click-to-pick regions, undo history, near-white fill removal, and immediate post-download server cleanup. See [listimage/README.md](listimage/README.md) and [deploy/listimage.md](deploy/listimage.md) for details.

## 🚀 Technologies Used

*   **Backend:** Python 3, Django 5.2
*   **Database:** PostgreSQL (Production), SQLite (Testing)
*   **Frontend:** HTML5, CSS3, JavaScript (Vanilla), Chart.js (for utility tracking)
*   **Styling:** Custom CSS with light/dark mode support

## 🛠️ Local Development Setup

Follow these instructions to get a copy of the project up and running on your local machine.

### Prerequisites
*   Python 3.10+
*   PostgreSQL installed and running
*   Git

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/project-h.git
cd project-h
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Create a `.env` file in the root directory (where `manage.py` is located) and add your database and secret key details. You can copy the template provided:
```bash
cp .env.example .env
```
*(Make sure to update `.env` with your actual local PostgreSQL credentials)*

### 5. Apply Migrations
```bash
python manage.py migrate
```

### 6. Create a Superuser (Optional, for Admin Access)
```bash
python manage.py createsuperuser
```

### 7. Run the Development Server
```bash
python manage.py runserver
```
Visit `http://127.0.0.1:8000/` in your browser.

## 🧪 Running Tests
The project uses SQLite for fast, isolated testing. To run the automated test suite:
```bash
python manage.py test
```

## 📸 Screenshots

| Home Page | Utility Tracker | Password Generator |
| :---: | :---: | :---: |
| ![Home](placeholders/home.png) | ![Utilities](placeholders/utilities.png) | ![PassGen](placeholders/passgen.png) |

*(Note: Replace the placeholder image paths with actual screenshots of your app!)*

## 🎨 ListImage: Image to SVG Vectorization

The `listimage` application includes both raster background removal (2000×2000 pure white canvas rendering) and a pure vector **Image to SVG** converter.

### Setup & Requirements
- Vectorization dependencies: `vtracer>=0.6.15` and `lxml>=5.2.0` (included in `requirements.txt`).
- Dual-engine vectorizer: primary `vtracer` binary tracer with an automatic OpenCV Bézier spline contour fallback ensuring 100% operation across restricted operating systems (such as Windows WDAC/SAC).

### Configuration Settings
Configure via environment variables or `project_h/settings.py`:
- `LISTIMAGE_SVG_MAX_TRACE_PX` (default: `2000`): Maximum source dimension on longest side. Small images (<800 px) are upscaled 2× with Lanczos before tracing.
- `LISTIMAGE_SVG_MAX_BYTES` (default: `3145728` [3 MB]): File size warning threshold suggesting simpler presets or fewer palette colors.

### Preset Parameter Mappings
The vector engine maps user quality presets to underlying vectorization parameters:
- **Simple**: `filter_speckle=16`, `color_precision=4`, `layer_difference=24`, `corner_threshold=60`, `length_threshold=6.0`, `splice_threshold=45`, `path_precision=2`, `mode="spline"`.
- **Balanced** (Default): `filter_speckle=4`, `color_precision=6`, `layer_difference=16`, `corner_threshold=50`, `length_threshold=4.0`, `splice_threshold=45`, `path_precision=4`, `mode="spline"`.
- **Detailed**: `filter_speckle=1`, `color_precision=8`, `layer_difference=8`, `corner_threshold=30`, `length_threshold=2.0`, `splice_threshold=40`, `path_precision=6`, `mode="spline"`.
- **Cutting Machines**: Setting `hierarchical="cutout"` generates non-overlapping, disjoint vector shapes suitable for vinyl cutters, Cricut, and laser machines (default: `"stacked"`).

### Workflow & Limits
- Queue limits & one-active-job rule: Users are limited to one active processing job at a time.
- Cooperative cancellation: The Cancel button at each stage cooperatively signals the background thread, deletes workspace files and DB records, and returns to `listimage:index`.
- Post-download cleanup: After browser download completes, an automated cleanup call removes all workspace assets and DB rows, redirecting to `listimage:index`.
- Periodic maintenance: Run `python manage.py cleanup_listimage --max-age-minutes=60` (supports optional `--kind=svg` filter).

See [`listimage/README.md`](listimage/README.md) for full endpoint specifications, UI architecture, and details.

## 📄 License
This project is proprietary and confidential. All rights are reserved by the copyright owner. See the [LICENSE](LICENSE) file for details.
