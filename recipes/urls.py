from django.urls import path

from . import views

app_name = "recipes"

urlpatterns = [
    # Public pages
    path("", views.index, name="index"),
    path("recipes/", views.recipe_list, name="recipes"),
    path("recipes/<slug:slug>/", views.recipe_detail, name="recipe_detail"),
    path("category/<slug:slug>/", views.category_detail, name="category"),
    path("cuisine/<slug:slug>/", views.cuisine_detail, name="cuisine"),
    path("under-30-mins/", views.quick_recipes, name="quick"),
    path("over-30-mins/", views.slow_recipes, name="slow"),

    # Accounts
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("signup/", views.signup, name="signup"),

    # Editor area (staff only)
    path("manage/", views.manage, name="manage"),
    path("manage/recipes/add/", views.recipe_create, name="recipe_create"),
    path("manage/recipes/<int:pk>/edit/", views.recipe_edit, name="recipe_edit"),
    path("manage/recipes/<int:pk>/delete/", views.recipe_delete, name="recipe_delete"),
    path("manage/categories/add/", views.category_create, name="category_create"),
    path("manage/categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("manage/categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("manage/cuisines/add/", views.cuisine_create, name="cuisine_create"),
    path("manage/cuisines/<int:pk>/edit/", views.cuisine_edit, name="cuisine_edit"),
    path("manage/cuisines/<int:pk>/delete/", views.cuisine_delete, name="cuisine_delete"),
    path("manage/images/upload/", views.image_upload, name="image_upload"),
]
