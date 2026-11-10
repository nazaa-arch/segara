# Laporan Evaluasi Ilmiah & Kinerja Sistem SEGARA

**Sistem Early-warning Gangguan termal Atas terumbu kaRAng**

Seluruh angka pada dokumen ini berasal dari eksekusi langsung `api/routers/evaluation.py`
pada 2026-11-06 (Python 3.13, Windows, satu mesin lokal). Angka lama dari draf sebelumnya
(MAE 0,024 °C-minggu, *r* = 0,9998, presisi QC 100%, lead time 35 hari, latensi 2,45 ms,
reduksi cooldown 98%) **dicabut** dan tidak lagi dipakai. Alasan pencabutan dijelaskan pada
bagian 7.

Setiap klaim di bawah ini diberi label cakupan. Tidak ada angka yang dipakai tanpa
menyebutkan apa yang sebenarnya diukur.

---

## 0. Ringkasan status bukti

| Komponen | Status bukti | Jenis pengujian |
|---|---|---|
| Payload biner 12-byte | Teruji unit | Roundtrip encode/decode |
| QC (range, spike, stuck, drift) | Teruji fungsional pada seri sintetis | Perilaku aturan, **bukan** akurasi |
| DHW | Konsistensi internal + deteksi inkonsistensi data acuan | **Bukan** validasi NOAA |
| Packet loss | Monte Carlo 100 seed, jalur SST berpasangan | Sintetis, bukan kanal radio riil |
| Peramalan | **Tidak dievaluasi** (data tidak memenuhi syarat) | — |
| Latensi | In-process CPU saja | Bukan end-to-end |
| MMM | Nilai manual, tanpa sumber CRW v3.1 | Belum tervalidasi |
| TimescaleDB / MQTT broker / Telegram / Docker | **Belum dijalankan** | — |

---

## 1. Cakupan data acuan dan peringatan provenance

Berkas `data/historical_noaa_indonesia.csv` yang dipakai sebagai pembanding:

- Berisi 17 baris data untuk node 1 (bukan 40 baris seperti klaim draf lama).
- Jarak antar-baris 5 hari; total rentang 80 hari.
- Baris komentar ketiga pada berkas itu sendiri berbunyi
  *"Rekonstruksi Siklus Gelombang Panas Laut (Marine Heatwave) 120 Hari"*.
- **Tidak ada bukti bahwa berkas ini hasil unduhan NOAA.** Tidak ada tanggal akses,
  URL sumber, checksum, atau log unduhan. Karena itu berkas ini disebut **rekonstruksi**,
  bukan data satelit NOAA.

Konsekuensinya: seluruh pembahasan DHW di dokumen ini adalah
**uji konsistensi internal**, bukan validasi terhadap produk NOAA Coral Reef Watch.

---

## 2. Verifikasi algoritma DHW dan uji konsistensi data acuan

**Jenis pengujian:** `run_dhw_algorithmic_verification()`
**Label yang dikembalikan kode:** *"Uji konsistensi internal (bukan validasi NOAA)"*

### 2.1 Kesesuaian terhadap kolom pembanding

Pembanding yang dipakai adalah kolom `dhw_official` **pada berkas yang sama** —
bukan produk CRW independen.

| Metrik | Nilai | Catatan |
|---|---|---|
| MAE | 1,219 °C-minggu | Kesesuaian hanya berarti implementasi mereproduksi kolom pada berkas yang sama |
| RMSE | 1,941 °C-minggu | — |
| Korelasi Pearson | 0,9158 | — |

Angka ini **tidak** boleh dibaca sebagai "terbukti identik dengan NOAA". Yang diuji adalah
apakah fungsi DHW SEGARA menghasilkan kurva yang mirip dengan kolom buatan pada berkas
rekonstruksi. Itu menguji ada tidaknya bug besar, bukan kebenaran fisik.

### 2.2 Uji konsistensi: kolom acuan melanggar definisi DHW

