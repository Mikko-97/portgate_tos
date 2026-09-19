import re
from django import forms
from apps.masterdata.models import Truck, Container
from apps.queue_gate.models import QueueEntry


class GateInForm(forms.Form):
    """
    Formulir operasional pendaftaran truk masuk (Gate In) di gerbang terminal peti kemas.
    """
    # --------------------------------------------------------------------------
    # 1. Identitas Armada & Pengemudi
    # --------------------------------------------------------------------------
    no_polisi = forms.CharField(
        max_length=20,
        label="Nomor Polisi Armada",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase fw-bold',
            'placeholder': 'Contoh: B 9012 XYZ',
            'autocomplete': 'off',
            'id': 'id_no_polisi'
        })
    )
    konfigurasi = forms.ChoiceField(
        choices=Truck.TruckConfigChoice.choices,
        initial=Truck.TruckConfigChoice.TRAILER_40,
        label="Konfigurasi Truk",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_konfigurasi'})
    )
    nama_ekspedisi = forms.CharField(
        max_length=150,
        label="Perusahaan Ekspedisi",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nama Perusahaan Transportir',
            'id': 'id_nama_ekspedisi'
        })
    )
    kode_ekspedisi = forms.CharField(
        max_length=30,
        required=False,
        label="Kode Ekspedisi (Opsional)",
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'Contoh: SAM, PST',
            'id': 'id_kode_ekspedisi'
        })
    )
    nama_driver = forms.CharField(
        max_length=150,
        label="Nama Pengemudi / Sopir",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nama Lengkap Sopir',
            'id': 'id_nama_driver'
        })
    )
    no_hp_driver = forms.CharField(
        max_length=25,
        label="No. HP / WhatsApp Sopir",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '08xxxxxxxxxx',
            'id': 'id_no_hp_driver'
        })
    )
    no_sim_driver = forms.CharField(
        max_length=50,
        label="Nomor SIM Sopir",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace',
            'placeholder': 'Nomor SIM BII Umum',
            'id': 'id_no_sim_driver'
        })
    )
    rfid_tag = forms.CharField(
        max_length=50,
        required=False,
        label="RFID Tag CMS (Opsional)",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase',
            'placeholder': 'Tag RFID Armada',
            'id': 'id_rfid_tag'
        })
    )

    # --------------------------------------------------------------------------
    # 2. Peti Kemas & Muatan
    # --------------------------------------------------------------------------
    has_container = forms.BooleanField(
        required=False,
        initial=True,
        label="Truk Membawa Kontainer?",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_has_container'
        })
    )
    no_kontainer = forms.CharField(
        max_length=15,
        required=False,
        label="Nomor Kontainer (ISO 6346)",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase fw-bold',
            'placeholder': 'Contoh: MSKU7712391',
            'id': 'id_no_kontainer'
        })
    )
    ukuran = forms.ChoiceField(
        choices=Container.ContainerSizeChoice.choices,
        initial=Container.ContainerSizeChoice.SIZE_40,
        required=False,
        label="Ukuran Kontainer",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_ukuran'})
    )
    tipe = forms.ChoiceField(
        choices=Container.ContainerTypeChoice.choices,
        initial=Container.ContainerTypeChoice.DRY,
        required=False,
        label="Tipe Kontainer",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipe'})
    )
    kategori = forms.ChoiceField(
        choices=Container.CargoCategoryChoice.choices,
        initial=Container.CargoCategoryChoice.IMPORT,
        required=False,
        label="Kategori Muatan",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_kategori'})
    )
    berat_kotor = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        label="Berat Kotor (kg)",
        widget=forms.NumberInput(attrs={
            'class': 'form-control font-monospace',
            'placeholder': 'Contoh: 34250.00',
            'step': '0.01',
            'id': 'id_berat_kotor'
        })
    )
    shipping_line = forms.CharField(
        max_length=100,
        required=False,
        label="Shipping Line / Pelayaran",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contoh: Maersk, Evergreen, MSC',
            'id': 'id_shipping_line'
        })
    )
    seal_number = forms.CharField(
        max_length=50,
        required=False,
        label="Nomor Segel (Seal)",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase',
            'placeholder': 'Nomor Segel Pelayaran / Bea Cukai',
            'id': 'id_seal_number'
        })
    )
    ref_dokumen = forms.CharField(
        max_length=100,
        required=False,
        label="No. Booking / DO / SPPB",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace',
            'placeholder': 'Nomor Dokumen Referensi',
            'id': 'id_ref_dokumen'
        })
    )
    status_vgm = forms.ChoiceField(
        choices=Container.VGMStatusChoice.choices,
        initial=Container.VGMStatusChoice.VERIFIED,
        required=False,
        label="Status VGM",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_status_vgm'})
    )

    # --------------------------------------------------------------------------
    # 3. Alokasi Lapangan (Yard) & Jalur Gerbang
    # --------------------------------------------------------------------------
    gerbang_lane = forms.ChoiceField(
        choices=QueueEntry.LaneChoice.choices,
        initial=QueueEntry.LaneChoice.LANE_01,
        label="Jalur / Lane Masuk",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_gerbang_lane'})
    )
    alokasi_blok = forms.CharField(
        max_length=20,
        required=False,
        label="Blok Yard",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase',
            'placeholder': 'Contoh: BLOCK C-04',
            'id': 'id_alokasi_blok'
        })
    )
    alokasi_bay = forms.CharField(
        max_length=10,
        required=False,
        label="Bay",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase',
            'placeholder': 'BAY 12',
            'id': 'id_alokasi_bay'
        })
    )
    alokasi_row = forms.CharField(
        max_length=10,
        required=False,
        label="Row",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase',
            'placeholder': 'ROW 03',
            'id': 'id_alokasi_row'
        })
    )
    alokasi_tier = forms.CharField(
        max_length=10,
        required=False,
        label="Tier",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace text-uppercase',
            'placeholder': 'TIER 3',
            'id': 'id_alokasi_tier'
        })
    )
    catatan = forms.CharField(
        required=False,
        label="Catatan Operasional",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Kondisi fisik armada / kontainer...',
            'id': 'id_catatan'
        })
    )
    alasan_tertahan = forms.CharField(
        max_length=255,
        required=False,
        label="Alasan Tertahan (Hold)",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Wajib diisi jika memilih Tahan / Hold Gate (contoh: Overweight, SPPB Expired)',
            'id': 'id_alasan_tertahan'
        })
    )
    action_type = forms.CharField(
        widget=forms.HiddenInput(),
        initial='save',
        required=False
    )

    def clean_no_polisi(self):
        plat = self.cleaned_data.get('no_polisi', '').strip().upper()
        # Normalisasi spasi berlebih
        plat = re.sub(r'\s+', ' ', plat)
        if not plat:
            raise forms.ValidationError("Nomor polisi wajib diisi.")
        return plat

    def clean_no_kontainer(self):
        no_kontainer = self.cleaned_data.get('no_kontainer', '').strip().upper()
        # Hilangkan spasi atau tanda minus jika ada: MSKU 771239-1 -> MSKU7712391
        no_kontainer = re.sub(r'[\s\-]', '', no_kontainer)
        return no_kontainer

    def clean(self):
        cleaned_data = super().clean()
        no_polisi = cleaned_data.get('no_polisi')
        has_container = cleaned_data.get('has_container')
        no_kontainer = cleaned_data.get('no_kontainer')
        berat_kotor = cleaned_data.get('berat_kotor')
        kategori = cleaned_data.get('kategori')
        ref_dokumen = cleaned_data.get('ref_dokumen', '').strip()
        action_type = cleaned_data.get('action_type', 'save')
        alasan_tertahan = cleaned_data.get('alasan_tertahan', '').strip()

        # ----------------------------------------------------------------------
        # 1. Validasi: Truk tidak boleh memiliki antrian aktif (MENUNGGU/PROSES/TERTAHAN)
        # ----------------------------------------------------------------------
        if no_polisi:
            active_queue = QueueEntry.objects.filter(
                truck__no_polisi=no_polisi,
                status__in=[
                    QueueEntry.QueueStatus.MENUNGGU,
                    QueueEntry.QueueStatus.PROSES,
                    QueueEntry.QueueStatus.TERTAHAN
                ]
            ).select_related('truck').first()

            if active_queue:
                raise forms.ValidationError(
                    f"Truk dengan nomor polisi '{no_polisi}' sedang berada dalam antrian aktif "
                    f"[{active_queue.no_antrian}] dengan status '{active_queue.get_status_display()}'. "
                    f"Truk tidak dapat didaftarkan kembali sebelum menyelesaikan proses dan berstatus KELUAR."
                )

        # ----------------------------------------------------------------------
        # 2. Validasi Kontainer
        # ----------------------------------------------------------------------
        if has_container:
            if not no_kontainer:
                self.add_error('no_kontainer', "Nomor kontainer wajib diisi jika truk membawa kontainer.")
            else:
                # Validasi format ISO 6346: 4 huruf kapital (kode pemilik & tipe) + 6 digit serial + 1 check digit = 11 karakter
                iso_pattern = r'^[A-Z]{4}[0-9]{7}$'
                if not re.match(iso_pattern, no_kontainer):
                    self.add_error(
                        'no_kontainer',
                        "Format nomor kontainer tidak valid sesuai standar ISO 6346 (harus 4 huruf diikuti 7 angka, contoh: MSKU7712391)."
                    )

            # Validasi berat kotor > 0
            if berat_kotor is None or berat_kotor <= 0:
                self.add_error('berat_kotor', "Berat kotor kontainer harus lebih besar dari 0 kg.")

            # Validasi dokumen wajib untuk Import Full dan Export Full
            if kategori in [Container.CargoCategoryChoice.IMPORT, Container.CargoCategoryChoice.EXPORT]:
                if not ref_dokumen:
                    self.add_error(
                        'ref_dokumen',
                        f"Nomor dokumen referensi (DO / Booking / SPPB) wajib diisi untuk kategori {Container.CargoCategoryChoice(kategori).label}."
                    )

        # ----------------------------------------------------------------------
        # 3. Validasi Alasan Tertahan (jika aksi Hold Gate dipilih)
        # ----------------------------------------------------------------------
        if action_type == 'hold':
            if not alasan_tertahan:
                self.add_error('alasan_tertahan', "Alasan penahanan (Hold) wajib diisi saat memilih aksi Tahan / Hold Gate.")

        return cleaned_data


