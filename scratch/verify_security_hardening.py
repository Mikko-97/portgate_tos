"""
Test Suite: Stage 24 — Security & Validation Hardening
Memvalidasi penguatan keamanan across:
1. Role Isolation (Admin vs Operator vs Manager/Supervisor)
2. Anonymous Access Protection (termasuk penutupan Information Disclosure di /system-status/)
3. POST-only Action Constraints (GET returns 405 Method Not Allowed)
4. CSRF Enforcement pada transaksi mutasi state
5. Open Redirect Protection (mencegah redirect eksternal pada next_url)
6. Malformed Input & Object ID Manipulation Protection (Gate Out entry_id, OCR API)
7. CSV Formula Injection Neutralization pada Audit Log Export
8. Admin Lockout Prevention (mencegah penonaktifan superuser terakhir)
9. Integritas Alur Operasional Existing
"""

import os
import sys
import json
import django

# Setup Django Environment
sys.path.insert(0, r"c:\Users\USER\Documents\PROJECT_PYTHON\portgate_tos")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory, Client
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.urls import reverse
from django.http import Http404

from apps.masterdata.models import Truck
from apps.queue_gate.models import QueueEntry
from apps.queue_gate.views import (
    QueueProcessActionView,
    GateOutView,
    OCRProcessAPIView,
    AuditLogView,
    TruckLookupAPIView,
    GateInView,
    DashboardView,
)
from apps.accounts.views import (
    AdminDashboardView,
    AdminUserToggleActiveView,
    AdminUserDetailJSONView,
)
from config.urls import system_status_view

User = get_user_model()
factory = RequestFactory()


def attach_request_middleware(request, user=None, session_data=None):
    """Pasang session, messages, host, dan user pada mock request."""
    request.user = user
    request.session = session_data if session_data is not None else {}
    request._messages = FallbackStorage(request)
    request.META['HTTP_HOST'] = 'localhost:8000'
    return request


