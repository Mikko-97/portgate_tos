from django.db import models


class Expedition(models.Model):
    """
    Perusahaan ekspedisi / transportir truk angkutan peti kemas.
    """
    nama_perusahaan = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nama Perusahaan Ekspedisi"
    )
    kode_ekspedisi = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name="Kode Ekspedisi"
    )
    no_telepon = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name="No Telepon"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Status Aktif"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Diperbarui Pada")

    class Meta:
        db_table = 'masterdata_expedition'
        verbose_name = "Perusahaan Ekspedisi"
        verbose_name_plural = "Perusahaan Ekspedisi"
        ordering = ['nama_perusahaan']

    def __str__(self):
        return f"{self.nama_perusahaan} ({self.kode_ekspedisi})" if self.kode_ekspedisi else self.nama_perusahaan


class Driver(models.Model):
    """
    Data pengemudi truk berlisensi resmi terminal/pelabuhan.
    """
    nama = models.CharField(
        max_length=150,
        verbose_name="Nama Lengkap Sopir"
    )
    no_hp = models.CharField(
        max_length=25,
        verbose_name="No HP / WhatsApp"
    )
    no_sim = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Nomor SIM"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Status Aktif"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Diperbarui Pada")

    class Meta:
        db_table = 'masterdata_driver'
        verbose_name = "Sopir Truk"
        verbose_name_plural = "Sopir Truk"
        ordering = ['nama']

    def __str__(self):
        return f"{self.nama} - SIM: {self.no_sim}"


class Truck(models.Model):
    """
    Armada truk kontainer.
    """
    class TruckConfigChoice(models.TextChoices):
        TRAILER_20 = 'TRAILER_20', 'Trailer 20ft / Single Axle'
        TRAILER_40 = 'TRAILER_40', 'Trailer 40ft / Multi Axle'
        TRONTON = 'TRONTON', 'Tronton Head Truck'
        FLATBED = 'FLATBED', 'Dump / Flatbed Carrier'
        LOWBED = 'LOWBED', 'Lowbed Heavy-Lift Carrier'

    no_polisi = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name="Nomor Polisi"
    )
    konfigurasi = models.CharField(
        max_length=50,
        choices=TruckConfigChoice.choices,
        default=TruckConfigChoice.TRAILER_40,
        verbose_name="Konfigurasi Truk"
    )
    rfid_tag = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name="RFID Tag CMS"
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trucks',
        verbose_name="Sopir Tetap / Default"
    )
    expedisi = models.ForeignKey(
        Expedition,
        on_delete=models.PROTECT,
        related_name='trucks',
        verbose_name="Perusahaan Ekspedisi"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Status Aktif"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Diperbarui Pada")

    class Meta:
        db_table = 'masterdata_truck'
        verbose_name = "Truk Armada"
        verbose_name_plural = "Truk Armada"
        ordering = ['no_polisi']

    def __str__(self):
        return f"{self.no_polisi} - {self.expedisi.nama_perusahaan}"


class Container(models.Model):
    """
    Peti kemas / kontainer standar ISO 6346 beserta status muatannya.
    """
    class ContainerSizeChoice(models.TextChoices):
        SIZE_20 = '20ft', '20 Feet'
        SIZE_40 = '40ft', '40 Feet'
        SIZE_45 = '45ft', '45 Feet'

    class ContainerTypeChoice(models.TextChoices):
        DRY = 'DRY', 'Dry / General Purpose'
        REEFER = 'REEFER', 'Refrigerated'
        FLAT_RACK = 'FLAT_RACK', 'Flat Rack'
        OPEN_TOP = 'OPEN_TOP', 'Open Top'
        TANK = 'TANK', 'ISO Tank'

    class CargoCategoryChoice(models.TextChoices):
        IMPORT = 'IMPORT', 'Import Full'
        EXPORT = 'EXPORT', 'Export Full'
        EMPTY_RETURN = 'EMPTY_RETURN', 'Empty Return'

    class VGMStatusChoice(models.TextChoices):
        VERIFIED = 'VERIFIED', 'Verified'
        PENDING = 'PENDING', 'Pending'

    no_kontainer = models.CharField(
        max_length=15,
        unique=True,
        db_index=True,
        verbose_name="Nomor Kontainer (ISO 6346)"
    )
    ukuran = models.CharField(
        max_length=10,
        choices=ContainerSizeChoice.choices,
        default=ContainerSizeChoice.SIZE_40,
        verbose_name="Ukuran Kontainer"
    )
    tipe = models.CharField(
        max_length=30,
        choices=ContainerTypeChoice.choices,
        default=ContainerTypeChoice.DRY,
        verbose_name="Tipe Kontainer"
    )
    kategori = models.CharField(
        max_length=30,
        choices=CargoCategoryChoice.choices,
        default=CargoCategoryChoice.IMPORT,
        verbose_name="Kategori Muatan"
    )
    berat_kotor = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Berat kotor muatan dalam satuan kilogram (kg)",
        verbose_name="Berat Kotor (kg)"
    )
    shipping_line = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Shipping Line / Pelayaran"
    )
    seal_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Nomor Segel (Seal)"
    )
    ref_dokumen = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="No Booking / DO / SPPB"
    )
    status_vgm = models.CharField(
        max_length=20,
        choices=VGMStatusChoice.choices,
        default=VGMStatusChoice.VERIFIED,
        verbose_name="Status VGM"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Status Aktif"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Diperbarui Pada")

    class Meta:
        db_table = 'masterdata_container'
        verbose_name = "Kontainer"
        verbose_name_plural = "Kontainer"
        ordering = ['no_kontainer']

    def __str__(self):
        return f"{self.no_kontainer} ({self.ukuran} {self.tipe} - {self.get_kategori_display()})"