DHW didefinisikan sebagai jumlah bergerak 84 hari. Bila seluruh seri observasi berada
di dalam jendela 84 hari, nilai akumulasi **tidak boleh menurun** — tidak ada suku yang
keluar dari jendela.

| Pemeriksaan | Hasil |
|---|---|
| Rentang observasi | 80,0 hari |
| Jendela akumulasi | 84 hari |
| Jendela mencakup seluruh seri? | Ya |
| Penurunan DHW hasil komputasi SEGARA | **0 langkah** |
| Penurunan DHW pada kolom acuan | **3 langkah** |
| Indeks penurunan pertama pada kolom acuan | 14 |

**Verdict (keluaran kode):** *"Kolom pembanding menurun meski jendela 84 hari belum
tergeser, sehingga kolom itu tidak konsisten dengan akumulasi HotSpot pada berkas yang sama."*

Ini temuan, bukan cacat tersembunyi: kolom pembanding pada berkas rekonstruksi tidak
dapat dihasilkan oleh rumus DHW 84-hari dari kolom HotSpot pada berkas itu sendiri.
Selama berkas ini belum diganti dengan unduhan CRW, tidak ada pembanding sah untuk DHW.

### 2.3 Versi sistem peringatan yang diimplementasikan

Kode mengembalikan:

- `implemented_version`: *"SEGARA legacy 5-tier approximation; not a current NOAA CRW implementation"*
- Level: No Stress, Bleaching Watch, Bleaching Warning, Alert Level 1, Alert Level 2

Sistem 5-tingkat ini adalah **sistem lama**. NOAA CRW merevisi kategori peringatannya
pada 15 Desember 2023 dengan menambahkan Alert Level 3 sampai 5 untuk DHW yang lebih
tinggi. SEGARA **belum mengimplementasikan** level 3–5, dan ambang resmi terbaru belum
diverifikasi terhadap publikasi CRW. Setiap label "Alert Level" di dashboard harus
dibaca sebagai aproksimasi legacy.

Referensi yang benar untuk klimatologi (bukan laporan teknis 2015 yang berjudul
*"Climatology Development for NOAA Coral Reef Watch's 5-km Product Suite"*):

- Halaman *5-km Climatology Description* — `coralreefwatch.noaa.gov/product/5km/description_climatology.php`
  (periode acuan 1985–1990 ditambah 1993; bukan turunan Pathfinder v5.2).
- Halaman riwayat produk 5-km — `coralreefwatch.noaa.gov/product/5km/history_5km_products.php`
  (catatan bias hangat klimatologi lama dan revisi kategori 2023).

---

## 3. Uji fungsional aturan QC

**Jenis pengujian:** `run_qc_functional_test()`
**Label yang dikembalikan kode:** *"Uji fungsional aturan QC pada kasus sintetis terisolasi"*
**Pernyataan cakupan (verbatim):** *"Kasus dibangun manual dan dijalankan in-process;
hasilnya menggambarkan perilaku aturan pada seri uji ini, bukan akurasi lapangan atau
presisi umum."*

Tidak ada presisi, recall, atau F1 yang dilaporkan. Matriks konfusi 155/200 paket pada
draf lama dicabut karena aritmetikanya tidak konsisten dan karena anomali disuntikkan
oleh simulator yang sama yang menulis aturannya.

### 3.1 Kontrol bersih

Seri sinusoidal terbatas pada 4 parameter, 120 siklus, tanpa pelanggaran yang disengaja.
Tidak ada flag kritis dari aturan mana pun:

| Aturan | Jumlah flag kritis |
|---|---|
| RANGE_FAIL | 0 |
| SPIKE_FAIL | 0 |
| STUCK_FAIL | 0 |
| DRIFT_FAIL | 0 |

Catatan desain: seri kontrol harus berosilasi. Nilai konstan akan memicu aturan *stuck*
dan itulah akar dari 95 false-positive pada versi uji sebelumnya.

