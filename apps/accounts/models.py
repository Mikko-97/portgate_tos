from django.db import models
from django.contrib.auth.models import User


class ShiftChoice(models.TextChoices):
    SHIFT_1 = 'SHIFT_1', 'Shift 1 (08:00 - 16:00)'
    SHIFT_2 = 'SHIFT_2', 'Shift 2 (16:00 - 24:00)'
    SHIFT_3 = 'SHIFT_3', 'Shift 3 (00:00 - 08:00)'


class BoothChoice(models.TextChoices):
    GATE_IN_01 = 'GATE_IN_01', 'Gate Inbound 01'
    GATE_IN_02 = 'GATE_IN_02', 'Gate Inbound 02'
    GATE_IN_03 = 'GATE_IN_03', 'Gate Inbound 03 (Auto OCR)'
    GATE_IN_04 = 'GATE_IN_04', 'Gate Inbound 04 (Trouble/Hold)'
    GATE_IN_05 = 'GATE_IN_05', 'Gate Inbound 05 (Empty Return)'
    GATE_IN_06 = 'GATE_IN_06', 'Gate Inbound 06 (Dedicated)'
    GATE_OUT_01 = 'GATE_OUT_01', 'Gate Outbound 01 (Dispatch)'
    GATE_OUT_02 = 'GATE_OUT_02', 'Gate Outbound 02 (Bypass)'
    CENTRAL_DESK = 'CENTRAL_DESK', 'Central Desk / Supervisor'


class OperatorProfile(models.Model):
    """
    Menyimpan data identitas operasional petugas terminal (Gate/Operator/Supervisor)
    yang terhubung One-to-One dengan User bawaan Django.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='operator_profile',
        verbose_name="Akun User"
    )
    nip = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="NIP / ID Operator"
    )
    nama = models.CharField(
        max_length=150,
        verbose_name="Nama Lengkap Operator"
    )
    booth_aktif = models.CharField(
        max_length=50,
        choices=BoothChoice.choices,
        blank=True,
        null=True,
        verbose_name="Booth / Gate Aktif"
    )
    shift_aktif = models.CharField(
        max_length=20,
        choices=ShiftChoice.choices,
        blank=True,
        null=True,
        verbose_name="Shift Aktif"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Diperbarui Pada")

    class Meta:
        db_table = 'accounts_operator_profile'
        verbose_name = "Profil Operator"
        verbose_name_plural = "Profil Operator"
        ordering = ['nama']

    def __str__(self):
        return f"{self.nip} - {self.nama} ({self.get_shift_aktif_display() if self.shift_aktif else 'No Shift'})"
