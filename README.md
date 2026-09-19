# Container Truck Queue Management System (Port Gate TOS)

Sistem manajemen antrian truk kontainer berbasis web untuk terminal peti kemas dengan tema visual dan alur operasional **Port Gate TOS (Terminal Operating System)**.

Sistem ini mengelola siklus operasional gerbang pelabuhan secara menyeluruh: registrasi Gate In truk dan kontainer, antrian buffer yard, penanganan hold/inspeksi, alokasi lapangan penumpukan, checkout Gate Out, audit trail kronologis, integrasi OCR plat nomor, dan pemantauan realtime melalui dashboard situasional.

---

## 1. Project Overview

**Port Gate TOS** dirancang untuk mendigitalkan dan mengoptimalkan aliran keluar-masuk armada truk kontainer di terminal peti kemas. Sistem menjamin keamanan data, pencatatan waktu yang presisi (*timestamping*), isolasi peran antar staf, serta kepatuhan penuh terhadap alur *state machine* operasional terminal pelabuhan.

### Karakteristik Utama:
- **Terminal Operating System Standard**: Alur stepper 4-tahap standar terminal pelabuhan.
- **Concurrency-Safe Queue Numbering**: Penomoran antrian harian unik format `Q-0001` dengan *row-level locking* transaksi database.
- **Strict Role Isolation**: Pemisahan tegas hak akses antara Administrator (pengelolaan akun) dan Staf Operasional (gate & yard).
- **Audit Trail Terintegrasi**: Setiap perubahan status antrian dicatat permanen dalam `QueueStatusLog` lengkap dengan operator dan keterangan.
- **Production-Ready Docker Architecture**: Dijalankan menggunakan Gunicorn WSGI server multi-worker dengan serving aset statis mandiri via WhiteNoise.

---

## 2. Technology Stack

| Komponen | Teknologi / Library | Keterangan |
|---|---|---|
| **Backend Framework** | Python 3.11, Django 5.1 | Arsitektur MVC modular |
| **WSGI Production Server** | Gunicorn 26.x | Multi-worker, multi-threaded (`gthread`) |
| **Static Files Serving** | WhiteNoise 6.12.x | Serving, kompresi (gzip/brotli), & caching manifest |
| **Database Utama** | PostgreSQL (Supabase) | Supabase connection pooling (port 5432 / 6543) via `psycopg2-binary` & `dj-database-url` |
| **Database Fallback** | SQLite 3 | Otomatis aktif untuk pengujian lokal jika `DATABASE_URL` kosong |
| **Frontend & UI** | Django Templates, Bootstrap 5, Vanilla CSS/JS | Tema visual Port Gate TOS (dark slate & high-contrast terminal) |
| **Containerization** | Docker, Docker Compose | Multi-stage build, healthcheck, non-root ready |

---

## 3. Current Project Structure

Struktur folder proyek terorganisir secara modular:

