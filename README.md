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
*   **🪄 ListImage Object Isolator (`listimage`):** Upload product images, automatically remove backgrounds using neural networks (`isnet-general-use`, `birefnet-general`, `u2netp`), center subjects with exact 10 px padding on a pure white 2000x2000 canvas, apply non-destructive amendments (erase/restore brush, tolerance magic wand, object selection, auto touch-up for transparent/reflective items), and download high-quality PNG or JPEG with immediate server cleanup. See [deploy/listimage.md](deploy/listimage.md) for full production and Gunicorn/nginx tuning.

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

## 📄 License
This project is proprietary and confidential. All rights are reserved by the copyright owner. See the [LICENSE](LICENSE) file for details.
