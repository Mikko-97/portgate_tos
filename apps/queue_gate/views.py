import re
import csv
import json
import math
from datetime import datetime, timedelta
from urllib.parse import quote as urlquote
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import DetailView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from apps.accounts.mixins import OperationalAccessMixin
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import ExtractHour
from apps.masterdata.models import Truck, Container
from apps.queue_gate.models import QueueEntry, QueueStatusLog
from apps.queue_gate.forms import GateInForm, GateOutProcessForm
from apps.queue_gate.services import (
    process_gate_in_registration,
    process_queue_transition,
    QueueTransitionError,
    QueueValidationError,
)
from apps.queue_gate.ocr_service import process_ocr_plate


class DashboardView(OperationalAccessMixin, View):
    """
    Dashboard Operasional Situational Awareness untuk Terminal Operating System (TOS).
    Menampilkan data aktual dari database:
    - Ringkasan jumlah antrian hari ini (Menunggu, Proses, Tertahan, Selesai, Keluar, Total).
    - Monitoring antrian aktif beserta durasi/progres.
    - Aktivitas/status audit log terkini.
    - Distribusi volume antrian per jam hari ini.
    - Status lane/gerbang dan simulasi telemetri TOS.
    """
    template_name = 'queue_gate/dashboard.html'

    def get_operator_info(self, request):
        booth = request.session.get('assigned_booth_label', 'Gate Inbound 01')
        shift = 'Shift 1 (08:00 - 16:00)'
        nip = 'OP-001'
        nama_petugas = 'Petugas Gate'

        if request.user.is_authenticated:
            nama_petugas = request.user.get_full_name() or request.user.username
            if hasattr(request.user, 'operator_profile') and request.user.operator_profile:
                prof = request.user.operator_profile
                nip = prof.nip or nip
                nama_petugas = prof.nama or nama_petugas
                if prof.booth_aktif:
                    booth = prof.get_booth_aktif_display()
                if prof.shift_aktif:
                    shift = prof.get_shift_aktif_display()

        return {
            'booth': booth,
            'shift': shift,
            'nip': nip,
            'nama_petugas': nama_petugas
        }

    def get(self, request):
        today = timezone.localdate()
        now = timezone.now()
        today_qs = QueueEntry.objects.filter(tanggal=today)

        # 1. Ringkasan Status Antrian Hari Ini (Data Aktual Database)
        count_menunggu = today_qs.filter(status=QueueEntry.QueueStatus.MENUNGGU).count()
        count_proses = today_qs.filter(status=QueueEntry.QueueStatus.PROSES).count()
        count_tertahan = today_qs.filter(status=QueueEntry.QueueStatus.TERTAHAN).count()
        count_selesai = today_qs.filter(status=QueueEntry.QueueStatus.SELESAI).count()
        count_total = today_qs.count()
        count_gate_in = count_total  # Setiap QueueEntry pada hari ini adalah pendaftaran Gate In
        count_gate_out = QueueEntry.objects.filter(
            Q(waktu_keluar__date=today) | Q(tanggal=today, status=QueueEntry.QueueStatus.KELUAR)
        ).distinct().count()
        count_keluar = count_gate_out
        count_aktif = count_menunggu + count_proses + count_tertahan

        # Buffer capacity estimate (40 truk)
        buffer_capacity = 40
        buffer_occupancy_pct = min(100, int((count_menunggu / buffer_capacity) * 100)) if buffer_capacity else 0

        # 2. Monitoring Antrian Aktif
        active_entries = QueueEntry.objects.filter(
            status__in=[
                QueueEntry.QueueStatus.MENUNGGU,
                QueueEntry.QueueStatus.PROSES,
                QueueEntry.QueueStatus.TERTAHAN
            ]
        ).select_related('truck', 'driver', 'container', 'truck__expedisi').order_by('waktu_masuk')

        active_list = []
        for q in active_entries:
            # Hitung durasi sejak masuk
            elapsed_seconds = max(0, int((now - q.waktu_masuk).total_seconds()))
            mins = elapsed_seconds // 60
            secs = elapsed_seconds % 60
            duration_str = f"{mins}m {secs:02d}s" if mins < 60 else f"{mins // 60}j {mins % 60}m"

            # Durasi proses jika sudah mulai proses
            process_duration_str = "-"
            if q.waktu_mulai_proses:
                p_seconds = max(0, int((now - q.waktu_mulai_proses).total_seconds()))
                p_mins = p_seconds // 60
                p_secs = p_seconds % 60
                process_duration_str = f"{p_mins}m {p_secs:02d}s"

            active_list.append({
                'entry': q,
                'duration': duration_str,
                'process_duration': process_duration_str,
            })

        # 3. Rata-rata Waktu Proses Riil (Dari Waktu Mulai Proses hingga Selesai Yard)
        process_durations = []
        for e in today_qs.filter(waktu_mulai_proses__isnull=False, waktu_selesai__isnull=False):
            d = (e.waktu_selesai - e.waktu_mulai_proses).total_seconds()
            if d >= 0:
                process_durations.append(d)

        # Jika belum ada yang selesai hari ini, hitung durasi berjalan dari truk yang sedang berproses
        if not process_durations:
            for e in today_qs.filter(status=QueueEntry.QueueStatus.PROSES, waktu_mulai_proses__isnull=False):
                d = (now - e.waktu_mulai_proses).total_seconds()
                if d >= 0:
                    process_durations.append(d)

        if process_durations:
            avg_seconds = sum(process_durations) / len(process_durations)
            avg_mins = avg_seconds / 60
            if avg_mins < 1:
                avg_process_str = f"{int(avg_seconds)} dtk"
            elif avg_mins < 60:
                avg_process_str = f"{avg_mins:.1f} Menit"
            else:
                avg_process_str = f"{int(avg_mins // 60)}j {int(avg_mins % 60)}m"
        else:
            avg_process_str = "0 Menit"

        avg_booth_str = avg_process_str

        # 4. Distribusi Status Antrian Hari Ini (Persentase Riil)
        status_distribution = [
            {
                'key': 'MENUNGGU',
                'label': 'Menunggu Buffer',
                'count': count_menunggu,
                'pct': round((count_menunggu / count_total * 100), 1) if count_total > 0 else 0,
                'badge_color': 'bg-surface-container text-on-surface border border-outline-variant',
                'bar_color': 'bg-outline',
                'icon': 'hourglass_empty',
            },
            {
                'key': 'PROSES',
                'label': 'Sedang Proses',
                'count': count_proses,
                'pct': round((count_proses / count_total * 100), 1) if count_total > 0 else 0,
                'badge_color': 'bg-secondary text-on-secondary',
                'bar_color': 'bg-secondary',
                'icon': 'sync_saved_locally',
            },
            {
                'key': 'TERTAHAN',
                'label': 'Tertahan (Hold)',
                'count': count_tertahan,
                'pct': round((count_tertahan / count_total * 100), 1) if count_total > 0 else 0,
                'badge_color': 'bg-tertiary-container text-on-tertiary-container',
                'bar_color': 'bg-tertiary-container',
                'icon': 'warning',
            },
            {
                'key': 'SELESAI',
                'label': 'Selesai di Yard',
                'count': count_selesai,
                'pct': round((count_selesai / count_total * 100), 1) if count_total > 0 else 0,
                'badge_color': 'bg-primary-container text-primary-fixed border border-primary',
                'bar_color': 'bg-primary-container',
                'icon': 'fact_check',
            },
            {
                'key': 'KELUAR',
                'label': 'Gate Out (Keluar)',
                'count': count_gate_out,
                'pct': round((count_gate_out / count_total * 100), 1) if count_total > 0 else 0,
                'badge_color': 'bg-primary text-on-primary',
                'bar_color': 'bg-primary',
                'icon': 'output',
            },
        ]

        # 5. Agregasi Throughput Per Jam Hari Ini (06:00 - 20:00 WIB, Timezone Aware)
        hourly_counts = {h: 0 for h in range(6, 21)}
        for entry in today_qs:
            if entry.waktu_masuk:
                h = timezone.localtime(entry.waktu_masuk).hour
                if 6 <= h <= 20:
                    hourly_counts[h] += 1

        max_hourly_val = max(list(hourly_counts.values()) + [1])
        current_hour = timezone.localtime(now).hour
        hourly_chart = []
        for h in range(6, 21):
            val = hourly_counts[h]
            is_live = (h == current_hour)
            is_estimate = (h > current_hour)
            is_peak = (val == max_hourly_val and val > 0)

            if val > 0:
                pct = max(14, min(100, int((val / max_hourly_val) * 92)))
            else:
                pct = 4 if is_estimate else 2

            note = ""
            if is_peak:
                note = f"Puncak: {val} Truk"
            elif is_live:
                note = f"Live: {val} Truk"
            elif h == 12:
                note = "Shift Siang"

            if is_peak:
                bar_color = "bg-tertiary-container hover:bg-tertiary"
            elif is_live:
                bar_color = "bg-primary hover:bg-primary-container"
            elif is_estimate:
                bar_color = "bg-surface-variant hover:bg-surface-container-high border border-dashed border-outline"
            else:
                bar_color = "bg-secondary hover:bg-secondary-container"

            hourly_chart.append({
                'hour': f"{h:02d}:00",
                'hour_label': f"{h:02d}:00",
                'count': val,
                'pct': pct,
                'is_live': is_live,
                'is_peak': is_peak,
                'is_estimate': is_estimate,
                'note': note,
                'bar_color': bar_color,
            })

        # 6. Aktivitas / Log Perubahan Status Terkini (Gate In / Gate Out Realtime Feed)
        recent_logs = QueueStatusLog.objects.select_related(
            'queue_entry', 'operator', 'queue_entry__truck', 'queue_entry__container', 'queue_entry__truck__expedisi'
        ).order_by('-timestamp')[:10]

        recent_activities = []
        for log in recent_logs:
            activity_type = 'MUTASI'
            badge_class = 'bg-surface-container text-on-surface'
            icon = 'swap_horiz'

            if log.status_baru == QueueEntry.QueueStatus.MENUNGGU and log.status_lama is None:
                activity_type = 'GATE IN'
                badge_class = 'bg-secondary text-on-secondary'
                icon = 'login'
            elif log.status_baru == QueueEntry.QueueStatus.PROSES:
                activity_type = 'PROSES'
                badge_class = 'bg-secondary-fixed text-on-secondary-fixed'
                icon = 'sync_saved_locally'
            elif log.status_baru == QueueEntry.QueueStatus.TERTAHAN:
                activity_type = 'HOLD'
                badge_class = 'bg-error text-on-error'
                icon = 'warning'
            elif log.status_baru == QueueEntry.QueueStatus.SELESAI:
                activity_type = 'SELESAI'
                badge_class = 'bg-primary-container text-on-primary-container'
                icon = 'task_alt'
            elif log.status_baru == QueueEntry.QueueStatus.KELUAR:
                activity_type = 'GATE OUT'
                badge_class = 'bg-primary text-on-primary'
                icon = 'output'

            recent_activities.append({
                'log': log,
                'timestamp': timezone.localtime(log.timestamp).strftime('%H:%M:%S'),
                'date': timezone.localtime(log.timestamp).strftime('%d/%m'),
                'activity_type': activity_type,
                'badge_class': badge_class,
                'icon': icon,
                'no_antrian': log.queue_entry.no_antrian if log.queue_entry else '-',
                'truck_plate': log.queue_entry.truck.no_polisi if log.queue_entry and log.queue_entry.truck else '-',
                'expedisi': log.queue_entry.truck.expedisi.nama_perusahaan if log.queue_entry and log.queue_entry.truck and log.queue_entry.truck.expedisi else '-',
                'container_no': log.queue_entry.container.no_kontainer if log.queue_entry and log.queue_entry.container else None,
                'operator_name': (log.operator.get_full_name() or log.operator.username) if log.operator else 'Sistem / Otomatis',
                'lane': log.queue_entry.gerbang_lane if log.queue_entry else '-',
                'keterangan': log.keterangan or '-',
            })

        # 7. Kalkulasi TEUs Riil Selesai Gate In Hari Ini
        total_teus = 0
        for entry in today_qs.filter(status__in=[QueueEntry.QueueStatus.SELESAI, QueueEntry.QueueStatus.KELUAR]).select_related('container'):
            if entry.container:
                u = str(entry.container.ukuran or '')
                if '40' in u or '45' in u:
                    total_teus += 2
                else:
                    total_teus += 1

        # 8. Lane Status Matrix Overview
        lanes_status = []
        for lane_choice in QueueEntry.LaneChoice.choices:
            lane_name = lane_choice[0]
            lane_count = today_qs.filter(gerbang_lane=lane_name, status__in=[QueueEntry.QueueStatus.MENUNGGU, QueueEntry.QueueStatus.PROSES]).count()
            lanes_status.append({
                'name': lane_name,
                'label': lane_choice[1],
                'active_count': lane_count,
            })

        # 9. Operational Alerts (Notification & Operational Alert)
        threshold_waiting = getattr(settings, 'ALERT_THRESHOLD_WAITING_MINS', 30)
        threshold_process = getattr(settings, 'ALERT_THRESHOLD_PROCESS_MINS', 45)

        # 9a. Alert 1: Truck Tertahan (Hold Gate)
        held_entries = QueueEntry.objects.filter(
            status=QueueEntry.QueueStatus.TERTAHAN
        ).select_related('truck', 'driver', 'container', 'truck__expedisi').order_by('-waktu_masuk')

        alerts_held = []
        for entry in held_entries:
            elapsed_sec = max(0, int((now - entry.waktu_masuk).total_seconds()))
            m = elapsed_sec // 60
            s = elapsed_sec % 60
            dur_str = f"{m}m {s:02d}s" if m < 60 else f"{m // 60}j {m % 60}m"
            alerts_held.append({
                'entry': entry,
                'no_antrian': entry.no_antrian,
                'no_polisi': entry.truck.no_polisi if entry.truck else '-',
                'driver_nama': entry.driver.nama if entry.driver else '-',
                'expedisi': entry.truck.expedisi.nama_perusahaan if entry.truck and entry.truck.expedisi else '-',
                'container_no': entry.container.no_kontainer if entry.container else None,
                'alasan_tertahan': entry.alasan_tertahan or 'Pemeriksaan Dokumen / Deviasi Lapangan',
                'waktu_masuk': timezone.localtime(entry.waktu_masuk).strftime('%H:%M:%S WIB'),
                'duration_str': dur_str,
                'lane': entry.gerbang_lane or '-',
            })

        # 9b. Alert 2: Antrian Terlalu Lama (Overdue Queue)
        overdue_waiting_cutoff = now - timedelta(minutes=threshold_waiting)
        overdue_process_cutoff = now - timedelta(minutes=threshold_process)

        overdue_waiting_qs = QueueEntry.objects.filter(
            status=QueueEntry.QueueStatus.MENUNGGU,
            waktu_masuk__lt=overdue_waiting_cutoff
        ).select_related('truck', 'driver', 'container', 'truck__expedisi').order_by('waktu_masuk')

        overdue_process_qs = QueueEntry.objects.filter(
            status=QueueEntry.QueueStatus.PROSES
        ).filter(
            Q(waktu_mulai_proses__lt=overdue_process_cutoff) |
            Q(waktu_mulai_proses__isnull=True, waktu_masuk__lt=overdue_process_cutoff)
        ).select_related('truck', 'driver', 'container', 'truck__expedisi').order_by('waktu_masuk')

        alerts_overdue = []
        for entry in overdue_waiting_qs:
            elapsed_sec = max(0, int((now - entry.waktu_masuk).total_seconds()))
            m = elapsed_sec // 60
            s = elapsed_sec % 60
            dur_str = f"{m}m {s:02d}s" if m < 60 else f"{m // 60}j {m % 60}m"
            alerts_overdue.append({
                'entry': entry,
                'no_antrian': entry.no_antrian,
                'no_polisi': entry.truck.no_polisi if entry.truck else '-',
                'driver_nama': entry.driver.nama if entry.driver else '-',
                'expedisi': entry.truck.expedisi.nama_perusahaan if entry.truck and entry.truck.expedisi else '-',
                'status': 'MENUNGGU',
                'status_label': 'Menunggu Buffer',
                'elapsed_mins': m,
                'duration_str': dur_str,
                'threshold_mins': threshold_waiting,
                'exceeded_mins': m - threshold_waiting,
                'lane': entry.gerbang_lane or '-',
                'waktu_masuk': timezone.localtime(entry.waktu_masuk).strftime('%H:%M:%S WIB'),
            })

        for entry in overdue_process_qs:
            ref_t = entry.waktu_mulai_proses or entry.waktu_masuk
            elapsed_sec = max(0, int((now - ref_t).total_seconds()))
            m = elapsed_sec // 60
            s = elapsed_sec % 60
            dur_str = f"{m}m {s:02d}s" if m < 60 else f"{m // 60}j {m % 60}m"
            alerts_overdue.append({
                'entry': entry,
                'no_antrian': entry.no_antrian,
                'no_polisi': entry.truck.no_polisi if entry.truck else '-',
                'driver_nama': entry.driver.nama if entry.driver else '-',
                'expedisi': entry.truck.expedisi.nama_perusahaan if entry.truck and entry.truck.expedisi else '-',
                'status': 'PROSES',
                'status_label': 'Sedang Proses',
                'elapsed_mins': m,
                'duration_str': dur_str,
                'threshold_mins': threshold_process,
                'exceeded_mins': m - threshold_process,
                'lane': entry.gerbang_lane or '-',
                'waktu_masuk': timezone.localtime(entry.waktu_masuk).strftime('%H:%M:%S WIB'),
            })

        alerts_overdue.sort(key=lambda x: x['elapsed_mins'], reverse=True)
        alerts_total_count = len(alerts_held) + len(alerts_overdue)

        # 10. Operator Info and Context
        op_info = self.get_operator_info(request)

        context = {
            'op_info': op_info,
            'today': today,
            'current_time': timezone.localtime(now).strftime('%H:%M:%S WIB'),
            'count_total': count_total,
            'count_gate_in': count_gate_in,
            'count_gate_out': count_gate_out,
            'count_menunggu': count_menunggu,
            'count_proses': count_proses,
            'count_proses_display': f"{count_proses:02d}",
            'count_tertahan': count_tertahan,
            'count_selesai': count_selesai,
            'count_keluar': count_keluar,
            'count_aktif': count_aktif,
            'total_teus': total_teus,
            'avg_process_str': avg_process_str,
            'avg_booth_str': avg_booth_str,
            'buffer_capacity': buffer_capacity,
            'buffer_occupancy_pct': buffer_occupancy_pct,
            'status_distribution': status_distribution,
            'active_list': active_list,
            'recent_activities': recent_activities,
            'hourly_chart': hourly_chart,
            'lanes_status': lanes_status,
            'threshold_waiting': threshold_waiting,
            'threshold_process': threshold_process,
            'alerts_held': alerts_held,
            'alerts_overdue': alerts_overdue,
            'alerts_total_count': alerts_total_count,
            'telemetry': {
                'ocr_status': 'READY',
                'wim_status': 'CALIB',
                'barrier_status': 'OK',
                'tos_link': 'NORMAL (12ms)',
            }
        }
        return render(request, self.template_name, context)


