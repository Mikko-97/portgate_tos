from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from apps.accounts.mixins import OperationalAccessMixin
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.utils import timezone

from .models import Truck, Driver, Expedition, Container
from .forms import TruckForm, ExpeditionForm, DriverForm, ContainerForm
from apps.queue_gate.models import QueueEntry


def get_masterdata_tab_counts():
    """Helper untuk menghitung jumlah total setiap master data pada tab navigasi."""
    return {
        'total_trucks_tab': Truck.objects.count(),
        'total_drivers_tab': Driver.objects.count(),
        'total_expeditions_tab': Expedition.objects.count(),
        'total_containers_tab': Container.objects.count(),
    }


# ==============================================================================
# 1. MASTER DATA: TRUK ARMADA & CMS
# ==============================================================================

class TruckMasterView(OperationalAccessMixin, View):
    """
    Workstation View untuk Master Data Truk & CMS Terdaftar.
    """
    template_name = 'masterdata/truck_master.html'
    paginate_by = 15

    def get(self, request):
        search_query = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', '').strip()
        config_filter = request.GET.get('config', '').strip()
        expedition_filter = request.GET.get('expedition', '').strip()

        qs = Truck.objects.select_related('driver', 'expedisi').order_by('-created_at', 'no_polisi')

        total_trucks = Truck.objects.count()
        active_trucks = Truck.objects.filter(is_active=True).count()
        inactive_trucks = Truck.objects.filter(is_active=False).count()
        rfid_tagged_trucks = Truck.objects.exclude(rfid_tag__isnull=True).exclude(rfid_tag='').count()

        if search_query:
            qs = qs.filter(
                Q(no_polisi__icontains=search_query) |
                Q(rfid_tag__icontains=search_query) |
                Q(driver__nama__icontains=search_query) |
                Q(driver__no_sim__icontains=search_query) |
                Q(expedisi__nama_perusahaan__icontains=search_query) |
                Q(expedisi__kode_ekspedisi__icontains=search_query)
            )

        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)

        if config_filter and config_filter in Truck.TruckConfigChoice.values:
            qs = qs.filter(konfigurasi=config_filter)

        if expedition_filter and expedition_filter.isdigit():
            qs = qs.filter(expedisi_id=int(expedition_filter))

        paginator = Paginator(qs, self.paginate_by)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        expeditions = Expedition.objects.filter(is_active=True).order_by('nama_perusahaan')
        drivers = Driver.objects.filter(is_active=True).order_by('nama')
        config_choices = Truck.TruckConfigChoice.choices

        context = {
            'page_obj': page_obj,
            'trucks': page_obj.object_list,
            'filtered_count': qs.count(),
            'total_trucks': total_trucks,
            'active_trucks': active_trucks,
            'inactive_trucks': inactive_trucks,
            'rfid_tagged_trucks': rfid_tagged_trucks,
            'search_query': search_query,
            'status_filter': status_filter,
            'config_filter': config_filter,
            'expedition_filter': expedition_filter,
            'expeditions': expeditions,
            'drivers': drivers,
            'config_choices': config_choices,
            'truck_form': TruckForm(),
            'active_tab': 'truck',
            **get_masterdata_tab_counts(),
        }
        return render(request, self.template_name, context)


class TruckCreateView(OperationalAccessMixin, View):
    def post(self, request):
        form = TruckForm(request.POST)
        if form.is_valid():
            truck = form.save()
            messages.success(
                request,
                f"Armada [{truck.no_polisi}] berhasil didaftarkan ke dalam Master Data Port-Gate TOS."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal mendaftarkan armada: {' | '.join(errors)}"
            )
        return redirect('truck_master')


