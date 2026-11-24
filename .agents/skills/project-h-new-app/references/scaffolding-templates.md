# Scaffolding Templates for `project-h-new-app`

## 1. `<app_name>/apps.py`
```python
from django.apps import AppConfig


class MyToolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mytool"
    verbose_name = "My Tool"

    # Auto-discovered by projectauth.registry.sync_protected_apps()
    projectauth_label = "My Tool"
    projectauth_description = "Short description shown in the ProjectAuth console."
    projectauth_icon = "fa-solid fa-cube"
    projectauth_home_url_name = "mytool:index"
    projectauth_sort_order = 70
```

## 2. `<app_name>/urls.py`
```python
from django.urls import path
from . import views

app_name = "mytool"

urlpatterns = [
    path("", views.index, name="index"),
]
```

## 3. `<app_name>/conf.py` (Optional — for configurable apps)
```python
from django.conf import settings


def _get(name, default):
    return getattr(settings, f"MYTOOL_{name}", default)


class MyToolConf:
    @property
    def MAX_ITEMS(self) -> int:
        return int(_get("MAX_ITEMS", 50))


conf = MyToolConf()
```

## 4. `home/templates/home.html` Snippets
**Tools dropdown item** (inside `<div class="dropdown-menu">`):
```html
<a class="nav-link ph-hover menu-item" href="{% url 'mytool:index' %}">
    <i class="fa-solid fa-cube"></i> <span>My Tool</span>
</a>
```

**Welcome card** (inside `<div class="welcome-cards">`):
```html
<a href="{% url 'mytool:index' %}" class="ph-card floating-card">
    <div class="floating-top">
        Short<br>Tagline
    </div>
    <span>My<span class="floating-lable"> Tool</span></span>
</a>
```

## 5. `<app_name>/tests.py` Baseline Auth & View Tests
```python
from django.test import TestCase
from django.urls import reverse

from projectauth.test_helpers import grant_test_client_app_access


class MyToolViewTests(TestCase):
    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("mytool:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login/", response["Location"])

    def test_granted_user_can_access_index(self):
        grant_test_client_app_access(self.client, "mytool")
        response = self.client.get(reverse("mytool:index"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
```
