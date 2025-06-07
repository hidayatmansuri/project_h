from django.urls import path
from cv.views import home,cv

urlpatterns=[
    path('',home,name='home'),
    path('cv/',cv,name='cv'),
]