class TruckUpdateView(OperationalAccessMixin, View):
    def post(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        form = TruckForm(request.POST, instance=truck)
        if form.is_valid():
            updated_truck = form.save()
            messages.success(
                request,
                f"Data armada [{updated_truck.no_polisi}] berhasil diperbarui."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal memperbarui armada [{truck.no_polisi}]: {' | '.join(errors)}"
            )
        return redirect('truck_master')


class TruckToggleActiveView(OperationalAccessMixin, View):
    def post(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        truck.is_active = not truck.is_active
        truck.save(update_fields=['is_active', 'updated_at'])

        status_text = "AKTIF (BERIZIN)" if truck.is_active else "NON-AKTIF (HOLD OPERASI)"
        messages.success(
            request,
            f"Status izin armada [{truck.no_polisi}] berhasil diubah menjadi {status_text}."
        )
        return redirect('truck_master')


class TruckDetailJSONView(OperationalAccessMixin, View):
    def get(self, request, pk):
        truck = get_object_or_404(
            Truck.objects.select_related('driver', 'expedisi'),
            pk=pk
        )
        recent_queues = []
        for q in QueueEntry.objects.filter(truck=truck).order_by('-waktu_masuk')[:5]:
            recent_queues.append({
                'no_antrian': q.no_antrian,
                'status': q.get_status_display(),
                'status_raw': q.status,
                'waktu_masuk': timezone.localtime(q.waktu_masuk).strftime('%d/%m/%Y %H:%M:%S') if q.waktu_masuk else '-',
                'lane': q.gerbang_lane or '-',
            })

        data = {
            'id': truck.pk,
            'no_polisi': truck.no_polisi,
            'konfigurasi': truck.konfigurasi,
            'konfigurasi_display': truck.get_konfigurasi_display(),
            'rfid_tag': truck.rfid_tag or '',
            'is_active': truck.is_active,
            'expedisi_id': truck.expedisi_id,
            'expedisi_nama': truck.expedisi.nama_perusahaan if truck.expedisi else '-',
            'expedisi_kode': truck.expedisi.kode_ekspedisi if truck.expedisi else '-',
            'driver_id': truck.driver_id or '',
            'driver_nama': truck.driver.nama if truck.driver else 'Belum Ditentukan',
            'driver_sim': truck.driver.no_sim if truck.driver else '-',
            'driver_hp': truck.driver.no_hp if truck.driver else '-',
            'created_at': timezone.localtime(truck.created_at).strftime('%d/%m/%Y %H:%M:%S') if truck.created_at else '-',
            'updated_at': timezone.localtime(truck.updated_at).strftime('%d/%m/%Y %H:%M:%S') if truck.updated_at else '-',
            'recent_queues': recent_queues,
        }
        return JsonResponse(data)


# ==============================================================================
# 2. MASTER DATA: PERUSAHAAN EKSPEDISI
# ==============================================================================

class ExpeditionMasterView(OperationalAccessMixin, View):
    """
    Workstation View untuk Master Data Perusahaan Ekspedisi / Transportir.
    """
    template_name = 'masterdata/expedition_master.html'
    paginate_by = 15

    def get(self, request):
        search_query = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = Expedition.objects.annotate(
            trucks_count=Count('trucks')
        ).order_by('nama_perusahaan')

        total_expeditions = Expedition.objects.count()
        active_expeditions = Expedition.objects.filter(is_active=True).count()
        inactive_expeditions = Expedition.objects.filter(is_active=False).count()
        total_trucks_registered = Truck.objects.filter(expedisi__isnull=False).count()

        if search_query:
            qs = qs.filter(
                Q(nama_perusahaan__icontains=search_query) |
                Q(kode_ekspedisi__icontains=search_query) |
                Q(no_telepon__icontains=search_query)
            )

        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)

        paginator = Paginator(qs, self.paginate_by)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'expeditions': page_obj.object_list,
            'filtered_count': qs.count(),
            'total_expeditions': total_expeditions,
            'active_expeditions': active_expeditions,
            'inactive_expeditions': inactive_expeditions,
            'total_trucks_registered': total_trucks_registered,
            'search_query': search_query,
            'status_filter': status_filter,
            'expedition_form': ExpeditionForm(),
            'active_tab': 'expedition',
            **get_masterdata_tab_counts(),
        }
        return render(request, self.template_name, context)


class ExpeditionCreateView(OperationalAccessMixin, View):
    def post(self, request):
        form = ExpeditionForm(request.POST)
        if form.is_valid():
            exp = form.save()
            messages.success(
                request,
                f"Perusahaan ekspedisi [{exp.nama_perusahaan}] berhasil didaftarkan."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal mendaftarkan ekspedisi: {' | '.join(errors)}"
            )
        return redirect('expedition_master')