### 3.2 Kurva sensitivitas lonjakan (ambang aturan 1,5 °C, 5 uji per titik)

| ΔT (°C) | Terdeteksi | Perilaku |
|---|---|---|
| 0,5 | 0/5 | tidak terflag |
| 0,8 | 0/5 | tidak terflag |
| 1,2 | 0/5 | tidak terflag |
| 1,5 | **0/5** | tidak terflag — aturan memakai `>` ketat, bukan `≥` |
| 1,8 | 5/5 | terflag |
| 2,5 | 5/5 | terflag |
| 3,5 | 5/5 | terflag |

Kurva ini memakai variasi magnitudo 0,5–3,5 °C seperti yang diminta pada tinjauan, bukan
hanya satu nilai. Batas potongnya tajam: nol deteksi sampai 1,5 °C, deteksi penuh mulai
1,8 °C. Perilaku tepat di ambang (1,5 °C tidak terflag) adalah konsekuensi aturan
perbandingan ketat, bukan kegagalan.

### 3.3 Kasus sensor macet

| Parameter | Nilai |
|---|---|
| Siklus uji | 10 |
| Jendela aturan | 6 siklus |
| Nilai konstan | 29,0 °C |
| Siklus terdeteksi | 5 |
| **Deteksi pertama** | **siklus 6** |
| Deteksi pertama yang diharapkan | siklus 6 |

Siklus 1–5 memang tidak terdeteksi. Ini adalah latensi inisiasi jendela, dan sekarang
dilaporkan sebagai angka eksplisit, bukan dikubur dalam narasi *false negative*.

### 3.4 Kasus drift

| Parameter | Nilai |
|---|---|
| Siklus uji | 40 |
| Jendela regresi | 24 siklus |
| Kemiringan pH per siklus | −0,02 |
| Ambang kemiringan | 0,015 |
| Siklus terdeteksi | 17 |
| **Deteksi pertama** | **siklus 24** |

Kasus drift ini nyata ada di dalam uji (draf lama menyebut drift padahal tidak ada kasus
drift pada 155 paketnya).

### 3.5 Kasus di luar batas fisik

15 dari 15 kasus terdeteksi. Rentang valid suhu: 20,0–35,0 °C.

### 3.6 Kontrol positif palsu untuk lonjakan

30 siklus dengan bump sub-ambang 0,4 °C: **0 flag lonjakan**. Aturan tidak bereaksi
terhadap fluktuasi di bawah ambang.

### 3.7 Batasan yang dinyatakan kode (verbatim)

1. *"Tidak ada ground truth lapangan; kasus dibangun dari spesifikasi aturan."*
2. *"Ambang dan jendela mengikuti implementasi saat ini, bukan standar eksternal."*
3. *"Tidak menguji packet loss, baterai rendah, atau duplikasi counter."*

---

## 4. Dampak kehilangan paket: Monte Carlo 100 seed, jalur berpasangan

**Fungsi:** `run_packet_loss_monte_carlo(num_seeds=100)`

### 4.1 Metode (yang sebelumnya tidak dilaporkan)

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

Jam simulasi dipatok karena simulator bawaan memakai `datetime.now()`; tanpa pin,
indeks pencapaian Alert 1 bergeser antar-jalan dan hasil tidak dapat direproduksi.
Dengan pin, dua pemanggilan berturut-turut menghasilkan keluaran identik (diuji di
`tests/test_evaluation.py::test_monte_carlo_is_deterministic`).

Karena setiap seed memakai jalur SST yang sama untuk referensi dan untuk ketiga tingkat
loss, perbandingan bersifat berpasangan. Ini memperbaiki kelemahan draf lama yang
membandingkan dua jalur acak berbeda.

### 4.2 Hasil (2026-11-06, 100 seed)

