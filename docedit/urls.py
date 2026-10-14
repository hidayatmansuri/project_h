from django.urls import path
from . import views

urlpatterns = [
    path('docedit/', views.docedit_home, name='docedit'),
    path('docedit/api/upload/', views.upload_document, name='docedit_upload'),
    path('docedit/api/status/<str:sid>/', views.session_status, name='docedit_status'),
    path('docedit/api/save/<str:sid>/', views.save_document, name='docedit_save'),
    path('docedit/api/download/<str:sid>/', views.download_document, name='docedit_download'),
    path('docedit/api/cancel/<str:sid>/', views.cancel_document, name='docedit_cancel'),
    path('docedit/api/font/<str:sid>/', views.change_font, name='docedit_change_font'),
    path('docedit/api/page-image/<str:sid>/<int:page_num>/', views.session_page_image, name='docedit_page_image'),
]

