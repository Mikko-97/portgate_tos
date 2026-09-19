from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import BoothChoice, ShiftChoice, OperatorProfile


BOOTH_CHOICES = [
    ('gate-03', 'Gate Inbound 03 (Jalur 2 - Standar)'),
    ('gate-01', 'Gate Inbound 01 (Jalur 1 - Timbang Cepat)'),
    ('gate-02', 'Gate Inbound 02 (Jalur Reefer & Khusus)'),
    ('gate-04', 'Gate Inbound 04 (Jalur Masalah / Trouble)'),
    ('out-01', 'Gate Outbound 01 (Exit Gateway)'),
    ('spv', 'Supervisor Kontrol Utama (Semua Jalur)'),
]

BOOTH_MAP = {
    'gate-03': ('Gate Inbound 03', BoothChoice.GATE_IN_03),
    'gate-01': ('Gate Inbound 01', BoothChoice.GATE_IN_01),
    'gate-02': ('Gate Inbound 02', BoothChoice.GATE_IN_02),
    'gate-04': ('Gate Inbound 04', BoothChoice.GATE_IN_04),
    'out-01': ('Gate Outbound 01', BoothChoice.GATE_OUT_01),
    'spv': ('Central Desk / Supervisor', BoothChoice.CENTRAL_DESK),
}

ROLE_CHOICES = [
    ('Operator', 'Operator (Petugas Gardu Gerbang)'),
    ('Supervisor', 'Supervisor (Pengawas Lapangan & Jalur)'),
    ('Manager', 'Manager (Manajemen Operasional Terminal)'),
    ('Admin', 'Administrator (Akses Penuh TOS)'),
]


