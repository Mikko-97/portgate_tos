from django.contrib import admin
from .models import DailyQueueSequence, QueueEntry, QueueStatusLog


class QueueStatusLogInLine(admin.TabularInline):
    model = QueueStatusLog
    extra = 0
    readonly_fields = ('status_lama', 'status_baru', 'operator', 'keterangan', 'timestamp')
    can_delete = False


@admin.register(DailyQueueSequence)
class DailyQueueSequenceAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'last_number')
    ordering = ('-tanggal',)


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = (
        'no_antrian',
        'tanggal',
        'truck',
        'driver',
        'container',
        'status',
        'gerbang_lane',
        'booth',
        'waktu_masuk',
        'waktu_selesai',
        'waktu_keluar',
    )
    list_filter = (
        'status',
        'gerbang_lane',
        'booth',
        'tanggal',
    )
    search_fields = (
        'no_antrian',
        'truck__no_polisi',
        'driver__nama',
        'container__no_kontainer',
        'alasan_tertahan',
    )
    autocomplete_fields = ('truck', 'driver', 'container', 'operator')
    date_hierarchy = 'tanggal'
    ordering = ('-waktu_masuk',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [QueueStatusLogInLine]


@admin.register(QueueStatusLog)
class QueueStatusLogAdmin(admin.ModelAdmin):
    list_display = (
        'queue_entry',
        'status_lama',
        'status_baru',
        'operator',
        'timestamp',
    )
    list_filter = (
        'status_baru',
        'status_lama',
        'timestamp',
    )
    search_fields = (
        'queue_entry__no_antrian',
        'queue_entry__truck__no_polisi',
        'operator__username',
        'keterangan',
    )
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)
