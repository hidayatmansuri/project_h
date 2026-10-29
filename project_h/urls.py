from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    path('', include('cv.urls')),
    path('', include('passgen.urls')),
    path('', include('utilitytracker.urls')),
    path('', include('shades.urls')),
    path('', include('docedit.urls')),
    path('listimage/', include('listimage.urls', namespace='listimage')),
    path('recipes/', include('recipes.urls')),
    path('simas-recipes/', RedirectView.as_view(url='/recipes/', permanent=False)),
    path('simas-recipes/<path:subpath>', RedirectView.as_view(url='/recipes/%(subpath)s', permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