class GateInView(OperationalAccessMixin, View):
    """
    Halaman dan pemrosesan formulir pendaftaran truk masuk (Gate In).
    """
    template_name = 'queue_gate/gate_in.html'

    def get_operator_info(self, request):
        booth = request.session.get('assigned_booth_label', 'Gate Inbound 01')
        shift = 'Shift 1 (08:00 - 16:00)'
        nip = 'OP-001'
        nama_petugas = 'Petugas Gate'

        if request.user.is_authenticated:
            nama_petugas = request.user.get_full_name() or request.user.username
            if hasattr(request.user, 'operator_profile') and request.user.operator_profile:
                prof = request.user.operator_profile
                nip = prof.nip or nip
                nama_petugas = prof.nama or nama_petugas
                if prof.booth_aktif:
                    booth = prof.get_booth_aktif_display()
                if prof.shift_aktif:
                    shift = prof.get_shift_aktif_display()

        return {
            'booth': booth,
            'shift': shift,
            'nip': nip,
            'nama_petugas': nama_petugas
        }

    def get(self, request):
        op_info = self.get_operator_info(request)
        form = GateInForm()

        context = {
            'form': form,
            'op_info': op_info,
            'today': timezone.localdate(),
            'current_time': timezone.localtime().strftime('%H:%M:%S WIB'),
            # Sensor Telemetry Status (Simulasi sesuai PRD & desain.md)
            'telemetry': {
                'ocr_status': 'READY',
                'wim_status': 'CALIB',
                'barrier_status': 'OK',
                'camera_feed': 'LIVE',
            }
        }
        return render(request, self.template_name, context)

    def post(self, request):
        op_info = self.get_operator_info(request)
        form = GateInForm(request.POST)
        action_type = request.POST.get('action_type', 'save')

        if form.is_valid():
            try:
                queue_entry = process_gate_in_registration(
                    operator_user=request.user,
                    cleaned_data=form.cleaned_data,
                    booth_name=op_info['booth'],
                    action_type=action_type
                )

                # Flash Message & Redirect sesuai aksi
                if action_type == 'save_print':
                    messages.success(
                        request,
                        f"Truk {queue_entry.truck.no_polisi} berhasil didaftarkan! Nomor antrian: {queue_entry.no_antrian}. Menampilkan tiket cetak..."
                    )
                    return redirect('gate_ticket', pk=queue_entry.pk)

                elif action_type == 'hold':
                    messages.warning(
                        request,
                        f"Truk {queue_entry.truck.no_polisi} dimasukkan ke antrian dengan status TERTAHAN [{queue_entry.no_antrian}]: {queue_entry.alasan_tertahan}."
                    )
                    return redirect('queue_list')

                else:  # action_type == 'save'
                    messages.success(
                        request,
                        f"Truk {queue_entry.truck.no_polisi} berhasil didaftarkan ke antrian [{queue_entry.no_antrian}]!"
                    )
                    return redirect('queue_list')

            except Exception as e:
                messages.error(request, f"Gagal memproses pendaftaran Gate In: {str(e)}")

        else:
            messages.error(
                request,
                "Terdapat kesalahan pada data yang diisi. Harap periksa pesan peringatan pada formulir di bawah."
            )

        context = {
            'form': form,
            'op_info': op_info,
            'today': timezone.localdate(),
            'current_time': timezone.localtime().strftime('%H:%M:%S WIB'),
            'telemetry': {
                'ocr_status': 'READY',
                'wim_status': 'CALIB',
                'barrier_status': 'OK',
                'camera_feed': 'LIVE',
            }
        }
        return render(request, self.template_name, context)


