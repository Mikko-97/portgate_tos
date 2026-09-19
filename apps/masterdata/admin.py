from django.contrib import admin
from .models import Expedition, Driver, Truck, Container


@admin.register(Expedition)
class ExpeditionAdmin(admin.ModelAdmin):
    list_display = (
        'nama_perusahaan',
        'kode_ekspedisi',
        'no_telepon',
        'is_active',
        'created_at',
    )
    list_filter = (
        'is_active',
        'created_at',
    )
    search_fields = (
        'nama_perusahaan',
        'kode_ekspedisi',
        'no_telepon',
    )
    ordering = ('nama_perusahaan',)


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = (
        'nama',
        'no_sim',
        'no_hp',
        'is_active',
        'created_at',
    )
    list_filter = (
        'is_active',
        'created_at',
    )
    search_fields = (
        'nama',
        'no_sim',
        'no_hp',
    )
    ordering = ('nama',)


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = (
        'no_polisi',
        'konfigurasi',
        'expedisi',
        'driver',
        'rfid_tag',
        'is_active',
    )
    list_filter = (
        'konfigurasi',
        'expedisi',
        'is_active',
    )
    search_fields = (
        'no_polisi',
        'rfid_tag',
        'driver__nama',
        'expedisi__nama_perusahaan',
    )
    autocomplete_fields = ('driver', 'expedisi')
    ordering = ('no_polisi',)


@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = (
        'no_kontainer',
        'ukuran',
        'tipe',
        'kategori',
        'berat_kotor',
        'shipping_line',
        'seal_number',
        'status_vgm',
    )
    list_filter = (
        'ukuran',
        'tipe',
        'kategori',
        'status_vgm',
    )
    search_fields = (
        'no_kontainer',
        'shipping_line',
        'seal_number',
        'ref_dokumen',
    )
    ordering = ('no_kontainer',)
