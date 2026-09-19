from django.contrib.auth.views import LoginView
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.http import HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q

from .models import OperatorProfile, BoothChoice, ShiftChoice
from .mixins import (
    is_admin_user,
    is_operator_user,
    get_user_role,
    AdminAccessRequiredMixin,
    OperationalAccessMixin,
)
from .forms import (
    TOSLoginForm,
    BOOTH_MAP,
    AdminUserCreateForm,
    AdminUserUpdateForm,
    ROLE_CHOICES,
)


class HomeRedirectView(View):
    """
    Root landing page resolver ('/').
    Mengarahkan pengguna berdasarkan status autentikasi dan peran:
    - Anonim -> /login/
    - Admin -> /admin-dashboard/
    - Operator -> /dashboard/
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if is_admin_user(request.user):
            return redirect('admin_dashboard')
        return redirect('dashboard')


class TOSLoginView(LoginView):
    """
    Workstation Autentikasi Masuk Port-Gate TOS.
    Visual Source of Truth: stitch_reference/ai_studio_export/src/views/LoginView.tsx
    Backend: Django Authentication (django.contrib.auth)
    Menggunakan satu form login untuk seluruh peran, lalu mengarahkan:
    - ADMIN -> /admin-dashboard/
    - OPERATOR -> /dashboard/
    """
    template_name = 'accounts/login.html'
    form_class = TOSLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        redirect_to = self.get_redirect_url()
        if is_admin_user(user):
            if redirect_to and redirect_to.startswith('/admin-dashboard'):
                return redirect_to
            return '/admin-dashboard/'
        else:
            if redirect_to and not redirect_to.startswith('/admin-dashboard'):
                return redirect_to
            return '/dashboard/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['server_time_str'] = timezone.localtime(now).strftime('%d-%b-%Y %H:%M:%S WIB').upper()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.get_user()

        # Atur durasi masa berlaku sesi (Remember Me / Shift 8 Jam)
        remember_me = form.cleaned_data.get('remember_me')
        if remember_me:
            self.request.session.set_expiry(8 * 3600)
        else:
            self.request.session.set_expiry(0)

        # Jika peran adalah Administrator, tidak membutuhkan penugasan booth operasional
        if is_admin_user(user):
            messages.success(
                self.request,
                f"Autentikasi Administrator berhasil: Selamat datang di Port Gate TOS Control Center, {user.get_full_name() or user.username}."
            )
            return response

        # Simpan penugasan booth aktif ke sesi untuk Operator
        booth_key = form.cleaned_data.get('booth')
        if booth_key in BOOTH_MAP:
            label, model_choice = BOOTH_MAP[booth_key]
            self.request.session['assigned_booth'] = booth_key
            self.request.session['assigned_booth_label'] = label

            if hasattr(user, 'operator_profile') and user.operator_profile:
                try:
                    user.operator_profile.booth_aktif = model_choice
                    user.operator_profile.save(update_fields=['booth_aktif', 'updated_at'])
                except Exception:
                    pass
        else:
            self.request.session['assigned_booth'] = 'gate-03'
            self.request.session['assigned_booth_label'] = 'Gate Inbound 03'

        booth_lbl = self.request.session.get('assigned_booth_label', 'Gate Inbound 03')
        messages.success(
            self.request,
            f"Autentikasi berhasil: Selamat bertugas di {booth_lbl}!"
        )

        return response


class TOSLogoutView(View):
    """
    Endpoint keluar sistem / ganti shift operator Port-Gate TOS.
    Mendukung metode GET dan POST, menghapus session Django secara aman,
    dan mengarahkan kembali ke halaman /login/.
    """
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            nama = request.user.get_full_name() or request.user.username
            if hasattr(request.user, 'operator_profile') and request.user.operator_profile.nama:
                nama = request.user.operator_profile.nama
            auth_logout(request)
            messages.info(request, f"Sesi tugas ({nama}) telah ditutup. Silakan masuk kembali.")
        else:
            auth_logout(request)

        return redirect('login')



class AdminDashboardView(AdminAccessRequiredMixin, View):
    """
    Admin Dashboard untuk Manajemen Akun & Hak Akses Pengguna Port Gate TOS.
    Visual Source of Truth: Stitch/AI Studio Design System.
    """
    template_name = 'accounts/admin_dashboard.html'
    paginate_by = 15

    def get(self, request):
        search_query = request.GET.get('search', '').strip()
        role_filter = request.GET.get('role', 'ALL').strip().upper()
        status_filter = request.GET.get('status', 'ALL').strip().upper()

        # 1. Base Queryset
        qs = User.objects.select_related('operator_profile').prefetch_related('groups').order_by('-date_joined')

        # 2. KPI Ringkas (Hitungan Aktual Database)
        total_accounts = User.objects.count()
        active_accounts = User.objects.filter(is_active=True).count()
        inactive_accounts = User.objects.filter(is_active=False).count()

        # Hitung Operator (Grup Operator atau Non-Staff Non-Superuser)
        operator_count = User.objects.filter(
            Q(groups__name='Operator') |
            (Q(is_staff=False) & Q(is_superuser=False) & ~Q(groups__name__in=['Admin', 'Supervisor', 'Manager']))
        ).distinct().count()

        # 3. Filtering
        if search_query:
            qs = qs.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(operator_profile__nip__icontains=search_query) |
                Q(operator_profile__nama__icontains=search_query)
            )

        if status_filter == 'ACTIVE':
            qs = qs.filter(is_active=True)
        elif status_filter == 'INACTIVE':
            qs = qs.filter(is_active=False)

        # 4. Anotasi Role & Atribut untuk Tampilan
        user_list = list(qs)
        for u in user_list:
            u.display_role = get_user_role(u)
            prof = getattr(u, 'operator_profile', None)
            u.display_name = prof.nama if (prof and prof.nama) else (u.get_full_name() or u.username)
            u.display_nip = prof.nip if (prof and prof.nip) else '-'
            u.display_booth = prof.get_booth_aktif_display() if (prof and prof.booth_aktif) else '-'
            u.display_shift = prof.get_shift_aktif_display() if (prof and prof.shift_aktif) else '-'

        # Filter berdasarkan Role jika dipilih
        if role_filter != 'ALL':
            user_list = [u for u in user_list if u.display_role.upper() == role_filter]

        # 5. Pagination
        paginator = Paginator(user_list, self.paginate_by)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'users': page_obj.object_list,
            'filtered_count': len(user_list),
            'total_accounts': total_accounts,
            'active_accounts': active_accounts,
            'inactive_accounts': inactive_accounts,
            'operator_count': operator_count,
            'search_query': search_query,
            'role_filter': role_filter,
            'status_filter': status_filter,
            'role_choices': ROLE_CHOICES,
            'booth_choices': BoothChoice.choices,
            'shift_choices': ShiftChoice.choices,
            'create_form': AdminUserCreateForm(),
        }
        return render(request, self.template_name, context)


class AdminUserCreateView(AdminAccessRequiredMixin, View):
    """
    Endpoint pemrosesan pendaftaran akun pengguna/operator baru oleh Administrator.
    """
    def post(self, request):
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data['role']
            messages.success(
                request,
                f"Akun [{user.username}] berhasil didaftarkan sebagai {role}."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal mendaftarkan akun: {' | '.join(errors)}"
            )

        return redirect('admin_dashboard')


class AdminUserUpdateView(AdminAccessRequiredMixin, View):
    """
    Endpoint pemrosesan pembaruan informasi profil, peran, booth, dan password akun.
    """
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        form = AdminUserUpdateForm(request.POST, target_user=user)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Informasi akun [{user.username}] berhasil diperbarui."
            )
        else:
            errors = []
            for field, err_list in form.errors.items():
                label = form.fields[field].label if field in form.fields and form.fields[field].label else field
                errors.append(f"{label}: {', '.join(err_list)}")
            messages.error(
                request,
                f"Gagal memperbarui akun [{user.username}]: {' | '.join(errors)}"
            )

        return redirect('admin_dashboard')


class AdminUserToggleActiveView(AdminAccessRequiredMixin, View):
    """
    Endpoint cepat untuk aktivasi / deaktivasi izin akses akun pengguna.
    """
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        # Mencegah deaktivasi akun diri sendiri jika sedang login
        if user == request.user:
            messages.error(
                request,
                "Operasi ditolak: Anda tidak dapat menonaktifkan akun Anda sendiri yang sedang aktif digunakan."
            )
            return redirect('admin_dashboard')

        # Mencegah penonaktifan satu-satunya akun Administrator yang aktif dalam sistem
        if user.is_superuser and user.is_active:
            active_superusers = User.objects.filter(is_superuser=True, is_active=True).count()
            if active_superusers <= 1:
                messages.error(
                    request,
                    "Operasi ditolak: Anda tidak dapat menonaktifkan satu-satunya akun Administrator yang aktif dalam sistem."
                )
                return redirect('admin_dashboard')

        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])

        status_text = "DIAKTIFKAN (AKUN AKTIF)" if user.is_active else "DINONAKTIFKAN (AKUN DITANGGUHKAN)"
        messages.success(
            request,
            f"Status akun [{user.username}] berhasil diubah menjadi {status_text}."
        )
        return redirect('admin_dashboard')


class AdminUserDetailJSONView(AdminAccessRequiredMixin, View):
    """
    API endpoint internal untuk pre-filling modal Detail & Edit akun pengguna.
    """
    def get(self, request, pk):
        user = get_object_or_404(
            User.objects.select_related('operator_profile').prefetch_related('groups'),
            pk=pk
        )

        role = get_user_role(user)
        prof = getattr(user, 'operator_profile', None)

        data = {
            'id': user.pk,
            'username': user.username,
            'nama': prof.nama if (prof and prof.nama) else (user.get_full_name() or user.username),
            'nip': prof.nip if (prof and prof.nip) else '',
            'role': role,
            'is_active': user.is_active,
            'booth': prof.booth_aktif if (prof and prof.booth_aktif) else '',
            'booth_display': prof.get_booth_aktif_display() if (prof and prof.booth_aktif) else '-',
            'shift': prof.shift_aktif if (prof and prof.shift_aktif) else '',
            'shift_display': prof.get_shift_aktif_display() if (prof and prof.shift_aktif) else '-',
            'last_login': user.last_login.strftime('%d/%m/%Y %H:%M:%S WIB') if user.last_login else 'Belum Pernah Login',
            'date_joined': user.date_joined.strftime('%d/%m/%Y %H:%M:%S WIB') if user.date_joined else '-',
        }
        return JsonResponse(data)
