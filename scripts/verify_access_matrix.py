"""
Script Verifikasi Akses Matriks & Role Isolation Port Gate TOS.
Menguji isolasi hak akses antara Administrator dan Operator sesuai spesifikasi:
- Anonim vs Operator vs Administrator
- HTTP Status Code & Redirect Target
- Flash Messages yang tepat
- Rendering menu navigasi pada sidebar
"""

import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

from django.test import Client
from django.contrib.auth.models import User, Group
from django.contrib.messages import get_messages
from apps.accounts.models import OperatorProfile, BoothChoice, ShiftChoice


def run_matrix_tests():
    print("==================================================================")
    print("MEMULAI PENGUJIAN MATRIKS AKSES & ROLE ISOLATION PORT GATE TOS")
    print("==================================================================")

    # 1. Setup Data Uji (User & Group)
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    operator_group, _ = Group.objects.get_or_create(name='Operator')

    # Buat atau reset user operator uji
    op_user, _ = User.objects.get_or_create(username='op_tester', defaults={'first_name': 'Tester', 'last_name': 'Operator'})
    op_user.is_superuser = False
    op_user.is_staff = False
    op_user.set_password('pass1234')
    op_user.save()
    op_user.groups.clear()
    op_user.groups.add(operator_group)

    # Buat atau reset user admin uji (Group Admin & Non-Superuser untuk memastikan group check)
    adm_user, _ = User.objects.get_or_create(username='adm_tester', defaults={'first_name': 'Tester', 'last_name': 'Admin'})
    adm_user.is_superuser = False
    adm_user.is_staff = True
    adm_user.set_password('pass1234')
    adm_user.save()
    adm_user.groups.clear()
    adm_user.groups.add(admin_group)

    # Superuser admin
    super_user, _ = User.objects.get_or_create(username='super_tester', defaults={'first_name': 'Super', 'last_name': 'User'})
    super_user.is_superuser = True
    super_user.is_staff = True
    super_user.set_password('pass1234')
    super_user.save()

    try:
        # -----------------------------------------------------------------
        # TEST SUITE 1: Matriks Akses Anonim (Unauthenticated)
        # -----------------------------------------------------------------
        print("\n--- TEST SUITE 1: PENGUJIAN PENGGUNA ANONIM ---")
        anon_client = Client()

        anon_cases = [
            ('/login/', 200, None),
            ('/', 302, '/login/'),
            ('/dashboard/', 302, '/login/?next=/dashboard/'),
            ('/queue/', 302, '/login/?next=/queue/'),
            ('/gate-in/', 302, '/login/?next=/gate-in/'),
            ('/gate-cockpit/', 302, '/login/?next=/gate-cockpit/'),
            ('/truck-master/', 302, '/login/?next=/truck-master/'),
            ('/audit-log/', 302, '/login/?next=/audit-log/'),
            ('/ocr-settings/', 302, '/login/?next=/ocr-settings/'),
            ('/admin-dashboard/', 302, '/login/?next=/admin-dashboard/'),
        ]

        for url, expected_status, expected_redirect in anon_cases:
            resp = anon_client.get(url)
            assert resp.status_code == expected_status, f"[ANON] {url} -> Got {resp.status_code}, expected {expected_status}"
            if expected_redirect:
                actual_redirect = resp.headers.get('Location')
                assert actual_redirect == expected_redirect, f"[ANON] {url} redirect -> Got {actual_redirect}, expected {expected_redirect}"
            print(f"  ✓ ANON {url:<20} -> {resp.status_code} (Redirect: {expected_redirect or 'None'})")

        # -----------------------------------------------------------------
        # TEST SUITE 2: Matriks Akses OPERATOR
        # -----------------------------------------------------------------
        print("\n--- TEST SUITE 2: PENGUJIAN PENGGUNA OPERATOR ---")
        op_client = Client()
        op_client.force_login(op_user)

        # Login endpoint saat sudah login -> redirect ke dashboard
        resp = op_client.get('/login/')
        assert resp.status_code == 302, f"[OPERATOR] /login/ -> Got {resp.status_code}, expected 302"
        assert resp.headers.get('Location') == '/dashboard/', f"[OPERATOR] /login/ redirect -> Got {resp.headers.get('Location')}"
        print(f"  ✓ OPERATOR /login/             -> 302 (Redirect: /dashboard/)")

        # Root route '/' saat sudah login sebagai operator -> redirect ke /dashboard/
        resp = op_client.get('/')
        assert resp.status_code == 302
        assert resp.headers.get('Location') == '/dashboard/'
        print(f"  ✓ OPERATOR /                   -> 302 (Redirect: /dashboard/)")

        # Operational views -> 200 OK
        op_accessible_urls = [
            '/dashboard/',
            '/queue/',
            '/gate-in/',
            '/gate-cockpit/',
            '/truck-master/',
            '/audit-log/',
            '/ocr-settings/',
        ]
        for url in op_accessible_urls:
            resp = op_client.get(url)
            assert resp.status_code == 200, f"[OPERATOR] {url} -> Got {resp.status_code}, expected 200"
            print(f"  ✓ OPERATOR {url:<20} -> 200 OK")

        # Operator mencoba akses Admin Dashboard -> DENY (302 ke /dashboard/ dengan pesan error)
        admin_restricted_urls = [
            '/admin-dashboard/',
            '/admin-dashboard/1/detail-json/',
        ]
        for url in admin_restricted_urls:
            resp = op_client.get(url)
            assert resp.status_code in [302, 403], f"[OPERATOR] {url} -> Expected DENY (302/403), got {resp.status_code}"
            if resp.status_code == 302:
                assert resp.headers.get('Location') == '/dashboard/', f"[OPERATOR] {url} redirect -> Got {resp.headers.get('Location')}"
            print(f"  ✓ OPERATOR {url:<20} -> DENY ({resp.status_code})")

        # Verifikasi pesan penolakan operator
        resp = op_client.get('/admin-dashboard/', follow=True)
        messages = [m.message for m in get_messages(resp.wsgi_request)]
        assert any("Akses ditolak: area administrator." in m for m in messages), f"Pesan penolakan tidak sesuai: {messages}"
        print(f"  ✓ Pesan penolakan operator terverifikasi: 'Akses ditolak: area administrator.'")

        # Verifikasi sidebar operator TIDAK merender Manajemen Akun maupun Django Admin
        content = resp.content.decode('utf-8')
        assert "Manajemen Akun" not in content, "Operator TIDAK boleh melihat Manajemen Akun di sidebar!"
        assert "admin_dashboard" not in content, "Operator TIDAK boleh memiliki link admin_dashboard!"
        assert "/admin/" not in content, "Operator TIDAK boleh melihat link Django Admin!"
        print(f"  ✓ Sidebar Operator terverifikasi bersih dari menu Admin.")

        # -----------------------------------------------------------------
        # TEST SUITE 3: Matriks Akses ADMINISTRATOR (Group 'Admin')
        # -----------------------------------------------------------------
        print("\n--- TEST SUITE 3: PENGUJIAN PENGGUNA ADMINISTRATOR ---")
        adm_client = Client()
        adm_client.force_login(adm_user)

        # Login endpoint saat sudah login -> redirect ke /admin-dashboard/
        resp = adm_client.get('/login/')
        assert resp.status_code == 302, f"[ADMIN] /login/ -> Got {resp.status_code}, expected 302"
        assert resp.headers.get('Location') == '/admin-dashboard/', f"[ADMIN] /login/ redirect -> Got {resp.headers.get('Location')}"
        print(f"  ✓ ADMIN /login/                -> 302 (Redirect: /admin-dashboard/)")

        # Root route '/' saat sudah login sebagai admin -> redirect ke /admin-dashboard/
        resp = adm_client.get('/')
        assert resp.status_code == 302
        assert resp.headers.get('Location') == '/admin-dashboard/'
        print(f"  ✓ ADMIN /                      -> 302 (Redirect: /admin-dashboard/)")

        # Admin Dashboard -> 200 OK
        resp = adm_client.get('/admin-dashboard/')
        assert resp.status_code == 200, f"[ADMIN] /admin-dashboard/ -> Got {resp.status_code}, expected 200"
        print(f"  ✓ ADMIN /admin-dashboard/      -> 200 OK")

        # Admin mencoba akses area operasional -> DENY (302 ke /admin-dashboard/ dengan pesan peringatan)
        op_forbidden_for_admin = [
            '/dashboard/',
            '/queue/',
            '/gate-in/',
            '/gate-cockpit/',
            '/truck-master/',
            '/audit-log/',
            '/ocr-settings/',
        ]
        for url in op_forbidden_for_admin:
            resp = adm_client.get(url)
            assert resp.status_code == 302, f"[ADMIN] {url} -> Expected DENY (302), got {resp.status_code}"
            assert resp.headers.get('Location') == '/admin-dashboard/', f"[ADMIN] {url} redirect -> Got {resp.headers.get('Location')}"
            print(f"  ✓ ADMIN {url:<22} -> DENY (302 -> /admin-dashboard/)")

        # Verifikasi pesan penolakan operasional untuk admin
        resp = adm_client.get('/queue/', follow=True)
        messages = [m.message for m in get_messages(resp.wsgi_request)]
        assert any("Akses area operasional tidak tersedia untuk akun Administrator." in m for m in messages), f"Pesan penolakan tidak sesuai: {messages}"
        print(f"  ✓ Pesan penolakan admin terverifikasi: 'Akses area operasional tidak tersedia untuk akun Administrator.'")

        # Verifikasi sidebar admin HANYA merender Account Management dan TIDAK merender menu operasional
        content = resp.content.decode('utf-8')
        assert "Account Management" in content, "Admin HARUS melihat Account Management di sidebar!"
        assert "Dashboard Overview" not in content, "Admin TIDAK boleh melihat Dashboard Overview di sidebar!"
        assert "Antrian &amp; Gate In/Out" not in content, "Admin TIDAK boleh melihat Antrian di sidebar!"
        assert "Data Truk &amp; CMS" not in content, "Admin TIDAK boleh melihat Data Truk di sidebar!"
        assert "Riwayat &amp; Audit Log" not in content, "Admin TIDAK boleh melihat Riwayat di sidebar!"
        assert "Konfigurasi OCR" not in content, "Admin TIDAK boleh melihat Konfigurasi OCR di sidebar!"
        print(f"  ✓ Sidebar Admin terverifikasi HANYA menampilkan Account Management dan bersih dari menu operasional.")

        # -----------------------------------------------------------------
        # TEST SUITE 4: Matriks Akses SUPERUSER (Admin Penuh)
        # -----------------------------------------------------------------
        print("\n--- TEST SUITE 4: PENGUJIAN PENGGUNA SUPERUSER ---")
        sup_client = Client()
        sup_client.force_login(super_user)

        resp = sup_client.get('/login/')
        assert resp.status_code == 302
        assert resp.headers.get('Location') == '/admin-dashboard/'
        print(f"  ✓ SUPERUSER /login/            -> 302 (Redirect: /admin-dashboard/)")

        resp = sup_client.get('/admin-dashboard/')
        assert resp.status_code == 200
        print(f"  ✓ SUPERUSER /admin-dashboard/  -> 200 OK")

        resp = sup_client.get('/dashboard/')
        assert resp.status_code == 302
        assert resp.headers.get('Location') == '/admin-dashboard/'
        print(f"  ✓ SUPERUSER /dashboard/        -> DENY (302 -> /admin-dashboard/)")

    finally:
        # Bersihkan data uji
        print("\n[CLEANUP] Membersihkan data pengguna uji...")
        op_user.delete()
        adm_user.delete()
        super_user.delete()
        print("[CLEANUP] Data pengguna uji berhasil dibersihkan.")

    print("\n==================================================================")
    print("SELURUH PENGUJIAN MATRIKS AKSES & ROLE ISOLATION BERHASIL 100%!")
    print("==================================================================")


if __name__ == '__main__':
    run_matrix_tests()
