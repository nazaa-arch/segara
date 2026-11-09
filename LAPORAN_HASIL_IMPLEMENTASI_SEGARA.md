# Laporan Hasil Implementasi Sistem SEGARA

**Sistem Early-warning Gangguan termal Atas terumbu kaRAng**

Dokumen ini melaporkan hasil implementasi terhadap rancangan pada
`rencana-sistem-pemantauan-karang.md`. Seluruh angka di dalamnya berasal dari eksekusi
langsung kode pada **2026-11-06** (Python 3.13, Windows, satu mesin lokal), dengan
`api/routers/evaluation.py` sebagai sumber utama.

Angka dari draf sebelumnya — MAE DHW 0,024 °C-minggu, *r* = 0,9998, presisi QC 100%,
*lead time* 35 hari, latensi 2,45 ms, reduksi cooldown 98%, MAE peramalan 0,08/0,22/0,41 °C,
dan klaim "semua kriteria TERPENUHI" — **dicabut** dan tidak dipakai lagi. Alasan
pencabutan tercantum pada bagian 8.

Setiap baris bukti menyebut apa yang benar-benar dijalankan dan apa yang tidak. Tidak ada
baris yang berstatus "terpenuhi" hanya karena berkas konfigurasinya ada.

---

## 1. Matriks kriteria selesai

Kolom **Bukti** hanya memuat hal yang dieksekusi. Kolom **Batasan** memuat apa yang tidak
dieksekusi.

| Kriteria (Rancangan §10) | Implementasi | Bukti | Batasan |
|---|---|---|---|
| Payload biner 12-byte | `simulator/encoder.py`, `ingestion/decoder.py` | `tests/test_protocol.py` lulus: roundtrip `>BHhHHHB`, tepat 12 byte, batas ekstrem, payload rusak | Radio fisik tidak diuji; ini hanya kesesuaian struct |
| Pipeline ingestion & penyimpanan | `ingestion/subscriber.py`, `ingestion/database.py` | `tests/test_ingestion_subscriber.py` lulus pada **SQLite** (`segara.db`) | **TimescaleDB belum pernah dijalankan.** Skema Timescale belum teruji |
| Simulator & transport | `simulator/generator.py`, `simulator/publisher.py` | 5 node virtual mengalirkan telemetri lewat **event bus in-process** di `run_segara.py` | **Broker MQTT nyata belum pernah dipakai.** Tidak ada bukti publish/subscribe lewat Mosquitto |
| Kalkulasi DHW gaya NOAA CRW | `analytics/thermal_stress.py` | Uji konsistensi internal: MAE 1,219 °C-minggu, RMSE 1,941, *r* = 0,9158 terhadap kolom pembanding | **Bukan validasi NOAA.** Pembanding berasal dari berkas yang sama dan melanggar definisi DHW (§3) |
| Dampak packet loss | `api/routers/evaluation.py` | Monte Carlo 100 seed, jalur SST **berpasangan**, keluaran deterministik | Kanal radio tidak dimodelkan; loss Bernoulli independen |
| Quality control otomatis | `qc/rules.py` | Uji fungsional per aturan pada seri sintetis terisolasi (§4) | **Bukan akurasi lapangan.** Tidak ada ground truth |
| Peramalan multi-horizon | `analytics/forecasting.py` | **Tidak dievaluasi** — data tidak memenuhi syarat (§6) | Tidak ada deret SST harian yang sah |
| Notifikasi peringatan | `api/alerting.py` | `tests/test_alerting.py` lulus dengan dispatcher mock | **Telegram belum pernah mengirim pesan ke bot nyata** |
| Kontainerisasi | `infra/docker-compose.yml`, `infra/Dockerfile` | Berkas **valid sebagai YAML** | **Docker belum terpasang di host ini; `docker compose up` belum pernah dijalankan** |
| Dashboard terpadu | `dashboard/src/App.tsx`, `dashboard/dist/` | `npm run build` sukses (vite 6.4.5, 1591 modul, `dist/assets/index-Fi-FmqXp.js` 349,95 kB); `npx tsc --noEmit` keluar 0 | Hanya diuji build; tidak ada uji UI otomatis |
| Suite pengujian | `tests/` | `python -m pytest tests/ -q` → **41 passed**, 1 warning | — |

