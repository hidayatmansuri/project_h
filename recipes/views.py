from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    CategoryCreateForm,
    CategoryForm,
    CuisineCreateForm,
    CuisineForm,
    ImageUploadForm,
    RecipeForm,
    SignUpForm,
)
from .models import Category, Cuisine, Recipe, RecipeImage, ensure_images_in_static_img

QUICK_MINUTES = 30
DEFAULT_PASSCODE = "000000"


# ============================================================================
# Helpers
# ============================================================================

def recipe_queryset():
    """Recipes with everything the cards need, fetched in one query."""
    ensure_images_in_static_img()
    return Recipe.objects.select_related("category", "cuisine", "image")


def verify_recipe_passcode(request, recipe):
    """
    Verify the 6-digit password for editing or deleting an existing recipe.
    Requires the recipe's creation date in 6-digit British DDMMYY format
    (e.g. '120226' for 12 Feb 2026), or '000000' if no creation date is set.
    """
    submitted = (request.POST.get("passcode") or "").strip()
    expected = recipe.passcode
    if submitted != expected:
        if recipe.created_on:
            date_str = recipe.created_on.strftime("%d %b %Y")
            hint = f"the 6-digit creation date (DDMMYY for {date_str})"
        else:
            hint = f"'{DEFAULT_PASSCODE}'"
        messages.error(
            request,
            f"Incorrect 6-digit password for '{recipe.name}'. Please enter {hint} to prevent accidental actions.",
        )
        return False
    return True


def verify_default_passcode(request, action_label="complete this action"):
    """
    Verify the 6-digit password ('000000') for non-recipe or new-item actions
    (categories, cuisines, image uploads, adding new recipes).
    """
    submitted = (request.POST.get("passcode") or "").strip()
    if submitted != DEFAULT_PASSCODE:
        messages.error(
            request,
            f"Incorrect 6-digit password to {action_label}. Please enter '{DEFAULT_PASSCODE}' to prevent accidental actions.",
        )
        return False
    return True


def flash_form_errors(request, form):
    for field, errors in form.errors.items():
        if field == "__all__":
            label = "Form"
        else:
            label = form.fields[field].label or field.replace("_", " ").title()
        for error in errors:
            messages.error(request, f"{label}: {error}")


def collection_context(title, recipes, section_id, empty_message="Will be available soon", **extra):
    ctx = {
        "page_title": title,
        "recipes": recipes,
        "section_id": section_id,
        "empty_message": empty_message,
        "categories": Category.objects.all(),
        "cuisines": Cuisine.objects.all(),
        "images": RecipeImage.objects.all(),
    }
    ctx.update(extra)
    return ctx


def get_redirect_target(request, default="recipes:index"):
    """
    Returns the custom 'next' URL parameter if provided, or falls back to
    the given default URL name.
    """
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return next_url
    return reverse(default)


def get_single_page_context(request):
    recipes = list(recipe_queryset())
    categories = list(
        Category.objects.annotate(recipe_count=Count("recipes")).prefetch_related(
            Prefetch("recipes", queryset=recipe_queryset())
        )
    )
    cuisines = list(
        Cuisine.objects.annotate(recipe_count=Count("recipes")).prefetch_related(
            Prefetch("recipes", queryset=recipe_queryset())
        )
    )
    images = list(RecipeImage.objects.all())
    quick_count = sum(1 for recipe in recipes if recipe.is_quick)

    return {
        "page_title": "Recipes",
        "recipes": recipes,
        "categories": categories,
        "cuisines": cuisines,
        "images": images,
        "total_recipes": len(recipes),
        "category_total": len(categories),
        "cuisine_total": len(cuisines),
        "quick_count": quick_count,
        "slow_count": len(recipes) - quick_count,
    }


# ============================================================================
# Public & Embedded Editor Pages (No Login Required; 6-Digit Passcode Guarded)
# ============================================================================

def index(request):
    """Single-page recipes cookbook embedded in project-h with embedded editing."""
    return render(request, "recipes.html", get_single_page_context(request))


def recipe_list(request):
    """All recipes grouped by category and by cuisine (renders the single-page app)."""
    return render(request, "recipes.html", get_single_page_context(request))