class TOSLoginForm(AuthenticationForm):
    """
    Form autentikasi operator Port Gate TOS.
    Mendukung login dengan Username Django maupun NIP OperatorProfile,
    serta pemilihan booth gardu aktif dan durasi shift sesi 8 jam.
    """
    username = forms.CharField(
        label="ID Operator / NIP TOS",
        widget=forms.TextInput(attrs={
            'class': 'tos-login-input',
            'placeholder': 'Contoh: TOS-88421 atau username',
            'autocomplete': 'username',
            'autofocus': 'autofocus',
            'id': 'operatorIdInput',
        })
    )
    password = forms.CharField(
        label="Kata Sandi / PIN Gardu",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'tos-login-input',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
            'id': 'passwordInput',
        })
    )
    booth = forms.ChoiceField(
        label="Penugasan Booth / Gardu Gerbang",
        choices=BOOTH_CHOICES,
        initial='gate-03',
        required=False,
        widget=forms.Select(attrs={
            'class': 'tos-login-select',
            'id': 'boothSelect',
        })
    )
    remember_me = forms.BooleanField(
        label="Ingat sesi di komputer gardu ini (Shift 8 Jam)",
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'tos-login-checkbox',
            'id': 'rememberMe',
        })
    )

    error_messages = {
        'invalid_login': _(
            "ID Operator atau Kata Sandi tidak valid. Silakan periksa kembali kredensial Anda."
        ),
        'inactive': _("Akun operator ini tidak aktif. Silakan hubungi Supervisor Terminal."),
    }

    def clean(self):
        username = self.cleaned_data.get('username', '').strip()
        password = self.cleaned_data.get('password')

        if username and password:
            # 1. Autentikasi langsung dengan username Django
            self.user_cache = authenticate(self.request, username=username, password=password)

            # 2. Jika tidak ditemukan, coba cari apakah input adalah NIP di OperatorProfile
            if self.user_cache is None:
                profile = OperatorProfile.objects.filter(nip__iexact=username).select_related('user').first()
                if profile and profile.user:
                    self.user_cache = authenticate(self.request, username=profile.user.username, password=password)

            if self.user_cache is None:
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class AdminUserCreateForm(forms.Form):
    """
    Form registrasi akun operator/pengguna baru oleh Administrator TOS.
    """
    username = forms.CharField(
        max_length=150,
        label="Username / Operator ID",
        widget=forms.TextInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded',
            'placeholder': 'Contoh: op_gate03 atau TOS-88421',
            'required': 'required',
        })
    )
    nip = forms.CharField(
        max_length=30,
        label="NIP / ID Petugas TOS",
        widget=forms.TextInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded uppercase',
            'placeholder': 'Contoh: TOS-88421',
            'required': 'required',
        })
    )
    nama = forms.CharField(
        max_length=150,
        label="Nama Lengkap Operator",
        widget=forms.TextInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-body-sm text-body-sm text-on-surface focus:outline-none focus:border-secondary rounded',
            'placeholder': 'Nama lengkap petugas...',
            'required': 'required',
        })
    )
    password = forms.CharField(
        label="Kata Sandi / PIN",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded',
            'placeholder': 'Minimal 8 karakter...',
            'required': 'required',
        })
    )
    confirm_password = forms.CharField(
        label="Konfirmasi Kata Sandi",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded',
            'placeholder': 'Ulangi kata sandi...',
            'required': 'required',
        })
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial='Operator',
        label="Peran / Hak Akses (Role)",
        widget=forms.Select(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded cursor-pointer',
        })
    )
    is_active = forms.BooleanField(
        initial=True,
        required=False,
        label="Status Izin Aktif",
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-secondary bg-surface-container-low border-outline-variant rounded cursor-pointer',
        })
    )
    booth = forms.ChoiceField(
        choices=[('', '-- Tanpa Penugasan Tetap --')] + list(BoothChoice.choices),
        required=False,
        label="Penugasan Booth Utama",
        widget=forms.Select(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded cursor-pointer',
        })
    )
    shift = forms.ChoiceField(
        choices=[('', '-- Tanpa Shift Tetap --')] + list(ShiftChoice.choices),
        required=False,
        label="Shift Kerja Utama",
        widget=forms.Select(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded cursor-pointer',
        })
    )

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise ValidationError("Username tidak boleh kosong.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(f"Username '{username}' sudah digunakan.")
        return username

    def clean_nip(self):
        nip = self.cleaned_data.get('nip', '').strip().upper()
        if not nip:
            raise ValidationError("NIP / ID Petugas tidak boleh kosong.")
        if OperatorProfile.objects.filter(nip__iexact=nip).exists():
            raise ValidationError(f"NIP '{nip}' sudah terdaftar pada operator lain.")
        return nip

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "Konfirmasi kata sandi tidak cocok.")
            else:
                try:
                    validate_password(password)
                except ValidationError as e:
                    self.add_error('password', e)

        return cleaned_data

    def save(self):
        username = self.cleaned_data['username']
        password = self.cleaned_data['password']
        nama = self.cleaned_data['nama']
        nip = self.cleaned_data['nip']
        role = self.cleaned_data['role']
        is_active = self.cleaned_data.get('is_active', True)
        booth = self.cleaned_data.get('booth') or None
        shift = self.cleaned_data.get('shift') or None

        # 1. Buat user Django dengan password terenkripsi aman
        user = User.objects.create_user(
            username=username,
            password=password,
            is_active=is_active
        )
        user.first_name = nama
        if role == 'Admin':
            user.is_staff = True
        else:
            user.is_staff = False
        user.save()

        # 2. Masukkan user ke Group Django yang sesuai
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)

        # 3. Buat OperatorProfile untuk user
        OperatorProfile.objects.create(
            user=user,
            nip=nip,
            nama=nama,
            booth_aktif=booth,
            shift_aktif=shift
        )

        return user


