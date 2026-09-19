"""
OCR Engine Integration Service (Port-Gate TOS)
Modul mandiri untuk pemrosesan teks OCR plat nomor, normalisasi format nomor polisi Indonesia,
lookup armada ke Master Data Truck, dan integrasi ambang batas (threshold) dari OCR Settings.

Didesain dengan arsitektur interface/engine terpisah (BaseOCREngine & ExternalOCREngine)
agar siap dihubungkan ke camera feed / ANPR hardware eksternal pada tahap berikutnya.
"""

import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from django.db.models import Q
from apps.masterdata.models import Truck
from apps.queue_gate.models import QueueEntry


# Konfigurasi default (sesuai OcrSettingsView)
DEFAULT_OCR_CONFIG = {
    'ocr_confidence': 95,
    'wim_tolerance': 5,
    'auto_open_barrier': False,
}

# Regex plat nomor Indonesia standar:
# Area: 1-2 huruf (misal B, D, BK, AA, AD, BG, DK, KT, L, dll.)
# Angka: 1-4 digit
# Seri/Wilayah belakang: 0-3 huruf (misal ABC, XYZ, AA, atau kosong)
INDONESIA_PLATE_REGEX = re.compile(
    r'^([A-Z]{1,2})\s*(\d{1,4})\s*([A-Z]{0,3})$',
    re.IGNORECASE
)


def get_ocr_config(request=None) -> Dict[str, Any]:
    """
    Mengambil konfigurasi OCR terkini dari session user/booth jika ada request,
    atau mengembalikan konfigurasi default standar pabrik.
    """
    if request and hasattr(request, 'session'):
        return request.session.get('ocr_config', DEFAULT_OCR_CONFIG.copy())
    return DEFAULT_OCR_CONFIG.copy()


def clean_ocr_text(raw_text: str) -> str:
    """
    Membersihkan noise umum dari hasil pembacaan OCR kamera:
    - Bounding box / noise symbols: [], (), {}, |, _, -, ., :, ;, ,, ", ', `, ~, *, #, /
    - Spasi berlebih dan karakter newline/tab
    """
    if not raw_text:
        return ""

    # Ubah ke string dan uppercase
    text = str(raw_text).upper()

    # Hapus karakter noise non-alfanumerik kecuali spasi
    # (karakter seperti tanda kurung, strip pembatas, titik desimal, dsb)
    text = re.sub(r'[\r\n\t]', ' ', text)
    text = re.sub(r'[\[\]\(\)\{\}\|\_\-\.\:\;\"\'\`\~\*\#\/\\=+\^!?@$%&<>]+', ' ', text)

    # Rampingkan beberapa spasi berturutan menjadi satu spasi
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def normalize_license_plate(cleaned_text: str) -> str:
    """
    Melakukan normalisasi plat nomor kendaraan Indonesia ke format standar:
    [KODE AREA] [NOMOR 1-4 DIGIT] [SERI SUB-WILAYAH]
    Contoh:
    'B1234ABC'   -> 'B 1234 ABC'
    'B 1234 ABC' -> 'B 1234 ABC'
    'BK 555 AA'  -> 'BK 555 AA'
    'D 9876 XYZ' -> 'D 9876 XYZ'
    'B 1234'     -> 'B 1234'
    """
    if not cleaned_text:
        return ""

    compact = re.sub(r'\s+', '', cleaned_text).upper()
    match = INDONESIA_PLATE_REGEX.match(compact)
    if match:
        prefix = match.group(1).upper()
        number = match.group(2)
        suffix = match.group(3).upper() if match.group(3) else ''
        if suffix:
            return f"{prefix} {number} {suffix}"
        return f"{prefix} {number}"

    # Fallback: jika pola tidak eksak 3 bagian, kembalikan teks yang sudah dirapikan spasinya
    return re.sub(r'\s+', ' ', cleaned_text).strip().upper()


