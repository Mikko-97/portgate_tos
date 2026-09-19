from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone


class DailyQueueSequence(models.Model):
    """
    Tabel penghitung urutan antrian harian (concurrency-safe).
    Menggunakan select_for_update() di PostgreSQL agar ketika beberapa
    operator mendaftarkan truk secara bersamaan, nomor antrian tetap
    berurutan (Q-0001, Q-0002, dst.) tanpa risiko duplikasi atau race condition.
    """
    tanggal = models.DateField(
        unique=True,
        default=timezone.localdate,
        verbose_name="Tanggal Antrian"
    )
    last_number = models.PositiveIntegerField(
        default=0,
        verbose_name="Nomor Urut Terakhir"
    )

    class Meta:
        db_table = 'queue_gate_daily_sequence'
        verbose_name = "Urutan Antrian Harian"
        verbose_name_plural = "Urutan Antrian Harian"

    def __str__(self):
        return f"{self.tanggal}: Q-{self.last_number:04d}"

    @classmethod
    def get_next_number(cls, date=None):
        """
        Menghasilkan nomor antrian harian berikutnya dengan row-level lock
        (select_for_update) di dalam transaksi database atomik.
        """
        if date is None:
            date = timezone.localdate()

        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(
                tanggal=date,
                defaults={'last_number': 0}
            )
            seq.last_number += 1
            seq.save(update_fields=['last_number'])
            return f"Q-{seq.last_number:04d}"


class QueueEntry(models.Model):
    """
    Transaksi operasional antrian truk kontainer dari Gate In hingga Gate Out.
    """
    class QueueStatus(models.TextChoices):
        MENUNGGU = 'MENUNGGU', 'Menunggu Buffer Gate'
        PROSES = 'PROSES', 'Sedang Proses di Booth / Yard'
        TERTAHAN = 'TERTAHAN', 'Tertahan / Hold'
        SELESAI = 'SELESAI', 'Selesai di Yard'
        KELUAR = 'KELUAR', 'Keluar Terminal (Gate Out)'

    class LaneChoice(models.TextChoices):
        LANE_01 = 'Lane 01 - Dry In', 'Lane 01 — Dry In'
        LANE_02 = 'Lane 02 - Reefer', 'Lane 02 — Reefer'
        LANE_03 = 'Lane 03 - Auto OCR', 'Lane 03 — Auto OCR'
        LANE_04 = 'Lane 04 - Trouble', 'Lane 04 — Trouble / Hold'
        LANE_05 = 'Lane 05 - Empty', 'Lane 05 — Empty Return'
        LANE_06 = 'Lane 06 - Dedicated', 'Lane 06 — Dedicated'
        OUT_01 = 'Out 01 - Dispatch', 'Out 01 — Dispatch'
        OUT_02 = 'Out 02 - Bypass', 'Out 02 — Bypass'

    tanggal = models.DateField(
        default=timezone.localdate,
        db_index=True,
        verbose_name="Tanggal Operasional"
    )
    no_antrian = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name="Nomor Antrian (Format Q-0001)"
    )
    truck = models.ForeignKey(
        'masterdata.Truck',
        on_delete=models.PROTECT,
        related_name='queue_entries',
        verbose_name="Truk Armada"
    )
    driver = models.ForeignKey(
        'masterdata.Driver',
        on_delete=models.PROTECT,
        related_name='queue_entries',
        verbose_name="Sopir Aktual"
    )
    container = models.ForeignKey(
        'masterdata.Container',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='queue_entries',
        verbose_name="Peti Kemas / Kontainer"
    )
    status = models.CharField(
        max_length=25,
        choices=QueueStatus.choices,
        default=QueueStatus.MENUNGGU,
        db_index=True,
        verbose_name="Status Antrian"
    )
    alasan_tertahan = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Alasan Tertahan (Hold)"
    )
    gerbang_lane = models.CharField(
        max_length=50,
        choices=LaneChoice.choices,
        default=LaneChoice.LANE_01,
        verbose_name="Lane / Jalur Gerbang"
    )
    booth = models.CharField(
        max_length=50,
        default='Gate Inbound 01',
        verbose_name="Booth Pendaftaran"
    )
    operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='queue_handled',
        verbose_name="Operator Pendaftar"
    )
    # Alokasi Yard Lapangan (diisi manual sesuai PRD)
    alokasi_blok = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Yard Block"
    )
    alokasi_bay = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        verbose_name="Yard Bay"
    )
    alokasi_row = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        verbose_name="Yard Row"
    )
    alokasi_tier = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        verbose_name="Yard Tier"
    )
    # Stempel Waktu Lifecycle (Stepper 4 Tahap)
    waktu_masuk = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name="Waktu Gate In"
    )
    waktu_mulai_proses = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Waktu Mulai Proses"
    )
    waktu_selesai = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Waktu Selesai Yard"
    )
    waktu_keluar = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Waktu Gate Out"
    )
    catatan = models.TextField(
        blank=True,
        null=True,
        verbose_name="Catatan Operasional"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Diperbarui Pada")

    class Meta:
        db_table = 'queue_gate_entry'
        verbose_name = "Antrian Truk"
        verbose_name_plural = "Antrian Truk"
        ordering = ['-waktu_masuk']
        constraints = [
            models.UniqueConstraint(
                fields=['tanggal', 'no_antrian'],
                name='unique_daily_queue_number'
            )
        ]

    def __str__(self):
        return f"[{self.no_antrian}] {self.truck.no_polisi} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Auto-generate nomor antrian harian jika belum terisi
        if not self.no_antrian:
            if not self.tanggal:
                self.tanggal = timezone.localdate()
            self.no_antrian = DailyQueueSequence.get_next_number(self.tanggal)
        super().save(*args, **kwargs)


class QueueStatusLog(models.Model):
    """
    Audit log / riwayat perpindahan status antrian secara kronologis.
    """
    queue_entry = models.ForeignKey(
        QueueEntry,
        on_delete=models.CASCADE,
        related_name='status_logs',
        verbose_name="Antrian Terkait"
    )
    status_lama = models.CharField(
        max_length=25,
        choices=QueueEntry.QueueStatus.choices,
        blank=True,
        null=True,
        verbose_name="Status Lama"
    )
    status_baru = models.CharField(
        max_length=25,
        choices=QueueEntry.QueueStatus.choices,
        verbose_name="Status Baru"
    )
    operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Operator Pengubah"
    )
    keterangan = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Keterangan / Alasan"
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name="Waktu Perubahan"
    )

    class Meta:
        db_table = 'queue_gate_status_log'
        verbose_name = "Audit Log Status Antrian"
        verbose_name_plural = "Audit Log Status Antrian"
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.queue_entry.no_antrian}: {self.status_lama or '-'} -> {self.status_baru} ({self.timestamp:%H:%M:%S})"