class ExpeditionUpdateView(OperationalAccessMixin, View):
    def post(self, request, pk):
        exp = get_object_or_404(Expedition, pk=pk)
        form = ExpeditionForm(request.POST, instance=exp)
        if form.is_valid():
            updated = form.save()
            messages.success(
                request,
                f"Data ekspedisi [{updated.nama_perusahaan}] berhasil diperbarui."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal memperbarui ekspedisi [{exp.nama_perusahaan}]: {' | '.join(errors)}"
            )
        return redirect('expedition_master')


class ExpeditionToggleActiveView(OperationalAccessMixin, View):
    def post(self, request, pk):
        exp = get_object_or_404(Expedition, pk=pk)
        exp.is_active = not exp.is_active
        exp.save(update_fields=['is_active', 'updated_at'])

        status_text = "AKTIF" if exp.is_active else "NON-AKTIF"
        messages.success(
            request,
            f"Status perusahaan ekspedisi [{exp.nama_perusahaan}] diubah menjadi {status_text}."
        )
        return redirect('expedition_master')


class ExpeditionDetailJSONView(OperationalAccessMixin, View):
    def get(self, request, pk):
        exp = get_object_or_404(
            Expedition.objects.prefetch_related('trucks'),
            pk=pk
        )
        trucks = []
        for t in exp.trucks.all()[:10]:
            trucks.append({
                'id': t.id,
                'no_polisi': t.no_polisi,
                'konfigurasi': t.get_konfigurasi_display(),
                'rfid_tag': t.rfid_tag or '-',
                'is_active': t.is_active,
            })

        data = {
            'id': exp.pk,
            'nama_perusahaan': exp.nama_perusahaan,
            'kode_ekspedisi': exp.kode_ekspedisi or '',
            'no_telepon': exp.no_telepon or '',
            'is_active': exp.is_active,
            'created_at': timezone.localtime(exp.created_at).strftime('%d/%m/%Y %H:%M:%S') if exp.created_at else '-',
            'updated_at': timezone.localtime(exp.updated_at).strftime('%d/%m/%Y %H:%M:%S') if exp.updated_at else '-',
            'total_trucks': exp.trucks.count(),
            'trucks': trucks,
        }
        return JsonResponse(data)


# ==============================================================================
# 3. MASTER DATA: SOPIR TRUK
# ==============================================================================

class DriverMasterView(OperationalAccessMixin, View):
    """
    Workstation View untuk Master Data Sopir Truk Berlisensi.
    """
    template_name = 'masterdata/driver_master.html'
    paginate_by = 15

    def get(self, request):
        search_query = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', '').strip()

        qs = Driver.objects.prefetch_related('trucks').order_by('nama')

        total_drivers = Driver.objects.count()
        active_drivers = Driver.objects.filter(is_active=True).count()
        inactive_drivers = Driver.objects.filter(is_active=False).count()
        assigned_drivers = Driver.objects.filter(trucks__isnull=False).distinct().count()

        if search_query:
            qs = qs.filter(
                Q(nama__icontains=search_query) |
                Q(no_sim__icontains=search_query) |
                Q(no_hp__icontains=search_query)
            )

        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)

        paginator = Paginator(qs, self.paginate_by)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'drivers': page_obj.object_list,
            'filtered_count': qs.count(),
            'total_drivers': total_drivers,
            'active_drivers': active_drivers,
            'inactive_drivers': inactive_drivers,
            'assigned_drivers': assigned_drivers,
            'search_query': search_query,
            'status_filter': status_filter,
            'driver_form': DriverForm(),
            'active_tab': 'driver',
            **get_masterdata_tab_counts(),
        }
        return render(request, self.template_name, context)


class DriverCreateView(OperationalAccessMixin, View):
    def post(self, request):
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save()
            messages.success(
                request,
                f"Sopir [{driver.nama}] dengan nomor SIM [{driver.no_sim}] berhasil didaftarkan."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal mendaftarkan sopir: {' | '.join(errors)}"
            )
        return redirect('driver_master')