class GateOutProcessForm(forms.Form):
    """
    Formulir konfirmasi pemrosesan Gate Out truk kontainer (SELESAI -> KELUAR).
    """
    gerbang_lane = forms.ChoiceField(
        choices=[
            (QueueEntry.LaneChoice.OUT_01, 'Out 01 — Dispatch (Pemeriksaan Standar)'),
            (QueueEntry.LaneChoice.OUT_02, 'Out 02 — Bypass (Jalur Cepat / Empty)'),
        ] + [(k, v) for k, v in QueueEntry.LaneChoice.choices if k not in (QueueEntry.LaneChoice.OUT_01, QueueEntry.LaneChoice.OUT_02)],
        initial=QueueEntry.LaneChoice.OUT_01,
        label="Gerbang Keluar (Outbound Lane)",
        widget=forms.Select(attrs={
            'class': 'form-select font-code-sm text-code-sm',
            'id': 'id_gerbang_lane'
        })
    )
    catatan = forms.CharField(
        max_length=255,
        required=False,
        label="Catatan / Keterangan Gate Out (Opsional)",
        widget=forms.TextInput(attrs={
            'class': 'form-control font-body-sm text-body-sm',
            'placeholder': 'Contoh: Pemeriksaan dokumen fisik & segel sesuai manifest (Clearance OK)',
            'id': 'id_catatan'
        })
    )
