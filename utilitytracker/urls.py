from django.urls import path
from .views import utilitytracker

urlpatterns = [
    path('utilitytracker/', utilitytracker, name='utilitytracker'),
]