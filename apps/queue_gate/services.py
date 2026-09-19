from django.db import transaction
from django.utils import timezone
from apps.masterdata.models import Expedition, Driver, Truck, Container
from apps.queue_gate.models import DailyQueueSequence, QueueEntry, QueueStatusLog


def process_gate_in_registration(operator_user, cleaned_data, booth_name="Gate Inbound 01", action_type="save"):
    """
    Eksekusi transaksi atomik registrasi Gate In truk kontainer:
    1. Sinkronisasi master data (Expedition, Driver, Truck, Container).
    2. Generate nomor antrian harian concurrency-safe via DailyQueueSequence.
    3. Simpan QueueEntry dengan status MENUNGGU atau TERTAHAN.
    4. Catat QueueStatusLog awal secara otomatis.
    """
    with transaction.atomic():
        today = timezone.localdate()

        # 1. Sinkronisasi Master Expedition
        expedisi_name = cleaned_data['nama_ekspedisi'].strip()
        kode_ekspedisi = cleaned_data.get('kode_ekspedisi', '').strip() or None
        expedisi, _ = Expedition.objects.get_or_create(
            nama_perusahaan=expedisi_name,
            defaults={
                'kode_ekspedisi': kode_ekspedisi,
                'is_active': True
            }
        )

        # 2. Sinkronisasi Master Driver
        no_sim = cleaned_data['no_sim_driver'].strip()
        nama_driver = cleaned_data['nama_driver'].strip()
        no_hp = cleaned_data['no_hp_driver'].strip()
        driver, driver_created = Driver.objects.get_or_create(
            no_sim=no_sim,
            defaults={
                'nama': nama_driver,
                'no_hp': no_hp,
                'is_active': True
            }
        )
        if not driver_created and (driver.nama != nama_driver or driver.no_hp != no_hp):
            driver.nama = nama_driver
            driver.no_hp = no_hp
            driver.save(update_fields=['nama', 'no_hp'])

        # 3. Sinkronisasi Master Truck
        no_polisi = cleaned_data['no_polisi']
        konfigurasi = cleaned_data['konfigurasi']
        rfid_tag = cleaned_data.get('rfid_tag', '').strip() or None
        truck, truck_created = Truck.objects.get_or_create(
            no_polisi=no_polisi,
            defaults={
                'konfigurasi': konfigurasi,
                'expedisi': expedisi,
                'driver': driver,
                'rfid_tag': rfid_tag,
                'is_active': True
            }
        )
        if not truck_created:
            truck.konfigurasi = konfigurasi
            truck.expedisi = expedisi
            truck.driver = driver
            if rfid_tag:
                truck.rfid_tag = rfid_tag
            truck.save(update_fields=['konfigurasi', 'expedisi', 'driver', 'rfid_tag'])

        # 4. Sinkronisasi Master Container (jika membawa kontainer)
        container_obj = None
        if cleaned_data.get('has_container'):
            no_kontainer = cleaned_data['no_kontainer']
            ukuran = cleaned_data.get('ukuran') or Container.ContainerSizeChoice.SIZE_40
            tipe = cleaned_data.get('tipe') or Container.ContainerTypeChoice.DRY
            kategori = cleaned_data.get('kategori') or Container.CargoCategoryChoice.IMPORT
            berat_kotor = cleaned_data.get('berat_kotor') or 0
            shipping_line = cleaned_data.get('shipping_line', '').strip() or None
            seal_number = cleaned_data.get('seal_number', '').strip() or None
            ref_dokumen = cleaned_data.get('ref_dokumen', '').strip() or None
            status_vgm = cleaned_data.get('status_vgm') or Container.VGMStatusChoice.VERIFIED

            container_obj, container_created = Container.objects.get_or_create(
                no_kontainer=no_kontainer,
                defaults={
                    'ukuran': ukuran,
                    'tipe': tipe,
                    'kategori': kategori,
                    'berat_kotor': berat_kotor,
                    'shipping_line': shipping_line,
                    'seal_number': seal_number,
                    'ref_dokumen': ref_dokumen,
                    'status_vgm': status_vgm,
                }
            )
            if not container_created:
                # Perbarui atribut siklus kargo terbaru kontainer
                container_obj.ukuran = ukuran
                container_obj.tipe = tipe
                container_obj.kategori = kategori
                container_obj.berat_kotor = berat_kotor
                container_obj.shipping_line = shipping_line
                container_obj.seal_number = seal_number
                container_obj.ref_dokumen = ref_dokumen
                container_obj.status_vgm = status_vgm
                container_obj.save()

        # 5. Generate Nomor Antrian Harian Concurrency-Safe
        no_antrian = DailyQueueSequence.get_next_number(today)

        # 6. Tentukan Status Awal
        if action_type == 'hold':
            initial_status = QueueEntry.QueueStatus.TERTAHAN
            alasan_hold = cleaned_data.get('alasan_tertahan', '').strip() or "Tertahan di pemeriksaan Gate In"
        else:
            initial_status = QueueEntry.QueueStatus.MENUNGGU
            alasan_hold = None

        user_operator = operator_user if operator_user and operator_user.is_authenticated else None

        # 7. Simpan Record Transaksi QueueEntry
        queue_entry = QueueEntry.objects.create(
            tanggal=today,
            no_antrian=no_antrian,
            truck=truck,
            driver=driver,
            container=container_obj,
            status=initial_status,
            alasan_tertahan=alasan_hold,
            gerbang_lane=cleaned_data['gerbang_lane'],
            booth=booth_name,
            operator=user_operator,
            alokasi_blok=cleaned_data.get('alokasi_blok', '').strip() or None,
            alokasi_bay=cleaned_data.get('alokasi_bay', '').strip() or None,
            alokasi_row=cleaned_data.get('alokasi_row', '').strip() or None,
            alokasi_tier=cleaned_data.get('alokasi_tier', '').strip() or None,
            catatan=cleaned_data.get('catatan', '').strip() or None,
            waktu_masuk=timezone.now(),
        )

        # 8. Simpan Audit Log Perdana QueueStatusLog
        if initial_status == QueueEntry.QueueStatus.TERTAHAN:
            log_keterangan = f"Truk ditahan di Gate In ({booth_name}): {alasan_hold}"
        else:
            log_keterangan = f"Registrasi Gate In berhasil via {booth_name} ({queue_entry.gerbang_lane})"

        QueueStatusLog.objects.create(
            queue_entry=queue_entry,
            status_lama=None,
            status_baru=initial_status,
            operator=user_operator,
            keterangan=log_keterangan,
            timestamp=timezone.now(),
        )

        return queue_entry