class OCRResult:
    """
    Struktur data terstandarisasi untuk hasil proses OCR plat nomor.
    """
    def __init__(
        self,
        plate_raw: str,
        plate_normalized: str,
        plate_compact: str,
        confidence: Optional[float] = None,
        confidence_threshold: int = 95,
        is_valid_format: bool = True,
        found: bool = False,
        truck: Optional[Dict[str, Any]] = None,
        active_queue: Optional[Dict[str, Any]] = None,
        engine_name: str = "ExternalOCREngine",
        message: str = ""
    ):
        self.plate_raw = plate_raw
        self.plate_normalized = plate_normalized
        self.plate_compact = plate_compact
        self.confidence = confidence
        self.confidence_threshold = confidence_threshold
        self.confidence_passed = (confidence is None) or (confidence >= confidence_threshold)
        self.is_valid_format = is_valid_format
        self.found = found
        self.truck = truck
        self.active_queue = active_queue
        self.engine_name = engine_name
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        """Konversi hasil ke format dictionary / JSON-serializable."""
        return {
            'status': 'success',
            'plate_raw': self.plate_raw,
            'plate_normalized': self.plate_normalized,
            'plate_compact': self.plate_compact,
            'confidence': self.confidence,
            'confidence_threshold': self.confidence_threshold,
            'confidence_passed': self.confidence_passed,
            'is_valid_format': self.is_valid_format,
            'found': self.found,
            'truck': self.truck,
            'has_active_queue': bool(self.active_queue),
            'active_queue': self.active_queue,
            'engine_name': self.engine_name,
            'message': self.message,
        }


class BaseOCREngine(ABC):
    """
    Interface / Abstract Base Class untuk OCR Engine di Port-Gate TOS.
    Memungkinkan penambahan engine OCR lokal (misal Tesseract, PaddleOCR, easyocr)
    maupun engine cloud/eksternal tanpa mengubah layer pemanggil.
    """
    @property
    @abstractmethod
    def engine_name(self) -> str:
        pass

    @abstractmethod
    def process(
        self,
        raw_input: str,
        confidence: Optional[float] = None,
        confidence_threshold: int = 95,
        **kwargs
    ) -> OCRResult:
        """Memproses raw input teks/payload menjadi OCRResult."""
        pass


class ExternalOCREngine(BaseOCREngine):
    """
    Implementasi engine OCR untuk menerima hasil OCR dari engine/kamera eksternal,
    misalnya via webhook, HTTP POST dari edge camera gateway, atau simulator kalibrasi.
    """
    @property
    def engine_name(self) -> str:
        return "ExternalOCREngine"

    def process(
        self,
        raw_input: str,
        confidence: Optional[float] = None,
        confidence_threshold: int = 95,
        **kwargs
    ) -> OCRResult:
        raw_str = str(raw_input or "").strip()
        if not raw_str:
            return OCRResult(
                plate_raw="",
                plate_normalized="",
                plate_compact="",
                confidence=confidence,
                confidence_threshold=confidence_threshold,
                is_valid_format=False,
                found=False,
                engine_name=self.engine_name,
                message="Teks OCR kosong."
            )

        # 1. Bersihkan noise dan whitespace
        cleaned = clean_ocr_text(raw_str)

        # 2. Normalisasi nomor polisi
        normalized = normalize_license_plate(cleaned)
        compact = re.sub(r'\s+', '', normalized).upper()

        # Validasi format dasar plat nomor Indonesia
        is_valid = bool(INDONESIA_PLATE_REGEX.match(compact))

        # 3. Lookup Truck Master di database
        found, truck_data, active_queue = lookup_truck_by_plate(normalized, compact)

        message = "Armada ditemukan di Master Data." if found else "Armada tidak terdaftar di Master Data."

        return OCRResult(
            plate_raw=raw_str,
            plate_normalized=normalized,
            plate_compact=compact,
            confidence=confidence,
            confidence_threshold=confidence_threshold,
            is_valid_format=is_valid,
            found=found,
            truck=truck_data,
            active_queue=active_queue,
            engine_name=self.engine_name,
            message=message
        )