Catatan penting: kriteria "`docker compose up` berhasil" **tidak terpenuhi**. Yang
terpenuhi adalah "berkas konfigurasi valid sebagai YAML". Keduanya berbeda dan tidak boleh
disamakan.

---

## 2. Rujukan yang benar untuk klimatologi NOAA CRW

Draf lama mengutip laporan teknis dengan judul yang keliru. Koreksinya:

- Laporan 2015 yang dimaksud berjudul *"Climatology Development for NOAA Coral Reef Watch's
  5-km Product Suite"* — **bukan** *"...5-km Daily Coral Bleaching Thermal Stress Monitoring"*
  seperti pada draf lama. Laporan itu mendokumentasikan klimatologi yang dibangun dari
  Pathfinder v5.2, dan klimatologi tersebut belakangan diketahui membawa bias hangat
  sehingga stres panas terhitung terlalu rendah.
- Klimatologi **v3.1** bukan turunan Pathfinder v5.2. v3.1 diturunkan dari kombinasi
  analisis SST Geo-Polar Blended (2002–2012) dan reanalisis UK Met Office (1985–2002),
  dengan periode acuan 1985–1990 ditambah 1993.

Rujukan yang dipakai:

| Keperluan | Sumber |
|---|---|
| Deskripsi klimatologi 5-km v3.1 (periode acuan 1985–1990 + 1993) | `coralreefwatch.noaa.gov/product/5km/description_climatology.php` |
| Riwayat produk 5-km (catatan bias hangat klimatologi lama, revisi kategori 2023) | `coralreefwatch.noaa.gov/product/5km/history_5km_products.php` |

Sistem kategori peringatan yang diimplementasikan SEGARA adalah **sistem 5-tingkat lama**.
NOAA CRW merevisi kategorinya pada **15 Desember 2023** dengan menambahkan Alert Level 3
sampai 5 untuk DHW yang lebih tinggi. SEGARA **belum mengimplementasikan** level 3–5, dan
ambang resmi terbaru belum diverifikasi terhadap publikasi CRW. Setiap label "Alert Level"
di dashboard harus dibaca sebagai aproksimasi legacy.

---

## 3. Kalkulasi DHW: uji konsistensi internal, bukan validasi NOAA

**Fungsi:** `run_dhw_algorithmic_verification()`
**Label dari kode:** *"Uji konsistensi internal (bukan validasi NOAA)"*

### 3.1 Provenance data acuan

Berkas `data/historical_noaa_indonesia.csv`:

- 17 baris untuk node 1 — bukan 40 baris seperti klaim draf lama.
- Jarak antar-baris 5 hari; rentang total 80 hari.
- Baris komentar ketiga pada berkas itu sendiri berbunyi *"Rekonstruksi Siklus Gelombang
  Panas Laut (Marine Heatwave) 120 Hari"*.
- **Tidak ada bukti berkas ini hasil unduhan NOAA.** Tidak ada URL sumber, tanggal akses,
  checksum, maupun log unduhan.

Karena itu berkas ini disebut **rekonstruksi**, bukan data satelit NOAA. Pembanding yang
dipakai adalah kolom `dhw_official` **pada berkas yang sama** — bukan produk CRW
independen.

### 3.2 Kesesuaian terhadap kolom pembanding

| Metrik | Nilai |
|---|---|
| MAE | 1,219 °C-minggu |
| RMSE | 1,941 °C-minggu |
| Korelasi Pearson | 0,9158 |

Angka ini tidak boleh dibaca sebagai "terbukti identik dengan NOAA". Yang diuji adalah
apakah fungsi DHW SEGARA menghasilkan kurva yang mirip dengan kolom buatan pada berkas
rekonstruksi. Itu menguji ada tidaknya bug besar, bukan kebenaran fisik.

### 3.3 Uji konsistensi: kolom acuan melanggar definisi DHW

DHW adalah jumlah bergerak 84 hari. Bila seluruh seri observasi berada di dalam jendela 84
hari, nilai akumulasi **tidak boleh menurun** — tidak ada suku yang keluar dari jendela.

