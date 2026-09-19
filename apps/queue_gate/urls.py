from django.urls import path
from . import views
from apps.masterdata import views as masterdata_views
from apps.accounts.views import HomeRedirectView

urlpatterns = [
    path('', HomeRedirectView.as_view(), name='home'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('gate-in/', views.GateInView.as_view(), name='gate_in'),
    path('gate-out/', views.GateOutView.as_view(), name='gate_out'),
    path('queue/', views.QueueListView.as_view(), name='queue_list'),
    path('queue/<int:pk>/', views.QueueDetailView.as_view(), name='queue_detail'),
    path('queue/<int:pk>/process/', views.QueueProcessActionView.as_view(), name='queue_process_action'),
    path('gate-cockpit/', views.GateCockpitView.as_view(), name='gate_cockpit'),
    path('ticket/<int:pk>/', views.GateTicketView.as_view(), name='gate_ticket'),
    path('api/truck-lookup/', views.TruckLookupAPIView.as_view(), name='api_truck_lookup'),
    path('api/container-lookup/', views.ContainerLookupAPIView.as_view(), name='api_container_lookup'),
    path('api/ocr-process/', views.OCRProcessAPIView.as_view(), name='api_ocr_process'),

    # Master Data - Truck Master (Stage 7)
    path('truck-master/', masterdata_views.TruckMasterView.as_view(), name='truck_master'),
    path('truck-master/create/', masterdata_views.TruckCreateView.as_view(), name='truck_create'),
    path('truck-master/<int:pk>/edit/', masterdata_views.TruckUpdateView.as_view(), name='truck_edit'),
    path('truck-master/<int:pk>/toggle/', masterdata_views.TruckToggleActiveView.as_view(), name='truck_toggle'),
    path('truck-master/<int:pk>/detail-json/', masterdata_views.TruckDetailJSONView.as_view(), name='truck_detail_json'),

    # Master Data - Driver Master
    path('driver-master/', masterdata_views.DriverMasterView.as_view(), name='driver_master'),
    path('driver-master/create/', masterdata_views.DriverCreateView.as_view(), name='driver_create'),
    path('driver-master/<int:pk>/edit/', masterdata_views.DriverUpdateView.as_view(), name='driver_edit'),
    path('driver-master/<int:pk>/toggle/', masterdata_views.DriverToggleActiveView.as_view(), name='driver_toggle'),
    path('driver-master/<int:pk>/detail-json/', masterdata_views.DriverDetailJSONView.as_view(), name='driver_detail_json'),

    # Master Data - Expedition Master
    path('expedition-master/', masterdata_views.ExpeditionMasterView.as_view(), name='expedition_master'),
    path('expedition-master/create/', masterdata_views.ExpeditionCreateView.as_view(), name='expedition_create'),
    path('expedition-master/<int:pk>/edit/', masterdata_views.ExpeditionUpdateView.as_view(), name='expedition_edit'),
    path('expedition-master/<int:pk>/toggle/', masterdata_views.ExpeditionToggleActiveView.as_view(), name='expedition_toggle'),
    path('expedition-master/<int:pk>/detail-json/', masterdata_views.ExpeditionDetailJSONView.as_view(), name='expedition_detail_json'),

    # Master Data - Container Master
    path('container-master/', masterdata_views.ContainerMasterView.as_view(), name='container_master'),
    path('container-master/create/', masterdata_views.ContainerCreateView.as_view(), name='container_create'),
    path('container-master/<int:pk>/edit/', masterdata_views.ContainerUpdateView.as_view(), name='container_edit'),
    path('container-master/<int:pk>/toggle/', masterdata_views.ContainerToggleActiveView.as_view(), name='container_toggle'),
    path('container-master/<int:pk>/detail-json/', masterdata_views.ContainerDetailJSONView.as_view(), name='container_detail_json'),

    # Riwayat & Audit Log (Stage 8)
    path('audit-log/', views.AuditLogView.as_view(), name='audit_log'),

    # Konfigurasi Kamera OCR (Stage 9)
    path('ocr-settings/', views.OcrSettingsView.as_view(), name='ocr_settings'),
]

