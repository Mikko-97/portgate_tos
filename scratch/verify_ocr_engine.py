"""
Test Suite: OCR Engine Integration
Memvalidasi fungsionalitas pemrosesan OCR, normalisasi nomor polisi, lookup armada,
evaluasi ambang batas keyakinan (confidence threshold), dan proteksi role isolation pada endpoint API.
"""

import os
import sys
import json
import django

# Setup Django Environment
sys.path.insert(0, r"c:\Users\USER\Documents\PROJECT_PYTHON\portgate_tos")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.urls import reverse

from apps.masterdata.models import Truck
from apps.queue_gate.models import QueueEntry
from apps.queue_gate.ocr_service import (
    clean_ocr_text,
    normalize_license_plate,
    lookup_truck_by_plate,
    process_ocr_plate,
    ExternalOCREngine,
    BaseOCREngine,
    OCRResult,
    DEFAULT_OCR_CONFIG,
)
from apps.queue_gate.views import OCRProcessAPIView

User = get_user_model()
factory = RequestFactory()


def attach_request_middleware(request, user=None, session_data=None):
    """Pasang session, messages, host, dan user pada mock request."""
    request.user = user
    request.session = session_data if session_data is not None else {}
    request._messages = FallbackStorage(request)
    request.META['HTTP_HOST'] = 'localhost:8000'
    return request