class GateTicketView(OperationalAccessMixin, DetailView):
    """
    Tampilan cetak tiket masuk terminal / Equipment Interchange Receipt (EIR).
    """
    model = QueueEntry
    template_name = 'queue_gate/ticket.html'
    context_object_name = 'queue'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['terminal_name'] = 'PORT GATE TOS — DERMAGA UTARA'
        context['terminal_sub'] = 'Koja Container Terminal / Pelabuhan Peti Kemas'
        return context


class QueueDetailView(OperationalAccessMixin, DetailView):
    """
    Tampilan detail operasional antrian truk masuk terminal (Queue Detail).
    Mengikuti visual dan operational metrics dari Stitch QueueDetailView.
    Mendukung quick-jump pencarian antrian dan navigasi transaksi sebelumnya/berikutnya.
    """
    model = QueueEntry
    template_name = 'queue_gate/queue_detail.html'
    context_object_name = 'queue'

    def get_queryset(self):
        return QueueEntry.objects.select_related(
            'truck', 'driver', 'container', 'truck__expedisi', 'operator'
        )

    def get(self, request, *args, **kwargs):
        q = request.GET.get('q', '').strip()
        if q:
            clean_q = q.upper().strip()
            clean_q_nospace = clean_q.replace(' ', '')
            m_plate = re.match(r'^([A-Za-z]{1,2})\s*(\d{1,4})\s*([A-Za-z]*)$', clean_q)
            clean_plate_spaced = f"{m_plate.group(1)} {m_plate.group(2)} {m_plate.group(3)}".strip() if m_plate else None

            antrian_q = Q(no_antrian__iexact=clean_q) | Q(no_antrian__icontains=clean_q)
            if clean_q.isdigit():
                antrian_q |= Q(no_antrian__icontains=f"Q-{int(clean_q):04d}")

            search_filter = (
                antrian_q |
                Q(truck__no_polisi__iexact=clean_q) |
                Q(truck__no_polisi__icontains=clean_q) |
                Q(truck__no_polisi__icontains=clean_q_nospace) |
                Q(container__no_kontainer__iexact=clean_q_nospace) |
                Q(container__no_kontainer__icontains=clean_q_nospace)
            )
            if clean_plate_spaced:
                search_filter |= Q(truck__no_polisi__iexact=clean_plate_spaced) | Q(truck__no_polisi__icontains=clean_plate_spaced)

            found = QueueEntry.objects.filter(search_filter).order_by('-waktu_masuk').first()

            if found:
                return redirect('queue_detail', pk=found.pk)
            else:
                messages.info(request, f"Antrian dengan kata kunci '{q}' tidak ditemukan langsung, dialihkan ke pencarian tabel antrian.")
                return redirect(f"{reverse('queue_list')}?search={urlquote(clean_q)}")

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queue = self.object
        now = timezone.now()

        # Dwell time calculation
        elapsed = max(0, int((now - queue.waktu_masuk).total_seconds()))
        m = elapsed // 60
        s = elapsed % 60
        context['dwell_time'] = f"{m}m {s:02d}s" if m < 60 else f"{m // 60}j {m % 60}m"

        # Chronological audit logs
        context['status_logs'] = queue.status_logs.select_related('operator').order_by('timestamp')

        # Navigasi transaksi antrian sebelumnya & berikutnya
        context['prev_queue'] = QueueEntry.objects.filter(waktu_masuk__lt=queue.waktu_masuk).order_by('-waktu_masuk').first()
        context['next_queue'] = QueueEntry.objects.filter(waktu_masuk__gt=queue.waktu_masuk).order_by('waktu_masuk').first()

        # 4-step flow stages
        status = queue.status
        context['step_1_active'] = (status == QueueEntry.QueueStatus.MENUNGGU)
        context['step_1_done'] = (status in [
            QueueEntry.QueueStatus.PROSES,
            QueueEntry.QueueStatus.TERTAHAN,
            QueueEntry.QueueStatus.SELESAI,
            QueueEntry.QueueStatus.KELUAR
        ])

        context['step_2_active'] = (status in [QueueEntry.QueueStatus.PROSES, QueueEntry.QueueStatus.TERTAHAN])
        context['step_2_done'] = (status in [QueueEntry.QueueStatus.SELESAI, QueueEntry.QueueStatus.KELUAR])

        context['step_3_active'] = (status == QueueEntry.QueueStatus.SELESAI)
        context['step_3_done'] = (status == QueueEntry.QueueStatus.KELUAR)

        context['step_4_active'] = (status == QueueEntry.QueueStatus.KELUAR)
        context['step_4_done'] = (status == QueueEntry.QueueStatus.KELUAR)

        # Telemetry sensor status (Simulasi)
        context['telemetry'] = {
            'ocr_status': 'READY',
            'wim_status': 'CALIB',
            'barrier_status': 'OK',
            'tos_link': 'NORMAL (12ms)',
        }
        return context


