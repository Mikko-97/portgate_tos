from django.urls import path
from . import views

urlpatterns = [
    # Autentikasi
    path('login/', views.TOSLoginView.as_view(), name='login'),
    path('logout/', views.TOSLogoutView.as_view(), name='logout'),

    # Admin Dashboard - Manajemen Akun (Port Gate TOS)
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('admin-dashboard/create/', views.AdminUserCreateView.as_view(), name='admin_user_create'),
    path('admin-dashboard/<int:pk>/edit/', views.AdminUserUpdateView.as_view(), name='admin_user_edit'),
    path('admin-dashboard/<int:pk>/toggle/', views.AdminUserToggleActiveView.as_view(), name='admin_user_toggle'),
    path('admin-dashboard/<int:pk>/detail-json/', views.AdminUserDetailJSONView.as_view(), name='admin_user_detail_json'),
]
