from collections import defaultdict
from datetime import date

from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from projectauth.registry import DEFAULT_APP_METADATA

from .models import Experience, PersonalInfo, Qualification, Skill

# Proficiency label -> percentage score (0-100)
PROFICIENCY_SCORES = {
    "expert": 95,
    "master": 95,
    "advanced": 88,
    "senior": 88,
    "proficient": 80,
    "strong": 82,
    "intermediate": 68,
    "competent": 70,
    "working": 65,
    "familiar": 55,
    "beginner": 45,
    "basic": 45,
}

# Engineering highlights per project-h app (augments DEFAULT_APP_METADATA without duplicating metadata)
PROJECT_H_APP_HIGHLIGHTS = {
    "projectauth": {
        "name": "ProjectAuth & Security",
        "description": "Centralised authentication, TOTP/email 2FA, per-app RBAC, admin console, audit logging & brute-force protection.",
        "icon": "fa-solid fa-shield-halved",
        "home_url_name": "projectauth:account",
        "stack": ["Argon2", "TOTP 2FA", "django-axes", "RBAC"],
        "highlight": "Full identity & audit platform",
    },
    "docedit": {
        "stack": ["PyMuPDF", "Tesseract OCR", "fontTools", "nh3"],
        "highlight": "Layout-preserving PDF editor",
    },
    "listimage": {
        "stack": ["ONNX / rembg", "vtracer SVG", "OpenCV", "Pillow"],
        "highlight": "AI cutout & SVG vectorizer",
    },
    "utilitytracker": {
        "stack": ["PostgreSQL 18", "Chart.js", "Decimal", "Django ORM"],
        "highlight": "Daily / Monthly / Yearly analytics",
    },
    "recipes": {
        "stack": ["Vanilla JS", "HTML5", "Media Storage", "JSONB"],
        "highlight": "Zero-framework cookbook & CRUD",
    },
    "shades": {
        "stack": ["Vanilla JS", "CSS Grid", "Color Math"],
        "highlight": "Interactive palette explorer",
    },
    "passgen": {
        "stack": ["Python secrets", "No-Store Headers", "CSPRNG"],
        "highlight": "Cryptographic password generator",
    },
    "cv": {
        "stack": ["Chart.js", "Gotu UI", "Responsive Grid"],
        "highlight": "Data-driven portfolio & resume",
    },
}

# Fallback skills derived directly from project-h stack when Skill table is empty
DEFAULT_PROJECT_SKILLS = [
    {"name": "Python & Django 5.2", "category": "Backend", "proficiency": "Expert", "score": 94},
    {"name": "PostgreSQL 18 & ORM", "category": "Databases", "proficiency": "Advanced", "score": 88},
    {"name": "Auth, 2FA & Security", "category": "Security", "proficiency": "Advanced", "score": 90},
    {"name": "HTML5, CSS3 & Vanilla JS", "category": "Frontend", "proficiency": "Advanced", "score": 88},
    {"name": "Data Visualisation (Chart.js)", "category": "Frontend", "proficiency": "Proficient", "score": 84},
    {"name": "Computer Vision & SVG (ONNX/OpenCV)", "category": "AI & Vision", "proficiency": "Proficient", "score": 82},
    {"name": "PDF & OCR Pipelines (PyMuPDF)", "category": "AI & Vision", "proficiency": "Advanced", "score": 86},
    {"name": "Automated Testing & CI/CD", "category": "DevOps & QA", "proficiency": "Advanced", "score": 88},
]


def _score_from_proficiency(proficiency):
    if not proficiency:
        return 75
    text = str(proficiency).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return max(10, min(100, int(digits)))
    low = text.lower()
    for key, val in PROFICIENCY_SCORES.items():
        if key in low:
            return val
    return 75


def _months_between(start_date, end_date):
    end = end_date or date.today()
    months = (end.year - start_date.year) * 12 + (end.month - start_date.month) + 1
    return max(1, months)


def _format_duration(total_months):
    years, months = divmod(total_months, 12)
    parts = []
    if years:
        parts.append(f"{years} yr{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} mo{'s' if months != 1 else ''}")
    return " ".join(parts) or "< 1 mo"