class GateCockpitView(OperationalAccessMixin, View):
    """
    Tampilan Gate Cockpit / Workstation Operasional Gardu Terminal.
    Mengikuti visual dan operational metrics dari Stitch GateCockpitView.
    """
    template_name = 'queue_gate/gate_cockpit.html'

    def get(self, request):
        today = timezone.localdate()
        now = timezone.now()

        # 1. Base Queryset
        base_qs = QueueEntry.objects.select_related(
            'truck', 'driver', 'container', 'truck__expedisi'
        ).order_by('-waktu_masuk')

        # 2. Filter Parameters
        search_query = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', '').strip().upper()
        cargo_filter = request.GET.get('cargo', '').strip().upper()
        lane_filter = request.GET.get('lane', '').strip()
        selected_id = request.GET.get('selected', '').strip()

        filtered_qs = base_qs
        if search_query:
            filtered_qs = filtered_qs.filter(
                Q(truck__no_polisi__icontains=search_query) |
                Q(no_antrian__icontains=search_query) |
                Q(driver__nama__icontains=search_query) |
                Q(container__no_kontainer__icontains=search_query) |
                Q(truck__expedisi__nama_perusahaan__icontains=search_query) |
                Q(container__ref_dokumen__icontains=search_query)
            )

        if status_filter and status_filter != 'ALL':
            filtered_qs = filtered_qs.filter(status=status_filter)

        if cargo_filter and cargo_filter != 'ALL':
            filtered_qs = filtered_qs.filter(container__kategori=cargo_filter)

        if lane_filter and lane_filter != 'ALL':
            filtered_qs = filtered_qs.filter(gerbang_lane=lane_filter)

        # 3. Compute Real Operational KPIs (Today)
        today_qs = QueueEntry.objects.filter(tanggal=today)
        antrian_gate_count = today_qs.filter(status=QueueEntry.QueueStatus.MENUNGGU).count()
        proses_booth_count = today_qs.filter(status=QueueEntry.QueueStatus.PROSES).count()
        hold_count = today_qs.filter(status=QueueEntry.QueueStatus.TERTAHAN).count()

        # Avg Turnaround Time (TTT)
        completed_entries = today_qs.filter(
            status__in=[QueueEntry.QueueStatus.SELESAI, QueueEntry.QueueStatus.KELUAR],
            waktu_selesai__isnull=False
        )
        durations = [
            (q.waktu_selesai - q.waktu_masuk).total_seconds()
            for q in completed_entries if q.waktu_selesai and q.waktu_masuk
        ]
        avg_ttt = round(sum(durations) / len(durations) / 60, 1) if durations else 2.8

        # Throughput Shift (TEUs today)
        throughput_teus = 0
        for entry in today_qs.filter(status__in=[QueueEntry.QueueStatus.SELESAI, QueueEntry.QueueStatus.KELUAR]).select_related('container'):
            if entry.container:
                u = str(entry.container.ukuran or '')
                if '40' in u or '45' in u:
                    throughput_teus += 2
                else:
                    throughput_teus += 1

        # 4. Gate Lanes Status Matrix (8 Lanes from Stitch)
        lane_definitions = [
            {'id': 'lane-01', 'name': 'Lane 01', 'type': 'Dry In', 'db_name': 'Lane 01 - Dry In', 'focus': False},
            {'id': 'lane-02', 'name': 'Lane 02', 'type': 'Reefer', 'db_name': 'Lane 02 - Reefer', 'focus': False},
            {'id': 'lane-03', 'name': 'Lane 03', 'type': 'Auto OCR', 'db_name': 'Lane 03 - Auto OCR', 'focus': True},
            {'id': 'lane-04', 'name': 'Lane 04', 'type': 'Trouble', 'db_name': 'Lane 04 - Trouble', 'focus': False},
            {'id': 'lane-05', 'name': 'Lane 05', 'type': 'Empty', 'db_name': 'Lane 05 - Empty', 'focus': False},
            {'id': 'lane-06', 'name': 'Lane 06', 'type': 'Dedicated', 'db_name': 'Lane 06 - Dedicated', 'focus': False},
            {'id': 'out-01', 'name': 'Out 01', 'type': 'Dispatch', 'db_name': 'Out 01 - Dispatch', 'focus': False},
            {'id': 'out-02', 'name': 'Out 02', 'type': 'Bypass', 'db_name': 'Out 02 - Bypass', 'focus': False},
        ]

        gate_lanes = []
        for ldef in lane_definitions:
            active_in_lane = base_qs.filter(
                gerbang_lane=ldef['db_name'],
                status__in=[QueueEntry.QueueStatus.PROSES, QueueEntry.QueueStatus.TERTAHAN]
            ).first()

            if not active_in_lane:
                active_in_lane = base_qs.filter(gerbang_lane=ldef['db_name']).first()

            lane_info = {
                'id': ldef['id'],
                'name': ldef['name'],
                'type': ldef['type'],
                'db_name': ldef['db_name'],
                'is_active_focus': ldef['focus'],
                'is_hold': False,
                'status': 'STANDBY',
                'sub_status': 'TERSEDIA',
                'truck_plate': '',
                'container_no': '',
                'container_type': '',
                'wim_weight': '0.00 MT',
                'ocr_score': 'READY',
                'entry_pk': None,
            }

            if active_in_lane:
                lane_info['entry_pk'] = active_in_lane.pk
                lane_info['truck_plate'] = active_in_lane.truck.no_polisi
                if active_in_lane.status == QueueEntry.QueueStatus.PROSES:
                    lane_info['status'] = 'PROSES'
                    lane_info['sub_status'] = 'VERIFIKASI'
                elif active_in_lane.status == QueueEntry.QueueStatus.TERTAHAN:
                    lane_info['status'] = 'HOLD'
                    lane_info['is_hold'] = True
                    lane_info['sub_status'] = 'TERTAHAN'
                elif active_in_lane.status == QueueEntry.QueueStatus.SELESAI:
                    lane_info['status'] = 'VALID'
                    lane_info['sub_status'] = 'PASS YARD'
                elif active_in_lane.status == QueueEntry.QueueStatus.KELUAR:
                    lane_info['status'] = 'DISPATCH'
                    lane_info['sub_status'] = 'GATE OUT'
                else:
                    lane_info['status'] = 'STANDBY'
                    lane_info['sub_status'] = 'MENUNGGU'

                if active_in_lane.container:
                    lane_info['container_no'] = active_in_lane.container.no_kontainer
                    lane_info['container_type'] = f"{active_in_lane.container.ukuran or ''} {active_in_lane.container.tipe or ''}".strip()
                    if active_in_lane.container.berat_kotor:
                        lane_info['wim_weight'] = f"{round(float(active_in_lane.container.berat_kotor)/1000, 2)} MT"
                lane_info['ocr_score'] = '99.4% MATCH' if active_in_lane.status == QueueEntry.QueueStatus.PROSES else 'VERIF OK'

            gate_lanes.append(lane_info)

        # 5. Dwell time calculation for table rows
        rows = list(filtered_qs[:30])
        for r in rows:
            elapsed = max(0, int((now - r.waktu_masuk).total_seconds()))
            m = elapsed // 60
            s = elapsed % 60
            r.dwell_time = f"{m}m {s:02d}s" if m < 60 else f"{m // 60}j {m % 60}m"
            r.is_lead = (r.status == QueueEntry.QueueStatus.PROSES)
            r.is_alert = (r.status == QueueEntry.QueueStatus.TERTAHAN)

        # 6. Selected Active Truck for Bottom Cockpit
        active_entry = None
        if selected_id:
            if selected_id.isdigit():
                active_entry = base_qs.filter(pk=int(selected_id)).first()
            else:
                active_entry = base_qs.filter(no_antrian=selected_id).first()

        if not active_entry:
            active_entry = base_qs.filter(status=QueueEntry.QueueStatus.PROSES).first()
            if not active_entry:
                active_entry = base_qs.filter(status=QueueEntry.QueueStatus.TERTAHAN).first()
            if not active_entry:
                active_entry = rows[0] if rows else None

        for r in rows:
            r.is_selected = (active_entry is not None and r.pk == active_entry.pk)

        active_truck_data = None
        if active_entry:
            gross = float(active_entry.container.berat_kotor) if active_entry.container and active_entry.container.berat_kotor else 0.0
            tare = 7120.0
            netto = max(0.0, gross - tare)
            weight_pct = min(100, int((gross / 38000.0) * 100)) if gross > 0 else 0

            active_truck_data = {
                'entry': active_entry,
                'no_antrian': active_entry.no_antrian,
                'no_polisi': active_entry.truck.no_polisi,
                'driver_nama': active_entry.driver.nama,
                'driver_sim': active_entry.driver.no_sim,
                'driver_hp': active_entry.driver.no_hp,
                'expedisi_nama': active_entry.truck.expedisi.nama_perusahaan if active_entry.truck.expedisi else '-',
                'rfid_tag': active_entry.truck.rfid_tag or 'TOS-ID-9912',
                'konfigurasi': active_entry.truck.get_konfigurasi_display(),
                'container_no': active_entry.container.no_kontainer if active_entry.container else 'Chassis Kosong',
                'container_size': active_entry.container.ukuran if active_entry.container else '-',
                'container_type': active_entry.container.tipe if active_entry.container else '-',
                'kategori': active_entry.container.get_kategori_display() if active_entry.container else '-',
                'ref_dokumen': active_entry.container.ref_dokumen if active_entry.container else '-',
                'seal_number': active_entry.container.seal_number if active_entry.container else '-',
                'gross_weight': f"{int(gross):,}" if gross else "0",
                'tare_weight': f"{int(tare):,}",
                'net_weight': f"{int(netto):,}",
                'weight_pct': f"{weight_pct}%",
                'alokasi_blok': active_entry.alokasi_blok or 'BLOCK C-04',
                'alokasi_bay': active_entry.alokasi_bay or '12',
                'alokasi_row': active_entry.alokasi_row or '03',
                'alokasi_tier': active_entry.alokasi_tier or '3',
                'lane': active_entry.gerbang_lane,
                'booth': active_entry.booth,
                'status': active_entry.status,
                'status_display': active_entry.get_status_display(),
                'alasan_tertahan': active_entry.alasan_tertahan,
            }

        context = {
            'rows': rows,
            'gate_lanes': gate_lanes,
            'active_truck': active_truck_data,
            'selected_id': active_entry.no_antrian if active_entry else '',
            'search_query': search_query,
            'status_filter': status_filter,
            'cargo_filter': cargo_filter,
            'lane_filter': lane_filter,
            'kpi': {
                'antrian_gate': antrian_gate_count,
                'proses_booth': proses_booth_count,
                'avg_ttt': avg_ttt,
                'throughput_teus': throughput_teus,
                'total_hold': hold_count,
            }
        }
        return render(request, self.template_name, context)


