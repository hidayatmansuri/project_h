from django.urls import path
from .views import passgen

urlpatterns = [
    path('passgen/', passgen, name='passgen'),
]