class DriverUpdateView(OperationalAccessMixin, View):
    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        form = DriverForm(request.POST, instance=driver)
        if form.is_valid():
            updated = form.save()
            messages.success(
                request,
                f"Data sopir [{updated.nama}] berhasil diperbarui."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal memperbarui sopir [{driver.nama}]: {' | '.join(errors)}"
            )
        return redirect('driver_master')


class DriverToggleActiveView(OperationalAccessMixin, View):
    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        driver.is_active = not driver.is_active
        driver.save(update_fields=['is_active', 'updated_at'])

        status_text = "AKTIF (BERLISENSI)" if driver.is_active else "NON-AKTIF (HOLD)"
        messages.success(
            request,
            f"Status lisensi sopir [{driver.nama}] diubah menjadi {status_text}."
        )
        return redirect('driver_master')


class DriverDetailJSONView(OperationalAccessMixin, View):
    def get(self, request, pk):
        driver = get_object_or_404(
            Driver.objects.prefetch_related('trucks'),
            pk=pk
        )
        recent_queues = []
        for q in QueueEntry.objects.filter(driver=driver).order_by('-waktu_masuk')[:5]:
            recent_queues.append({
                'no_antrian': q.no_antrian,
                'truck_plate': q.truck.no_polisi if q.truck else '-',
                'status': q.get_status_display(),
                'waktu_masuk': timezone.localtime(q.waktu_masuk).strftime('%d/%m/%Y %H:%M:%S') if q.waktu_masuk else '-',
            })

        default_truck = driver.trucks.first()

        data = {
            'id': driver.pk,
            'nama': driver.nama,
            'no_sim': driver.no_sim,
            'no_hp': driver.no_hp,
            'is_active': driver.is_active,
            'default_truck': default_truck.no_polisi if default_truck else None,
            'created_at': timezone.localtime(driver.created_at).strftime('%d/%m/%Y %H:%M:%S') if driver.created_at else '-',
            'updated_at': timezone.localtime(driver.updated_at).strftime('%d/%m/%Y %H:%M:%S') if driver.updated_at else '-',
            'recent_queues': recent_queues,
        }
        return JsonResponse(data)


# ==============================================================================
# 4. MASTER DATA: PETI KEMAS / KONTAINER
# ==============================================================================

class ContainerMasterView(OperationalAccessMixin, View):
    """
    Workstation View untuk Master Data Peti Kemas / Kontainer ISO 6346.
    """
    template_name = 'masterdata/container_master.html'
    paginate_by = 15

    def get(self, request):
        search_query = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', '').strip()
        ukuran_filter = request.GET.get('ukuran', '').strip()
        tipe_filter = request.GET.get('tipe', '').strip()
        kategori_filter = request.GET.get('kategori', '').strip()
        vgm_filter = request.GET.get('vgm', '').strip()

        qs = Container.objects.order_by('-created_at', 'no_kontainer')

        total_containers = Container.objects.count()
        active_containers = Container.objects.filter(is_active=True).count()
        inactive_containers = Container.objects.filter(is_active=False).count()
        import_count = Container.objects.filter(kategori=Container.CargoCategoryChoice.IMPORT).count()
        export_count = Container.objects.filter(kategori=Container.CargoCategoryChoice.EXPORT).count()
        empty_count = Container.objects.filter(kategori=Container.CargoCategoryChoice.EMPTY_RETURN).count()
        vgm_verified_count = Container.objects.filter(status_vgm=Container.VGMStatusChoice.VERIFIED).count()

        if search_query:
            qs = qs.filter(
                Q(no_kontainer__icontains=search_query) |
                Q(shipping_line__icontains=search_query) |
                Q(seal_number__icontains=search_query) |
                Q(ref_dokumen__icontains=search_query)
            )

        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)

        if ukuran_filter and ukuran_filter in Container.ContainerSizeChoice.values:
            qs = qs.filter(ukuran=ukuran_filter)

        if tipe_filter and tipe_filter in Container.ContainerTypeChoice.values:
            qs = qs.filter(tipe=tipe_filter)

        if kategori_filter and kategori_filter in Container.CargoCategoryChoice.values:
            qs = qs.filter(kategori=kategori_filter)

        if vgm_filter and vgm_filter in Container.VGMStatusChoice.values:
            qs = qs.filter(status_vgm=vgm_filter)

        paginator = Paginator(qs, self.paginate_by)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'containers': page_obj.object_list,
            'filtered_count': qs.count(),
            'total_containers': total_containers,
            'active_containers': active_containers,
            'inactive_containers': inactive_containers,
            'import_count': import_count,
            'export_count': export_count,
            'empty_count': empty_count,
            'vgm_verified_count': vgm_verified_count,
            'search_query': search_query,
            'status_filter': status_filter,
            'ukuran_filter': ukuran_filter,
            'tipe_filter': tipe_filter,
            'kategori_filter': kategori_filter,
            'vgm_filter': vgm_filter,
            'size_choices': Container.ContainerSizeChoice.choices,
            'type_choices': Container.ContainerTypeChoice.choices,
            'category_choices': Container.CargoCategoryChoice.choices,
            'vgm_choices': Container.VGMStatusChoice.choices,
            'container_form': ContainerForm(),
            'active_tab': 'container',
            **get_masterdata_tab_counts(),
        }
        return render(request, self.template_name, context)