def recipe_detail(request, slug):
    recipes = recipe_queryset()
    recipe = recipes.filter(slug=slug).first()
    if recipe is None and slug.isdigit():
        recipe = recipes.filter(pk=int(slug)).first()
    if recipe is None:
        messages.error(request, "Recipe not found.")
        return redirect("recipes:recipes")
    return render(request, "recipe_detail.html", {
        "recipe": recipe,
        "page_title": recipe.name,
        "categories": Category.objects.all(),
        "cuisines": Cuisine.objects.all(),
        "images": RecipeImage.objects.all(),
    })


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    recipes = recipe_queryset().filter(category=category)
    return render(request, "collection.html", collection_context(
        f"{category.name} Recipes",
        recipes,
        f"cat-{category.slug}",
        category=category,
    ))


def cuisine_detail(request, slug):
    cuisine = get_object_or_404(Cuisine, slug=slug)
    recipes = recipe_queryset().filter(cuisine=cuisine)
    return render(request, "collection.html", collection_context(
        f"{cuisine.name}s",
        recipes,
        f"cus-{cuisine.slug}",
        cuisine=cuisine,
    ))


def quick_recipes(request):
    recipes = recipe_queryset().filter(cook_time__lte=QUICK_MINUTES)
    return render(request, "collection.html", collection_context(
        "Recipes Under 30 Mins to Cook", recipes, "u30"))


def slow_recipes(request):
    recipes = recipe_queryset().filter(cook_time__gt=QUICK_MINUTES)
    return render(request, "collection.html", collection_context(
        "Recipes Over 30 Mins to Cook", recipes, "o30"))


# ============================================================================
# Legacy Account Views (kept for URL compatibility; not required for editing)
# ============================================================================

class LoginView(LoginView):
    template_name = "login.html"

    def get_success_url(self):
        return self.get_redirect_url() or (reverse("recipes:index") + "#admin-section")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(self.request, f"Welcome back, {form.get_user().get_username()}!")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Login"
        context["signup_enabled"] = getattr(
            settings, "RECIPES_ALLOW_SIGNUP", getattr(settings, "recipes_ALLOW_SIGNUP", True)
        )
        return context


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You have been successfully logged out.")
    target = request.POST.get("next") or request.GET.get("next") or reverse("recipes:index")
    return redirect(target)


def signup(request):
    if not getattr(settings, "RECIPES_ALLOW_SIGNUP", getattr(settings, "recipes_ALLOW_SIGNUP", True)):
        messages.error(request, "Account creation is disabled.")
        return redirect("recipes:login")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_staff = getattr(
                settings, "RECIPES_SIGNUP_GRANTS_STAFF", getattr(settings, "recipes_SIGNUP_GRANTS_STAFF", False)
            )
            user.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.info(request, "Account successfully created!")
            return redirect(reverse("recipes:index") + "#admin-section")
        flash_form_errors(request, form)
    else:
        form = SignUpForm()
    return render(request, "signup.html", {"page_title": "Create New User", "form": form})


# ============================================================================
# Management & CRUD Endpoints (Guarded by 6-Digit Passcode)
# ============================================================================

def manage(request):
    return render(request, "manage.html", {
        "page_title": "Recipes Management",
        "recipes": recipe_queryset(),
        "categories": Category.objects.all(),
        "cuisines": Cuisine.objects.all(),
        "images": RecipeImage.objects.all(),
    })


# --- Recipes ----------------------------------------------------------------

@require_POST
def recipe_create(request):
    form = RecipeForm(request.POST, request.FILES)
    submitted = (request.POST.get("passcode") or "").strip()
    if form.is_valid():
        created_on = form.cleaned_data.get("created_on")
        date_code = created_on.strftime("%d%m%y") if created_on else None
        if submitted != DEFAULT_PASSCODE and (not date_code or submitted != date_code):
            messages.error(
                request,
                f"Incorrect 6-digit password to add a recipe. Please enter '{DEFAULT_PASSCODE}'"
                + (f" or '{date_code}'" if date_code else "")
                + " to prevent accidental actions.",
            )
            return redirect(get_redirect_target(request, default="recipes:manage"))
        recipe = form.save()
        messages.info(request, f"Recipe '{recipe.name}' created successfully!")
    else:
        if submitted != DEFAULT_PASSCODE:
            messages.error(
                request,
                f"Incorrect 6-digit password to add a recipe. Please enter '{DEFAULT_PASSCODE}' to prevent accidental actions.",
            )
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request, default="recipes:manage"))