```text
portgate_tos/
├── config/                          # Konfigurasi inti Django
│   ├── __init__.py
│   ├── asgi.py                      # Konfigurasi ASGI
│   ├── settings.py                  # Pengaturan Django (WhiteNoise, Supabase, Security)
│   ├── urls.py                      # URL routing tingkat proyek & system-status
│   └── wsgi.py                      # Entrypoint WSGI untuk Gunicorn
├── apps/                            # Modul aplikasi modular
│   ├── accounts/                    # Manajemen akun, otentikasi, & role isolation
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── context_processors.py    # Inject user_role ke seluruh template
│   │   ├── forms.py                 # Form login TOS dengan pemilihan booth
│   │   ├── mixins.py                # Role isolation mixins (Admin & Operational)
│   │   ├── models.py                # OperatorProfile & ekstensi pengguna
│   │   ├── urls.py
│   │   └── views.py                 # TOSLoginView, AdminDashboardView, dsb.
│   ├── masterdata/                  # Master data armada & kargo
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── forms.py                 # Form Truck, Driver, Expedition, Container
│   │   ├── models.py                # Model Truck, Driver, Expedition, Container
│   │   ├── urls.py
│   │   └── views.py                 # CRUD workstation & JSON detail API
│   └── queue_gate/                  # Modul inti antrian & gerbang terminal
│       ├── admin.py
│       ├── apps.py
│       ├── forms.py                 # GateInForm & GateOutProcessForm
│       ├── models.py                # QueueEntry, DailyQueueSequence, QueueStatusLog
│       ├── ocr_service.py           # Engine OCR normalisasi plat nomor Indonesia
│       ├── services.py              # State machine transisi & registrasi atomik
│       ├── urls.py
│       └── views.py                 # Dashboard, GateIn, GateOut, Queue, AuditLog
├── templates/                       # Template Django bertema Port Gate TOS
│   ├── accounts/                    # Login & admin workstation templates
│   ├── masterdata/                  # Master data templates & modals
│   ├── queue_gate/                  # Dashboard, gate in/out, queue detail, audit log
│   ├── components/                  # Sidebar, navbar, toasts, stepper
│   ├── base.html                    # Master layout TOS
│   └── index.html                   # Halaman verifikasi sistem
├── static/                          # Aset statis frontend
│   ├── css/
│   │   └── style.css                # Stylesheet tema Port Gate TOS
│   ├── js/                          # Script interaksi UI & validasi form
│   └── img/                         # Asset grafis & ikon pelabuhan
├── scripts/                         # Script verifikasi & automated test
│   ├── verify_e2e_workflow.py       # End-to-End full workflow test suite
│   ├── verify_queue_process.py      # Pengujian transisi antrian & status log
│   └── verify_access_matrix.py      # Pengujian matriks isolasi hak akses peran
├── scratch/                         # Test suite pengujian keamanan & OCR
│   ├── verify_security_hardening.py # Pengujian CSRF, open redirect, & injection
│   └── verify_ocr_engine.py         # Pengujian parser & normalisasi OCR
├── Dockerfile                       # Spesifikasi container produksi Gunicorn
├── docker-compose.yml               # Orkestrasi container produksi
├── docker-compose.dev.yml           # Override compose untuk development live-reload
├── .dockerignore                    # Penyaringan file sensitif & cache saat build
├── requirements.txt                 # Dependensi Python produksi
├── .env.example                     # Template konfigurasi environment variable
├── .gitignore                       # File ignore Git
└── README.md                        # Dokumentasi resmi proyek
```

---

## 4. Prerequisites

Sebelum menjalankan aplikasi, pastikan perangkat telah terpasang:
- **Docker Engine** (v20.10+ atau Docker Desktop)
- **Docker Compose** (v2.0+)
- **Python 3.11+** *(opsional, jika menjalankan secara lokal tanpa Docker)*
- Akun dan project **Supabase** aktif untuk database PostgreSQL

---

## 5. Supabase PostgreSQL Configuration

Aplikasi menggunakan connection pooling PostgreSQL yang disediakan oleh Supabase. **Tidak diperlukan container database lokal.**

1. Salin template konfigurasi environment:
   ```bash
   cp .env.example .env
   ```

2. Buka berkas `.env` dan masukkan connection string Supabase Anda:
   ```env
   # Format URI Connection String Supabase (Connection Pooling):
   DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
   ```

> [!NOTE]
> Jika `DATABASE_URL` dikosongkan, aplikasi akan otomatis menggunakan fallback database lokal SQLite (`db.sqlite3`) untuk memudahkan pengujian awal.

---

## 6. Docker Usage

### A. Lingkungan Produksi (Production Mode)
Menjalankan container menggunakan **Gunicorn WSGI Server** (3 workers, 2 threads), menyajikan static files via WhiteNoise, mengaktifkan healthcheck otomatis, dan tanpa bind-mount kode mentah host:

```bash
# Build dan jalankan di background:
docker compose up --build -d
```

### B. Lingkungan Pengembangan (Development Mode)
Menjalankan container dengan Django development server (`runserver`), volume mount `.:/app` untuk *live-reloading*, dan `DEBUG=True`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

