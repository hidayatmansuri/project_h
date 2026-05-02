from django.urls import path
from .views import utility

urlpatterns = [
    path('utility', utility, name='utility'),
]