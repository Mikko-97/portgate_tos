"""
Mixins dan Helper Otorisasi Berbasis Peran (Role Isolation) Port Gate TOS.
Memisahkan hak akses Administrator (manajemen akun) dan Operator (operasional gate/antrian).
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.http import JsonResponse


def is_admin_user(user):
    """
    Mendeteksi apakah pengguna memiliki peran Administrator.
    Berdasarkan: superuser atau anggota Group Django 'Admin'.
    Catatan: is_staff=True saja TIDAK memberikan hak akses Admin TOS kecuali berstatus superuser
    atau terdaftar di group 'Admin'.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__iexact='Admin').exists()


def is_operator_user(user):
    """
    Mendeteksi apakah pengguna adalah staf operasional gerbang.
    Administrator BUKAN operator operasional.
    """
    if not user or not user.is_authenticated:
        return False
    return not is_admin_user(user)


def get_user_role(user):
    """
    Helper untuk mendeteksi peran primer pengguna berdasarkan Django Group & Flag.
    Prioritas: Admin > Manager > Supervisor > Operator.
    """
    if not user or not user.is_authenticated:
        return 'Anonymous'
    group_names = [g.name for g in user.groups.all()]
    if 'Admin' in group_names or user.is_superuser:
        return 'Admin'
    elif 'Manager' in group_names:
        return 'Manager'
    elif 'Supervisor' in group_names:
        return 'Supervisor'
    elif 'Operator' in group_names:
        return 'Operator'
    elif user.is_staff:
        return 'Admin'
    return 'Operator'


class AdminAccessRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Memastikan hanya pengguna terautentikasi dengan hak Administrator (superuser / Group Admin)
    yang dapat mengakses Admin Dashboard dan endpoint manajemen akun.
    
    Operator biasa yang mencoba mengakses akan DITOLAK (DENY) dan dialihkan ke /dashboard/
    dengan pesan error: "Akses ditolak: area administrator."
    """
    def test_func(self):
        return is_admin_user(self.request.user)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        # Respon khusus untuk panggilan API / JSON / AJAX
        if (self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
                'detail-json' in self.request.path or 
                self.request.path.startswith('/api/')):
            return JsonResponse({
                'success': False,
                'error': 'Akses ditolak: area administrator.',
                'redirect': '/dashboard/'
            }, status=403)

        messages.error(
            self.request,
            "Akses ditolak: area administrator."
        )
        return redirect('dashboard')


class OperationalAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Memastikan hanya staf operasional (bukan Administrator) yang dapat mengakses area operasional
    seperti Dashboard, Queue, Gate In, Gate Cockpit, Truck Master, Audit Log, dan OCR Settings.
    
    Administrator yang mencoba mengakses area operasional akan DITOLAK (DENY) dan dialihkan ke
    /admin-dashboard/ dengan pesan peringatan:
    "Akses area operasional tidak tersedia untuk akun Administrator."
    """
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        # Administrator TIDAK boleh mengakses area operasional
        return not is_admin_user(user)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        # Respon khusus untuk panggilan API / AJAX
        if (self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
                self.request.path.startswith('/api/') or 
                'detail-json' in self.request.path):
            return JsonResponse({
                'success': False,
                'error': 'Akses area operasional tidak tersedia untuk akun Administrator.',
                'redirect': '/admin-dashboard/'
            }, status=403)

        messages.warning(
            self.request,
            "Akses area operasional tidak tersedia untuk akun Administrator."
        )
        return redirect('admin_dashboard')