class QueueTransitionError(Exception):
    """Exception dilempar saat transisi status antrian tidak valid."""
    pass


class QueueValidationError(Exception):
    """Exception dilempar saat validasi data status (seperti alasan hold) gagal."""
    pass


ALLOWED_TRANSITIONS = {
    QueueEntry.QueueStatus.MENUNGGU: [QueueEntry.QueueStatus.PROSES],
    QueueEntry.QueueStatus.PROSES: [QueueEntry.QueueStatus.TERTAHAN, QueueEntry.QueueStatus.SELESAI],
    QueueEntry.QueueStatus.TERTAHAN: [QueueEntry.QueueStatus.PROSES],
    QueueEntry.QueueStatus.SELESAI: [QueueEntry.QueueStatus.KELUAR],
    QueueEntry.QueueStatus.KELUAR: [],
}


def process_queue_transition(queue_entry_or_id, target_status, operator_user=None, reason=None, lane=None):
    """
    Memproses perpindahan status antrian secara atomik dan tervalidasi.
    Alur yang diizinkan:
    MENUNGGU -> PROSES -> TERTAHAN (opsional) -> PROSES -> SELESAI -> KELUAR

    Menjamin pencatatan waktu otomatis, pencatatan operator, dan QueueStatusLog.
    """
    with transaction.atomic():
        if isinstance(queue_entry_or_id, QueueEntry):
            queue_entry = QueueEntry.objects.select_for_update().get(pk=queue_entry_or_id.pk)
        else:
            queue_entry = QueueEntry.objects.select_for_update().get(pk=queue_entry_or_id)

        current_status = queue_entry.status
        target_status = str(target_status).strip().upper()

        # 1. Validasi nilai status target
        valid_choices = [c[0] for c in QueueEntry.QueueStatus.choices]
        if target_status not in valid_choices:
            raise QueueValidationError(f"Status target '{target_status}' tidak valid.")

        # 2. Validasi transisi status yang diizinkan
        allowed = ALLOWED_TRANSITIONS.get(current_status, [])
        if target_status not in allowed:
            current_label = queue_entry.get_status_display()
            target_label = dict(QueueEntry.QueueStatus.choices).get(target_status, target_status)
            raise QueueTransitionError(
                f"Transisi status dari '{current_label}' ke '{target_label}' tidak diizinkan."
            )

        now = timezone.now()
        user_operator = operator_user if operator_user and operator_user.is_authenticated else None
        clean_reason = (reason or "").strip()[:255]
        log_keterangan = ""

        # 3. Logika per status
        if target_status == QueueEntry.QueueStatus.PROSES:
            if current_status == QueueEntry.QueueStatus.MENUNGGU:
                # Transisi MENUNGGU -> PROSES
                if not queue_entry.waktu_mulai_proses:
                    queue_entry.waktu_mulai_proses = now
                log_keterangan = clean_reason or "Mulai proses penanganan antrian di terminal/yard"
            elif current_status == QueueEntry.QueueStatus.TERTAHAN:
                # Transisi TERTAHAN -> PROSES (Lanjut setelah Hold)
                # waktu_mulai_proses tidak di-reset
                if not queue_entry.waktu_mulai_proses:
                    queue_entry.waktu_mulai_proses = now
                # alasan_tertahan tetap tersimpan sebagai informasi histori
                prev_hold_info = f" (Alasan hold sebelumnya: {queue_entry.alasan_tertahan})" if queue_entry.alasan_tertahan else ""
                log_keterangan = clean_reason or f"Melanjutkan proses antrian setelah ditahan{prev_hold_info}"

            queue_entry.status = QueueEntry.QueueStatus.PROSES

        elif target_status == QueueEntry.QueueStatus.TERTAHAN:
            # Transisi PROSES -> TERTAHAN
            if not clean_reason:
                raise QueueValidationError("Alasan tertahan (Hold) wajib diisi.")

            queue_entry.status = QueueEntry.QueueStatus.TERTAHAN
            queue_entry.alasan_tertahan = clean_reason
            log_keterangan = f"Tertahan: {clean_reason}"

        elif target_status == QueueEntry.QueueStatus.SELESAI:
            # Transisi PROSES -> SELESAI
            queue_entry.status = QueueEntry.QueueStatus.SELESAI
            queue_entry.waktu_selesai = now
            log_keterangan = clean_reason or "Pekerjaan dan proses yard selesai"

        elif target_status == QueueEntry.QueueStatus.KELUAR:
            # Transisi SELESAI -> KELUAR
            queue_entry.status = QueueEntry.QueueStatus.KELUAR
            queue_entry.waktu_keluar = now
            if lane:
                queue_entry.gerbang_lane = lane
            log_keterangan = clean_reason or f"Truk keluar terminal (Gate Out) via {queue_entry.gerbang_lane}"

        queue_entry.save()

        # 4. Setiap perubahan status WAJIB masuk QueueStatusLog
        status_log = QueueStatusLog.objects.create(
            queue_entry=queue_entry,
            status_lama=current_status,
            status_baru=target_status,
            operator=user_operator,
            keterangan=log_keterangan[:255],
            timestamp=now,
        )

        return queue_entry, status_log