class ContainerCreateView(OperationalAccessMixin, View):
    def post(self, request):
        form = ContainerForm(request.POST)
        if form.is_valid():
            container = form.save()
            messages.success(
                request,
                f"Peti kemas [{container.no_kontainer}] ({container.ukuran} {container.tipe}) berhasil didaftarkan."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal mendaftarkan peti kemas: {' | '.join(errors)}"
            )
        return redirect('container_master')


class ContainerUpdateView(OperationalAccessMixin, View):
    def post(self, request, pk):
        container = get_object_or_404(Container, pk=pk)
        form = ContainerForm(request.POST, instance=container)
        if form.is_valid():
            updated = form.save()
            messages.success(
                request,
                f"Data peti kemas [{updated.no_kontainer}] berhasil diperbarui."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal memperbarui kontainer [{container.no_kontainer}]: {' | '.join(errors)}"
            )
        return redirect('container_master')


class ContainerToggleActiveView(OperationalAccessMixin, View):
    def post(self, request, pk):
        container = get_object_or_404(Container, pk=pk)
        container.is_active = not container.is_active
        container.save(update_fields=['is_active', 'updated_at'])

        status_text = "AKTIF (SIAP OPERASI)" if container.is_active else "NON-AKTIF (HOLD / REPAIR)"
        messages.success(
            request,
            f"Status peti kemas [{container.no_kontainer}] diubah menjadi {status_text}."
        )
        return redirect('container_master')


class ContainerDetailJSONView(OperationalAccessMixin, View):
    def get(self, request, pk):
        container = get_object_or_404(Container, pk=pk)
        recent_queues = []
        for q in QueueEntry.objects.filter(container=container).select_related('truck', 'driver').order_by('-waktu_masuk')[:5]:
            recent_queues.append({
                'no_antrian': q.no_antrian,
                'truck_plate': q.truck.no_polisi if q.truck else '-',
                'driver_name': q.driver.nama if q.driver else '-',
                'status': q.get_status_display(),
                'waktu_masuk': timezone.localtime(q.waktu_masuk).strftime('%d/%m/%Y %H:%M:%S') if q.waktu_masuk else '-',
            })

        data = {
            'id': container.pk,
            'no_kontainer': container.no_kontainer,
            'ukuran': container.ukuran,
            'ukuran_display': container.get_ukuran_display(),
            'tipe': container.tipe,
            'tipe_display': container.get_tipe_display(),
            'kategori': container.kategori,
            'kategori_display': container.get_kategori_display(),
            'berat_kotor': str(container.berat_kotor),
            'shipping_line': container.shipping_line or '-',
            'seal_number': container.seal_number or '-',
            'ref_dokumen': container.ref_dokumen or '-',
            'status_vgm': container.status_vgm,
            'status_vgm_display': container.get_status_vgm_display(),
            'is_active': container.is_active,
            'created_at': timezone.localtime(container.created_at).strftime('%d/%m/%Y %H:%M:%S') if container.created_at else '-',
            'updated_at': timezone.localtime(container.updated_at).strftime('%d/%m/%Y %H:%M:%S') if container.updated_at else '-',
            'recent_queues': recent_queues,
        }
        return JsonResponse(data)
