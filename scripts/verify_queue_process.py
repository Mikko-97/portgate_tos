import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')
if 'localhost' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('localhost')

from django.contrib.auth.models import User
from django.utils import timezone
from django.test import Client
from apps.masterdata.models import Truck, Driver, Expedition, Container
from apps.queue_gate.models import QueueEntry, QueueStatusLog
from apps.queue_gate.services import (
    process_queue_transition,
    QueueTransitionError,
    QueueValidationError,
)


def run_tests():
    print("=== MEMULAI PENGUJIAN FITUR QUEUE PROCESSING ===")

    # 1. Persiapan Data Uji
    user, _ = User.objects.get_or_create(username='test_operator', defaults={'first_name': 'Operator', 'last_name': 'Test'})
    expedisi, _ = Expedition.objects.get_or_create(nama_perusahaan="PT Samudera Logistik Test", defaults={'kode_ekspedisi': 'SLT'})
    driver, _ = Driver.objects.get_or_create(no_sim="SIM-TEST-9999", defaults={'nama': 'Budi Supir Test', 'no_hp': '081299990000'})
    truck, _ = Truck.objects.get_or_create(no_polisi="B 9999 TST", defaults={'expedisi': expedisi, 'driver': driver})
    container, _ = Container.objects.get_or_create(no_kontainer="TESTU9999991", defaults={'berat_kotor': 24000})

    queue = QueueEntry.objects.create(
        tanggal=timezone.localdate(),
        truck=truck,
        driver=driver,
        container=container,
        status=QueueEntry.QueueStatus.MENUNGGU,
        operator=user,
        gerbang_lane=QueueEntry.LaneChoice.LANE_01,
        booth="Gate Inbound 01"
    )

    initial_log_count = QueueStatusLog.objects.filter(queue_entry=queue).count()
    print(f"[SETUP] Antrian uji dibuat: {queue.no_antrian}, Status: {queue.status}")

    try:
        # -------------------------------------------------------------
        # TEST 1: MENUNGGU -> PROSES
        # -------------------------------------------------------------
        print("\n--- TEST 1: MENUNGGU -> PROSES ---")
        q1, log1 = process_queue_transition(queue, QueueEntry.QueueStatus.PROSES, operator_user=user)
        assert q1.status == QueueEntry.QueueStatus.PROSES, f"Expected PROSES, got {q1.status}"
        assert q1.waktu_mulai_proses is not None, "waktu_mulai_proses harus terisi"
        mulai_proses_time = q1.waktu_mulai_proses
        assert log1.status_lama == QueueEntry.QueueStatus.MENUNGGU, f"Expected log lama MENUNGGU, got {log1.status_lama}"
        assert log1.status_baru == QueueEntry.QueueStatus.PROSES, f"Expected log baru PROSES, got {log1.status_baru}"
        assert log1.operator == user, "Operator pada log harus sesuai"
        print("✓ PASS: MENUNGGU -> PROSES berhasil. waktu_mulai_proses:", q1.waktu_mulai_proses)

        # -------------------------------------------------------------
        # TEST 2: PROSES -> TERTAHAN (HOLD) DENGAN ALASAN
        # -------------------------------------------------------------
        print("\n--- TEST 2: PROSES -> TERTAHAN (DENGAN ALASAN) ---")
        reason = "Segel kontainer tidak cocok dengan manifest (Butuh verifikasi dokumen)"
        q2, log2 = process_queue_transition(q1, QueueEntry.QueueStatus.TERTAHAN, operator_user=user, reason=reason)
        assert q2.status == QueueEntry.QueueStatus.TERTAHAN, f"Expected TERTAHAN, got {q2.status}"
        assert q2.alasan_tertahan == reason, f"Expected {reason}, got {q2.alasan_tertahan}"
        assert log2.status_lama == QueueEntry.QueueStatus.PROSES, f"Expected log lama PROSES, got {log2.status_lama}"
        assert log2.status_baru == QueueEntry.QueueStatus.TERTAHAN, f"Expected log baru TERTAHAN, got {log2.status_baru}"
        assert reason in log2.keterangan, "Alasan harus ada di log keterangan"
        print("✓ PASS: PROSES -> TERTAHAN berhasil. Alasan:", q2.alasan_tertahan)

        # -------------------------------------------------------------
        # TEST 3: TERTAHAN -> PROSES (LANJUT SETELAH HOLD)
        # -------------------------------------------------------------
        print("\n--- TEST 3: TERTAHAN -> PROSES (LANJUT PROSES) ---")
        q3, log3 = process_queue_transition(q2, QueueEntry.QueueStatus.PROSES, operator_user=user)
        assert q3.status == QueueEntry.QueueStatus.PROSES, f"Expected PROSES, got {q3.status}"
        assert q3.waktu_mulai_proses == mulai_proses_time, "waktu_mulai_proses TIDAK boleh di-reset!"
        assert q3.alasan_tertahan == reason, "alasan_tertahan tidak boleh dihapus sembarangan!"
        assert log3.status_lama == QueueEntry.QueueStatus.TERTAHAN, f"Expected log lama TERTAHAN, got {log3.status_lama}"
        assert log3.status_baru == QueueEntry.QueueStatus.PROSES, f"Expected log baru PROSES, got {log3.status_baru}"
        print("✓ PASS: TERTAHAN -> PROSES berhasil. Waktu mulai proses terjaga, alasan hold tersimpan.")

        # -------------------------------------------------------------
        # TEST 4: PROSES -> SELESAI
        # -------------------------------------------------------------
        print("\n--- TEST 4: PROSES -> SELESAI ---")
        q4, log4 = process_queue_transition(q3, QueueEntry.QueueStatus.SELESAI, operator_user=user)
        assert q4.status == QueueEntry.QueueStatus.SELESAI, f"Expected SELESAI, got {q4.status}"
        assert q4.waktu_selesai is not None, "waktu_selesai harus terisi otomatis"
        assert log4.status_lama == QueueEntry.QueueStatus.PROSES, f"Expected log lama PROSES, got {log4.status_lama}"
        assert log4.status_baru == QueueEntry.QueueStatus.SELESAI, f"Expected log baru SELESAI, got {log4.status_baru}"
        print("✓ PASS: PROSES -> SELESAI berhasil. waktu_selesai:", q4.waktu_selesai)

        # -------------------------------------------------------------
        # TEST 5: SELESAI -> KELUAR
        # -------------------------------------------------------------
        print("\n--- TEST 5: SELESAI -> KELUAR ---")
        q5, log5 = process_queue_transition(q4, QueueEntry.QueueStatus.KELUAR, operator_user=user)
        assert q5.status == QueueEntry.QueueStatus.KELUAR, f"Expected KELUAR, got {q5.status}"
        assert q5.waktu_keluar is not None, "waktu_keluar harus terisi otomatis"
        assert log5.status_lama == QueueEntry.QueueStatus.SELESAI, f"Expected log lama SELESAI, got {log5.status_lama}"
        assert log5.status_baru == QueueEntry.QueueStatus.KELUAR, f"Expected log baru KELUAR, got {log5.status_baru}"
        print("✓ PASS: SELESAI -> KELUAR berhasil. waktu_keluar:", q5.waktu_keluar)

        # -------------------------------------------------------------
        # TEST 6: TEST ALASAN HOLD KOSONG HARUS DITOLAK
        # -------------------------------------------------------------
        print("\n--- TEST 6: UJI ALASAN HOLD KOSONG HARUS DITOLAK ---")
        dummy_q = QueueEntry.objects.create(
            tanggal=timezone.localdate(),
            truck=truck,
            driver=driver,
            status=QueueEntry.QueueStatus.PROSES,
            gerbang_lane=QueueEntry.LaneChoice.LANE_02
        )
        empty_reason_rejected = False
        try:
            process_queue_transition(dummy_q, QueueEntry.QueueStatus.TERTAHAN, operator_user=user, reason="")
        except QueueValidationError as e:
            empty_reason_rejected = True
            print("✓ Berhasil menangkap QueueValidationError saat alasan kosong:", str(e))

        assert empty_reason_rejected, "Alasan hold kosong harus menghasilkan QueueValidationError"

        # Uji juga jika hanya spasi putih (whitespace)
        whitespace_rejected = False
        try:
            process_queue_transition(dummy_q, QueueEntry.QueueStatus.TERTAHAN, operator_user=user, reason="     ")
        except QueueValidationError as e:
            whitespace_rejected = True
            print("✓ Berhasil menangkap QueueValidationError saat alasan hanya spasi:", str(e))

        assert whitespace_rejected, "Alasan hold hanya spasi harus menghasilkan QueueValidationError"
        dummy_q_current = QueueEntry.objects.get(pk=dummy_q.pk)
        assert dummy_q_current.status == QueueEntry.QueueStatus.PROSES, "Status tidak boleh berubah jika validasi gagal"
        print("✓ PASS: Alasan hold kosong/spasi berhasil ditolak dengan benar.")

        # -------------------------------------------------------------
        # TEST 7: TRANSISI TERLARANG HARUS DITOLAK
        # -------------------------------------------------------------
        print("\n--- TEST 7: UJI TRANSISI TIDAK SAH (ILLEGAL TRANSITIONS) ---")
        test_cases = [
            (dummy_q, QueueEntry.QueueStatus.KELUAR),    # PROSES -> KELUAR (ilegal, harus SELESAI dulu)
            (q5, QueueEntry.QueueStatus.PROSES),         # KELUAR -> PROSES (ilegal, terminal state)
            (q5, QueueEntry.QueueStatus.MENUNGGU),       # KELUAR -> MENUNGGU (ilegal)
        ]
        for ent, invalid_target in test_cases:
            rejected = False
            try:
                process_queue_transition(ent, invalid_target, operator_user=user)
            except QueueTransitionError as e:
                rejected = True
                print(f"✓ Berhasil menolak transisi ilegal {ent.status} -> {invalid_target}: {str(e)}")
            assert rejected, f"Transisi {ent.status} -> {invalid_target} seharusnya ditolak!"
        print("✓ PASS: Semua transisi ilegal berhasil dicegah.")

        # -------------------------------------------------------------
        # TEST 8: UJI ENDPOINT HTTP DENGAN CLIENT (POST & CSRF)
        # -------------------------------------------------------------
        print("\n--- TEST 8: UJI HTTP ENDPOINT /queue/<pk>/process/ ---")
        client = Client()
        client.force_login(user)

        # Uji transisi melalui HTTP POST
        post_q = QueueEntry.objects.create(
            tanggal=timezone.localdate(),
            truck=truck,
            driver=driver,
            status=QueueEntry.QueueStatus.MENUNGGU,
            gerbang_lane=QueueEntry.LaneChoice.LANE_01
        )
        url = f"/queue/{post_q.pk}/process/"

        # 1. Mulai proses via HTTP POST
        resp = client.post(url, {'target_status': 'PROSES'})
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        post_q.refresh_from_db()
        assert post_q.status == QueueEntry.QueueStatus.PROSES, f"Expected PROSES, got {post_q.status}"

        # 2. Hold via HTTP POST tanpa alasan (harus gagal, status tetap PROSES)
        resp = client.post(url, {'target_status': 'TERTAHAN', 'reason': ''})
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        post_q.refresh_from_db()
        assert post_q.status == QueueEntry.QueueStatus.PROSES, f"Status harus tetap PROSES karena reason kosong, got {post_q.status}"

        # 3. Hold via HTTP POST dengan alasan (berhasil)
        resp = client.post(url, {'target_status': 'TERTAHAN', 'reason': 'Pemeriksaan fisik peti kemas'})
        assert resp.status_code == 302
        post_q.refresh_from_db()
        assert post_q.status == QueueEntry.QueueStatus.TERTAHAN
        assert post_q.alasan_tertahan == 'Pemeriksaan fisik peti kemas'

        print("✓ PASS: HTTP Endpoint QueueProcessActionView bekerja dengan baik sesuai alur!")

        # -------------------------------------------------------------
        # TEST 9: VERIFIKASI SETIAP PERUBAHAN MEMILIKI QueueStatusLog
        # -------------------------------------------------------------
        print("\n--- TEST 9: VERIFIKASI KELENGKAPAN QueueStatusLog ---")
        logs = QueueStatusLog.objects.filter(queue_entry=queue).order_by('timestamp')
        print(f"Total status log untuk antrian {queue.no_antrian}: {logs.count()}")
        for log in logs:
            print(f"  - [{log.timestamp.strftime('%H:%M:%S')}] {log.status_lama or 'AWAL'} -> {log.status_baru} | Op: {log.operator} | Ket: {log.keterangan}")

        assert logs.filter(status_lama=QueueEntry.QueueStatus.MENUNGGU, status_baru=QueueEntry.QueueStatus.PROSES).exists()
        assert logs.filter(status_lama=QueueEntry.QueueStatus.PROSES, status_baru=QueueEntry.QueueStatus.TERTAHAN).exists()
        assert logs.filter(status_lama=QueueEntry.QueueStatus.TERTAHAN, status_baru=QueueEntry.QueueStatus.PROSES).exists()
        assert logs.filter(status_lama=QueueEntry.QueueStatus.PROSES, status_baru=QueueEntry.QueueStatus.SELESAI).exists()
        assert logs.filter(status_lama=QueueEntry.QueueStatus.SELESAI, status_baru=QueueEntry.QueueStatus.KELUAR).exists()
        print("✓ PASS: Semua transisi status menghasilkan QueueStatusLog secara lengkap!")

    finally:
        # Bersihkan data uji agar database tetap rapi
        print("\n[CLEANUP] Membersihkan data uji...")
        QueueStatusLog.objects.filter(queue_entry__truck=truck).delete()
        QueueEntry.objects.filter(truck=truck).delete()
        truck.delete()
        driver.delete()
        container.delete()
        expedisi.delete()
        user.delete()
        print("[CLEANUP] Data uji berhasil dibersihkan.")

    print("\n=======================================================")
    print("SEMUA PENGUJIAN QUEUE PROCESSING BERHASIL 100%!")
    print("=======================================================")


if __name__ == '__main__':
    run_tests()