class QueueListView(OperationalAccessMixin, ListView):
    """
    Daftar antrian truk untuk memantau antrian aktif dan riwayat masuk.
    Mengikuti visual dan operational metrics dari Stitch QueueListView.
    """
    model = QueueEntry
    template_name = 'queue_gate/queue_list.html'
    context_object_name = 'queues'
    paginate_by = 10

    def get_paginate_by(self, queryset):
        per_page = self.request.GET.get('per_page', '').strip()
        if per_page.isdigit() and int(per_page) in [10, 25, 50, 100]:
            return int(per_page)
        return self.paginate_by

    def get_queryset(self):
        qs = QueueEntry.objects.select_related('truck', 'driver', 'container', 'truck__expedisi', 'operator').order_by('-waktu_masuk')
        status_filter = self.request.GET.get('status', '').strip().upper()
        search_query = self.request.GET.get('search', '').strip()
        lane_filter = self.request.GET.get('lane', '').strip()
        hold_only = self.request.GET.get('hold', '').strip()
        date_param = self.request.GET.get('date', '').strip()

        if hold_only == '1':
            qs = qs.filter(status=QueueEntry.QueueStatus.TERTAHAN)
        elif status_filter and status_filter != 'ALL':
            qs = qs.filter(status=status_filter)

        if lane_filter and lane_filter != 'ALL':
            qs = qs.filter(gerbang_lane=lane_filter)

        # Filter tanggal menggunakan timezone project
        if date_param:
            if date_param.lower() == 'today':
                qs = qs.filter(tanggal=timezone.localdate())
            else:
                try:
                    parsed_date = datetime.strptime(date_param, '%Y-%m-%d').date()
                    qs = qs.filter(tanggal=parsed_date)
                except ValueError:
                    pass

        if search_query:
            search_query_nospace = search_query.replace(' ', '')
            m_plate = re.match(r'^([A-Za-z]{1,2})\s*(\d{1,4})\s*([A-Za-z]*)$', search_query.strip())
            clean_plate_spaced = f"{m_plate.group(1)} {m_plate.group(2)} {m_plate.group(3)}".strip() if m_plate else None

            search_filter = (
                Q(truck__no_polisi__icontains=search_query) |
                Q(truck__no_polisi__icontains=search_query_nospace) |
                Q(no_antrian__icontains=search_query) |
                Q(driver__nama__icontains=search_query) |
                Q(container__no_kontainer__icontains=search_query) |
                Q(container__no_kontainer__icontains=search_query_nospace) |
                Q(truck__expedisi__nama_perusahaan__icontains=search_query) |
                Q(booth__icontains=search_query) |
                Q(operator__username__icontains=search_query) |
                Q(operator__first_name__icontains=search_query) |
                Q(operator__last_name__icontains=search_query)
            )
            if clean_plate_spaced:
                search_filter |= Q(truck__no_polisi__icontains=clean_plate_spaced)

            qs = qs.filter(search_filter)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        now = timezone.now()
        today_qs = QueueEntry.objects.filter(tanggal=today)

        count_menunggu = today_qs.filter(status=QueueEntry.QueueStatus.MENUNGGU).count()
        count_proses = today_qs.filter(status=QueueEntry.QueueStatus.PROSES).count()
        count_tertahan = today_qs.filter(status=QueueEntry.QueueStatus.TERTAHAN).count()
        count_selesai = today_qs.filter(status=QueueEntry.QueueStatus.SELESAI).count()
        count_keluar = today_qs.filter(status=QueueEntry.QueueStatus.KELUAR).count()
        count_total = today_qs.count()

        # Hitung waktu tunggu / dwell time pada antrian yang sedang ditampilkan
        for q in context['queues']:
            elapsed = max(0, int((now - q.waktu_masuk).total_seconds()))
            m = elapsed // 60
            s = elapsed % 60
            q.dwell_time = f"{m}m {s:02d}s" if m < 60 else f"{m // 60}j {m % 60}m"

        # Rata-rata Turnaround Time (TTT)
        completed_entries = today_qs.filter(
            status__in=[QueueEntry.QueueStatus.SELESAI, QueueEntry.QueueStatus.KELUAR],
            waktu_selesai__isnull=False
        )
        durations = [
            (q.waktu_selesai - q.waktu_masuk).total_seconds()
            for q in completed_entries if q.waktu_selesai and q.waktu_masuk
        ]
        if durations:
            avg_ttt = round(sum(durations) / len(durations) / 60, 1)
            avg_ttt_str = f"{avg_ttt}"
        else:
            avg_ttt_str = "14.8"

        context['count_menunggu'] = count_menunggu
        context['count_proses'] = count_proses
        context['count_proses_display'] = f"{count_proses:02d}"
        context['count_tertahan'] = count_tertahan
        context['count_selesai'] = count_selesai
        context['count_keluar'] = count_keluar
        context['count_total'] = count_total
        context['avg_ttt_mins'] = avg_ttt_str

        context['selected_status'] = self.request.GET.get('status', 'all')
        context['search_query'] = self.request.GET.get('search', '')
        context['selected_lane'] = self.request.GET.get('lane', 'all')
        context['selected_date'] = self.request.GET.get('date', '').strip()
        context['hold_only'] = self.request.GET.get('hold', '') == '1' or context['selected_status'] == 'TERTAHAN'
        context['current_per_page'] = self.get_paginate_by(self.object_list)
        context['today'] = today
        context['lanes_list'] = QueueEntry.LaneChoice.choices

        return context


class QueueProcessActionView(OperationalAccessMixin, View):
    """
    Endpoint pemrosesan transisi status antrian truk (POST only dengan proteksi CSRF).
    Mendukung alur:
    MENUNGGU -> PROSES -> TERTAHAN (opsional) -> PROSES -> SELESAI -> KELUAR
    """
    def post(self, request, pk):
        queue_entry = get_object_or_404(QueueEntry, pk=pk)
        target_status = request.POST.get('target_status', '').strip().upper()
        reason = request.POST.get('reason', '').strip()

        if not target_status:
            messages.error(request, "Target status antrian tidak ditentukan.")
            return redirect('queue_list')

        try:
            updated_entry, _ = process_queue_transition(
                queue_entry_or_id=queue_entry,
                target_status=target_status,
                operator_user=request.user,
                reason=reason
            )

            status_display = updated_entry.get_status_display()
            if target_status == QueueEntry.QueueStatus.PROSES:
                messages.success(
                    request,
                    f"Antrian [{updated_entry.no_antrian}] ({updated_entry.truck.no_polisi}) berhasil diproses!"
                )
            elif target_status == QueueEntry.QueueStatus.TERTAHAN:
                messages.warning(
                    request,
                    f"Antrian [{updated_entry.no_antrian}] ({updated_entry.truck.no_polisi}) berhasil di-HOLD: {updated_entry.alasan_tertahan}."
                )
            elif target_status == QueueEntry.QueueStatus.SELESAI:
                messages.success(
                    request,
                    f"Antrian [{updated_entry.no_antrian}] ({updated_entry.truck.no_polisi}) telah SELESAI di yard."
                )
            elif target_status == QueueEntry.QueueStatus.KELUAR:
                messages.success(
                    request,
                    f"Antrian [{updated_entry.no_antrian}] ({updated_entry.truck.no_polisi}) telah GATE OUT (KELUAR)."
                )
            else:
                messages.success(
                    request,
                    f"Status antrian [{updated_entry.no_antrian}] berhasil diperbarui menjadi {status_display}."
                )

        except (QueueTransitionError, QueueValidationError) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Gagal memperbarui status antrian: {str(e)}")

        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            if any(path in next_url for path in ['/queue/', '/ticket/', '/gate-cockpit/', '/dashboard/']):
                return redirect(next_url)
        return redirect('queue_list')