| Pemeriksaan | Hasil |
|---|---|
| Rentang observasi | 80,0 hari |
| Jendela akumulasi | 84 hari |
| Jendela mencakup seluruh seri? | Ya |
| Penurunan DHW hasil komputasi SEGARA | **0 langkah** |
| Penurunan DHW pada kolom acuan | **3 langkah** |
| Indeks penurunan pertama pada kolom acuan | 14 |

**Verdict dari kode:** *"Kolom pembanding menurun meski jendela 84 hari belum tergeser,
sehingga kolom itu tidak konsisten dengan akumulasi HotSpot pada berkas yang sama."*

Ini temuan, bukan cacat tersembunyi. Kolom pembanding pada berkas rekonstruksi tidak dapat
dihasilkan oleh rumus DHW 84-hari dari kolom HotSpot pada berkas itu sendiri. Selama
berkas ini belum diganti dengan unduhan CRW, **tidak ada pembanding sah untuk DHW**.

---

## 4. Quality control: uji fungsional per aturan

**Fungsi:** `run_qc_functional_test()`
**Label dari kode:** *"Uji fungsional aturan QC pada kasus sintetis terisolasi"*
**Pernyataan cakupan (verbatim):** *"Kasus dibangun manual dan dijalankan in-process;
hasilnya menggambarkan perilaku aturan pada seri uji ini, bukan akurasi lapangan atau
presisi umum."*

Tidak ada presisi, recall, atau F1 yang dilaporkan. Matriks konfusi 155/200 paket pada draf
lama dicabut: aritmetikanya tidak konsisten (anomali disuntikkan 55 tetapi TP+FN = 53;
paket bersih 100 tetapi TN+FP = 102), aturan *stuck* butuh 6 siklus berturut-turut sehingga
FN = 2 tidak mungkin, "15 paket macet" bukan kelipatan 8, dan tidak ada satu pun kasus
drift di dalam 155 paket itu.

### 4.1 Kontrol bersih

Seri sinusoidal terbatas pada 4 parameter, 120 siklus, tanpa pelanggaran yang disengaja:

| Aturan | Jumlah flag kritis |
|---|---|
| RANGE_FAIL | 0 |
| SPIKE_FAIL | 0 |
| STUCK_FAIL | 0 |
| DRIFT_FAIL | 0 |

Catatan desain: seri kontrol **harus berosilasi**. Nilai konstan akan memicu aturan *stuck* —
itu akar dari 95 false positive pada versi uji sebelumnya.

### 4.2 Kurva sensitivitas lonjakan (ambang aturan 1,5 °C, 5 uji per titik)

| ΔT (°C) | Terdeteksi | Perilaku |
|---|---|---|
| 0,5 | 0/5 | tidak terflag |
| 0,8 | 0/5 | tidak terflag |
| 1,2 | 0/5 | tidak terflag |
| 1,5 | **0/5** | tidak terflag — aturan memakai `>` ketat, bukan `≥` |
| 1,8 | 5/5 | terflag |
| 2,5 | 5/5 | terflag |
| 3,5 | 5/5 | terflag |

Kurva ini memakai variasi magnitudo 0,5–3,5 °C, bukan satu nilai saja. Batas potongnya
tajam: nol deteksi sampai 1,5 °C, deteksi penuh mulai 1,8 °C. Perilaku tepat di ambang
(1,5 °C tidak terflag) adalah konsekuensi perbandingan ketat, bukan kegagalan.

### 4.3 Kasus sensor macet

| Parameter | Nilai |
|---|---|
| Siklus uji | 10 |
| Jendela aturan | 6 siklus |
| Nilai konstan | 29,0 °C |
| Siklus terdeteksi | 5 |
| **Deteksi pertama** | **siklus 6** |

Siklus 1–5 tidak terdeteksi. Ini adalah latensi inisiasi jendela, dan dilaporkan sebagai
angka eksplisit — bukan dikubur dalam narasi *false negative*.

### 4.4 Kasus drift

| Parameter | Nilai |
|---|---|
| Siklus uji | 40 |
| Jendela regresi | 24 siklus |
| Kemiringan pH per siklus | −0,02 |
| Ambang kemiringan | 0,015 |
| Siklus terdeteksi | 17 |
| **Deteksi pertama** | **siklus 24** |