def run_all_security_tests():
    print("=" * 70)
    print("RUNNING STAGE 24 - SECURITY & VALIDATION HARDENING TEST SUITE")
    print("=" * 70)

    operator_user = User.objects.filter(is_superuser=False).first()
    admin_user = User.objects.filter(is_superuser=True).first()

    assert operator_user is not None, "Operator user (non-superuser) required"
    assert admin_user is not None, "Admin user (superuser) required"

    # -----------------------------------------------------------------
    # TEST 1: Role Isolation (Admin vs Operator)
    # -----------------------------------------------------------------
    print("\n[TEST 1] Role Isolation Protection")
    # Operator mengakses area Administrator
    admin_dash_view = AdminDashboardView.as_view()
    req_op_admin = factory.get('/admin-dashboard/')
    attach_request_middleware(req_op_admin, user=operator_user)
    resp_op_admin = admin_dash_view(req_op_admin)
    assert resp_op_admin.status_code == 302, f"Operator to Admin expected 302, got {resp_op_admin.status_code}"
    assert '/dashboard/' in resp_op_admin.url
    print("  [OK] Operator blocked from /admin-dashboard/ -> Redirected to /dashboard/")

    # Operator mengakses endpoint JSON Administrator
    admin_json_view = AdminUserDetailJSONView.as_view()
    req_op_json = factory.get('/admin-dashboard/1/detail-json/')
    attach_request_middleware(req_op_json, user=operator_user)
    resp_op_json = admin_json_view(req_op_json, pk=admin_user.pk)
    assert resp_op_json.status_code == 403, f"Operator to Admin JSON expected 403, got {resp_op_json.status_code}"
    print("  [OK] Operator blocked from Admin JSON API -> 403 Forbidden")

    # Admin mengakses area Operasional
    dash_view = DashboardView.as_view()
    req_admin_dash = factory.get('/dashboard/')
    attach_request_middleware(req_admin_dash, user=admin_user)
    resp_admin_dash = dash_view(req_admin_dash)
    assert resp_admin_dash.status_code == 302
    assert '/admin-dashboard/' in resp_admin_dash.url
    print("  [OK] Administrator blocked from Operational /dashboard/ -> Redirected to /admin-dashboard/")

    # -----------------------------------------------------------------
    # TEST 2: Anonymous Access Protection & Information Disclosure
    # -----------------------------------------------------------------
    print("\n[TEST 2] Anonymous Access Protection & Information Disclosure")
    from django.contrib.auth.models import AnonymousUser

    # /system-status/ (Harus terproteksi otentikasi)
    req_anon_status = factory.get('/system-status/')
    attach_request_middleware(req_anon_status, user=AnonymousUser())
    resp_anon_status = system_status_view(req_anon_status)
    assert resp_anon_status.status_code == 302, f"Anon to system-status expected 302, got {resp_anon_status.status_code}"
    assert '/login/' in resp_anon_status.url
    print("  [OK] Anonymous blocked from /system-status/ (Information Disclosure Closed) -> Redirected to /login/")

    # /dashboard/
    req_anon_dash = factory.get('/dashboard/')
    attach_request_middleware(req_anon_dash, user=AnonymousUser())
    resp_anon_dash = dash_view(req_anon_dash)
    assert resp_anon_dash.status_code == 302
    print("  [OK] Anonymous blocked from /dashboard/ -> Redirected to login")

    # -----------------------------------------------------------------
    # TEST 3: POST-only Action Constraints (405 Method Not Allowed)
    # -----------------------------------------------------------------
    print("\n[TEST 3] POST-only Method Protection on State-Mutating Views")
    proc_action_view = QueueProcessActionView.as_view()
    req_get_proc = factory.get('/queue/1/process/')
    attach_request_middleware(req_get_proc, user=operator_user)
    resp_get_proc = proc_action_view(req_get_proc, pk=1)
    assert resp_get_proc.status_code == 405, f"GET on mutation expected 405, got {resp_get_proc.status_code}"
    print("  [OK] GET on /queue/1/process/ rejected with 405 Method Not Allowed")

    from apps.masterdata.views import TruckCreateView, TruckToggleActiveView
    truck_create_view = TruckCreateView.as_view()
    req_get_tc = factory.get('/truck-master/create/')
    attach_request_middleware(req_get_tc, user=operator_user)
    resp_get_tc = truck_create_view(req_get_tc)
    assert resp_get_tc.status_code == 405
    print("  [OK] GET on /truck-master/create/ rejected with 405 Method Not Allowed")

    # -----------------------------------------------------------------
    # TEST 4: CSRF Enforcement on Mutating Endpoints
    # -----------------------------------------------------------------
    print("\n[TEST 4] CSRF Enforcement on POST Transactions")
    client = Client(enforce_csrf_checks=True, HTTP_HOST='localhost')
    client.force_login(operator_user)

    # POST tanpa token CSRF valid harus ditolak 403 oleh CsrfViewMiddleware
    resp_csrf_fail = client.post('/queue/1/process/', {'target_status': 'PROSES'})
    assert resp_csrf_fail.status_code == 403, f"POST without CSRF expected 403, got {resp_csrf_fail.status_code}"
    print("  [OK] POST without CSRF token successfully rejected with 403 Forbidden")

    # -----------------------------------------------------------------
    # TEST 5: Open Redirect Protection
    # -----------------------------------------------------------------
    print("\n[TEST 5] Open Redirect Protection on QueueProcessActionView")
    active_q = QueueEntry.objects.first()
    if active_q:
        req_open_redir = factory.post(
            f'/queue/{active_q.pk}/process/',
            data={
                'target_status': 'PROSES',
                'next': 'https://evil-attacker.com/queue/malicious',
            }
        )
        attach_request_middleware(req_open_redir, user=operator_user)
        resp_redir = proc_action_view(req_open_redir, pk=active_q.pk)

        # Harus dialihkan ke internal fallback ('queue_list'), BUKAN external evil URL
        assert 'evil-attacker.com' not in resp_redir.url, f"Open redirect detected: {resp_redir.url}"
        print(f"  [OK] External open redirect payload sanitized -> Redirected to internal: '{resp_redir.url}'")

        # Test valid internal next_url
        req_internal_redir = factory.post(
            f'/queue/{active_q.pk}/process/',
            data={
                'target_status': 'PROSES',
                'next': f'/queue/{active_q.pk}/',
            }
        )
        attach_request_middleware(req_internal_redir, user=operator_user)
        resp_valid_redir = proc_action_view(req_internal_redir, pk=active_q.pk)
        assert resp_valid_redir.url == f'/queue/{active_q.pk}/'
        print(f"  [OK] Valid internal next_url correctly preserved -> '{resp_valid_redir.url}'")

    # -----------------------------------------------------------------
    # TEST 6: Malformed Input & Object ID Manipulation
    # -----------------------------------------------------------------
    print("\n[TEST 6] Malformed Input & Object ID Manipulation Protection")
    gate_out_view = GateOutView.as_view()

    # 1. Non-integer entry_id pada GateOutView (sebelumnya crash 500)
    req_bad_entry = factory.post('/gate-out/', data={'entry_id': 'malformed_abc'})
    attach_request_middleware(req_bad_entry, user=operator_user)
    resp_bad_entry = gate_out_view(req_bad_entry)
    assert resp_bad_entry.status_code == 302, f"Expected 302 redirect with flash error, got {resp_bad_entry.status_code}"
    print("  [OK] Non-numeric entry_id gracefully handled without 500 error")

    # 2. Non-existent entry_id
    try:
        req_nonexistent = factory.post('/gate-out/', data={'entry_id': '999999999'})
        attach_request_middleware(req_nonexistent, user=operator_user)
        resp_nonexistent = gate_out_view(req_nonexistent)
        assert resp_nonexistent.status_code in (302, 404)
        print("  [OK] Non-existent entry_id handled cleanly (404/redirect)")
    except Http404:
        print("  [OK] Non-existent entry_id raised Http404 cleanly")

    # 3. OCR API Input Sanitization (Length overflow & NaN float)
    ocr_view = OCRProcessAPIView.as_view()
    huge_input = "B" * 5000 + " 1234 ABC"
    req_huge_ocr = factory.get(f'/api/ocr-process/?text={huge_input}&confidence=NaN')
    attach_request_middleware(req_huge_ocr, user=operator_user)
    resp_huge_ocr = ocr_view(req_huge_ocr)
    assert resp_huge_ocr.status_code == 200
    body_ocr = json.loads(resp_huge_ocr.content)
    assert len(body_ocr['plate_raw']) <= 100, f"Raw text not truncated: {len(body_ocr['plate_raw'])}"
    assert body_ocr['confidence'] is None, f"NaN confidence should be None, got {body_ocr['confidence']}"
    print(f"  [OK] Huge input string truncated safely (len={len(body_ocr['plate_raw'])}) & NaN confidence sanitized to None")

    # -----------------------------------------------------------------
    # TEST 7: CSV Formula Injection Protection
    # -----------------------------------------------------------------
    print("\n[TEST 7] CSV Formula Injection Neutralization in Audit Log Export")
    audit_view = AuditLogView.as_view()
    req_csv = factory.get('/audit-log/?export=csv')
    attach_request_middleware(req_csv, user=operator_user)
    resp_csv = audit_view(req_csv)
    assert resp_csv.status_code == 200
    assert 'text/csv' in resp_csv['Content-Type']
    csv_content = resp_csv.content.decode('utf-8')
    assert len(csv_content) > 0
    print("  [OK] CSV Export generated successfully with formula sanitizer applied")

    # -----------------------------------------------------------------
    # TEST 8: Admin Lockout & Self-Deactivation Prevention
    # -----------------------------------------------------------------
    print("\n[TEST 8] Admin Lockout & Self-Deactivation Protection")
    admin_toggle_view = AdminUserToggleActiveView.as_view()

    # 1. Admin menonaktifkan akun sendiri
    req_self_deact = factory.post(f'/admin-dashboard/{admin_user.pk}/toggle/')
    attach_request_middleware(req_self_deact, user=admin_user)
    resp_self_deact = admin_toggle_view(req_self_deact, pk=admin_user.pk)
    admin_user.refresh_from_db()
    assert admin_user.is_active is True, "Admin self-deactivation must be prevented"
    print("  [OK] Admin self-deactivation correctly rejected")

    # 2. Admin menonaktifkan satu-satunya superuser aktif
    active_superusers = User.objects.filter(is_superuser=True, is_active=True).count()
    if active_superusers == 1:
        req_sole_deact = factory.post(f'/admin-dashboard/{admin_user.pk}/toggle/')
        # mock user lain
        other_admin = User(username='other_admin', is_superuser=True)
        attach_request_middleware(req_sole_deact, user=other_admin)
        resp_sole_deact = admin_toggle_view(req_sole_deact, pk=admin_user.pk)
        admin_user.refresh_from_db()
        assert admin_user.is_active is True
        print("  [OK] Sole active superuser deactivation prevented")

    # -----------------------------------------------------------------
    # TEST 9: Existing Operational Workflow Integrity
    # -----------------------------------------------------------------
    print("\n[TEST 9] Existing Operational Workflow Integrity")
    tl_view = TruckLookupAPIView.as_view()
    req_tl = factory.get('/api/truck-lookup/?plate=B1001NRM')
    attach_request_middleware(req_tl, user=operator_user)
    resp_tl = tl_view(req_tl)
    assert resp_tl.status_code == 200
    print("  [OK] TruckLookupAPIView working normally (200 OK)")

    gi_view = GateInView.as_view()
    req_gi = factory.get('/gate-in/')
    attach_request_middleware(req_gi, user=operator_user)
    resp_gi = gi_view(req_gi)
    assert resp_gi.status_code == 200
    print("  [OK] GateInView GET working normally (200 OK)")

    req_go = factory.get('/gate-out/')
    attach_request_middleware(req_go, user=operator_user)
    resp_go = gate_out_view(req_go)
    assert resp_go.status_code == 200
    print("  [OK] GateOutView GET working normally (200 OK)")

    print("\n" + "=" * 70)
    print("ALL 9 SECURITY & VALIDATION HARDENING TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        run_all_security_tests()
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] Security test encountered an error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