### C. Pemantauan Log Container
Memantau aktivitas stdout/stderr Gunicorn secara realtime:
```bash
docker compose logs -f web
```

### D. Menghentikan Container
```bash
docker compose down
```

---

## 7. Django Management Commands

Perintah administratif Django dapat dijalankan langsung di dalam container aktif:

- **System Check:**
  ```bash
  docker compose exec web python manage.py check
  ```
- **Production Deployment Check:**
  ```bash
  docker compose exec web python manage.py check --deploy
  ```
- **Menjalankan Migrasi Database:**
  ```bash
  docker compose exec web python manage.py migrate
  ```
- **Membuat Berkas Migrasi Baru:**
  ```bash
  docker compose exec web python manage.py makemigrations
  ```
- **Membuat Akun Administrator (Superuser):**
  ```bash
  docker compose exec web python manage.py createsuperuser
  ```
- **Kompilasi Aset Statis (Collectstatic):**
  ```bash
  docker compose exec web python manage.py collectstatic --noinput
  ```
- **Django Interactive Shell:**
  ```bash
  docker compose exec web python manage.py shell
  ```

---

## 8. Main System Features

### 1. Autentikasi & Role Isolation
- Halaman login workstation terpadu (`/login/`) dengan pilihan booth aktif (`Gate Inbound 01` s/d `06`).
- Manajemen sesi berbasis waktu shift operasional atau fitur *Remember Me*.
- Proteksi route berbasis peran: Staf Operasional tidak dapat mengakses halaman Admin, dan Administrator dibatasi dari aksi operasional gate.

### 2. Situational Awareness Dashboard
- Monitoring realtime metrik harian: jumlah antrian `MENUNGGU`, `PROSES`, `TERTAHAN`, `SELESAI`, `KELUAR`, serta total TEUs.
- Grafik visual distribusi volume antrian per jam (06:00 - 20:00 WIB).
- Matriks utilisasi lajur (*Lane Status Matrix*) dan estimasi kapasitas buffer gate.
- Feed aktivitas mutasi status antrian terkini secara kronologis.

### 3. Queue Management
- Daftar seluruh antrian truk dengan pencarian instan (plat nomor, nomor antrian, kontainer, supir, ekspedisi).
- Filter status operasional, lajur, dan tanggal.
- Tampilan detail antrian (`/queue/<pk>/`) dilengkapi stepper visual 4 tahap, informasi muatan, dan riwayat status log.

### 4. Workstation Gate In
- Pendaftaran truk masuk gerbang dengan verifikasi data armada, pengemudi, ekspedisi, dan peti kemas.
- Pembangkitan nomor antrian harian unik format `Q-0001` yang aman dari race condition (*concurrency-safe*).
- Alokasi manual koordinat penumpukan yard: Blok, Bay, Row, dan Tier.
- Pencetakan tiket barcode antrian gerbang masuk (`/ticket/<pk>/`).

### 5. Workstation Gate Out
- Validasi ketat pemeriksaan gerbang keluar: hanya truk berstatus `SELESAI` di yard yang diizinkan memproses Gate Out.
- Pencarian cepat antrian berdasarkan scan barcode, nomor antrian, plat nomor, atau nomor kontainer.
- Pemilihan gerbang keluar (*Outbound Lane*) dan pencatatan catatan clearance fisik.

### 6. Queue State Processing
- Pemrosesan transisi status yang tervalidasi: `MENUNGGU` &rarr; `PROSES` &rarr; `TERTAHAN` &rarr; `PROSES` &rarr; `SELESAI` &rarr; `KELUAR`.
- Transisi status wajib melalui request HTTP POST dengan proteksi CSRF.
- Penahanan truk (*Hold Gate*) mewajibkan pengisian alasan yang jelas.
- Pencatatan stempel waktu otomatis untuk setiap tahap siklus operasional.

### 7. Master Data Management
- Modul administrasi Master Truk, Master Pengemudi, Master Ekspedisi, dan Master Kontainer.
- Fitur pencarian, pagination, aktivasi/deaktivasi status entitas, form modal, dan API detail JSON.