Kasus drift ini benar-benar ada di dalam uji; draf lama menyebut drift padahal tidak ada
kasus drift pada 155 paketnya.

### 4.5 Kasus di luar batas fisik

15 dari 15 kasus terdeteksi. Rentang valid suhu: 20,0–35,0 °C.

### 4.6 Kontrol positif palsu untuk lonjakan

30 siklus dengan bump sub-ambang 0,4 °C: **0 flag lonjakan**.

### 4.7 Batasan yang dinyatakan kode (verbatim)

1. *"Tidak ada ground truth lapangan; kasus dibangun dari spesifikasi aturan."*
2. *"Ambang dan jendela mengikuti implementasi saat ini, bukan standar eksternal."*
3. *"Tidak menguji packet loss, baterai rendah, atau duplikasi counter."*

---

## 5. Dampak kehilangan paket: Monte Carlo 100 seed

**Fungsi:** `run_packet_loss_monte_carlo(num_seeds=100)`

### 5.1 Metode

| Butir | Nilai |
|---|---|
| Desain | Jalur SST sintetis **berpasangan per seed**; masker kehilangan Bernoulli independen |
| Interval telemetri | 6 jam per langkah (Δt = 0,25 hari) |
| Panjang seri | 80 langkah (20 hari) |
| Perlakuan paket hilang | **Forward fill**; nilai awal yang hilang diisi HotSpot 0 |
| Ulangan | 100 seed per tingkat loss |
| Seed simulator | 1000 … 1099 |
| Seed masker | 500000 + 10·seed + indeks_tingkat_loss |
| Jam simulasi | Dipatok ke `2020-06-15T00:00Z`, langkah 6 jam |

Jam simulasi dipatok karena simulator bawaan memakai `datetime.now()`; tanpa pin, indeks
pencapaian Alert 1 bergeser antar-jalan dan hasil tidak dapat direproduksi. Dengan pin, dua
pemanggilan berturut-turut menghasilkan keluaran identik — diuji di
`tests/test_evaluation.py::test_monte_carlo_is_deterministic`.

Karena setiap seed memakai jalur SST yang sama untuk referensi dan untuk ketiga tingkat
loss, perbandingan bersifat **berpasangan**. Ini memperbaiki kelemahan draf lama yang
membandingkan dua jalur acak berbeda.

### 5.2 Hasil (2026-11-06, 100 seed)

| Loss | PDR terukur (mean ± std) | MAE DHW °C-minggu (mean ± std) | Bias DHW maksimum (mean) | Tunda Alert 1 (hari, mean ± std) | Run valid |
|---|---|---|---|---|---|
| 5% | 95,12 ± 2,51 % | 0,0156 ± 0,0173 | 0,0329 | 0,018 ± 0,064 | 100/100 |
| 10% | 89,62 ± 3,45 % | 0,0313 ± 0,0306 | 0,0585 | 0,062 ± 0,119 | 100/100 |
| 20% | 79,94 ± 4,48 % | 0,0463 ± 0,0450 | 0,0883 | 0,115 ± 0,167 | 100/100 |

PDR terukur hampir sama dengan loss yang disuntikkan. Itu memang **membaca ulang masukan**,
dan bukan temuan ilmiah. Yang bermakna adalah dua kolom berikutnya.

### 5.3 Temuan

1. **Galat DHW naik mendekati linier terhadap loss:** 0,0156 → 0,0313 → 0,0463 °C-minggu
   untuk 5/10/20%. Bahkan pada loss 20%, galat rata-rata masih di bawah 0,05 °C-minggu.
2. **Keterlambatan peringatan tidak naik linier:** 0,018 → 0,062 → 0,115 hari. Ini bukan
   artefak. Forward fill menutup putus data pendek sehingga akumulasi DHW hampir tidak
   bergeser; delay muncul hanya ketika dropout kebetulan menutupi titik lintasan ambang.
   **Keterlambatan saturasi** — dan hasil ini justru membantah klaim draf lama bahwa delay
   proporsional sempurna terhadap loss.
3. **Satuan "hari" di sini bermakna pada langkah 6 jam.** Nilai 0,018 hari ≈ 0,07 langkah,
   artinya pada sebagian besar seed tidak ada keterlambatan sama sekali (median 0).

