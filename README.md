# Container Truck Queue Management System (Port Gate TOS)

Sistem antrian truk kontainer berbasis web untuk terminal peti kemas dengan tema visual **Port Gate TOS (Terminal Operating System)**.

Proyek ini dibangun menggunakan:
- **Python 3.11**
- **Django 5.1**
- **Django Templates** & **Bootstrap 5**
- **Docker** & **Docker Compose**
- **PostgreSQL** (Database utama: **Supabase PostgreSQL**)

---

## 1. Struktur Project

Struktur folder dirancang modular, terorganisir, dan production-friendly:

```text
portgate_tos/ (container-truck-queue)
├── config/                  # Konfigurasi inti Django (settings, urls, wsgi, asgi)
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/                    # Direktori modular untuk aplikasi Django mendatang (core, queue, dll)
│   └── __init__.py
├── templates/               # Template Django dengan tema Port Gate TOS & Bootstrap 5
│   ├── base.html            # Layout utama (Navbar TOS, footer, assets)
│   └── index.html           # Halaman verifikasi kesiapan fondasi sistem
├── static/                  # File aset statis
│   ├── css/
│   │   └── style.css        # Custom stylesheet tema Port Gate TOS
│   ├── js/                  # JavaScript
│   └── img/                 # Gambar & icon
├── media/                   # Upload file pengguna (dokumen, foto kontainer)
├── manage.py                # Django CLI utility
├── Dockerfile               # Spesifikasi image container Django
├── docker-compose.yml       # Konfigurasi container service web
├── requirements.txt         # Daftar dependensi Python
├── .env.example             # Template konfigurasi environment variables
├── .gitignore               # Konfigurasi git ignore
└── README.md                # Dokumentasi petunjuk penggunaan
```

---

## 2. Prasyarat

- **Docker** (v20+ atau Docker Desktop)
- **Docker Compose** (v2+)
- Akun / Project **Supabase** (untuk database PostgreSQL)

---

## 3. Konfigurasi Database (Supabase PostgreSQL)

Sesuai ketentuan, **tidak ada container PostgreSQL lokal** di Docker Compose karena database utama menggunakan Supabase.

1. Salin template file environment:
   ```powershell
   cp .env.example .env
   ```

2. Buka file `.env`, lalu masukkan connection string PostgreSQL dari dashboard Supabase Anda:
   - Masuk ke dashboard Supabase: **Project Settings** &rarr; **Database** &rarr; **Connection string** &rarr; **URI**.
   - Masukkan ke variabel `DATABASE_URL`:
     ```env
     # Connection Pooling (Port 6543 - Sangat direkomendasikan):
     DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
     ```
   *(Catatan: Jika `DATABASE_URL` belum diisi, Django otomatis menggunakan fallback SQLite lokal sementara agar proses build & check awal tetap berjalan lancar).*

---

## 4. Cara Menjalankan Project dengan Docker

### A. Build dan Jalankan Container
Jalankan perintah berikut di root folder project:
```bash
docker compose up --build -d
```

### B. Melihat Log Container
Untuk memantau aktivitas server Django:
```bash
docker compose logs -f web
```

### C. Menghentikan Container
```bash
docker compose down
```

---

## 5. Cara Menjalankan `manage.py` Melalui Docker

Seluruh perintah administratif Django dapat dieksekusi langsung di dalam container:

- **Mengecek konfigurasi sistem (System Check):**
  ```bash
  docker compose exec web python manage.py check
  ```

- **Menjalankan migrasi database:**
  ```bash
  docker compose exec web python manage.py migrate
  ```

- **Membuat migrasi baru:**
  ```bash
  docker compose exec web python manage.py makemigrations
  ```

- **Membuat superuser (Admin):**
  ```bash
  docker compose exec web python manage.py createsuperuser
  ```

- **Membuka shell Django:**
  ```bash
  docker compose exec web python manage.py shell
  ```

---

## 6. Cara Memastikan Django Berhasil Berjalan

1. Pastikan container aktif dengan perintah:
   ```bash
   docker compose ps
   ```
   Status container `container_truck_queue_web` harus menunjukkan `Up` dan port `0.0.0.0:8000->8000/tcp`.

2. Buka browser dan akses alamat:
   [http://localhost:8000/](http://localhost:8000/)

3. Halaman verifikasi sistem **Port Gate TOS** akan menampilkan:
   - **Status Framework:** Django v5.1.x
   - **Status Database:** Engine database aktif (PostgreSQL / SQLite fallback)
   - **Status Environment:** Docker Compose / DEBUG Mode
   - **Navbar TOS & Bootstrap 5:** Indikator *SYSTEM READY* warna hijau berkedip.