### 8. Riwayat & Audit Log
- Pencatatan seluruh mutasi status antrian secara otomatis pada `QueueStatusLog`.
- Penyaringan berdasarkan tingkat urgensi (*severity*), lajur gerbang, tanggal, dan kata kunci pencarian.
- Fitur ekspor laporan audit trail ke format CSV dengan proteksi netralisasi *CSV Formula Injection*.

### 9. Integrasi OCR Plat Nomor
- API internal pencarian armada (`/api/truck-lookup/`), kontainer (`/api/container-lookup/`), dan pengenalan plat OCR (`/api/ocr-process/`).
- Engine normalisasi karakter, pembersihan noise spasi/tanda baca, dan evaluasi threshold keyakinan (*confidence score*).

### 10. Operational Alerts
- Deteksi otomatis peringatan operasional:
  - Truk dalam kondisi tertahan (*Hold Gate*).
  - Antrian yang melebihi batas waktu toleransi tunggu buffer (`ALERT_THRESHOLD_WAITING_MINS = 30`).
  - Antrian yang melebihi batas waktu penanganan yard (`ALERT_THRESHOLD_PROCESS_MINS = 45`).

---

## 9. User Roles & Access Matrix

Sistem menerapkan pembagian hak akses berdasarkan 4 peran utama:

| Peran (Role) | Hak Akses Utama | Area Kerja |
|---|---|---|
| **Admin** | Manajemen pengguna, aktivasi akun, konfigurasi sistem | `/admin-dashboard/`, `/admin/` |
| **Supervisor** | Monitoring audit log, persetujuan release hold, pengawasan yard | `/dashboard/`, `/queue/`, `/audit-log/` |
| **Manager** | Tinjauan analitik throughput, laporan performa gate & TEUs | `/dashboard/`, `/audit-log/` |
| **Operator** | Registrasi Gate In, mutasi status antrian, verifikasi Gate Out | `/dashboard/`, `/gate-in/`, `/gate-out/`, `/queue/` |

---

## 10. Queue Workflow

Alur siklus hidup antrian kontainer mengikuti *finite state machine* terarah:

```
[ GATE IN ] ──> Status: MENUNGGU (Q-0001)
                      │
                      ▼
               Status: PROSES ──(Inspeksi/Deviasi)──> Status: TERTAHAN (Hold)
                      │                                      │
                      │ <──────(Klarifikasi/Lanjut)──────────┘
                      ▼
               Status: SELESAI (Pekerjaan Yard Rampung)
                      │
                      ▼
[ GATE OUT ] ─> Status: KELUAR (Resmi Meninggalkan Terminal)
```

1. **MENUNGGU**: Truk berhasil didaftarkan di Gate In, tiket tercetak, truk menunggu di buffer area. Stempel `waktu_masuk` tercatat.
2. **PROSES**: Truk dipanggil masuk ke booth pemeriksaan atau bergerak menuju blok yard. Stempel `waktu_mulai_proses` tercatat.
3. **TERTAHAN** *(Opsional)*: Terjadi kendala dokumen, fisik segel, atau berat muatan. Memerlukan input `alasan_tertahan`.
4. **PROSES**: Masalah terselesaikan, operasional yard dilanjutkan. Stempel `waktu_mulai_proses` awal tetap dipertahankan.
5. **SELESAI**: Bongkar/muat kontainer di yard selesai. Stempel `waktu_selesai` tercatat.
6. **KELUAR**: Pemeriksaan fisik akhir di gerbang keluar rampung. Truk resmi keluar terminal via lajur outbound. Stempel `waktu_keluar` tercatat.

---

## 11. Security & Validation