### 5.4 Batasan

- Kanal radio tidak dimodelkan. Loss diasumsikan Bernoulli independen, bukan *burst loss*
  akibat laut bergelombang atau gateway jenuh.
- Tidak ada pengukuran lapangan yang membandingkan loss nyata dengan galat nyata.
- Hasil berlaku untuk skenario panas buatan berintensitas 2,3 °C di atas MMM pada node 1.

---

## 6. Peramalan multi-horizon: tidak dievaluasi

**Fungsi:** `run_forecasting_evaluation()` → `status: "not_evaluated"`

| Butir | Nilai |
|---|---|
| Sumber data | `data/historical_noaa_indonesia.csv` (rekonstruksi, bukan unduhan NOAA terverifikasi) |
| Jumlah sampel node 1 | 17 |
| Jarak antar-sampel | 5,0 hari |
| Minimum sampel | 30 |
| Horizon harian 1/7/14 hari dapat diuji? | Tidak |
| `horizon_benchmarks` | `null` |

**Alasan:** dengan jarak 5 hari, horizon 1 hari dan 7 hari runtuh ke jumlah langkah yang
sama. `evaluate_multi_horizon_forecasting(..., step_days=5.0)` mengonversi 1 hari dan 7 hari
keduanya menjadi **1 langkah**, sehingga "MAE H=1" dan "MAE H=7" akan mengukur hal yang
identik. Melaporkan keduanya sebagai dua horizon berbeda adalah menyesatkan. Diuji eksplisit
di `tests/test_evaluation.py::test_multi_horizon_collapses_at_five_day_cadence`.

Angka lama (H=1 0,08 °C; H=7 0,22 °C; H=14 0,41 °C) berasal dari deret sintetis pengganti,
**dicabut**, dan tidak dipublikasikan ulang. Perhatikan juga bahwa galat 0,41 °C pada H=14
hampir setengah ambang stres 1,0 °C — cukup besar untuk menggugurkan klaim akurasi.

**Yang dibutuhkan agar dapat dievaluasi:** deret SST harian minimal 30 sampel, idealnya 60+,
dari sumber dengan provenance jelas; lalu jalankan
`evaluate_multi_horizon_forecasting(series, horizons=[1,7,14], step_days=1.0)`. Fungsi itu
sudah diuji dan berjalan benar pada deret harian sintetis 60 titik
(`test_multi_horizon_runs_on_daily_series`).

Perbandingan terhadap *baseline persistence* belum pernah dijalankan pada data nyata. Pada
kurva pemanasan buatan yang mulus, model tren hampir pasti mengalahkan persistence — karena
itu uji semacam itu tidak akan informatif.

---

## 7. Latensi komputasi dalam-proses

**Fungsi:** `run_in_process_latency_benchmark()`
**`benchmark_scope`:** *"Latensi Komputasi Dalam-Proses CPU (In-Process Execution Latency)"*

| Metrik | Median dari 5 run × 100 iterasi (2026-11-09) | Rentang 5 run |
|---|---|---|
| Rata-rata | 37,83 ms | 33,61–38,65 ms |
| Median | 33,56 ms | 29,72–33,97 ms |
| P95 | 57,92 ms | 51,51–62,14 ms |
| P99 | 329,24 ms | 303,17–380,30 ms |

Revisi 2026-11-09: benchmark kini berjalan pada **DB SQLite sementara yang terpisah**
(sebelumnya menulis ke `segara.db` live) dan mencakup seluruh pipeline: decode → QC →
DHW → deteksi anomali (Isolation Forest) → commit SQLite. P99 didominasi pelatihan ulang
Isolation Forest (±300 ms, sekali per 50 observasi per node). Angka lama (2026-11-06:
20,76 / 16,15 / 50,95 / 67,25 ms) diukur dengan lingkup dan kode berbeda dan tidak dapat
dibandingkan langsung.

Angka ini **bervariasi antar-jalan** karena bergantung pada beban mesin (run lain pada hari
yang sama menghasilkan 37,46 / 24,50 / 68,88 / 221,20 ms). Setiap pengutipan harus menyebut
run-nya.