class AdminUserUpdateForm(forms.Form):
    """
    Form pembaruan informasi profil, peran, booth, dan password operator.
    """
    nama = forms.CharField(
        max_length=150,
        label="Nama Lengkap Operator",
        widget=forms.TextInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-body-sm text-body-sm text-on-surface focus:outline-none focus:border-secondary rounded',
            'required': 'required',
            'id': 'editNamaInput',
        })
    )
    nip = forms.CharField(
        max_length=30,
        label="NIP / ID Petugas TOS",
        widget=forms.TextInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded uppercase',
            'required': 'required',
            'id': 'editNipInput',
        })
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        label="Peran / Hak Akses (Role)",
        widget=forms.Select(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded cursor-pointer',
            'id': 'editRoleSelect',
        })
    )
    is_active = forms.BooleanField(
        required=False,
        label="Status Izin Aktif",
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-secondary bg-surface-container-low border-outline-variant rounded cursor-pointer',
            'id': 'editIsActiveCheckbox',
        })
    )
    booth = forms.ChoiceField(
        choices=[('', '-- Tanpa Penugasan Tetap --')] + list(BoothChoice.choices),
        required=False,
        label="Penugasan Booth Utama",
        widget=forms.Select(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded cursor-pointer',
            'id': 'editBoothSelect',
        })
    )
    shift = forms.ChoiceField(
        choices=[('', '-- Tanpa Shift Tetap --')] + list(ShiftChoice.choices),
        required=False,
        label="Shift Kerja Utama",
        widget=forms.Select(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded cursor-pointer',
            'id': 'editShiftSelect',
        })
    )
    new_password = forms.CharField(
        label="Ganti Kata Sandi Baru (Opsional)",
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded',
            'placeholder': 'Kosongkan jika tidak ingin mengubah kata sandi',
            'id': 'editNewPasswordInput',
        })
    )
    confirm_new_password = forms.CharField(
        label="Konfirmasi Kata Sandi Baru",
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant font-code-sm text-code-sm text-on-surface focus:outline-none focus:border-secondary rounded',
            'placeholder': 'Ulangi kata sandi baru...',
            'id': 'editConfirmNewPasswordInput',
        })
    )

    def __init__(self, *args, target_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_user = target_user

    def clean_nip(self):
        nip = self.cleaned_data.get('nip', '').strip().upper()
        if not nip:
            raise ValidationError("NIP tidak boleh kosong.")
        qs = OperatorProfile.objects.filter(nip__iexact=nip)
        if self.target_user:
            qs = qs.exclude(user=self.target_user)
        if qs.exists():
            raise ValidationError(f"NIP '{nip}' sudah digunakan oleh operator lain.")
        return nip

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_new_password = cleaned_data.get('confirm_new_password')

        if new_password:
            if new_password != confirm_new_password:
                self.add_error('confirm_new_password', "Konfirmasi kata sandi baru tidak cocok.")
            else:
                try:
                    validate_password(new_password, user=self.target_user)
                except ValidationError as e:
                    self.add_error('new_password', e)

        return cleaned_data

    def save(self):
        nama = self.cleaned_data['nama']
        nip = self.cleaned_data['nip']
        role = self.cleaned_data['role']
        is_active = self.cleaned_data.get('is_active', False)
        booth = self.cleaned_data.get('booth') or None
        shift = self.cleaned_data.get('shift') or None
        new_password = self.cleaned_data.get('new_password')

        user = self.target_user

        # 1. Update status aktif & nama
        user.is_active = is_active
        user.first_name = nama
        if role == 'Admin':
            user.is_staff = True
        elif not user.is_superuser:
            user.is_staff = False

        if new_password:
            user.set_password(new_password)

        user.save()

        # 2. Update Role / Group (Single-role architecture)
        all_roles = ['Admin', 'Supervisor', 'Manager', 'Operator']
        for r_name in all_roles:
            grp = Group.objects.filter(name=r_name).first()
            if grp:
                user.groups.remove(grp)

        target_group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(target_group)

        # 3. Update OperatorProfile
        profile, _ = OperatorProfile.objects.get_or_create(
            user=user,
            defaults={'nip': nip, 'nama': nama}
        )
        profile.nama = nama
        profile.nip = nip
        profile.booth_aktif = booth
        profile.shift_aktif = shift
        profile.save()

        return user
