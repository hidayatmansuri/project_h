from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView, redirect_to_login
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


# ============================================================================
# Helpers
# ============================================================================

def recipe_queryset():
    """Recipes with everything the cards need, fetched in one query."""
    ensure_images_in_static_img()
    return Recipe.objects.select_related("category", "cuisine", "image")


def staff_required(view_func):
    """
    Editor-area guard. Uses Django's auth system so staff/superusers can manage recipes.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to access the admin area.")
            return redirect_to_login(request.get_full_path(), reverse("recipes:login"))
        if not request.user.is_staff:
            messages.error(request, "Your account does not have editor access yet.")
            return redirect("recipes:login")
        return view_func(request, *args, **kwargs)

    return wrapper


def flash_form_errors(request, form):
    for field, errors in form.errors.items():
        if field == "__all__":
            label = "Form"
        else:
            label = form.fields[field].label or field.replace("_", " ").title()
        for error in errors:
            messages.error(request, f"{label}: {error}")


def collection_context(title, recipes, section_id, empty_message="Will be available soon"):
    return {
        "page_title": title,
        "recipes": recipes,
        "section_id": section_id,
        "empty_message": empty_message,
    }


def get_redirect_target(request, default="recipes:manage"):
    """
    Returns the custom 'next' URL parameter if provided (e.g. from the embedded
    admin section on the single-page recipes view), or defaults to the given URL name.
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
# Public pages
# ============================================================================

def index(request):
    """Single-page recipes cookbook embedded in project-h with embedded admin."""
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
    })


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    recipes = recipe_queryset().filter(category=category)
    return render(request, "collection.html", collection_context(
        f"{category.name} Recipes", recipes, f"cat-{category.slug}"))


def cuisine_detail(request, slug):
    cuisine = get_object_or_404(Cuisine, slug=slug)
    recipes = recipe_queryset().filter(cuisine=cuisine)
    return render(request, "collection.html", collection_context(
        f"{cuisine.name}s", recipes, f"cus-{cuisine.slug}"))


def quick_recipes(request):
    recipes = recipe_queryset().filter(cook_time__lte=QUICK_MINUTES)
    return render(request, "collection.html", collection_context(
        "Recipes Under 30 Mins to Cook", recipes, "u30"))


def slow_recipes(request):
    recipes = recipe_queryset().filter(cook_time__gt=QUICK_MINUTES)
    return render(request, "collection.html", collection_context(
        "Recipes Over 30 Mins to Cook", recipes, "o30"))


# ============================================================================
# Accounts
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
            if user.is_staff:
                messages.info(request, "Account successfully created! You are now logged in.")
                return redirect(reverse("recipes:index") + "#admin-section")
            messages.info(
                request,
                "Account created. An administrator must enable editor access before you can manage recipes."
            )
            return redirect("recipes:index")
        flash_form_errors(request, form)
    else:
        form = SignUpForm()
    return render(request, "signup.html", {"page_title": "Create New User", "form": form})


# ============================================================================
# Editor area (staff only)
# ============================================================================

@staff_required
def manage(request):
    return render(request, "manage.html", {
        "page_title": "Admin Dashboard",
        "recipes": recipe_queryset(),
        "categories": Category.objects.all(),
        "cuisines": Cuisine.objects.all(),
        "images": RecipeImage.objects.all(),
    })


# --- Recipes ----------------------------------------------------------------

@staff_required
@require_POST
def recipe_create(request):
    form = RecipeForm(request.POST, request.FILES)
    if form.is_valid():
        form.save()
        messages.info(request, "Recipe created successfully!")
    else:
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request))


@staff_required
def recipe_edit(request, pk):
    recipe = get_object_or_404(recipe_queryset(), pk=pk)
    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        if form.is_valid():
            form.save()
            messages.info(request, "Recipe updated successfully!")
            return redirect(get_redirect_target(request))
        flash_form_errors(request, form)
    return render(request, "recipe_edit.html", {
        "page_title": "Edit Recipe",
        "recipe": recipe,
        "categories": Category.objects.all(),
        "cuisines": Cuisine.objects.all(),
        "images": RecipeImage.objects.all(),
    })


@staff_required
@require_POST
def recipe_delete(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    recipe.delete()
    messages.info(request, "Recipe deleted successfully.")
    return redirect(get_redirect_target(request))


# --- Categories -------------------------------------------------------------

@staff_required
@require_POST
def category_create(request):
    form = CategoryCreateForm(request.POST)
    if form.is_valid():
        category = form.save()
        messages.info(request, f"Category '{category.name}' added!")
    else:
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request))


@staff_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.info(request, "Category updated successfully!")
            return redirect(get_redirect_target(request))
        flash_form_errors(request, form)
    return render(request, "category_edit.html", {
        "page_title": "Edit Category",
        "category": category,
    })


@staff_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    affected = category.recipes.count()
    category.delete()
    note = f" {affected} recipe(s) are now uncategorised." if affected else ""
    messages.info(request, f"Category deleted.{note}")
    return redirect(get_redirect_target(request))


# --- Cuisines ---------------------------------------------------------------

@staff_required
@require_POST
def cuisine_create(request):
    form = CuisineCreateForm(request.POST)
    if form.is_valid():
        cuisine = form.save()
        messages.info(request, f"Cuisine '{cuisine.name}' added!")
    else:
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request))


@staff_required
def cuisine_edit(request, pk):
    cuisine = get_object_or_404(Cuisine, pk=pk)
    if request.method == "POST":
        form = CuisineForm(request.POST, instance=cuisine)
        if form.is_valid():
            form.save()
            messages.info(request, "Cuisine updated successfully!")
            return redirect(get_redirect_target(request))
        flash_form_errors(request, form)
    return render(request, "cuisine_edit.html", {
        "page_title": "Edit Cuisine",
        "cuisine": cuisine,
    })


@staff_required
@require_POST
def cuisine_delete(request, pk):
    cuisine = get_object_or_404(Cuisine, pk=pk)
    affected = cuisine.recipes.count()
    cuisine.delete()
    note = f" {affected} recipe(s) no longer have a cuisine." if affected else ""
    messages.info(request, f"Cuisine deleted.{note}")
    return redirect(get_redirect_target(request))


# --- Image library ----------------------------------------------------------

@staff_required
@require_POST
def image_upload(request):
    form = ImageUploadForm(request.POST, request.FILES)
    if form.is_valid():
        image = form.save()
        messages.info(request, f"Image '{image.title}' uploaded successfully to library!")
    else:
        flash_form_errors(request, form)
    return redirect(get_redirect_target(request))
