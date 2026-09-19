from django.urls import path
from . import views

urlpatterns = [
    # Trucks
    path('', views.TruckMasterView.as_view(), name='truck_master'),
    path('create/', views.TruckCreateView.as_view(), name='truck_create'),
    path('<int:pk>/edit/', views.TruckUpdateView.as_view(), name='truck_edit'),
    path('<int:pk>/toggle/', views.TruckToggleActiveView.as_view(), name='truck_toggle'),
    path('<int:pk>/detail-json/', views.TruckDetailJSONView.as_view(), name='truck_detail_json'),

    # Drivers
    path('drivers/', views.DriverMasterView.as_view(), name='driver_master_sub'),
    path('drivers/create/', views.DriverCreateView.as_view(), name='driver_create_sub'),
    path('drivers/<int:pk>/edit/', views.DriverUpdateView.as_view(), name='driver_edit_sub'),
    path('drivers/<int:pk>/toggle/', views.DriverToggleActiveView.as_view(), name='driver_toggle_sub'),
    path('drivers/<int:pk>/detail-json/', views.DriverDetailJSONView.as_view(), name='driver_detail_json_sub'),

    # Expeditions
    path('expeditions/', views.ExpeditionMasterView.as_view(), name='expedition_master_sub'),
    path('expeditions/create/', views.ExpeditionCreateView.as_view(), name='expedition_create_sub'),
    path('expeditions/<int:pk>/edit/', views.ExpeditionUpdateView.as_view(), name='expedition_edit_sub'),
    path('expeditions/<int:pk>/toggle/', views.ExpeditionToggleActiveView.as_view(), name='expedition_toggle_sub'),
    path('expeditions/<int:pk>/detail-json/', views.ExpeditionDetailJSONView.as_view(), name='expedition_detail_json_sub'),

    # Containers
    path('containers/', views.ContainerMasterView.as_view(), name='container_master_sub'),
    path('containers/create/', views.ContainerCreateView.as_view(), name='container_create_sub'),
    path('containers/<int:pk>/edit/', views.ContainerUpdateView.as_view(), name='container_edit_sub'),
    path('containers/<int:pk>/toggle/', views.ContainerToggleActiveView.as_view(), name='container_toggle_sub'),
    path('containers/<int:pk>/detail-json/', views.ContainerDetailJSONView.as_view(), name='container_detail_json_sub'),
]