def run_all_tests():
    print("=" * 65)
    print("RUNNING OCR ENGINE INTEGRATION TEST SUITE")
    print("=" * 65)

    # -------------------------------------------------------------
    # TEST 1: OCR Text Normal
    # -------------------------------------------------------------
    print("\n[TEST 1] OCR Text Normal Processing")
    raw_plate_1 = "B 1234 ABC"
    res_1 = process_ocr_plate(raw_plate_1)
    assert res_1.plate_raw == "B 1234 ABC", f"Raw mismatch: {res_1.plate_raw}"
    assert res_1.plate_normalized == "B 1234 ABC", f"Norm mismatch: {res_1.plate_normalized}"
    assert res_1.is_valid_format is True, "Format should be valid"
    assert res_1.engine_name == "ExternalOCREngine", "Engine should be ExternalOCREngine"
    print(f"  [OK] Processed normal plate: '{res_1.plate_raw}' -> '{res_1.plate_normalized}'")

    raw_plate_2 = "B 9876 XYZ"
    res_2 = process_ocr_plate(raw_plate_2)
    assert res_2.plate_normalized == "B 9876 XYZ"
    assert res_2.is_valid_format is True
    print(f"  [OK] Processed second plate: '{res_2.plate_raw}' -> '{res_2.plate_normalized}'")

    # -------------------------------------------------------------
    # TEST 2: OCR Text dengan Whitespace & Noise Karakter
    # -------------------------------------------------------------
    print("\n[TEST 2] OCR Text dengan Whitespace & Noise")
    noise_samples = [
        ("[B-1234-ABC]", "B 1234 ABC"),
        ("\n\t  b.1234.abc  \r\n", "B 1234 ABC"),
        ("| B 1234 ABC |", "B 1234 ABC"),
        ("--B-1234-ABC--", "B 1234 ABC"),
        ("{B 1234 ABC}", "B 1234 ABC"),
        ("#B 9876 XYZ*", "B 9876 XYZ"),
        ("~`b_9876_xyz`~", "B 9876 XYZ"),
    ]

    for noisy_input, expected_normalized in noise_samples:
        cleaned = clean_ocr_text(noisy_input)
        normalized = normalize_license_plate(cleaned)
        assert normalized == expected_normalized, f"Failed for '{noisy_input}': got '{normalized}', expected '{expected_normalized}'"
        
        # Test via service entry point
        res_noise = process_ocr_plate(noisy_input)
        assert res_noise.plate_normalized == expected_normalized
        assert res_noise.is_valid_format is True
        print(f"  [OK] Noise cleaned: '{noisy_input}' -> '{res_noise.plate_normalized}'")

    # -------------------------------------------------------------
    # TEST 3: Normalisasi Nomor Polisi Indonesia
    # -------------------------------------------------------------
    print("\n[TEST 3] Normalisasi Nomor Polisi Standar Indonesia")
    patterns = [
        ("B1234ABC", "B 1234 ABC"),
        ("b1234abc", "B 1234 ABC"),
        ("BK555AA", "BK 555 AA"),
        ("bk 555 aa", "BK 555 AA"),
        ("D9876XYZ", "D 9876 XYZ"),
        ("B1234", "B 1234"),
        ("L 1 A", "L 1 A"),
        ("B 1001 NRM", "B 1001 NRM"),
    ]

    for raw, expected in patterns:
        norm = normalize_license_plate(clean_ocr_text(raw))
        assert norm == expected, f"Normalization mismatch for '{raw}': got '{norm}', expected '{expected}'"
        print(f"  [OK] Normalized format: '{raw}' -> '{norm}'")

    # -------------------------------------------------------------
    # TEST 4: Plate Ditemukan di Truck Master
    # -------------------------------------------------------------
    print("\n[TEST 4] Plate Ditemukan di Truck Master (Real Database)")
    # Ambil sample truck dari database
    existing_truck = Truck.objects.filter(is_active=True).first()
    assert existing_truck is not None, "At least one active truck must exist in DB for test"

    truck_plate = existing_truck.no_polisi
    # Beri sedikit noise untuk simulasi pembacaan kamera
    camera_read = f"[{truck_plate}]"
    res_found = process_ocr_plate(camera_read)

    assert res_found.found is True, f"Truck '{truck_plate}' should be found"
    assert res_found.truck is not None, "Truck data dictionary should not be None"
    assert res_found.truck['no_polisi'] == truck_plate, f"Plate mismatch: {res_found.truck['no_polisi']} vs {truck_plate}"
    assert 'expedisi' in res_found.truck
    assert 'driver' in res_found.truck
    assert res_found.plate_normalized == truck_plate
    print(f"  [OK] Found Truck in DB: [{res_found.truck['no_polisi']}]")
    print(f"       Ekspedisi: {res_found.truck['expedisi']['nama_perusahaan'] if res_found.truck['expedisi'] else '-'}")
    print(f"       Konfigurasi: {res_found.truck['konfigurasi_display']}")

    # -------------------------------------------------------------
    # TEST 5: Plate Tidak Ditemukan
    # -------------------------------------------------------------
    print("\n[TEST 5] Plate Tidak Ditemukan di Truck Master")
    unknown_plate = "Z 9999 NON"
    res_not_found = process_ocr_plate(unknown_plate)

    assert res_not_found.found is False, "Unknown plate must return found=False"
    assert res_not_found.truck is None, "Unknown plate truck must be None"
    assert res_not_found.plate_normalized == "Z 9999 NON"
    assert res_not_found.is_valid_format is True
    assert "tidak terdaftar" in res_not_found.message
    print(f"  [OK] Unknown plate gracefully handled: found={res_not_found.found}, message='{res_not_found.message}'")

    # -------------------------------------------------------------
    # TEST 6: OCR Confidence & Session Threshold Integration
    # -------------------------------------------------------------
    print("\n[TEST 6] OCR Confidence & Threshold Integration")
    # Default threshold adalah 95%
    res_high_conf = process_ocr_plate("B 1234 ABC", confidence=98.5)
    assert res_high_conf.confidence == 98.5
    assert res_high_conf.confidence_threshold == 95
    assert res_high_conf.confidence_passed is True, "98.5% should pass 95% threshold"
    print(f"  [OK] Confidence 98.5% >= 95% threshold: passed={res_high_conf.confidence_passed}")

    res_low_conf = process_ocr_plate("B 1234 ABC", confidence=88.0)
    assert res_low_conf.confidence == 88.0
    assert res_low_conf.confidence_threshold == 95
    assert res_low_conf.confidence_passed is False, "88.0% should fail 95% threshold"
    print(f"  [OK] Confidence 88.0% < 95% threshold: passed={res_low_conf.confidence_passed}")

    # Menggunakan konfigurasi session kustom (misal disetel di OCR Settings = 85%)
    custom_session = {'ocr_config': {'ocr_confidence': 85, 'wim_tolerance': 4, 'auto_open_barrier': True}}
    req_custom = factory.get('/api/ocr-process/?text=B1234ABC')
    attach_request_middleware(req_custom, session_data=custom_session)

    res_session_conf = process_ocr_plate("B 1234 ABC", confidence=88.0, request=req_custom)
    assert res_session_conf.confidence_threshold == 85
    assert res_session_conf.confidence_passed is True, "88.0% should pass custom 85% session threshold"
    print(f"  [OK] Custom session threshold (85%): 88.0% passed={res_session_conf.confidence_passed}")

    # Confidence None (pass through)
    res_none_conf = process_ocr_plate("B 1234 ABC", confidence=None)
    assert res_none_conf.confidence is None
    assert res_none_conf.confidence_passed is True
    print(f"  [OK] No confidence provided: passed={res_none_conf.confidence_passed}")

    # -------------------------------------------------------------
    # TEST 7: Role Isolation & API Endpoint Access
    # -------------------------------------------------------------
    print("\n[TEST 7] Role Isolation & API Endpoint (/api/ocr-process/)")
    operator_user = User.objects.filter(is_superuser=False).first()
    admin_user = User.objects.filter(is_superuser=True).first()

    assert operator_user is not None, "Operator user (non-superuser) required"
    assert admin_user is not None, "Admin user (superuser) required"

    api_view = OCRProcessAPIView.as_view()

    # 1. Akses oleh Operator (GET)
    req_op_get = factory.get('/api/ocr-process/?text=%5BB-1234-ABC%5D&confidence=96.2')
    attach_request_middleware(req_op_get, user=operator_user)
    resp_op_get = api_view(req_op_get)

    assert resp_op_get.status_code == 200, f"Operator GET expected 200, got {resp_op_get.status_code}"
    body_get = json.loads(resp_op_get.content)
    assert body_get['status'] == 'success'
    assert body_get['plate_raw'] == '[B-1234-ABC]'
    assert body_get['plate_normalized'] == 'B 1234 ABC'
    assert body_get['confidence'] == 96.2
    assert body_get['confidence_passed'] is True
    print(f"  [OK] Operator GET access returned 200 with structured JSON: status='{body_get['status']}'")

    # 2. Akses oleh Operator (POST JSON)
    post_payload = json.dumps({'text': truck_plate, 'confidence': 97.0})
    req_op_post = factory.post('/api/ocr-process/', data=post_payload, content_type='application/json')
    attach_request_middleware(req_op_post, user=operator_user)
    resp_op_post = api_view(req_op_post)

    assert resp_op_post.status_code == 200, f"Operator POST expected 200, got {resp_op_post.status_code}"
    body_post = json.loads(resp_op_post.content)
    assert body_post['status'] == 'success'
    assert body_post['found'] is True
    assert body_post['truck']['no_polisi'] == truck_plate
    print(f"  [OK] Operator POST JSON access returned 200 with truck data found=True")

    # 3. Akses input kosong (Validation Error)
    req_empty = factory.get('/api/ocr-process/?text=')
    attach_request_middleware(req_empty, user=operator_user)
    resp_empty = api_view(req_empty)
    assert resp_empty.status_code == 400
    body_empty = json.loads(resp_empty.content)
    assert body_empty['status'] == 'error'
    print(f"  [OK] Empty input returns 400 with message: '{body_empty['message']}'")

    # 4. Akses oleh Admin/Superuser (Harus DITOLAK oleh OperationalAccessMixin)
    # Khusus endpoint /api/, OperationalAccessMixin mengembalikan 403 JSON dengan pointer redirect
    req_admin = factory.get('/api/ocr-process/?text=B1234ABC')
    attach_request_middleware(req_admin, user=admin_user)
    resp_admin = api_view(req_admin)
    assert resp_admin.status_code == 403, f"Admin API expected 403, got {resp_admin.status_code}"
    admin_body = json.loads(resp_admin.content)
    assert admin_body['success'] is False
    assert admin_body['redirect'] == '/admin-dashboard/'
    print(f"  [OK] Admin correctly denied (403 JSON) on operational API: redirect='{admin_body['redirect']}'")

    # 5. Akses oleh Anonymous (Harus dialihkan ke Login)
    from django.contrib.auth.models import AnonymousUser
    req_anon = factory.get('/api/ocr-process/?text=B1234ABC')
    attach_request_middleware(req_anon, user=AnonymousUser())
    resp_anon = api_view(req_anon)
    assert resp_anon.status_code == 302
    assert '/accounts/login/' in resp_anon.url or 'login' in resp_anon.url
    print(f"  [OK] Anonymous redirected (302) to login: url='{resp_anon.url}'")

    # -------------------------------------------------------------
    # TEST 8: Existing Feature Integrity
    # -------------------------------------------------------------
    print("\n[TEST 8] Existing Feature Verification")
    from apps.queue_gate.views import TruckLookupAPIView, OcrSettingsView
    truck_lookup_view = TruckLookupAPIView.as_view()
    req_tl = factory.get(f'/api/truck-lookup/?plate={truck_plate}')
    attach_request_middleware(req_tl, user=operator_user)
    resp_tl = truck_lookup_view(req_tl)
    assert resp_tl.status_code == 200
    data_tl = json.loads(resp_tl.content)
    assert data_tl['found'] is True
    print(f"  [OK] Existing TruckLookupAPIView working: found={data_tl['found']}")

    ocr_set_view = OcrSettingsView.as_view()
    req_os = factory.get('/ocr-settings/')
    attach_request_middleware(req_os, user=operator_user)
    resp_os = ocr_set_view(req_os)
    assert resp_os.status_code == 200
    print(f"  [OK] Existing OcrSettingsView working: status={resp_os.status_code}")

    print("\n" + "=" * 65)
    print("ALL 8 OCR ENGINE INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    try:
        run_all_tests()
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] Test encountered an error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