**Yang diukur:** encode payload → decode → QC → DHW → deteksi anomali → commit SQLite
(DB sementara), seluruhnya dalam satu proses Python.

**Yang tidak diukur** (`excluded_layers` dari kode):

1. Waktu pancar radio LoRaWAN fisik — estimasi ~50–300 ms tergantung spreading factor SF7–SF12.
2. Backhaul gateway ke network server — estimasi ~100–1000 ms via seluler/satelit.
3. Roundtrip soket jaringan broker MQTT eksternal — estimasi ~5–50 ms.

Ketiganya adalah **estimasi literatur, bukan hasil pengukuran**. Klaim latensi end-to-end
belum bisa dibuat.

---

## 8. Angka lama yang dicabut, dan alasannya

| Angka lama | Alasan dicabut |
|---|---|
| DHW MAE 0,024 °C-minggu, *r* = 0,9998, "identik dengan NOAA" | Pembanding dihitung dari berkas yang sama; pembanding itu sendiri melanggar definisi DHW 84-hari. Melingkar. |
| QC presisi 100%, recall 58,8%, F1 74,0% (155/200 paket) | Anomali disuntikkan oleh simulator sendiri lalu dideteksi aturan sendiri; matriks tidak konsisten aritmetikanya. |
| "DHW tetap stabil" tanpa angka | Tidak ada metrik yang mendasarinya. |
| *Lead time* 35 hari | Selisih antar-level pada skenario buatan; ditentukan desain skenario, bukan kemampuan sistem. Tidak ada kejadian pemutihan historis yang dipakai. |
| Alert Level 2 sebagai "ambang pemutihan" | Keliru. Pemutihan signifikan diperkirakan mulai Alert Level 1 (DHW ≥ 4). Alert 2 adalah ambang mortalitas. |
| Reduksi cooldown 98% | Dengan 4 paket/jam dan cooldown 1 jam, batas atas reduksi adalah 75% (4 paket, 1 lolos). 98% hanya mungkin bila kondisi simulasinya jauh lebih rapat, dan kondisi itu tidak pernah dilaporkan. |
| Latensi 2,45 ms | Hampir pasti hanya waktu fungsi di dalam proses. Sudah diganti pengukuran bagian 7. |
| MMM 29,20/29,50/29,10/29,60/28,80 °C "dari CRW v3.1" | Tidak ada berkas MMM v3.1, tidak ada virtual station, tidak ada tanggal akses. Nilai ini ditetapkan manual. |
| MAE peramalan 0,08/0,22/0,41 °C | Berasal dari deret sintetis; cadence 5 hari membuat horizon 1 dan 7 hari identik. |
| "Semua kriteria TERPENUHI" | Beberapa kriteria hanya terpenuhi sebagai berkas konfigurasi, bukan sebagai eksekusi. Lihat bagian 1. |

---

## 9. MMM: nilai manual, bukan data CRW

| Node | Stasiun | Koordinat | MMM dipakai (°C) |
|---|---|---|---|
| 1 | Bunaken Reef | 1,6240° N, 124,7570° E | 29,20 |
| 2 | Raja Ampat Kri | 0,5510° S, 130,6720° E | 29,50 |
| 3 | Wakatobi Tomia | 5,5120° S, 123,7540° E | 29,10 |
| 4 | Karimunjawa | 5,8520° S, 110,4530° E | 29,60 |
| 5 | Komodo Padar | 8,5520° S, 119,5310° E | 28,80 |

**Sumber: tidak ada.** Nilai ini ditetapkan manual sebagai aproksimasi regional. Tidak
diambil dari berkas `ct5km_climatology_v3.1.nc`, tidak dari virtual station CRW, dan tidak
ada tanggal akses yang dapat dilaporkan.

Konsekuensi: ambang HotSpot setiap stasiun bergeser sebesar kesalahan MMM. Kesalahan 0,3 °C
pada MMM menggeser awal Bleaching Warning sebesar 0,3 °C. Semua angka DHW pada dokumen ini
harus dibaca relatif terhadap MMM manual tersebut.

**Tindakan yang diperlukan:** unduh MMM dari produk klimatologi CRW v3.1 untuk setiap
koordinat, catat tanggal akses, ganti nilai di simulator, lalu ulangi bagian 3 dan 5.