| Loss | PDR terukur (mean ± std) | MAE DHW °C-minggu (mean ± std) | Bias DHW maksimum (mean) | Tunda Alert 1 (hari, mean ± std) | Run valid |
|---|---|---|---|---|---|
| 5% | 95,12 ± 2,51 % | 0,0156 ± 0,0173 | 0,0329 | 0,018 ± 0,064 | 100/100 |
| 10% | 89,62 ± 3,45 % | 0,0313 ± 0,0306 | 0,0585 | 0,062 ± 0,119 | 100/100 |
| 20% | 79,94 ± 4,48 % | 0,0463 ± 0,0450 | 0,0883 | 0,115 ± 0,167 | 100/100 |

PDR terukur hampir sama dengan loss yang disuntikkan — itu memang **membaca ulang
masukan**, dan bukan temuan ilmiah. Yang bermakna adalah dua kolom berikutnya.

### 4.3 Temuan yang sebenarnya

1. **Galat DHW naik mendekati linier terhadap loss:** 0,0156 → 0,0313 → 0,0463 °C-minggu
   untuk 5/10/20%. Bahkan pada loss 20%, galat rata-rata masih di bawah 0,05 °C-minggu.
2. **Keterlambatan peringatan tidak naik secara linier:** 0,018 → 0,062 → 0,115 hari.
   Ini bukan artefak. Forward fill menutup putus data pendek sehingga akumulasi DHW
   hampir tidak bergeser; delay muncul hanya ketika dropout kebetulan menutupi titik
   lintasan ambang. **Keterlambatan saturasi** — itu hasil pengukuran, dan justru
   membantah klaim draf lama bahwa delay proporsional sempurna terhadap loss.
3. **Satuan "hari" di sini bermakna pada langkah 6 jam.** Nilai 0,018 hari ≈ 0,07 langkah,
   artinya pada sebagian besar seed tidak ada keterlambatan sama sekali (median 0).

### 4.4 Batasan

- Kanal radio tidak dimodelkan. Loss diasumsikan Bernoulli independen, bukan *burst loss*
  akibat laut bergelombang atau gateway jenuh.
- Tidak ada pengukuran lapangan yang membandingkan loss nyata dengan galat nyata.
- Hasil berlaku untuk skenario panas buatan berintensitas 2,3 °C di atas MMM pada node 1.

---

## 5. Peramalan multi-horizon: tidak dievaluasi

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
sama. Fungsi `evaluate_multi_horizon_forecasting(..., step_days=5.0)` mengonversi 1 hari
dan 7 hari keduanya menjadi **1 langkah** — sehingga "MAE H=1" dan "MAE H=7" akan
mengukur hal yang identik. Melaporkan keduanya sebagai dua horizon berbeda adalah
menyesatkan. Diuji eksplisit di
`tests/test_evaluation.py::test_multi_horizon_collapses_at_five_day_cadence`.

Angka lama (H=1 0,08 °C; H=7 0,22 °C; H=14 0,41 °C) berasal dari deret sintetis
pengganti, **dicabut**, dan tidak dipublikasikan ulang.

**Yang dibutuhkan agar dapat dievaluasi:** deret SST harian minimal 30 sampel, idealnya
60+, dari sumber yang provenance-nya jelas; lalu jalankan
`evaluate_multi_horizon_forecasting(series, horizons=[1,7,14], step_days=1.0)`.
Fungsi itu sudah diuji dan berjalan benar pada deret harian sintetis 60 titik
(`test_multi_horizon_runs_on_daily_series`).

---

## 6. Latensi komputasi dalam-proses

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

Angka ini **bervariasi antar-jalan** karena bergantung pada beban mesin. Nilai di atas
adalah run yang dipakai untuk dokumen ini; setiap pengutipan harus menyebut run-nya.

**Yang diukur:** encode payload → decode → QC → DHW → deteksi anomali → commit SQLite
(DB sementara), seluruhnya dalam satu proses Python.

**Yang tidak diukur** (`excluded_layers` yang dikembalikan kode):