Sistem menerapkan standar pengerasan keamanan (*security hardening*):
- **Role Isolation Protection**: Pengalihan otomatis jika pengguna mengakses area di luar kewenangannya.
- **CSRF Enforcement**: Proteksi token CSRF pada seluruh aksi mutasi status antrian dan endpoint formulir.
- **POST-Only Actions**: Endpoint mutasi status menolak request GET dengan HTTP `405 Method Not Allowed`.
- **Open Redirect Prevention**: Validasi skema dan host lokal (`url_has_allowed_host_and_scheme`) pada parameter `next` redirect.
- **CSV Formula Injection Sanitization**: Seluruh sel ekspor CSV diawali karakter penjinak kutip tunggal (`'`) jika terdeteksi simbol formula (`=`, `+`, `-`, `@`).
- **ISO 6346 Validation**: Nomor kontainer divalidasi dengan regex format standar 4 huruf kapital diikuti 7 digit angka (`^[A-Z]{4}[0-9]{7}$`).
- **Admin Lockout Prevention**: Mencegah penonaktifan tidak sengaja pada akun superuser aktif terakhir.

---

## 12. Verification & Testing

Tersedia skrip pengujian otomatis mandiri di direktori `scripts/` dan `scratch/`:

### 1. End-to-End Workflow Verification (Stage 25)
Memvalidasi seluruh alur 13 tahap dari login hingga checkout Gate Out beserta pembersihan data otomatis:
```bash
python scripts/verify_e2e_workflow.py
```

### 2. Queue State Processing Verification
Memvalidasi seluruh aturan transisi status antrian dan pencatatan `QueueStatusLog`:
```bash
python scripts/verify_queue_process.py
```

### 3. Role Access Matrix Verification
Memvalidasi matriks izin akses untuk peran Anonim, Operator, Administrator, dan Superuser:
```bash
python scripts/verify_access_matrix.py
```

### 4. Security Hardening Verification
Memvalidasi penolakan unauthorized access, CSRF enforcement, open redirect, dan formula injection:
```bash
python scratch/verify_security_hardening.py
```

### 5. OCR Engine Verification
Memvalidasi algoritma pembersihan noise teks OCR dan normalisasi plat nomor kendaraan:
```bash
python scratch/verify_ocr_engine.py
```

---

## 13. Production Notes

Saat mengoperasikan aplikasi di server produksi (*cloud / VPS / on-premise*):

### Gunicorn WSGI Server
- Dikonfigurasi dengan parameter: `--bind 0.0.0.0:8000 --workers 3 --threads 2 --timeout 60`.
- Logging stdout dan stderr diteruskan langsung ke Docker container runtime (`--access-logfile - --error-logfile -`).

### WhiteNoise Static Serving
- Aset statis dikompilasi secara otomatis saat build image (`RUN python manage.py collectstatic --noinput`).
- Middleware `whitenoise.middleware.WhiteNoiseMiddleware` menyajikan berkas dengan header `Cache-Control` optimal dan kompresi manifest otomatis.

### Konfigurasi Environment Produksi (.env)
Pastikan parameter berikut disesuaikan di server produksi:
```env
# Matikan mode debug di produksi:
DEBUG=False

# Kunci rahasia unik dan acak (panjang minimal 50 karakter):
SECRET_KEY=ganti-dengan-kunci-rahasia-acak-yang-sangat-kuat-dan-panjang-50-karakter

# Domain atau IP host yang diizinkan:
ALLOWED_HOSTS=tos.portterminal.co.id,10.10.1.50,localhost

# Domain yang diizinkan untuk request POST / CSRF:
CSRF_TRUSTED_ORIGINS=https://tos.portterminal.co.id

# Aktifkan pengalihan otomatis ke HTTPS jika domain menggunakan SSL:
SECURE_SSL_REDIRECT=True
```

---

## 14. Git / GitHub Workflow

Alur kerja standar Git untuk version control dan rilis kode:

1. **Periksa status perubahan lokal:**
   ```bash
   git status
   ```

2. **Tambahkan perubahan ke staging area:**
   ```bash
   git add .
   ```

3. **Commit perubahan dengan pesan deskriptif:**
   ```bash
   git commit -m "docs: update comprehensive project documentation in README.md"
   ```

4. **Kirim commit ke repository remote (GitHub):**
   ```bash
   git push origin master
   ```