class TruckLookupAPIView(OperationalAccessMixin, View):
    """
    API endpoint internal untuk auto-fill data armada dan pengemudi saat operator
    mengetik nomor polisi di form Gate In.
    Mendukung pencarian eksak, parsial, dan format tanpa spasi.
    """
    def get(self, request):
        raw_plate = request.GET.get('plate', '').strip().upper()
        plate = re.sub(r'\s+', ' ', raw_plate)
        plate_nospace = re.sub(r'\s+', '', raw_plate)

        if not plate:
            return JsonResponse({'found': False, 'message': 'Nomor polisi kosong.'})

        # Cek antrian aktif (eksak, tanpa spasi, atau parsial)
        active_queue = QueueEntry.objects.filter(
            Q(truck__no_polisi__iexact=plate) |
            Q(truck__no_polisi__icontains=plate),
            status__in=[
                QueueEntry.QueueStatus.MENUNGGU,
                QueueEntry.QueueStatus.PROSES,
                QueueEntry.QueueStatus.TERTAHAN
            ]
        ).first()

        if not active_queue and plate_nospace:
            active_qs = QueueEntry.objects.filter(
                status__in=[
                    QueueEntry.QueueStatus.MENUNGGU,
                    QueueEntry.QueueStatus.PROSES,
                    QueueEntry.QueueStatus.TERTAHAN
                ]
            ).select_related('truck')
            for q in active_qs:
                if q.truck and q.truck.no_polisi.replace(' ', '').upper() == plate_nospace:
                    active_queue = q
                    break

        active_info = None
        if active_queue:
            active_info = {
                'no_antrian': active_queue.no_antrian,
                'status': active_queue.get_status_display(),
                'status_raw': active_queue.status,
                'waktu_masuk': active_queue.waktu_masuk.strftime('%d/%m/%Y %H:%M:%S'),
            }

        # 1. Exact match (case-insensitive)
        truck = Truck.objects.filter(no_polisi__iexact=plate).select_related('expedisi', 'driver').first()

        # 2. Match without spaces (e.g. B9012XYZ vs B 9012 XYZ)
        if not truck and plate_nospace:
            for t in Truck.objects.select_related('expedisi', 'driver').filter(is_active=True)[:100]:
                if t.no_polisi.replace(' ', '').upper() == plate_nospace:
                    truck = t
                    break

        # 3. Partial match (icontains)
        if not truck and len(plate) >= 3:
            truck = Truck.objects.filter(no_polisi__icontains=plate).select_related('expedisi', 'driver').first()

        if not truck:
            return JsonResponse({
                'found': False,
                'has_active_queue': bool(active_info),
                'active_queue': active_info
            })

        return JsonResponse({
            'found': True,
            'no_polisi': truck.no_polisi,
            'konfigurasi': truck.konfigurasi,
            'rfid_tag': truck.rfid_tag or '',
            'nama_ekspedisi': truck.expedisi.nama_perusahaan if truck.expedisi else '',
            'kode_ekspedisi': truck.expedisi.kode_ekspedisi or '' if truck.expedisi else '',
            'nama_driver': truck.driver.nama if truck.driver else '',
            'no_hp_driver': truck.driver.no_hp if truck.driver else '',
            'no_sim_driver': truck.driver.no_sim if truck.driver else '',
            'has_active_queue': bool(active_info),
            'active_queue': active_info
        })


class ContainerLookupAPIView(OperationalAccessMixin, View):
    """
    API endpoint internal untuk auto-fill data kontainer saat nomor kontainer diketik.
    Mendukung pencarian eksak, parsial, dan fallback ke riwayat antrian.
    """
    def get(self, request):
        raw_no = request.GET.get('no', '').strip().upper()
        no_kontainer = re.sub(r'[\s\-]', '', raw_no)

        if not no_kontainer:
            return JsonResponse({'found': False, 'message': 'Nomor kontainer kosong.'})

        # 1. Exact match di masterdata Container
        container = Container.objects.filter(no_kontainer__iexact=no_kontainer).first()

        # 2. Partial match di masterdata Container
        if not container and len(no_kontainer) >= 4:
            container = Container.objects.filter(no_kontainer__icontains=no_kontainer).first()

        # 3. Fallback: pencarian dari transaksi antrian sebelumnya jika belum ada di masterdata
        if not container:
            prev_entry = QueueEntry.objects.filter(
                container__no_kontainer__icontains=no_kontainer
            ).select_related('container').first()
            if prev_entry and prev_entry.container:
                container = prev_entry.container

        if not container:
            return JsonResponse({'found': False})

        return JsonResponse({
            'found': True,
            'no_kontainer': container.no_kontainer,
            'ukuran': container.ukuran,
            'tipe': container.tipe,
            'kategori': container.kategori,
            'berat_kotor': str(container.berat_kotor),
            'shipping_line': container.shipping_line or '',
            'seal_number': container.seal_number or '',
            'ref_dokumen': container.ref_dokumen or '',
            'status_vgm': container.status_vgm,
        })


class OCRProcessAPIView(OperationalAccessMixin, View):
    """
    API endpoint internal untuk integrasi pemrosesan hasil pembacaan OCR nomor polisi.
    Dapat dipanggil oleh modul Gate In, Gate Out, maupun kamera/edge gateway controller.

    Fitur:
    - Menerima raw OCR text (via GET parameter atau POST JSON/form)
    - Menerima skor confidence opsional
    - Membersihkan noise karakter dan spasi
    - Normalisasi nomor polisi standar Indonesia
    - Evaluasi threshold keyakinan berdasarkan session OCR Settings
    - Lookup armada ke Truck Master dan verifikasi status antrian aktif
    - Mengembalikan format terstruktur JSON
    """
    def get(self, request):
        raw_text = request.GET.get('text') or request.GET.get('plate_raw') or request.GET.get('plate') or ''
        raw_text = str(raw_text).strip()[:100]

        confidence = None
        conf_param = request.GET.get('confidence')
        if conf_param is not None:
            try:
                confidence = float(conf_param)
                if math.isnan(confidence) or math.isinf(confidence) or confidence < 0 or confidence > 100:
                    confidence = None
            except (ValueError, TypeError):
                confidence = None

        if not raw_text:
            return JsonResponse({
                'status': 'error',
                'message': 'Parameter raw OCR text (text / plate_raw) wajib diisi.'
            }, status=400)

        result = process_ocr_plate(raw_text=raw_text, confidence=confidence, request=request)
        return JsonResponse(result.to_dict())

    def post(self, request):
        raw_text = ''
        confidence = None

        # Mendukung Content-Type: application/json maupun form-urlencoded / multipart
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
                raw_text = data.get('text') or data.get('plate_raw') or data.get('plate') or ''
                conf_val = data.get('confidence')
                if conf_val is not None:
                    try:
                        c_float = float(conf_val)
                        if not (math.isnan(c_float) or math.isinf(c_float) or c_float < 0 or c_float > 100):
                            confidence = c_float
                    except (ValueError, TypeError):
                        confidence = None
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        else:
            raw_text = request.POST.get('text') or request.POST.get('plate_raw') or request.POST.get('plate') or ''
            conf_param = request.POST.get('confidence')
            if conf_param is not None:
                try:
                    c_float = float(conf_param)
                    if not (math.isnan(c_float) or math.isinf(c_float) or c_float < 0 or c_float > 100):
                        confidence = c_float
                except (ValueError, TypeError):
                    confidence = None

        raw_text = str(raw_text).strip()[:100]
        if not raw_text:
            return JsonResponse({
                'status': 'error',
                'message': 'Raw OCR text (text / plate_raw) wajib diisi.'
            }, status=400)

        result = process_ocr_plate(raw_text=raw_text, confidence=confidence, request=request)
        return JsonResponse(result.to_dict())