1. Waktu pancar radio LoRaWAN fisik — estimasi ~50–300 ms tergantung spreading factor SF7–SF12.
2. Backhaul gateway ke network server — estimasi ~100–1000 ms via seluler/satelit.
3. Roundtrip soket jaringan broker MQTT eksternal — estimasi ~5–50 ms.

Ketiganya adalah **estimasi literatur, bukan hasil pengukuran**. Klaim latensi
end-to-end belum bisa dibuat.

---

## 7. Angka lama yang dicabut, dan alasannya

| Angka lama | Alasan dicabut |
|---|---|
| DHW MAE 0,024 °C-minggu, *r* = 0,9998, "identik dengan NOAA" | Pembanding dihitung dari berkas yang sama; pembanding itu sendiri melanggar definisi DHW 84-hari. Melingkar. |
| QC presisi 100%, recall 58,8%, F1 74,0% (155/200 paket) | Anomali disuntikkan oleh simulator sendiri lalu dideteksi aturan sendiri; matriks tidak konsisten aritmetikanya (anomali 55 vs TP+FN 53; bersih 100 vs TN+FP 102). |
| "DHW tetap stabil" tanpa angka | Tidak ada metrik yang mendasarinya. |
| Lead time 35 hari | Selisih antar-level pada skenario buatan; ditentukan desain skenario, bukan kemampuan sistem. Tidak ada kejadian pemutihan historis yang dipakai. |
| Alert Level 2 sebagai "ambang pemutihan" | Keliru. Pemutihan signifikan diperkirakan mulai Alert Level 1 (DHW ≥ 4). Alert 2 adalah ambang mortalitas. |
| Reduksi cooldown 98% | Dengan 4 paket/jam dan cooldown 1 jam, batas atas reduksi adalah 75% (4 paket, 1 lolos). 98% hanya mungkin bila kondisi simulasinya jauh lebih rapat, dan kondisi itu tidak pernah dilaporkan. |
| Latensi 2,45 ms | Hampir pasti hanya waktu fungsi di dalam proses, tanpa jaringan MQTT dan tanpa tulis ke TimescaleDB. Sudah diganti pengukuran berkas ini. |
| MMM 29,20 / 29,50 / 29,10 / 29,60 / 28,80 °C "dari CRW v3.1" | Tidak ada berkas MMM v3.1, tidak ada virtual station, tidak ada tanggal akses. Nilai ini ditetapkan manual. |
| "Semua kriteria TERPENUHI" | Beberapa kriteria hanya terpenuhi sebagai berkas konfigurasi, bukan sebagai eksekusi. Lihat matriks bagian 8. |

---

## 8. Matriks bukti infrastruktur

Kolom *bukti* hanya memuat hal yang benar-benar dijalankan. Kolom *batasan* menyebut apa
yang tidak dijalankan.

| Komponen | Bukti yang ada | Batasan |
|---|---|---|
| Payload 12-byte | `tests/test_protocol.py` lulus: roundtrip, batas ekstrem, payload rusak | Radio fisik tidak diuji |
| Ingestion + penyimpanan | `tests/test_ingestion_subscriber.py` lulus pada **SQLite** (`segara.db`) | **TimescaleDB belum pernah dijalankan**; skema Timescale belum teruji |
| MQTT | Jalur in-process event bus dipakai oleh `run_segara.py` | **Broker MQTT nyata belum pernah dipakai**; tidak ada bukti publish/subscribe lewat Mosquitto |
| Alerting | `tests/test_alerting.py` lulus dengan dispatcher mock | **Telegram belum pernah mengirim pesan ke bot nyata**; mode logging simulasi |
| Docker Compose | `infra/docker-compose.yml` ada dan **valid sebagai YAML** | **Docker belum terpasang di host ini; compose belum pernah dijalankan** |
| Dashboard | `npm run build` sukses (vite 6.4.5, 1591 modul, `dist/assets/index-Fi-FmqXp.js` 349,95 kB); `npx tsc --noEmit` keluar 0 | Hanya diuji build; tidak ada uji UI otomatis |
| Evaluator | `tests/test_evaluation.py` — 18 pengujian baru | Angka ilmiahnya tetap sintetis |
| Suite total | `python -m pytest tests/ -q` → **82 passed**, 0 warning | — |