def lookup_truck_by_plate(plate_normalized: str, plate_compact: str = None):
    """
    Mencari truk di Master Data berdasarkan nomor polisi normalized atau compact.
    Juga memeriksa apakah truk memiliki antrian aktif (MENUNGGU, PROSES, TERTAHAN).
    """
    if not plate_normalized:
        return False, None, None

    if not plate_compact:
        plate_compact = re.sub(r'\s+', '', plate_normalized).upper()

    truck = None

    # 1. Exact match (case-insensitive) pada plat nomor yang tersimpan
    truck = Truck.objects.filter(no_polisi__iexact=plate_normalized).select_related('expedisi', 'driver').first()

    # 2. Compact match (tanpa spasi) untuk menangani variasi penulisan di database
    if not truck and plate_compact:
        for t in Truck.objects.select_related('expedisi', 'driver').filter(is_active=True)[:100]:
            if t.no_polisi.replace(' ', '').upper() == plate_compact:
                truck = t
                break

    # 3. Partial match jika plat lebih dari 3 karakter
    if not truck and len(plate_normalized) >= 3:
        truck = Truck.objects.filter(no_polisi__icontains=plate_normalized).select_related('expedisi', 'driver').first()

    # Cek antrian aktif
    active_queue = None
    active_entry = QueueEntry.objects.filter(
        Q(truck__no_polisi__iexact=plate_normalized) |
        Q(truck__no_polisi__icontains=plate_normalized),
        status__in=[
            QueueEntry.QueueStatus.MENUNGGU,
            QueueEntry.QueueStatus.PROSES,
            QueueEntry.QueueStatus.TERTAHAN
        ]
    ).first()

    if not active_entry and plate_compact:
        active_qs = QueueEntry.objects.filter(
            status__in=[
                QueueEntry.QueueStatus.MENUNGGU,
                QueueEntry.QueueStatus.PROSES,
                QueueEntry.QueueStatus.TERTAHAN
            ]
        ).select_related('truck')
        for q in active_qs:
            if q.truck and q.truck.no_polisi.replace(' ', '').upper() == plate_compact:
                active_entry = q
                break

    if active_entry:
        active_queue = {
            'no_antrian': active_entry.no_antrian,
            'status': active_entry.get_status_display(),
            'status_raw': active_entry.status,
            'gerbang_lane': active_entry.gerbang_lane,
            'waktu_masuk': active_entry.waktu_masuk.strftime('%d/%m/%Y %H:%M:%S') if active_entry.waktu_masuk else '',
        }

    if not truck:
        return False, None, active_queue

    truck_data = {
        'id': truck.id,
        'no_polisi': truck.no_polisi,
        'konfigurasi': truck.konfigurasi,
        'konfigurasi_display': truck.get_konfigurasi_display(),
        'rfid_tag': truck.rfid_tag or '',
        'is_active': truck.is_active,
        'expedisi': {
            'id': truck.expedisi.id,
            'nama_perusahaan': truck.expedisi.nama_perusahaan,
            'kode_ekspedisi': truck.expedisi.kode_ekspedisi or '',
        } if truck.expedisi else None,
        'driver': {
            'id': truck.driver.id,
            'nama': truck.driver.nama,
            'no_hp': truck.driver.no_hp,
            'no_sim': truck.driver.no_sim,
        } if truck.driver else None,
    }

    return True, truck_data, active_queue


# Default active engine instance
_active_engine = ExternalOCREngine()


def process_ocr_plate(
    raw_text: str,
    confidence: Optional[float] = None,
    request=None,
    config: Optional[Dict[str, Any]] = None,
    engine: Optional[BaseOCREngine] = None
) -> OCRResult:
    """
    Fungsi entri utama pemrosesan OCR plat nomor.
    Menerima raw text, opsi nilai keyakinan (confidence), request objek (untuk session config),
    dan menjalankan engine OCR yang aktif.
    """
    cfg = config or get_ocr_config(request)
    threshold = int(cfg.get('ocr_confidence', 95))

    eng = engine or _active_engine
    return eng.process(
        raw_input=raw_text,
        confidence=confidence,
        confidence_threshold=threshold
    )
