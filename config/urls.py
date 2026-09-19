"""
URL configuration for Container Truck Queue Management System (Port Gate TOS).
"""

from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
import django
from django.db import connection


@login_required
def system_status_view(request):
    """
    View status verifikasi infrastruktur Django dan database.
    Terproteksi otentikasi login untuk mencegah information disclosure internal host ke pihak anonim.
    """
    engine_name = connection.settings_dict.get('ENGINE', 'Unknown').split('.')[-1]
    is_postgres = 'postgres' in connection.settings_dict.get('ENGINE', '').lower()
    
    # Deteksi apakah host database mengarah ke Supabase
    db_host = connection.settings_dict.get('HOST', '')
    is_supabase = 'supabase' in db_host.lower()

    context = {
        'django_version': django.get_version(),
        'db_engine': engine_name,
        'is_postgres': is_postgres,
        'is_supabase': is_supabase,
        'db_host': db_host if db_host else 'Local SQLite Fallback',
        'debug_mode': settings.DEBUG,
        'time_zone': settings.TIME_ZONE,
    }
    return render(request, 'index.html', context)


from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.accounts.urls')),
    path('', include('apps.queue_gate.urls')),
    path('system-status/', system_status_view, name='system_status'),
]


# Serve static & media files during development
if settings.DEBUG:
    if settings.STATICFILES_DIRS:
        urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