Catatan: kriteria "`docker compose up` berhasil" **tidak** terpenuhi. Yang terpenuhi
adalah "berkas konfigurasi valid sebagai YAML". Keduanya berbeda dan tidak boleh disamakan.

---

## 9. MMM: nilai manual, bukan data CRW

| Node | Stasiun | Koordinat | MMM dipakai (°C) |
|---|---|---|---|
| 1 | Bunaken Reef | 1,6240° N, 124,7570° E | 29,20 |
| 2 | Raja Ampat Kri | 0,5510° S, 130,6720° E | 29,50 |
| 3 | Wakatobi Tomia | 5,5120° S, 123,7540° E | 29,10 |
| 4 | Karimunjawa | 5,8520° S, 110,4530° E | 29,60 |
| 5 | Komodo Padar | 8,5520° S, 119,5310° E | 28,80 |

**Sumber: tidak ada.** Nilai-nilai ini ditetapkan manual sebagai aproksimasi regional.
Tidak diambil dari berkas `ct5km_climatology_v3.1.nc`, tidak dari virtual station CRW,
dan tidak ada tanggal akses yang dapat dilaporkan.

Konsekuensi: ambang HotSpot setiap stasiun bergeser sebesar kesalahan MMM. Kesalahan
0,3 °C pada MMM menggeser awal Bleaching Warning sebesar 0,3 °C. Semua angka DHW di
dokumen ini harus dibaca relatif terhadap MMM manual tersebut.

**Tindakan yang diperlukan:** unduh MMM dari produk klimatologi CRW v3.1 untuk setiap
koordinat, catat tanggal akses, ganti nilai di simulator, lalu ulangi bagian 2 dan 4.

---

## 10. Cara mereproduksi

```powershell
python -m pytest tests/ -q                     # 82 passed
python -c "from api.routers.evaluation import run_packet_loss_monte_carlo as f; import json; print(json.dumps(f(100), indent=1))"
python -c "from api.routers.evaluation import run_qc_functional_test as f; import json; print(json.dumps(f(), indent=1))"
python -c "from api.routers.evaluation import run_dhw_algorithmic_verification as f; import json; print(json.dumps(f(), indent=1))"
python run_segara.py                           # dashboard di http://127.0.0.1:8000/
```

Endpoint HTTP: `GET /api/evaluation/metrics` mengembalikan seluruh payload di atas.

---

## 11. Keterbatasan keseluruhan

1. **Tidak ada validasi NOAA.** Tidak ada satu pun angka DHW yang dibandingkan dengan
   produk CRW resmi. Berkas acuan adalah rekonstruksi tanpa provenance.
2. **Tidak ada ground truth lapangan** untuk QC maupun DHW. Semua kasus uji dibangun
   dari spesifikasi aturan sendiri.
3. **Tidak ada kejadian pemutihan historis** yang dipakai. Karena itu tidak ada klaim
   *lead time* pemutihan yang sah — angka 35 hari pada draf lama adalah desain skenario.
4. **Sistem peringatan adalah aproksimasi legacy 5-tingkat.** Revisi CRW 15 Desember 2023
   (Alert Level 3–5) belum diimplementasikan.
5. **Infrastruktur produksi belum diuji:** TimescaleDB, broker MQTT, Telegram, Docker.
   Yang teruji adalah SQLite, event bus in-process, dispatcher mock, dan YAML valid.
6. **Kanal radio tidak dimodelkan.** Loss paket adalah Bernoulli independen pada jalur SST
   sintetis, bukan propagasi LoRaWAN di laut.
7. **Peramalan tidak dievaluasi** karena tidak ada deret SST harian yang sah.
8. **MMM manual** menggeser seluruh ambang stres secara tidak terkontrol.