def recipe_edit(request, pk):
    recipe = get_object_or_404(recipe_queryset(), pk=pk)
    if request.method == "POST":
        if not verify_recipe_passcode(request, recipe):
            return redirect(get_redirect_target(request, default="recipes:manage"))
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        if form.is_valid():
            form.save()
            messages.info(request, f"Recipe '{recipe.name}' updated successfully!")
            return redirect(get_redirect_target(request, default="recipes:manage"))
        flash_form_errors(request, form)
    return render(request, "recipe_edit.html", {
        "page_title": "Edit Recipe",
        "recipe": recipe,
        "categories": Category.objects.all(),
        "cuisines": Cuisine.objects.all(),
        "images": RecipeImage.objects.all(),
    })


@require_POST
def recipe_delete(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    if not verify_recipe_passcode(request, recipe):
        return redirect(get_redirect_target(request, default="recipes:manage"))
    recipe_name = recipe.name
    recipe.delete()
    messages.info(request, f"Recipe '{recipe_name}' deleted successfully.")
    return redirect(get_redirect_target(request, default="recipes:manage"))


# --- Categories -------------------------------------------------------------

@require_POST
def category_create(request):
    if not verify_default_passcode(request, "add a category"):
        return redirect(get_redirect_target(request, default="recipes:manage"))
    form = CategoryCreateForm(request.POST)
    if form.is_valid():
        category = form.save()
        messages.info(request, f"Category '{category.name}' added!")
    else:
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request, default="recipes:manage"))


def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        if not verify_default_passcode(request, f"edit category '{category.name}'"):
            return redirect(get_redirect_target(request, default="recipes:manage"))
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.info(request, f"Category '{category.name}' updated successfully!")
            return redirect(get_redirect_target(request, default="recipes:manage"))
        flash_form_errors(request, form)
    return render(request, "category_edit.html", {
        "page_title": "Edit Category",
        "category": category,
    })


@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if not verify_default_passcode(request, f"delete category '{category.name}'"):
        return redirect(get_redirect_target(request, default="recipes:manage"))
    affected = category.recipes.count()
    category.delete()
    note = f" {affected} recipe(s) are now uncategorised." if affected else ""
    messages.info(request, f"Category deleted.{note}")
    return redirect(get_redirect_target(request, default="recipes:manage"))


# --- Cuisines ---------------------------------------------------------------

@require_POST
def cuisine_create(request):
    if not verify_default_passcode(request, "add a cuisine"):
        return redirect(get_redirect_target(request, default="recipes:manage"))
    form = CuisineCreateForm(request.POST)
    if form.is_valid():
        cuisine = form.save()
        messages.info(request, f"Cuisine '{cuisine.name}' added!")
    else:
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request, default="recipes:manage"))


def cuisine_edit(request, pk):
    cuisine = get_object_or_404(Cuisine, pk=pk)
    if request.method == "POST":
        if not verify_default_passcode(request, f"edit cuisine '{cuisine.name}'"):
            return redirect(get_redirect_target(request, default="recipes:manage"))
        form = CuisineForm(request.POST, instance=cuisine)
        if form.is_valid():
            form.save()
            messages.info(request, f"Cuisine '{cuisine.name}' updated successfully!")
            return redirect(get_redirect_target(request, default="recipes:manage"))
        flash_form_errors(request, form)
    return render(request, "cuisine_edit.html", {
        "page_title": "Edit Cuisine",
        "cuisine": cuisine,
    })


@require_POST
def cuisine_delete(request, pk):
    cuisine = get_object_or_404(Cuisine, pk=pk)
    if not verify_default_passcode(request, f"delete cuisine '{cuisine.name}'"):
        return redirect(get_redirect_target(request, default="recipes:manage"))
    affected = cuisine.recipes.count()
    cuisine.delete()
    note = f" {affected} recipe(s) no longer have a cuisine." if affected else ""
    messages.info(request, f"Cuisine deleted.{note}")
    return redirect(get_redirect_target(request, default="recipes:manage"))


# --- Image library ----------------------------------------------------------

@require_POST
def image_upload(request):
    if not verify_default_passcode(request, "upload an image"):
        return redirect(get_redirect_target(request, default="recipes:manage"))
    form = ImageUploadForm(request.POST, request.FILES)
    if form.is_valid():
        image = form.save()
        messages.info(request, f"Image '{image.title}' uploaded successfully to library!")
    else:
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request, default="recipes:manage"))
