import re
from django import forms
from django.db.models import Q
from .models import Truck, Driver, Expedition, Container


class TruckForm(forms.ModelForm):
    """
    Formulir validasi untuk Master Data Truk & CMS Terdaftar.
    Menjamin keunikan nomor polisi dan RFID tag, serta memastikan
    relasi driver dan expedisi valid dari database Supabase PostgreSQL.
    """
    class Meta:
        model = Truck
        fields = [
            'no_polisi',
            'konfigurasi',
            'rfid_tag',
            'expedisi',
            'driver',
            'is_active',
        ]
        widgets = {
            'no_polisi': forms.TextInput(attrs={
                'class': 'form-control font-code-md text-code-md uppercase',
                'placeholder': 'Contoh: B 9012 XYZ',
                'required': True,
                'autocomplete': 'off',
            }),
            'konfigurasi': forms.Select(attrs={
                'class': 'form-select font-body-sm text-body-sm',
                'required': True,
            }),
            'rfid_tag': forms.TextInput(attrs={
                'class': 'form-control font-code-sm text-code-sm uppercase',
                'placeholder': 'Contoh: RFID-KJA-9912',
                'autocomplete': 'off',
            }),
            'expedisi': forms.Select(attrs={
                'class': 'form-select font-body-sm text-body-sm',
                'required': True,
            }),
            'driver': forms.Select(attrs={
                'class': 'form-select font-body-sm text-body-sm',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Menampilkan ekspedisi dan supir aktif, serta mempertahankan relasi eksisting saat edit
        if self.instance and self.instance.pk:
            exp_filter = Q(is_active=True)
            if self.instance.expedisi_id:
                exp_filter |= Q(pk=self.instance.expedisi_id)
            self.fields['expedisi'].queryset = Expedition.objects.filter(exp_filter).order_by('nama_perusahaan')

            drv_filter = Q(is_active=True)
            if self.instance.driver_id:
                drv_filter |= Q(pk=self.instance.driver_id)
            self.fields['driver'].queryset = Driver.objects.filter(drv_filter).order_by('nama')
        else:
            self.fields['expedisi'].queryset = Expedition.objects.filter(is_active=True).order_by('nama_perusahaan')
            self.fields['driver'].queryset = Driver.objects.filter(is_active=True).order_by('nama')

        self.fields['driver'].required = False
        self.fields['rfid_tag'].required = False
        self.fields['expedisi'].empty_label = "-- Pilih Perusahaan Ekspedisi --"
        self.fields['driver'].empty_label = "-- Tanpa Sopir Tetap (Opsional) --"

    def clean_no_polisi(self):
        nopol = self.cleaned_data.get('no_polisi', '')
        if nopol:
            nopol = re.sub(r'\s+', ' ', nopol.strip().upper())
            qs = Truck.objects.filter(no_polisi__iexact=nopol)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Truk dengan nomor polisi '{nopol}' sudah terdaftar dalam sistem.")
            return nopol
        raise forms.ValidationError("Nomor polisi wajib diisi.")

    def clean_rfid_tag(self):
        rfid = self.cleaned_data.get('rfid_tag')
        if rfid:
            rfid = rfid.strip().upper()
            if rfid:
                qs = Truck.objects.filter(rfid_tag__iexact=rfid)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise forms.ValidationError(f"RFID Tag '{rfid}' sudah digunakan oleh armada lain.")
                return rfid
        return None


class ExpeditionForm(forms.ModelForm):
    """
    Formulir validasi Master Data Perusahaan Ekspedisi.
    """
    class Meta:
        model = Expedition
        fields = [
            'nama_perusahaan',
            'kode_ekspedisi',
            'no_telepon',
            'is_active',
        ]
        widgets = {
            'nama_perusahaan': forms.TextInput(attrs={
                'class': 'form-control font-code-md text-code-md uppercase',
                'placeholder': 'Contoh: PT SAMUDERA LOGISTIK UTAMA',
                'required': True,
                'autocomplete': 'off',
            }),
            'kode_ekspedisi': forms.TextInput(attrs={
                'class': 'form-control font-code-sm text-code-sm uppercase',
                'placeholder': 'Contoh: SLU-01',
                'autocomplete': 'off',
            }),
            'no_telepon': forms.TextInput(attrs={
                'class': 'form-control font-body-sm text-body-sm',
                'placeholder': 'Contoh: 021-43901234 atau 08123456789',
                'autocomplete': 'off',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def clean_nama_perusahaan(self):
        nama = self.cleaned_data.get('nama_perusahaan', '')
        if nama:
            nama = re.sub(r'\s+', ' ', nama.strip().upper())
            qs = Expedition.objects.filter(nama_perusahaan__iexact=nama)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Perusahaan ekspedisi dengan nama '{nama}' sudah terdaftar dalam sistem.")
            return nama
        raise forms.ValidationError("Nama perusahaan ekspedisi wajib diisi.")

    def clean_kode_ekspedisi(self):
        kode = self.cleaned_data.get('kode_ekspedisi')
        if kode:
            kode = kode.strip().upper()
            if kode:
                qs = Expedition.objects.filter(kode_ekspedisi__iexact=kode)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise forms.ValidationError(f"Kode ekspedisi '{kode}' sudah digunakan oleh perusahaan lain.")
                return kode
        return None


class DriverForm(forms.ModelForm):
    """
    Formulir validasi Master Data Sopir Truk Kontainer.
    """
    class Meta:
        model = Driver
        fields = [
            'nama',
            'no_sim',
            'no_hp',
            'is_active',
        ]
        widgets = {
            'nama': forms.TextInput(attrs={
                'class': 'form-control font-body-md text-body-md',
                'placeholder': 'Nama lengkap sesuai KTP / SIM B2 Umum',
                'required': True,
                'autocomplete': 'off',
            }),
            'no_sim': forms.TextInput(attrs={
                'class': 'form-control font-code-md text-code-md uppercase',
                'placeholder': 'Contoh: SIM-B2-990182412',
                'required': True,
                'autocomplete': 'off',
            }),
            'no_hp': forms.TextInput(attrs={
                'class': 'form-control font-code-sm text-code-sm',
                'placeholder': 'Contoh: 081298765432',
                'required': True,
                'autocomplete': 'off',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def clean_nama(self):
        nama = self.cleaned_data.get('nama', '')
        if nama:
            return re.sub(r'\s+', ' ', nama.strip())
        raise forms.ValidationError("Nama sopir wajib diisi.")

    def clean_no_sim(self):
        sim = self.cleaned_data.get('no_sim', '')
        if sim:
            sim = sim.strip().upper()
            qs = Driver.objects.filter(no_sim__iexact=sim)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Sopir dengan nomor SIM '{sim}' sudah terdaftar dalam sistem.")
            return sim
        raise forms.ValidationError("Nomor SIM wajib diisi.")

    def clean_no_hp(self):
        hp = self.cleaned_data.get('no_hp', '')
        if hp:
            hp = hp.strip()
            if not re.match(r'^[0-9+\-\s]{8,25}$', hp):
                raise forms.ValidationError("Format nomor HP tidak valid (hanya angka, tanda +, spasi, dan strip).")
            return hp
        raise forms.ValidationError("Nomor HP / WhatsApp wajib diisi.")


class ContainerForm(forms.ModelForm):
    """
    Formulir validasi Master Data Peti Kemas / Kontainer.
    Menerapkan validasi ISO 6346 yang selaras dengan Gate In.
    """
    class Meta:
        model = Container
        fields = [
            'no_kontainer',
            'ukuran',
            'tipe',
            'kategori',
            'berat_kotor',
            'shipping_line',
            'seal_number',
            'ref_dokumen',
            'status_vgm',
            'is_active',
        ]
        widgets = {
            'no_kontainer': forms.TextInput(attrs={
                'class': 'form-control font-code-md text-code-md uppercase',
                'placeholder': 'Contoh: MSKU7712391',
                'required': True,
                'autocomplete': 'off',
                'maxlength': '11',
            }),
            'ukuran': forms.Select(attrs={
                'class': 'form-select font-body-sm text-body-sm',
                'required': True,
            }),
            'tipe': forms.Select(attrs={
                'class': 'form-select font-body-sm text-body-sm',
                'required': True,
            }),
            'kategori': forms.Select(attrs={
                'class': 'form-select font-body-sm text-body-sm',
                'required': True,
            }),
            'berat_kotor': forms.NumberInput(attrs={
                'class': 'form-control font-code-sm text-code-sm',
                'placeholder': 'Berat dalam kilogram (kg)',
                'required': True,
                'step': '0.01',
                'min': '1',
            }),
            'shipping_line': forms.TextInput(attrs={
                'class': 'form-control font-body-sm text-body-sm',
                'placeholder': 'Contoh: MAERSK LINE / ONE / EVERGREEN',
                'autocomplete': 'off',
            }),
            'seal_number': forms.TextInput(attrs={
                'class': 'form-control font-code-sm text-code-sm uppercase',
                'placeholder': 'Nomor segel resmi peti kemas',
                'autocomplete': 'off',
            }),
            'ref_dokumen': forms.TextInput(attrs={
                'class': 'form-control font-code-sm text-code-sm uppercase',
                'placeholder': 'No Booking / DO / SPPB',
                'autocomplete': 'off',
            }),
            'status_vgm': forms.Select(attrs={
                'class': 'form-select font-body-sm text-body-sm',
                'required': True,
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def clean_no_kontainer(self):
        no_kontainer = self.cleaned_data.get('no_kontainer', '')
        if no_kontainer:
            no_kontainer = no_kontainer.strip().upper().replace(' ', '')
            iso_pattern = r'^[A-Z]{4}[0-9]{7}$'
            if not re.match(iso_pattern, no_kontainer):
                raise forms.ValidationError(
                    "Format nomor kontainer tidak valid sesuai standar ISO 6346 (harus 4 huruf kapital diikuti 7 angka, contoh: MSKU7712391)."
                )

            qs = Container.objects.filter(no_kontainer__iexact=no_kontainer)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Kontainer dengan nomor '{no_kontainer}' sudah terdaftar dalam sistem.")

            return no_kontainer
        raise forms.ValidationError("Nomor kontainer wajib diisi.")

    def clean_berat_kotor(self):
        berat = self.cleaned_data.get('berat_kotor')
        if berat is None or berat <= 0:
            raise forms.ValidationError("Berat kotor kontainer harus lebih besar dari 0 kg.")
        return berat

    def clean(self):
        cleaned_data = super().clean()
        kategori = cleaned_data.get('kategori')
        ref_dokumen = cleaned_data.get('ref_dokumen', '').strip() if cleaned_data.get('ref_dokumen') else ''

        if kategori in [Container.CargoCategoryChoice.IMPORT, Container.CargoCategoryChoice.EXPORT]:
            if not ref_dokumen:
                self.add_error(
                    'ref_dokumen',
                    f"Nomor dokumen referensi (DO / Booking / SPPB) wajib diisi untuk kategori {Container.CargoCategoryChoice(kategori).label}."
                )

        return cleaned_data
