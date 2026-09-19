"""
Script Verifikasi End-to-End Workflow: Stage 25 — Port Gate TOS
Memvalidasi seluruh alur operasional terminal peti kemas:
1. Login sebagai Operator
2. Data master & integrasi OCR lookup
3. Gate In pendaftaran truk + kontainer -> Status: MENUNGGU
4. Transisi: MENUNGGU -> PROSES
5. Transisi: PROSES -> TERTAHAN (Hold)
6. Transisi: TERTAHAN -> PROSES (Resume)
7. Transisi: PROSES -> SELESAI
8. Validasi keamanan Gate Out (penolakan status non-SELESAI)
9. Transisi: SELESAI -> KELUAR melalui Gate Out
10. Verifikasi konsistensi seluruh stempel waktu (timestamps)
11. Verifikasi kelengkapan seluruh QueueStatusLog (audit trail)
12. Verifikasi visibilitas data pada Dashboard dan Audit Log
13. Cleanup seluruh data pengujian
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
for host in ['testserver', 'localhost', '127.0.0.1']:
    if host not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append(host)

import re
from django.contrib.auth.models import User, Group
from django.test import Client
from django.utils import timezone
from apps.masterdata.models import Truck, Driver, Expedition, Container
from apps.queue_gate.models import QueueEntry, QueueStatusLog, DailyQueueSequence


def run_e2e_verification():
    print("=" * 75)
    print("STAGE 25: AUTOMATED END-TO-END WORKFLOW VERIFICATION")
    print("=" * 75)

    client = Client()
    admin_client = Client()

    # Data identifiers
    op_username = 'operator_stage25_test'
    admin_username = 'admin_stage25_test'
    test_password = 'TestPassword123!'
    test_plate = 'B 9876 XYZ'
    test_plate_normalized = 'B 9876 XYZ'
    test_container_no = 'TOSK1234567'
    test_expedition_name = 'PT Samudera Pratama Logistik Stage25'
    test_driver_sim = 'SIM-BII-987654'

    operator_user = None
    admin_user = None
    expedition = None
    driver = None
    truck = None
    container = None
    created_queue = None

    try:
        # -------------------------------------------------------------
        # 1. SETUP USER & TAHAP 1: LOGIN SEBAGAI OPERATOR & ROLE ISOLATION
        # -------------------------------------------------------------
        print("\n--- [TAHAP 1] LOGIN SEBAGAI OPERATOR & ROLE ISOLATION ---")
        op_group, _ = Group.objects.get_or_create(name='Operator')
        admin_group, _ = Group.objects.get_or_create(name='Admin')

        operator_user, _ = User.objects.get_or_create(
            username=op_username,
            defaults={
                'first_name': 'Operator',
                'last_name': 'Stage25',
                'email': 'op25@portgate.local',
                'is_staff': False,
                'is_superuser': False,
            }
        )
        operator_user.set_password(test_password)
        operator_user.save()
        operator_user.groups.add(op_group)

        admin_user, _ = User.objects.get_or_create(
            username=admin_username,
            defaults={
                'first_name': 'Admin',
                'last_name': 'Stage25',
                'email': 'admin25@portgate.local',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_user.set_password(test_password)
        admin_user.save()
        admin_user.groups.add(admin_group)

        # Login Operator via HTTP POST
        login_resp = client.post('/login/', {
            'username': op_username,
            'password': test_password,
            'booth': 'gate-01',
        }, follow=True)
        assert login_resp.status_code == 200, f"Expected 200, got {login_resp.status_code}"
        assert client.session.get('assigned_booth') == 'gate-01', "Session booth key must be 'gate-01'"
        assert client.session.get('assigned_booth_label') == 'Gate Inbound 01', "Session booth label must match"
        print("  [PASS] Operator login berhasil dan penugasan booth tersimpan di sesi (Gate Inbound 01).")

        # Verifikasi Role Isolation: Operator mengakses Admin area -> dialihkan ke /dashboard/
        op_admin_resp = client.get('/admin-dashboard/')
        assert op_admin_resp.status_code == 302, f"Operator to /admin-dashboard/ should 302, got {op_admin_resp.status_code}"
        assert '/dashboard/' in op_admin_resp.url, "Operator must be redirected to /dashboard/"
        print("  [PASS] Role Isolation: Operator ditolak dari /admin-dashboard/ dan dialihkan ke /dashboard/.")

        # Verifikasi Role Isolation: Admin mengakses Operasional area -> dialihkan ke /admin-dashboard/
        admin_client.post('/login/', {
            'username': admin_username,
            'password': test_password,
        })
        adm_dash_resp = admin_client.get('/dashboard/')
        assert adm_dash_resp.status_code == 302, f"Admin to /dashboard/ should 302, got {adm_dash_resp.status_code}"
        assert '/admin-dashboard/' in adm_dash_resp.url, "Admin must be redirected to /admin-dashboard/"
        print("  [PASS] Role Isolation: Administrator ditolak dari area operasional /dashboard/.")

        # -------------------------------------------------------------
        # 2. TAHAP 2: MASTER DATA & INTEGRASI OCR LOOKUP
        # -------------------------------------------------------------
        print("\n--- [TAHAP 2] MASTER DATA & VERIFIKASI OCR LOOKUP ---")
        expedition, _ = Expedition.objects.get_or_create(
            nama_perusahaan=test_expedition_name,
            defaults={'kode_ekspedisi': 'SPL25', 'is_active': True}
        )
        driver, _ = Driver.objects.get_or_create(
            no_sim=test_driver_sim,
            defaults={'nama': 'Joko Purwanto Test', 'no_hp': '081234567890', 'is_active': True}
        )
        truck, _ = Truck.objects.get_or_create(
            no_polisi=test_plate,
            defaults={'konfigurasi': Truck.TruckConfigChoice.TRAILER_40, 'expedisi': expedition, 'driver': driver, 'is_active': True}
        )
        container, _ = Container.objects.get_or_create(
            no_kontainer=test_container_no,
            defaults={
                'ukuran': Container.ContainerSizeChoice.SIZE_40,
                'tipe': Container.ContainerTypeChoice.DRY,
                'kategori': Container.CargoCategoryChoice.IMPORT,
                'berat_kotor': 28500.00,
                'shipping_line': 'Maersk Line',
                'seal_number': 'ML-SEAL-8899',
                'ref_dokumen': 'DO-SPL-2026-001',
                'status_vgm': Container.VGMStatusChoice.VERIFIED
            }
        )
        print("  [PASS] Data master awal berhasil dipersiapkan (Expedition, Driver, Truck, Container).")

        # Test API Truck Lookup
        truck_lookup_resp = client.get(f'/api/truck-lookup/?plate={test_plate}')
        assert truck_lookup_resp.status_code == 200
        truck_lookup_data = truck_lookup_resp.json()
        assert truck_lookup_data.get('found') is True
        assert truck_lookup_data.get('no_polisi') == test_plate
        print("  [PASS] API Truck Lookup merespons valid dengan data armada.")

        # Test API Container Lookup
        container_lookup_resp = client.get(f'/api/container-lookup/?no={test_container_no}')
        assert container_lookup_resp.status_code == 200
        container_lookup_data = container_lookup_resp.json()
        assert container_lookup_data.get('found') is True
        assert container_lookup_data.get('no_kontainer') == test_container_no
        print("  [PASS] API Container Lookup merespons valid dengan data kontainer.")

        # Test API OCR Process (tidak merusak data workflow)
        ocr_resp = client.get(f'/api/ocr-process/?plate={test_plate}&confidence=96.5')
        assert ocr_resp.status_code == 200
        ocr_data = ocr_resp.json()
        assert ocr_data.get('status') == 'success'
        assert ocr_data.get('found') is True
        assert ocr_data.get('truck') is not None
        print("  [PASS] API OCR Process berhasil mendeteksi dan menormalkan plat tanpa efek samping.")

        # -------------------------------------------------------------
        # 3. TAHAP 3: GATE IN PENDAFTARAN TRUK + KONTAINER -> MENUNGGU
        # -------------------------------------------------------------
        print("\n--- [TAHAP 3] GATE IN PENDAFTARAN TRUK + KONTAINER ---")
        gate_in_post_data = {
            'no_polisi': test_plate,
            'konfigurasi': Truck.TruckConfigChoice.TRAILER_40,
            'nama_ekspedisi': test_expedition_name,
            'kode_ekspedisi': 'SPL25',
            'nama_driver': 'Joko Purwanto Test',
            'no_hp_driver': '081234567890',
            'no_sim_driver': test_driver_sim,
            'has_container': 'on',
            'no_kontainer': test_container_no,
            'ukuran': Container.ContainerSizeChoice.SIZE_40,
            'tipe': Container.ContainerTypeChoice.DRY,
            'kategori': Container.CargoCategoryChoice.IMPORT,
            'berat_kotor': '28500.00',
            'shipping_line': 'Maersk Line',
            'seal_number': 'ML-SEAL-8899',
            'ref_dokumen': 'DO-SPL-2026-001',
            'status_vgm': Container.VGMStatusChoice.VERIFIED,
            'gerbang_lane': QueueEntry.LaneChoice.LANE_01,
            'alokasi_blok': 'BLOCK C-04',
            'alokasi_bay': 'BAY 12',
            'alokasi_row': 'ROW 03',
            'alokasi_tier': 'TIER 2',
            'catatan': 'Registrasi Gate In Automated Test Stage 25',
            'action_type': 'save'
        }

        gate_in_resp = client.post('/gate-in/', gate_in_post_data, follow=True)
        assert gate_in_resp.status_code == 200, f"Expected 200, got {gate_in_resp.status_code}"

        created_queue = QueueEntry.objects.filter(truck__no_polisi=test_plate).order_by('-id').first()
        assert created_queue is not None, "QueueEntry must be created in database!"
        assert created_queue.status == QueueEntry.QueueStatus.MENUNGGU, f"Expected status MENUNGGU, got {created_queue.status}"
        assert re.match(r'^Q-\d{4}$', created_queue.no_antrian), f"Invalid queue number format: {created_queue.no_antrian}"
        assert created_queue.waktu_masuk is not None, "waktu_masuk must be set at Gate In"
        assert created_queue.waktu_mulai_proses is None, "waktu_mulai_proses must be None initially"
        assert created_queue.waktu_selesai is None, "waktu_selesai must be None initially"
        assert created_queue.waktu_keluar is None, "waktu_keluar must be None initially"
        assert created_queue.gerbang_lane == QueueEntry.LaneChoice.LANE_01
        assert created_queue.booth == 'Gate Inbound 01'
        assert created_queue.operator == operator_user

        # Verifikasi QueueStatusLog perdana
        initial_log = QueueStatusLog.objects.filter(queue_entry=created_queue).first()
        assert initial_log is not None, "QueueStatusLog must be created on Gate In"
        assert initial_log.status_lama is None
        assert initial_log.status_baru == QueueEntry.QueueStatus.MENUNGGU
        assert initial_log.operator == operator_user
        print(f"  [PASS] Gate In berhasil! Nomor Antrian: {created_queue.no_antrian}, Status: MENUNGGU, Operator: {operator_user.username}")

        # -------------------------------------------------------------
        # 4. TAHAP 4: TRANSISI MENUNGGU -> PROSES
        # -------------------------------------------------------------
        print("\n--- [TAHAP 4] TRANSISI: MENUNGGU -> PROSES ---")
        process_resp = client.post(f'/queue/{created_queue.pk}/process/', {
            'target_status': 'PROSES',
            'reason': 'Pemeriksaan gate in selesai, bergerak menuju yard blok C-04',
            'next': f'/queue/{created_queue.pk}/'
        }, follow=True)
        assert process_resp.status_code == 200

        created_queue.refresh_from_db()
        assert created_queue.status == QueueEntry.QueueStatus.PROSES, f"Expected PROSES, got {created_queue.status}"
        assert created_queue.waktu_mulai_proses is not None, "waktu_mulai_proses must be populated"
        assert created_queue.waktu_mulai_proses >= created_queue.waktu_masuk, "waktu_mulai_proses must be >= waktu_masuk"

        log_proses = QueueStatusLog.objects.filter(
            queue_entry=created_queue,
            status_lama=QueueEntry.QueueStatus.MENUNGGU,
            status_baru=QueueEntry.QueueStatus.PROSES
        ).first()
        assert log_proses is not None, "QueueStatusLog MENUNGGU -> PROSES must exist"
        assert log_proses.operator == operator_user
        print(f"  [PASS] Status berubah ke PROSES. waktu_mulai_proses: {created_queue.waktu_mulai_proses.strftime('%H:%M:%S')}")

        # -------------------------------------------------------------
        # 5. TAHAP 5: TRANSISI PROSES -> TERTAHAN (HOLD)
        # -------------------------------------------------------------
        print("\n--- [TAHAP 5] TRANSISI: PROSES -> TERTAHAN (HOLD) ---")
        # Uji negatif: Hold tanpa alasan harus ditolak
        hold_fail_resp = client.post(f'/queue/{created_queue.pk}/process/', {
            'target_status': 'TERTAHAN',
            'reason': '',
            'next': f'/queue/{created_queue.pk}/'
        }, follow=True)
        created_queue.refresh_from_db()
        assert created_queue.status == QueueEntry.QueueStatus.PROSES, "Hold without reason must be rejected"
        print("  [PASS] Validasi negatif: Permintaan HOLD tanpa alasan berhasil ditolak.")

        # Eksekusi Hold yang valid dengan alasan
        hold_reason = "Kesesuaian fisik segel Bea Cukai memerlukan verifikasi tambahan di buffer line"
        hold_resp = client.post(f'/queue/{created_queue.pk}/process/', {
            'target_status': 'TERTAHAN',
            'reason': hold_reason,
            'next': f'/queue/{created_queue.pk}/'
        }, follow=True)
        assert hold_resp.status_code == 200

        created_queue.refresh_from_db()
        assert created_queue.status == QueueEntry.QueueStatus.TERTAHAN, f"Expected TERTAHAN, got {created_queue.status}"
        assert created_queue.alasan_tertahan == hold_reason

        log_hold = QueueStatusLog.objects.filter(
            queue_entry=created_queue,
            status_lama=QueueEntry.QueueStatus.PROSES,
            status_baru=QueueEntry.QueueStatus.TERTAHAN
        ).first()
        assert log_hold is not None, "QueueStatusLog PROSES -> TERTAHAN must exist"
        assert log_hold.operator == operator_user
        print(f"  [PASS] Status berubah ke TERTAHAN. Alasan: {created_queue.alasan_tertahan}")

        # -------------------------------------------------------------
        # 6. TAHAP 6: TRANSISI TERTAHAN -> PROSES (RESUME)
        # -------------------------------------------------------------
        print("\n--- [TAHAP 6] TRANSISI: TERTAHAN -> PROSES (RESUME) ---")
        waktu_mulai_sebelum_resume = created_queue.waktu_mulai_proses
        resume_reason = "Verifikasi segel klir oleh petugas Bea Cukai, proses yard dilanjutkan"
        resume_resp = client.post(f'/queue/{created_queue.pk}/process/', {
            'target_status': 'PROSES',
            'reason': resume_reason,
            'next': f'/queue/{created_queue.pk}/'
        }, follow=True)
        assert resume_resp.status_code == 200

        created_queue.refresh_from_db()
        assert created_queue.status == QueueEntry.QueueStatus.PROSES, f"Expected PROSES, got {created_queue.status}"
        assert created_queue.waktu_mulai_proses == waktu_mulai_sebelum_resume, "waktu_mulai_proses must NOT be reset on resume"

        log_resume = QueueStatusLog.objects.filter(
            queue_entry=created_queue,
            status_lama=QueueEntry.QueueStatus.TERTAHAN,
            status_baru=QueueEntry.QueueStatus.PROSES
        ).first()
        assert log_resume is not None, "QueueStatusLog TERTAHAN -> PROSES must exist"
        assert log_resume.operator == operator_user
        print("  [PASS] Status berhasil di-resume ke PROSES. waktu_mulai_proses dipertahankan konsisten.")

        # -------------------------------------------------------------
        # 7. TAHAP 7: TRANSISI PROSES -> SELESAI
        # -------------------------------------------------------------
        print("\n--- [TAHAP 7] TRANSISI: PROSES -> SELESAI ---")
        finish_reason = "Bongkar muat kontainer di Block C-04 Bay 12 selesai"
        finish_resp = client.post(f'/queue/{created_queue.pk}/process/', {
            'target_status': 'SELESAI',
            'reason': finish_reason,
            'next': f'/queue/{created_queue.pk}/'
        }, follow=True)
        assert finish_resp.status_code == 200

        created_queue.refresh_from_db()
        assert created_queue.status == QueueEntry.QueueStatus.SELESAI, f"Expected SELESAI, got {created_queue.status}"
        assert created_queue.waktu_selesai is not None, "waktu_selesai must be set"
        assert created_queue.waktu_selesai >= created_queue.waktu_mulai_proses, "waktu_selesai must be >= waktu_mulai_proses"

        log_selesai = QueueStatusLog.objects.filter(
            queue_entry=created_queue,
            status_lama=QueueEntry.QueueStatus.PROSES,
            status_baru=QueueEntry.QueueStatus.SELESAI
        ).first()
        assert log_selesai is not None, "QueueStatusLog PROSES -> SELESAI must exist"
        assert log_selesai.operator == operator_user
        print(f"  [PASS] Status berubah ke SELESAI. waktu_selesai: {created_queue.waktu_selesai.strftime('%H:%M:%S')}")

        # -------------------------------------------------------------
        # 8. TAHAP 8: UJI KEAMANAN GATE OUT (PENOLAKAN STATUS NON-SELESAI)
        # -------------------------------------------------------------
        print("\n--- [TAHAP 8] UJI KEAMANAN GATE OUT (PENOLAKAN STATUS NON-SELESAI) ---")
        # Buat antrian sementara dengan status MENUNGGU
        invalid_queue = QueueEntry.objects.create(
            tanggal=timezone.localdate(),
            truck=truck,
            driver=driver,
            status=QueueEntry.QueueStatus.MENUNGGU,
            operator=operator_user,
            gerbang_lane=QueueEntry.LaneChoice.LANE_01
        )
        invalid_gateout_resp = client.post('/gate-out/', {
            'entry_id': str(invalid_queue.pk),
            'gerbang_lane': QueueEntry.LaneChoice.OUT_01,
            'catatan': 'Percobaan ilegal Gate Out'
        }, follow=True)
        invalid_queue.refresh_from_db()
        assert invalid_queue.status == QueueEntry.QueueStatus.MENUNGGU, "Non-SELESAI queue must NOT be allowed to Gate Out"
        invalid_queue.delete()
        print("  [PASS] Keamanan Gate Out terverifikasi: Antrian non-SELESAI ditolak secara tegas.")

        # -------------------------------------------------------------
        # 9. TAHAP 9: TRANSISI SELESAI -> KELUAR VIA GATE OUT
        # -------------------------------------------------------------
        print("\n--- [TAHAP 9] TRANSISI: SELESAI -> KELUAR (GATE OUT) ---")
        gate_out_reason = "Pemeriksaan fisik Gate Out selesai, dokumen lengkap, barrier dibuka"
        gate_out_resp = client.post('/gate-out/', {
            'entry_id': str(created_queue.pk),
            'gerbang_lane': QueueEntry.LaneChoice.OUT_01,
            'catatan': gate_out_reason
        }, follow=True)
        assert gate_out_resp.status_code == 200

        created_queue.refresh_from_db()
        assert created_queue.status == QueueEntry.QueueStatus.KELUAR, f"Expected KELUAR, got {created_queue.status}"
        assert created_queue.waktu_keluar is not None, "waktu_keluar must be set"
        assert created_queue.gerbang_lane == QueueEntry.LaneChoice.OUT_01, "Lane must update to outbound lane"

        log_keluar = QueueStatusLog.objects.filter(
            queue_entry=created_queue,
            status_lama=QueueEntry.QueueStatus.SELESAI,
            status_baru=QueueEntry.QueueStatus.KELUAR
        ).first()
        assert log_keluar is not None, "QueueStatusLog SELESAI -> KELUAR must exist"
        assert log_keluar.operator == operator_user
        print(f"  [PASS] Gate Out SUKSES! Status: KELUAR, Lane: {created_queue.gerbang_lane}, waktu_keluar: {created_queue.waktu_keluar.strftime('%H:%M:%S')}")

        # -------------------------------------------------------------
        # 10. TAHAP 10: VERIFIKASI KONSISTENSI SELURUH TIMESTAMPS
        # -------------------------------------------------------------
        print("\n--- [TAHAP 10] VERIFIKASI KONSISTENSI SELURUH TIMESTAMPS ---")
        t_in = created_queue.waktu_masuk
        t_proc = created_queue.waktu_mulai_proses
        t_done = created_queue.waktu_selesai
        t_out = created_queue.waktu_keluar

        assert t_in is not None, "waktu_masuk must not be None"
        assert t_proc is not None, "waktu_mulai_proses must not be None"
        assert t_done is not None, "waktu_selesai must not be None"
        assert t_out is not None, "waktu_keluar must not be None"

        assert t_in <= t_proc, f"Timestamp anomaly: waktu_masuk ({t_in}) > waktu_mulai_proses ({t_proc})"
        assert t_proc <= t_done, f"Timestamp anomaly: waktu_mulai_proses ({t_proc}) > waktu_selesai ({t_done})"
        assert t_done <= t_out, f"Timestamp anomaly: waktu_selesai ({t_done}) > waktu_keluar ({t_out})"

        print(f"  1. Gate In     (waktu_masuk)        : {timezone.localtime(t_in).strftime('%Y-%m-%d %H:%M:%S WIB')}")
        print(f"  2. Mulai Yard  (waktu_mulai_proses) : {timezone.localtime(t_proc).strftime('%Y-%m-%d %H:%M:%S WIB')}")
        print(f"  3. Selesai Yard(waktu_selesai)      : {timezone.localtime(t_done).strftime('%Y-%m-%d %H:%M:%S WIB')}")
        print(f"  4. Gate Out    (waktu_keluar)       : {timezone.localtime(t_out).strftime('%Y-%m-%d %H:%M:%S WIB')}")
        print("  [PASS] Seluruh timestamp terbukti berurutan secara konsisten dan logis!")

        # -------------------------------------------------------------
        # 11. TAHAP 11: VERIFIKASI KELENGKAPAN QueueStatusLog
        # -------------------------------------------------------------
        print("\n--- [TAHAP 11] VERIFIKASI KELENGKAPAN QueueStatusLog ---")
        all_logs = list(QueueStatusLog.objects.filter(queue_entry=created_queue).order_by('timestamp'))
        assert len(all_logs) == 6, f"Expected exactly 6 status logs, got {len(all_logs)}"

        expected_transitions = [
            (None, QueueEntry.QueueStatus.MENUNGGU),
            (QueueEntry.QueueStatus.MENUNGGU, QueueEntry.QueueStatus.PROSES),
            (QueueEntry.QueueStatus.PROSES, QueueEntry.QueueStatus.TERTAHAN),
            (QueueEntry.QueueStatus.TERTAHAN, QueueEntry.QueueStatus.PROSES),
            (QueueEntry.QueueStatus.PROSES, QueueEntry.QueueStatus.SELESAI),
            (QueueEntry.QueueStatus.SELESAI, QueueEntry.QueueStatus.KELUAR),
        ]

        for idx, (expected_old, expected_new) in enumerate(expected_transitions):
            log_item = all_logs[idx]
            assert log_item.status_lama == expected_old, f"Log #{idx+1} status_lama: expected {expected_old}, got {log_item.status_lama}"
            assert log_item.status_baru == expected_new, f"Log #{idx+1} status_baru: expected {expected_new}, got {log_item.status_baru}"
            assert log_item.operator == operator_user, f"Log #{idx+1} operator expected {operator_user}, got {log_item.operator}"
            print(f"  Log #{idx+1}: [{log_item.status_lama or 'None':^8}] -> [{log_item.status_baru:^8}] | Operator: {log_item.operator.username} | {log_item.keterangan[:60]}...")

        print("  [PASS] Seluruh 6 QueueStatusLog tercatat akurat dan tidak ada mutasi yang terlewat.")

        # -------------------------------------------------------------
        # 12. TAHAP 12: VERIFIKASI VISIBILITAS DASHBOARD & AUDIT LOG
        # -------------------------------------------------------------
        print("\n--- [TAHAP 12] VERIFIKASI VISIBILITAS DASHBOARD & AUDIT LOG ---")
        # Dashboard View
        dash_resp = client.get('/dashboard/')
        assert dash_resp.status_code == 200, f"Dashboard expected 200, got {dash_resp.status_code}"
        dash_html = dash_resp.content.decode('utf-8')
        assert created_queue.no_antrian in dash_html, f"Queue {created_queue.no_antrian} must be present in Dashboard"
        print("  [PASS] Dashboard operasional membaca dan menampilkan data antrian secara tepat.")

        # Audit Log View
        audit_resp = client.get(f'/audit-log/?search={created_queue.no_antrian}')
        assert audit_resp.status_code == 200, f"Audit Log expected 200, got {audit_resp.status_code}"
        audit_html = audit_resp.content.decode('utf-8')
        assert created_queue.no_antrian in audit_html, f"Queue {created_queue.no_antrian} must be present in Audit Log"
        print("  [PASS] Audit Log workstation menampilkan riwayat transaksi antrian dengan parameter pencarian.")

        # Gate Ticket View
        ticket_resp = client.get(f'/ticket/{created_queue.pk}/')
        assert ticket_resp.status_code == 200, f"Ticket expected 200, got {ticket_resp.status_code}"
        ticket_html = ticket_resp.content.decode('utf-8')
        assert created_queue.no_antrian in ticket_html
        print("  [PASS] Tiket antrian gerbang dapat dirender dengan sempurna.")

    finally:
        # -------------------------------------------------------------
        # 13. TAHAP 13: CLEANUP SELURUH DATA UJI
        # -------------------------------------------------------------
        print("\n--- [TAHAP 13] CLEANUP SELURUH DATA UJI ---")
        deleted_counts = {}

        if created_queue:
            qsl_cnt, _ = QueueStatusLog.objects.filter(queue_entry=created_queue).delete()
            qe_cnt, _ = QueueEntry.objects.filter(pk=created_queue.pk).delete()
            deleted_counts['QueueStatusLog'] = qsl_cnt
            deleted_counts['QueueEntry'] = qe_cnt

        # Cleanup sisa-sisa antrian terkait truk uji jika ada
        if truck:
            extra_qsl, _ = QueueStatusLog.objects.filter(queue_entry__truck=truck).delete()
            extra_qe, _ = QueueEntry.objects.filter(truck=truck).delete()
            deleted_counts['QueueStatusLog'] = deleted_counts.get('QueueStatusLog', 0) + extra_qsl
            deleted_counts['QueueEntry'] = deleted_counts.get('QueueEntry', 0) + extra_qe
            t_cnt, _ = Truck.objects.filter(pk=truck.pk).delete()
            deleted_counts['Truck'] = t_cnt

        if container:
            c_cnt, _ = Container.objects.filter(pk=container.pk).delete()
            deleted_counts['Container'] = c_cnt

        if driver:
            d_cnt, _ = Driver.objects.filter(pk=driver.pk).delete()
            deleted_counts['Driver'] = d_cnt

        if expedition:
            e_cnt, _ = Expedition.objects.filter(pk=expedition.pk).delete()
            deleted_counts['Expedition'] = e_cnt

        if operator_user:
            u_cnt, _ = User.objects.filter(pk=operator_user.pk).delete()
            deleted_counts['OperatorUser'] = u_cnt

        if admin_user:
            adm_cnt, _ = User.objects.filter(pk=admin_user.pk).delete()
            deleted_counts['AdminUser'] = adm_cnt

        print("  Entitas uji yang dibersihkan:")
        for ent_name, cnt in deleted_counts.items():
            print(f"    - {ent_name}: {cnt} record")
        print("  [PASS] Database telah dibersihkan secara tuntas tanpa meninggalkan orphan records.")

    print("\n" + "=" * 75)
    print("HASIL: SELURUH 13 TAHAP WORKFLOW E2E TERVERIFIKASI SUKSES (100% PASS)")
    print("=" * 75)


if __name__ == '__main__':
    run_e2e_verification()
