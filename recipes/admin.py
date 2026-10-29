from django.contrib import admin

from .forms import RecipeAdminForm
from .models import Category, ChatMessage, Cuisine, Recipe, RecipeImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "accent")
    search_fields = ("name",)


@admin.register(Cuisine)
class CuisineAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "accent")
    search_fields = ("name",)


@admin.register(RecipeImage)
class RecipeImageAdmin(admin.ModelAdmin):
    list_display = ("__str__", "uploaded_at")
    search_fields = ("title",)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    form = RecipeAdminForm
    list_display = ("name", "category", "cuisine", "prep_time", "cook_time", "created_on")
    list_filter = ("category", "cuisine")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("created", "username", "message")
    search_fields = ("username", "message")
    date_hierarchy = "created"
