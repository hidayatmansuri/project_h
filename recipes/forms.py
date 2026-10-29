from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import FileExtensionValidator

from .models import (
    ALLOWED_IMAGE_EXTENSIONS,
    Category,
    ChatMessage,
    Cuisine,
    Recipe,
    RecipeImage,
)

# Same limit as the Flask app (MAX_CONTENT_LENGTH = 16 MB).
MAX_IMAGE_BYTES = 16 * 1024 * 1024

# Materialize's datepicker writes "Oct 24, 2026"; the others are accepted for convenience.
DATE_INPUT_FORMATS = ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y"]


def validate_image_size(file):
    if file and file.size > MAX_IMAGE_BYTES:
        raise forms.ValidationError("Image is too large (maximum 16 MB).")


class LinesField(forms.Field):
    """One item per line <-> JSON list. Used by the Django admin for ingredients/methods."""

    widget = forms.Textarea(attrs={"rows": 8, "cols": 80})

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, (list, tuple)):
            return "\n".join(str(v) for v in value)
        return value

    def to_python(self, value):
        if not value:
            return []
        return [line.strip() for line in str(value).splitlines() if line.strip()]


class RecipeAdminForm(forms.ModelForm):
    """Used by admin.py so ingredients / methods are edited as plain text lines."""

    ingredients = LinesField(help_text="One ingredient per line")
    methods = LinesField(help_text="One step per line, in order")

    class Meta:
        model = Recipe
        fields = "__all__"


class RecipeForm(forms.ModelForm):
    """
    Handles the custom dashboard / edit-page forms.

    The templates post repeated ``ingredient[]`` and ``method[]`` inputs (the same
    names the Flask app used), so those are read straight from the request data.
    """

    image_file = forms.ImageField(
        required=False,
        validators=[FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS), validate_image_size],
    )
    created_on = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format="%b %d, %Y"),
    )

    class Meta:
        model = Recipe
        fields = ["name", "category", "cuisine", "image", "prep_time", "cook_time", "created_on"]

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def save(self, commit=True):
        recipe = super().save(commit=False)

        # Dynamic rows: keep only non-empty values, preserve order.
        recipe.ingredients = [v.strip() for v in self.data.getlist("ingredient[]") if v.strip()]
        recipe.methods = [v.strip() for v in self.data.getlist("method[]") if v.strip()]

        uploaded = self.cleaned_data.get("image_file")
        if uploaded:
            # Same behaviour as Flask: an upload is added to the library and used for this recipe.
            title = uploaded.name.rsplit(".", 1)[0][:150]
            recipe.image = RecipeImage.objects.create(title=title, image=uploaded)
        elif not self.cleaned_data.get("image") and self.instance.pk:
            # Nothing chosen on edit -> keep the current image (Flask did the same).
            previous = Recipe.objects.filter(pk=self.instance.pk).values_list("image_id", flat=True).first()
            recipe.image_id = previous

        if commit:
            recipe.save()
        return recipe


class CategoryCreateForm(forms.ModelForm):
    """Dashboard quick-add: name only (icon / colour fall back to the model defaults)."""

    class Meta:
        model = Category
        fields = ["name"]

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "icon", "tagline", "accent"]

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class CuisineCreateForm(forms.ModelForm):
    """Dashboard quick-add: name only."""

    class Meta:
        model = Cuisine
        fields = ["name"]

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class CuisineForm(forms.ModelForm):
    class Meta:
        model = Cuisine
        fields = ["name", "short_name", "icon", "tagline", "accent"]

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class ImageUploadForm(forms.ModelForm):
    class Meta:
        model = RecipeImage
        fields = ["image"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].validators.append(validate_image_size)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.title = instance.image.name.rsplit("/", 1)[-1].rsplit(".", 1)[0][:150]
        if commit:
            instance.save()
        return instance


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")


class ContactForm(forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField()
    phone = forms.CharField(max_length=30, required=False)
    message = forms.CharField(max_length=2000)


class ChatNameForm(forms.Form):
    chatname = forms.CharField(max_length=40)

    def clean_chatname(self):
        return self.cleaned_data["chatname"].strip()


class ChatMessageForm(forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ["message"]

    def clean_message(self):
        return self.cleaned_data["message"].strip()