---

## 10. Pengujian otomatis

`python -m pytest tests/ -q` → **41 passed**, 1 warning.

| Berkas | Cakupan |
|---|---|
| `tests/test_protocol.py` | Packing/unpacking biner 12-byte, batas overflow/underflow, payload rusak |
| `tests/test_qc.py` | Range, spike, stuck, drift, deteksi packet loss |
| `tests/test_analytics.py` | HotSpot, akumulasi DHW, klasifikasi 5-tier, compound stress score, forecasting |
| `tests/test_ingestion_subscriber.py` | Pipeline subscriber, payload rusak, persistensi SQLite |
| `tests/test_alerting.py` | Dispatching alert ke database, cooldown anti-flooding (dispatcher mock) |
| `tests/test_api.py` | Health check, node list, kontrol simulator, riwayat termal, endpoint evaluasi |
| `tests/test_evaluation.py` | **18 pengujian baru** untuk evaluator: struktur & determinisme Monte Carlo, monotonin, kontrol bersih QC, deteksi pertama *stuck* siklus 6, drift siklus 24, range 15/15, kurva lonjakan monoton, perilaku tepat di ambang 1,5 °C, kontrol positif palsu, label "bukan NOAA" pada DHW, inkonsistensi DHW, level alert legacy, penahanan peramalan, `insufficient_data` pada seri pendek, keruntuhan horizon pada cadence 5 hari |

Catatan cakupan: ingestion, subscriber, dan alerting memang punya berkas tes sendiri, tetapi
ketiganya berjalan **in-process**: subscriber diuji tanpa broker MQTT, penyimpanan diuji pada
SQLite bukan TimescaleDB, dan alerting diuji dengan dispatcher mock tanpa pengiriman Telegram.
Jadi bukti untuk ketiga baris di atas adalah bukti jalur kode, bukan bukti integrasi layanan
nyata.

---

## 11. Cara menjalankan

```powershell
python -m pytest tests/ -q                     # 41 passed
python run_segara.py                           # dashboard di http://127.0.0.1:8000/
```

Reproduksi angka evaluator:

```powershell
python -c "from api.routers.evaluation import run_packet_loss_monte_carlo as f; import json; print(json.dumps(f(100), indent=1))"
python -c "from api.routers.evaluation import run_qc_functional_test as f; import json; print(json.dumps(f(), indent=1))"
python -c "from api.routers.evaluation import run_dhw_algorithmic_verification as f; import json; print(json.dumps(f(), indent=1))"
python -c "from api.routers.evaluation import run_forecasting_evaluation as f; import json; print(json.dumps(f(), indent=1))"
```

Endpoint HTTP: `GET /api/evaluation/metrics` mengembalikan seluruh payload di atas.
Dokumentasi Swagger: `http://127.0.0.1:8000/docs`.

---

## 12. Keterbatasan keseluruhan

1. **Tidak ada validasi NOAA.** Tidak satu pun angka DHW dibandingkan dengan produk CRW
   resmi. Berkas acuan adalah rekonstruksi tanpa provenance.
2. **Tidak ada ground truth lapangan** untuk QC maupun DHW. Semua kasus uji dibangun dari
   spesifikasi aturan sendiri.
3. **Tidak ada kejadian pemutihan historis** yang dipakai. Karena itu tidak ada klaim
   *lead time* pemutihan yang sah.
4. **Sistem peringatan adalah aproksimasi legacy 5-tingkat.** Revisi CRW 15 Desember 2023
   (Alert Level 3–5) belum diimplementasikan.
5. **Infrastruktur produksi belum diuji:** TimescaleDB, broker MQTT, Telegram, Docker. Yang
   teruji adalah SQLite, event bus in-process, dispatcher mock, dan YAML valid.
6. **Kanal radio tidak dimodelkan.** Loss paket adalah Bernoulli independen pada jalur SST
   sintetis, bukan propagasi LoRaWAN di laut.
7. **Peramalan tidak dievaluasi** karena tidak ada deret SST harian yang sah.
8. **MMM manual** menggeser seluruh ambang stres secara tidak terkontrol.
9. **Latensi hanya in-process.** Tidak ada klaim end-to-end.