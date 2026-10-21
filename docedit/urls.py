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
    path('docedit/api/fonts/', views.font_list_api, name='docedit_font_list'),
    path('docedit/api/fonts/install/', views.install_font_api, name='docedit_font_install'),
    path('docedit/api/page-image/<str:sid>/<int:page_num>/', views.session_page_image, name='docedit_page_image'),
    path('docedit/api/font-file/<str:sid>/<str:filename>/', views.session_font_file, name='docedit_font_file'),
    path('docedit/api/confirm-download/<str:sid>/', views.confirm_download, name='docedit_confirm_download'),
    path('docedit/api/word-crop/<str:sid>/<str:word_id>/', views.session_word_crop, name='docedit_word_crop'),
    path('docedit/api/fuzzy-words/<str:sid>/', views.get_fuzzy_words_api, name='docedit_fuzzy_words'),
    path('docedit/api/review-word/<str:sid>/<str:word_id>/', views.review_word_api, name='docedit_review_word'),
]