class AuditLogView(OperationalAccessMixin, View):
    """
    Workstation Riwayat & Audit Log Operasional Gerbang (Stitch: AuditLogView.tsx).
    Audit trail tersertifikasi seluruh aktivitas pemindaian OCR, timbangan WIM,
    dan perpindahan status antrian gerbang dari database riil QueueStatusLog.
    """
    template_name = 'queue_gate/audit_log.html'
    paginate_by = 20

    def get(self, request):
        search_query = request.GET.get('search', '').strip()
        severity_filter = request.GET.get('severity', 'ALL').strip().upper()
        lane_filter = request.GET.get('lane', '').strip()
        date_filter = request.GET.get('date', '').strip()

        qs = QueueStatusLog.objects.select_related(
            'queue_entry',
            'queue_entry__truck',
            'queue_entry__container',
            'operator'
        ).order_by('-timestamp')

        # Filter tanggal
        if date_filter:
            try:
                qs = qs.filter(timestamp__date=date_filter)
            except Exception:
                pass

        # Filter lajur gerbang
        if lane_filter:
            qs = qs.filter(queue_entry__gerbang_lane=lane_filter)

        # Filter pencarian teks
        if search_query:
            qs = qs.filter(
                Q(queue_entry__no_antrian__icontains=search_query) |
                Q(queue_entry__truck__no_polisi__icontains=search_query) |
                Q(queue_entry__container__no_kontainer__icontains=search_query) |
                Q(operator__username__icontains=search_query) |
                Q(operator__first_name__icontains=search_query) |
                Q(operator__last_name__icontains=search_query) |
                Q(keterangan__icontains=search_query)
            )

        # Proses klasifikasi event & severity
        processed_logs = []
        for log in qs:
            keterangan_lower = (log.keterangan or '').lower()
            if 'reject' in keterangan_lower or 'gagal' in keterangan_lower or 'tolak' in keterangan_lower or 'batal' in keterangan_lower:
                event = 'GATE_REJECT'
                severity = 'ERROR'
            elif log.status_baru == QueueEntry.QueueStatus.TERTAHAN:
                event = 'GATE_HOLD'
                severity = 'WARN'
            elif log.status_baru == QueueEntry.QueueStatus.SELESAI:
                event = 'GATE_IN_SUCCESS'
                severity = 'SUCCESS'
            elif log.status_baru == QueueEntry.QueueStatus.KELUAR:
                event = 'GATE_OUT_SUCCESS'
                severity = 'SUCCESS'
            elif log.status_lama == QueueEntry.QueueStatus.TERTAHAN and log.status_baru == QueueEntry.QueueStatus.PROSES:
                event = 'RELEASE_HOLD'
                severity = 'INFO'
            elif log.status_baru == QueueEntry.QueueStatus.PROSES:
                event = 'BOOTH_PROCESSING'
                severity = 'INFO'
            else:
                event = 'GATE_IN_REGISTERED'
                severity = 'INFO'

            log.event = event
            log.severity = severity
            log.log_id = f"LOG-{log.pk:05d}"
            log.lane = log.queue_entry.gerbang_lane or 'LANE_01'
            log.truck_plate = log.queue_entry.truck.no_polisi if (log.queue_entry and log.queue_entry.truck) else '-'

            if log.operator:
                full_name = log.operator.get_full_name()
                log.operator_name = full_name if full_name else log.operator.username
            else:
                log.operator_name = 'Sistem Auto-Gate'

            # Filter severity
            if severity_filter != 'ALL' and severity != severity_filter:
                continue

            processed_logs.append(log)

        # Fitur Ekspor CSV jika ?export=csv (dengan proteksi CSV Formula Injection)
        if request.GET.get('export') == 'csv':
            def sanitize_csv_cell(val):
                s = str(val if val is not None else '')
                if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
                    return "'" + s
                return s

            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="audit_log_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
            writer = csv.writer(response)
            writer.writerow(['ID Log', 'Stempel Waktu', 'Jalur', 'Tipe Kejadian', 'Severity', 'No Antrian', 'No Polisi', 'Petugas/Operator', 'Keterangan'])
            for item in processed_logs:
                writer.writerow([
                    sanitize_csv_cell(item.log_id),
                    sanitize_csv_cell(item.timestamp.strftime('%d/%m/%Y %H:%M:%S WIB')),
                    sanitize_csv_cell(item.lane),
                    sanitize_csv_cell(item.event),
                    sanitize_csv_cell(item.severity),
                    sanitize_csv_cell(item.queue_entry.no_antrian if item.queue_entry else '-'),
                    sanitize_csv_cell(item.truck_plate),
                    sanitize_csv_cell(item.operator_name),
                    sanitize_csv_cell(item.keterangan or '-'),
                ])
            return response

        # Pagination
        paginator = Paginator(processed_logs, self.paginate_by)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_count = len(processed_logs)
        lanes = QueueEntry.LaneChoice.choices

        context = {
            'page_obj': page_obj,
            'logs': page_obj.object_list,
            'total_logs': total_count,
            'severity_filter': severity_filter,
            'search_query': search_query,
            'lane_filter': lane_filter,
            'date_filter': date_filter,
            'lanes': lanes,
        }
        return render(request, self.template_name, context)


class OcrSettingsView(OperationalAccessMixin, View):
    """
    Workstation Pengaturan & Kalibrasi Kamera OCR (Stitch: OcrSettingsView.tsx).
    Diagnostik streaming RTSP kamera ANPR plat nomor, pengenal kode kontainer ISO 6346,
    dan kalibrasi sensor WIM.
    Konfigurasi disimpan secara aman pada session gateway controller gardu.
    """
    template_name = 'queue_gate/ocr_settings.html'

    DEFAULT_CONFIG = {
        'ocr_confidence': 95,
        'wim_tolerance': 5,
        'auto_open_barrier': False,
    }

    def get_config(self, request):
        return request.session.get('ocr_config', self.DEFAULT_CONFIG.copy())

    def get(self, request):
        config = self.get_config(request)
        context = {
            'ocr_confidence': config.get('ocr_confidence', 95),
            'wim_tolerance': config.get('wim_tolerance', 5),
            'auto_open_barrier': config.get('auto_open_barrier', False),
            'booth_name': 'GATE INBOUND 03',
            'cam1_info': {
                'name': 'CAM-01: CABIN & FRONT NOPOL',
                'rtsp_url': 'RTSP://10.12.4.31',
                'resolution': 'ONLINE 1080P',
                'fps': '29.8',
                'bitrate': '4.2 Mbps',
                'anpr_score': '99.4%',
                'status': 'ONLINE',
            },
            'cam2_info': {
                'name': 'CAM-02: SIDE / REAR ISO CONTAINER',
                'rtsp_url': 'RTSP://10.12.4.32',
                'resolution': 'ONLINE 1080P',
                'fps': '30.0',
                'bitrate': '4.0 Mbps',
                'iso_status': 'VALID',
                'status': 'ONLINE',
            },
        }
        return render(request, self.template_name, context)

    def post(self, request):
        action = request.POST.get('action', 'save')

        if action == 'reset':
            request.session['ocr_config'] = self.DEFAULT_CONFIG.copy()
            messages.info(request, "Konfigurasi kamera OCR & WIM Scale dikembalikan ke nilai standar pabrik.")
            return redirect('ocr_settings')

        try:
            confidence = int(request.POST.get('ocr_confidence', 95))
            confidence = max(80, min(99, confidence))
        except (ValueError, TypeError):
            confidence = 95

        try:
            tolerance = int(request.POST.get('wim_tolerance', 5))
            tolerance = max(1, min(10, tolerance))
        except (ValueError, TypeError):
            tolerance = 5

        auto_barrier = bool(request.POST.get('auto_open_barrier') in ['on', 'true', '1', True])

        request.session['ocr_config'] = {
            'ocr_confidence': confidence,
            'wim_tolerance': tolerance,
            'auto_open_barrier': auto_barrier,
        }

        messages.success(request, "Konfigurasi Kamera OCR & WIM Scale berhasil disimpan ke Gateway Controller.")
        return redirect('ocr_settings')


