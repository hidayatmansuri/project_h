from django.urls import path
from . import views, svg_views

app_name = 'listimage'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload, name='upload'),
    path('status/<uuid:job_id>/', views.job_status, name='status'),
    path('preview/<uuid:job_id>/', views.preview_image, name='preview'),
    path('preview/<uuid:job_id>/cutout/', views.cutout_preview, name='cutout_preview'),
    path('objects/<uuid:job_id>/', views.objects_metadata, name='objects'),
    path('edit/<uuid:job_id>/', views.edit_job, name='edit'),
    path('touchup/<uuid:job_id>/', views.auto_touchup, name='touchup'),
    path('download/<uuid:job_id>/', views.download_image, name='download'),
    path('cleanup/<uuid:job_id>/', views.cleanup_job, name='cleanup'),
    path('cancel/<uuid:job_id>/', views.cancel_job, name='cancel'),
    # Batch processing endpoints
    path('batch/upload/', views.batch_upload, name='batch_upload'),
    path('batch/status/<uuid:batch_id>/', views.batch_status, name='batch_status'),
    path('batch/download/<uuid:batch_id>/', views.batch_download_zip, name='batch_download'),
    path('batch/cleanup/<uuid:batch_id>/', views.batch_cleanup, name='batch_cleanup'),
    path('batch/cancel/<uuid:batch_id>/', views.batch_cancel, name='batch_cancel'),
    # SVG Vectorization endpoints
    path('svg/', svg_views.svg_start, name='svg_start'),
    path('svg/from-job/<uuid:job_id>/', svg_views.svg_from_raster, name='svg_from_raster'),
    path('svg/<uuid:job_id>/options/', svg_views.svg_options, name='svg_options'),
    path('svg/<uuid:job_id>/render/', svg_views.svg_render, name='svg_render'),
    path('svg/<uuid:job_id>/status/', views.job_status, name='svg_status'),
    path('svg/<uuid:job_id>/preview.svg', svg_views.svg_preview, name='svg_preview'),
    path('svg/<uuid:job_id>/download/', svg_views.svg_download, name='svg_download'),
    path('svg/<uuid:job_id>/cancel/', svg_views.svg_cancel, name='svg_cancel'),
    path('svg/<uuid:job_id>/recolor/', svg_views.svg_recolor, name='svg_recolor'),
]
