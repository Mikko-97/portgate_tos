from django.contrib import admin
from .models import OperatorProfile


@admin.register(OperatorProfile)
class OperatorProfileAdmin(admin.ModelAdmin):
    list_display = (
        'nip',
        'nama',
        'user',
        'shift_aktif',
        'booth_aktif',
        'created_at',
    )
    list_filter = (
        'shift_aktif',
        'booth_aktif',
        'created_at',
    )
    search_fields = (
        'nip',
        'nama',
        'user__username',
        'user__email',
    )
    ordering = ('nama',)
    readonly_fields = ('created_at', 'updated_at')
