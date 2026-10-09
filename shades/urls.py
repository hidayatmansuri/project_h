from django.urls import path
from .views import shades

urlpatterns = [
    path('shades/', shades, name='shades'),
]