class GateOutView(OperationalAccessMixin, View):
    """
    Workstation dan Pemrosesan Gerbang Keluar (Gate Out) Terminal Peti Kemas.
    Menangani alur: SELESAI -> GATE OUT -> KELUAR
    - Pencarian antrian berdasarkan nomor antrian atau plat nomor polisi
    - Inspeksi verifikasi fisik kargo, driver, dan status antrian
    - Hanya antrian berstatus SELESAI yang boleh diproses Gate Out
    - Pemilihan jalur gerbang keluar (Outbound Lane)
    - Penyimpanan timestamp waktu_keluar, operator pengubah, dan QueueStatusLog
    """
    template_name = 'queue_gate/gate_out.html'

    def get_operator_info(self, request):
        booth = request.session.get('assigned_booth_label', 'Gate Outbound 01')
        shift = 'Shift 1 (08:00 - 16:00)'
        nip = 'OP-001'
        nama_petugas = 'Petugas Gate'

        if request.user.is_authenticated:
            nama_petugas = request.user.get_full_name() or request.user.username
            if hasattr(request.user, 'operator_profile') and request.user.operator_profile:
                prof = request.user.operator_profile
                nip = prof.nip or nip
                nama_petugas = prof.nama or nama_petugas
                if prof.booth_aktif:
                    booth = prof.get_booth_aktif_display()
                if prof.shift_aktif:
                    shift = prof.get_shift_aktif_display()

        return {
            'booth': booth,
            'shift': shift,
            'nip': nip,
            'nama_petugas': nama_petugas
        }

    def get(self, request):
        today = timezone.localdate()
        now = timezone.now()
        q = request.GET.get('q', '').strip()
        entry_id = request.GET.get('entry_id', '').strip()

        today_qs = QueueEntry.objects.filter(tanggal=today)
        count_selesai = today_qs.filter(status=QueueEntry.QueueStatus.SELESAI).count()
        count_keluar = today_qs.filter(status=QueueEntry.QueueStatus.KELUAR).count()
        count_total = today_qs.count()

        selected_entry = None
        search_error = None

        if entry_id and entry_id.isdigit():
            selected_entry = QueueEntry.objects.filter(pk=int(entry_id)).select_related(
                'truck', 'driver', 'container', 'truck__expedisi', 'operator'
            ).first()
        elif q:
            clean_q = q.upper().strip()
            clean_q_nospace = clean_q.replace(' ', '')
            m_plate = re.match(r'^([A-Za-z]{1,2})\s*(\d{1,4})\s*([A-Za-z]*)$', clean_q)
            clean_plate_spaced = f"{m_plate.group(1)} {m_plate.group(2)} {m_plate.group(3)}".strip() if m_plate else None

            # 1. Match on no_antrian (exact or numeric/partial Q-0001)
            antrian_q = Q(no_antrian__iexact=clean_q) | Q(no_antrian__icontains=clean_q)
            if clean_q.isdigit():
                antrian_q |= Q(no_antrian__icontains=f"Q-{int(clean_q):04d}")

            selected_entry = QueueEntry.objects.filter(antrian_q).select_related(
                'truck', 'driver', 'container', 'truck__expedisi', 'operator'
            ).order_by('-waktu_masuk').first()

            # 2. Match on truck plate (with or without spaces)
            if not selected_entry:
                plate_q = (
                    Q(truck__no_polisi__iexact=clean_q) |
                    Q(truck__no_polisi__icontains=clean_q) |
                    Q(truck__no_polisi__icontains=clean_q_nospace)
                )
                if clean_plate_spaced:
                    plate_q |= Q(truck__no_polisi__iexact=clean_plate_spaced) | Q(truck__no_polisi__icontains=clean_plate_spaced)

                selected_entry = QueueEntry.objects.filter(plate_q).select_related(
                    'truck', 'driver', 'container', 'truck__expedisi', 'operator'
                ).order_by('-waktu_masuk').first()

            # 3. Fallback truck check without space across records
            if not selected_entry and clean_q_nospace:
                for cand in QueueEntry.objects.filter(
                    status__in=[QueueEntry.QueueStatus.SELESAI, QueueEntry.QueueStatus.KELUAR]
                ).select_related('truck', 'driver', 'container', 'truck__expedisi', 'operator').order_by('-waktu_masuk')[:50]:
                    if cand.truck and cand.truck.no_polisi.replace(' ', '').upper() == clean_q_nospace:
                        selected_entry = cand
                        break

            # 4. Match on container number
            if not selected_entry:
                selected_entry = QueueEntry.objects.filter(
                    Q(container__no_kontainer__iexact=clean_q_nospace) |
                    Q(container__no_kontainer__icontains=clean_q_nospace)
                ).select_related(
                    'truck', 'driver', 'container', 'truck__expedisi', 'operator'
                ).order_by('-waktu_masuk').first()

            if not selected_entry:
                search_error = f"Antrian atau armada dengan kata kunci '{q}' tidak ditemukan dalam sistem."

        # Hitung durasi / dwell time antrian terpilih jika ada
        dwell_time_str = "-"
        if selected_entry and selected_entry.waktu_masuk:
            end_t = selected_entry.waktu_keluar or now
            elapsed = max(0, int((end_t - selected_entry.waktu_masuk).total_seconds()))
            m = elapsed // 60
            s = elapsed % 60
            dwell_time_str = f"{m}m {s:02d}s" if m < 60 else f"{m // 60}j {m % 60}m"

        # Daftar antrian yang siap Gate Out (status SELESAI di yard)
        ready_entries_qs = QueueEntry.objects.filter(
            status=QueueEntry.QueueStatus.SELESAI
        ).select_related('truck', 'driver', 'container', 'truck__expedisi').order_by('-waktu_selesai')

        # Filter tabel siap gate out jika operator memasukkan kata kunci pencarian
        if q:
            clean_q = q.upper().strip()
            clean_q_nospace = clean_q.replace(' ', '')
            m_plate = re.match(r'^([A-Za-z]{1,2})\s*(\d{1,4})\s*([A-Za-z]*)$', clean_q)
            clean_plate_spaced = f"{m_plate.group(1)} {m_plate.group(2)} {m_plate.group(3)}".strip() if m_plate else None

            ready_filter = (
                Q(no_antrian__icontains=clean_q) |
                Q(truck__no_polisi__icontains=clean_q) |
                Q(truck__no_polisi__icontains=clean_q_nospace) |
                Q(container__no_kontainer__icontains=clean_q) |
                Q(container__no_kontainer__icontains=clean_q_nospace) |
                Q(driver__nama__icontains=clean_q) |
                Q(truck__expedisi__nama_perusahaan__icontains=clean_q)
            )
            if clean_plate_spaced:
                ready_filter |= Q(truck__no_polisi__icontains=clean_plate_spaced)

            ready_entries_qs = ready_entries_qs.filter(ready_filter)

        ready_entries = ready_entries_qs[:25]

        for item in ready_entries:
            if item.waktu_masuk:
                el = max(0, int((now - item.waktu_masuk).total_seconds()))
                im = el // 60
                item.dwell_time = f"{im}m" if im < 60 else f"{im // 60}j {im % 60}m"
            else:
                item.dwell_time = "-"

        form = GateOutProcessForm()
        op_info = self.get_operator_info(request)

        context = {
            'op_info': op_info,
            'today': today,
            'current_time': timezone.localtime(now).strftime('%H:%M:%S WIB'),
            'search_query': q,
            'search_error': search_error,
            'selected_entry': selected_entry,
            'dwell_time_str': dwell_time_str,
            'ready_entries': ready_entries,
            'count_selesai': count_selesai,
            'count_keluar': count_keluar,
            'count_total': count_total,
            'form': form,
            'QueueStatus': QueueEntry.QueueStatus,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        entry_id = request.POST.get('entry_id')
        if not entry_id:
            messages.error(request, "Antrian truk yang akan diproses Gate Out tidak ditemukan.")
            return redirect('gate_out')

        try:
            entry_id_int = int(entry_id)
        except (ValueError, TypeError):
            messages.error(request, "Format ID antrian tidak valid.")
            return redirect('gate_out')

        queue_entry = get_object_or_404(QueueEntry, pk=entry_id_int)

        # Validasi ketat: Hanya antrian SELESAI yang dapat diproses Gate Out
        if queue_entry.status != QueueEntry.QueueStatus.SELESAI:
            current_status_label = queue_entry.get_status_display()
            messages.error(
                request,
                f"Antrian [{queue_entry.no_antrian}] ({queue_entry.truck.no_polisi}) berstatus '{current_status_label}'. "
                f"Hanya antrian berstatus 'SELESAI' di yard yang dapat diproses Gate Out!"
            )
            return redirect(f"/gate-out/?entry_id={queue_entry.pk}")

        form = GateOutProcessForm(request.POST)
        if form.is_valid():
            lane = form.cleaned_data['gerbang_lane']
            catatan = form.cleaned_data.get('catatan') or 'Pemeriksaan Gate Out selesai, truk keluar terminal'

            try:
                updated_entry, _ = process_queue_transition(
                    queue_entry_or_id=queue_entry,
                    target_status=QueueEntry.QueueStatus.KELUAR,
                    operator_user=request.user,
                    reason=catatan,
                    lane=lane
                )
                messages.success(
                    request,
                    f"SUKSES GATE OUT! Truk [{updated_entry.truck.no_polisi}] (Antrian {updated_entry.no_antrian}) "
                    f"telah resmi KELUAR terminal melalui {updated_entry.gerbang_lane}."
                )
                return redirect(f"/gate-out/?q={updated_entry.no_antrian}")
            except (QueueTransitionError, QueueValidationError) as e:
                messages.error(request, f"Gagal memproses Gate Out: {str(e)}")
                return redirect(f"/gate-out/?entry_id={queue_entry.pk}")
            except Exception as e:
                messages.error(request, f"Terjadi kesalahan saat pemrosesan Gate Out: {str(e)}")
                return redirect(f"/gate-out/?entry_id={queue_entry.pk}")
        else:
            messages.error(request, "Data formulir Gate Out tidak valid. Harap periksa kembali pilihan gerbang.")
            return redirect(f"/gate-out/?entry_id={queue_entry.pk}")