def _build_project_showcase():
    """Reuse DEFAULT_APP_METADATA from projectauth.registry to showcase project-h apps."""
    showcase = []
    ordered_keys = [
        "projectauth",
        "docedit",
        "listimage",
        "utilitytracker",
        "recipes",
        "shades",
        "passgen",
    ]
    for key in ordered_keys:
        base = DEFAULT_APP_METADATA.get(key, {})
        extra = PROJECT_H_APP_HIGHLIGHTS.get(key, {})
        url_name = extra.get("home_url_name") or base.get("home_url_name") or ""
        try:
            url = reverse(url_name) if url_name else "#"
        except NoReverseMatch:
            url = "#"
        showcase.append({
            "key": key,
            "name": extra.get("name") or base.get("name", key.title()),
            "description": extra.get("description") or base.get("description", ""),
            "icon": extra.get("icon") or base.get("icon", "fa-solid fa-cube"),
            "url": url,
            "stack": extra.get("stack", []),
            "highlight": extra.get("highlight", ""),
        })
    return showcase


def cv(request):
    personal_info = list(PersonalInfo.objects.all())
    qualifications = list(Qualification.objects.all().order_by("-start_date"))
    experiences_qs = list(Experience.objects.all().order_by("-start_date"))
    skills_qs = list(Skill.objects.all().order_by("category", "name"))

    # Enrich experiences with computed duration
    experiences = []
    total_exp_months = 0
    industry_months = defaultdict(int)
    timeline_labels = []
    timeline_years = []

    for exp in experiences_qs:
        months = _months_between(exp.start_date, exp.end_date)
        total_exp_months += months
        industry_name = (exp.industry or "Technology").strip()
        industry_months[industry_name] += months
        timeline_labels.append(f"{exp.title} ({exp.employer})")
        timeline_years.append(round(months / 12.0, 2))
        experiences.append({
            "obj": exp,
            "title": exp.title,
            "employer": exp.employer,
            "industry": industry_name,
            "start_date": exp.start_date,
            "end_date": exp.end_date,
            "description": exp.description,
            "duration_label": _format_duration(months),
            "duration_years": round(months / 12.0, 1),
        })

    # Normalize skills (use DB skills when present, else showcase project-h skills)
    using_default_skills = len(skills_qs) == 0
    skill_items = []
    if skills_qs:
        for s in skills_qs:
            skill_items.append({
                "name": s.name,
                "category": (s.category or "General").strip(),
                "proficiency": (s.proficiency or "Proficient").strip(),
                "score": _score_from_proficiency(s.proficiency),
            })
    else:
        skill_items = list(DEFAULT_PROJECT_SKILLS)

    # Group skills by category for filter pills & radar chart
    category_scores = defaultdict(list)
    categories = []
    for item in skill_items:
        cat = item["category"]
        if cat not in category_scores:
            categories.append(cat)
        category_scores[cat].append(item["score"])

    radar_labels = categories
    radar_values = [
        round(sum(category_scores[c]) / len(category_scores[c]), 1)
        for c in categories
    ]

    project_showcase = _build_project_showcase()

    cv_chart_payload = {
        "skills": skill_items,
        "radar_labels": radar_labels,
        "radar_values": radar_values,
        "timeline_labels": timeline_labels,
        "timeline_years": timeline_years,
        "industry_labels": list(industry_months.keys()),
        "industry_years": [round(m / 12.0, 2) for m in industry_months.values()],
    }

    total_years_display = (
        f"{round(total_exp_months / 12.0, 1)}+"
        if total_exp_months >= 12
        else (f"{total_exp_months}m" if total_exp_months else "1+")
    )

    return render(request, "cv.html", {
        "personal_info": personal_info,
        "primary_profile": personal_info[0] if personal_info else None,
        "qualification": qualifications,
        "experience": experiences,
        "skills": skill_items,
        "skill_categories": categories,
        "using_default_skills": using_default_skills,
        "project_showcase": project_showcase,
        "cv_chart_payload": cv_chart_payload,
        "metrics": {
            "experience_years": total_years_display,
            "roles_count": len(experiences),
            "skills_count": len(skill_items),
            "qualifications_count": len(qualifications),
            "apps_built": len(DEFAULT_APP_METADATA) + 1,  # 8 local apps + projectauth
        },
    })
