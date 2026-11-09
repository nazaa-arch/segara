# Metodologi Ilmiah, Quality Control & Verifikasi Sistem SEGARA

Dokumen ini mendokumentasikan landasan teori termal, rujukan klimatologi NOAA Coral Reef
Watch (CRW) yang benar, aturan kendali mutu, desain evaluasi, dan batasan pengujian pada
SEGARA (*Sistem Early-warning Gangguan termal Atas terumbu kaRAng*).

Angka hasil pengujian **tidak** ada di dokumen ini; sumber tunggal angka adalah
`docs/evaluation-report.md`. Dokumen ini menjelaskan *bagaimana* sesuatu diukur dan
*sejauh mana* hasilnya sah.

---

## 0. Batas validitas

| Hal | Status |
|---|---|
| `data/historical_noaa_indonesia.csv` | **Rekonstruksi tanpa provenance.** Header berkas sendiri menyebut "Rekonstruksi". Tidak ada URL, tanggal akses, atau checksum. Kolom `dhw_official` di dalamnya **melanggar definisi DHW 84-hari** (menurun 3 kali meski jendela akumulasi belum tergeser), sehingga tidak dapat dipakai sebagai pembanding sah. |
| MMM stasiun | **Aproksimasi manual.** Tidak diekstrak dari `ct5km_climatology_v3.1.nc` maupun virtual station CRW. |
| Verifikasi DHW | **Konsistensi internal**, bukan validasi observasional. |
| Uji QC | **Uji fungsional** pada seri sintetis terisolasi, bukan akurasi lapangan. |
| Packet loss | Sintetis, pasangan per seed, loss Bernoulli independen. |
| Peramalan | **Tidak dievaluasi** — data tidak memenuhi syarat cadence. |
| Latensi | **In-process** saja. |
| TimescaleDB / MQTT broker / Telegram / Docker | **Belum pernah dijalankan.** |

---

## 1. Pertanyaan penelitian dan cara menjawabnya

### 1.1 Pertanyaan

1. **Dinamika peringatan dini.** Berapa lama interval dari Bleaching Warning
   (HotSpot ≥ 1,0) sampai Alert Level 1 (DHW ≥ 4,0) dan Alert Level 2 (DHW ≥ 8,0)?
2. **Dampak kehilangan paket.** Berapa galat DHW dan berapa penundaan deteksi Alert Level 1
   pada loss 5%, 10%, 20%?
3. **Verifikasi fungsional aturan QC.** Bagaimana kurva sensitivitas lonjakan pada magnitudo
   0,5–3,5 °C, dan bagaimana latensi inisiasi jendela memengaruhi deteksi *stuck* dan *drift*?

### 1.2 Batasan yang mengikat ketiga pertanyaan

- Seluruh telemetri dibangkitkan secara numerik (*software-in-the-loop*). Tidak ada klaim
  empiris tentang korosi air laut, *biofouling* pada probe, atau keandalan baterai.
- **Tidak ada kejadian pemutihan historis** yang dipakai sebagai pembanding. Karena itu
  pertanyaan 1 hanya dapat dijawab sebagai deskripsi skenario, **bukan** sebagai *lead time*
  pemutihan. Angka "35 hari" pada draf lama adalah selisih antar-level pada skenario buatan;
  nilainya ditentukan oleh desain skenario, bukan kemampuan sistem.
- Karena DHW adalah akumulasi, pergeseran MMM manual sebesar 0,3 °C menggeser seluruh ambang
  stres sebesar 0,3 °C. Semua hasil harus dibaca relatif terhadap MMM manual tersebut.

---

## 2. Rujukan klimatologi NOAA CRW (dikoreksi)

Draf lama mengutip laporan 2015 dengan judul yang keliru dan mengaitkannya ke v3.1. Koreksinya:

### 2.1 Laporan 2015 — apa isinya sebenarnya

- Judul benar: *"Climatology Development for NOAA Coral Reef Watch's 5-km Product Suite"*
  (NOAA Technical Report NESDIS 145). **Bukan** *"...5-km Daily Coral Bleaching Thermal
  Stress Monitoring"*.
- Laporan itu mendokumentasikan klimatologi 5-km yang dibangun dari dataset **Pathfinder
  v5.2**.
- Klimatologi tersebut belakangan diketahui membawa **bias hangat**, sehingga stres panas
  terhitung terlalu rendah.

### 2.2 Klimatologi v3.1 — produk berbeda

- Diturunkan dari kombinasi analisis SST **Geo-Polar Blended (2002–2012)** dan reanalisis
  **UK Met Office (1985–2002)**.
- Periode acuan: **1985–1990 ditambah 1993**.
- Karena itu laporan 2015 **tidak boleh** dikutip sebagai sumber v3.1.

### 2.3 Rujukan yang dipakai

| Keperluan | Sumber |
|---|---|
| Deskripsi klimatologi 5-km v3.1 | `coralreefwatch.noaa.gov/product/5km/description_climatology.php` |
| Riwayat produk 5-km dan revisi 2023 | `coralreefwatch.noaa.gov/product/5km/history_5km_products.php` |

Halaman-halaman ini menjelaskan **metode** NOAA. Keduanya **tidak** membuktikan nilai MMM
lokal yang dipakai aplikasi ini.

### 2.4 Penetapan MMM stasiun

$$ \text{MMM} = \max_{m \in \{1,\dots,12\}} \overline{\text{SST}}_m $$

Pada prototipe ini MMM ditetapkan manual:

| Node | Stasiun | Koordinat | MMM (°C) | Ambang +1 °C |
|---|---|---|---|---|
| 1 | Bunaken Reef | 1,6240° N, 124,7570° E | 29,20 | 30,20 |
| 2 | Raja Ampat Kri | 0,5510° S, 130,6720° E | 29,50 | 30,50 |
| 3 | Wakatobi Tomia | 5,5120° S, 123,7540° E | 29,10 | 30,10 |
| 4 | Karimunjawa | 5,8520° S, 110,4530° E | 29,60 | 30,60 |
| 5 | Komodo Padar | 8,5520° S, 119,5310° E | 28,80 | 29,80 |

**Sumber nilai: tidak ada.** Bukan ekstraksi NetCDF, bukan virtual station, tanpa tanggal
akses. Untuk penggunaan nyata: unduh MMM dari produk klimatologi CRW v3.1 pada koordinat
tersebut, catat tanggal akses, lalu ganti nilai di simulator.

---

## 3. Formulasi stres termal dan sistem peringatan

### 3.1 HotSpot dan Degree Heating Weeks

$$ \text{HotSpot}(t) = \max(0.0,\ \text{SST}(t) - \text{MMM}) $$

$$ \text{DHW}(t) = \frac{1}{7} \sum_{i=t-83}^{t} \left( \text{HotSpot}(i) \cdot
\mathbb{I}_{[\text{HotSpot}(i) \ge 1.0]} \right) \quad (^\circ\text{C}\text{-minggu}) $$

Jendela 84 hari. Konsekuensi yang dapat diuji: bila seluruh seri observasi berada di dalam
jendela 84 hari, DHW **tidak boleh menurun** — tidak ada suku yang keluar dari jendela.
Inilah dasar uji konsistensi pada `run_dhw_algorithmic_verification()`.

### 3.2 Sistem kategori yang diimplementasikan

SEGARA mengimplementasikan **sistem 5-tingkat lama**:

1. **No Stress** — HotSpot ≤ 0
2. **Bleaching Watch** — 0 < HotSpot < 1,0
3. **Bleaching Warning** — HotSpot ≥ 1,0 dan DHW < 4,0
4. **Alert Level 1** — HotSpot ≥ 1,0 dan 4,0 ≤ DHW < 8,0
5. **Alert Level 2** — HotSpot ≥ 1,0 dan DHW ≥ 8,0

Level Warning ke atas mensyaratkan HotSpot ≥ 1,0 (revisi 2026-11-09). Versi sebelumnya
menetapkan Alert Level 1/2 dari DHW saja, sehingga status alert bertahan hingga 12 minggu
setelah suhu kembali normal.

**Koreksi penting terhadap draf lama:** pemutihan signifikan diperkirakan mulai **Alert
Level 1** (DHW ≥ 4), bukan Alert Level 2. Alert Level 2 adalah ambang mortalitas.

**Revisi NOAA 15 Desember 2023:** CRW memperluas sistem menjadi 7 tingkat dengan menambahkan
Alert Level 3 (DHW ≥ 12), Level 4 (≥ 16), dan Level 5 (≥ 20). SEGARA **belum**
mengimplementasikan level 3–5, dan ambang resmi terbaru belum diverifikasi terhadap
publikasi CRW. Setiap label "Alert Level" di dashboard adalah aproksimasi legacy.

---

## 4. Aturan kendali mutu

Sumber tunggal nilai di bawah ini adalah konstanta pada `qc/rules.py`
(`RANGE_LIMITS`, `SPIKE_LIMITS`, `SPIKE_REBASELINE_CYCLES`, `default_stuck_windows`,
`DRIFT_PH_SLOPE_LIMIT`, `drift_window_size`).

Flag dicatat **per parameter**. Data suhu dipakai untuk DHW selama suhunya sendiri lolos
range/spike/stuck; kegagalan pH, kekeruhan, atau baterai tidak lagi membuang data suhu.
pH/kekeruhan yang ditolak diisi 0 pada indeks stres gabungan dan ditandai tidak tersedia.

1. **Range test** (`RANGE_LIMITS`) — suhu 20,0–35,0 °C; pH 7,5–8,5; salinitas
   30,0–37,0 PSU; kekeruhan 0–100 NTU; baterai 0–100 %.
2. **Spike test** (`SPIKE_LIMITS`, perbandingan **ketat** `>` bukan `≥`) — selisih terhadap
   **nilai valid terakhir** (bukan nilai mentah terakhir): suhu > 1,5 °C; pH > 0,40;
   salinitas > 2,0 PSU; kekeruhan > 35,0 NTU. Satu lonjakan menghasilkan satu flag, bukan
   dua (naik dan turun). Bila 3 pembacaan berturut-turut menyimpang, dianggap pergeseran
   level nyata dan acuan disetel ulang.
3. **Stuck test** — variansi nol pada jendela bergerak per parameter: suhu W = 6, pH W = 8,
   salinitas dan kekeruhan W = 12. Jendela lebih panjang untuk parameter yang resolusi
   payload-nya kasar dan secara alami stabil (heuristik, bukan standar eksternal).
4. **Drift test** — hanya pH: |slope| regresi linier > 0,015 per siklus pada jendela
   W = 24 observasi. Suhu sengaja tidak diuji karena tren pemanasan saat gelombang panas
   adalah sinyal yang ingin dideteksi.
5. **Packet loss detection** — Δcounter (mod 65536) > 1. Δcounter = 0 diberi flag
   `DUPLICATE` dan dikeluarkan dari analitik; Δcounter > 32768 dianggap counter mundur
   (reboot), bukan paket hilang.
6. **Integritas frame** — hanya panjang 12 byte yang diperiksa; frame tidak membawa CRC,
   sehingga integritas bit diandalkan pada lapisan transport (MIC LoRaWAN).

### 4.1 Konsekuensi metodologis yang harus dilaporkan, bukan disembunyikan

- **Stuck** suhu tidak dapat terdeteksi sebelum siklus ke-6 (pH ke-8, salinitas/kekeruhan ke-12). Siklus 1–5 adalah latensi inisiasi
  jendela, bukan kegagalan aturan. Karena itu uji melaporkan *deteksi pertama* secara
  eksplisit: **siklus 6**.
- **Drift** tidak dapat terdeteksi sebelum 24 observasi terkumpul. Deteksi pertama: **siklus 24**.
- **Spike** tepat di 1,5 °C **tidak** terflag karena aturan memakai `>`. Ini konsekuensi
  desain, diuji eksplisit.
- Seri kontrol bersih **harus berosilasi**. Nilai konstan akan memicu aturan stuck — itulah
  akar 95 false positive pada versi uji sebelumnya. Kegagalan ini adalah cacat fixture, bukan
  cacat aturan.

### 4.2 Mengapa presisi/recall tidak dilaporkan

Draf lama melaporkan presisi 100%, recall 58,8%, F1 74,0% dari 155–200 paket sintetis.
Angka itu dicabut karena:

1. Aritmetikanya tidak konsisten: anomali disuntikkan 55 tetapi TP + FN = 53; paket bersih
   100 tetapi TN + FP = 102.
2. Aturan stuck butuh 6 siklus berturut-turut, sedangkan run macetnya 8 siklus — seharusnya
   paket awal setiap run lolos, jadi FN mestinya lebih dari 2.
3. Anomali disuntikkan oleh simulator yang sama yang menulis aturannya. Itu menguji
   konsistensi diri, bukan akurasi.
4. Sampel 155 paket terlalu kecil untuk klaim presisi umum.
5. "15 paket macet" bukan kelipatan 8.
6. Tidak ada kasus drift di dalam 155 paket itu, padahal pertanyaan penelitian menyebut drift.

Yang dilaporkan sekarang adalah **uji fungsional per aturan** dengan cakupan yang dinyatakan
verbatim oleh kode: *"Kasus dibangun manual dan dijalankan in-process; hasilnya menggambarkan
perilaku aturan pada seri uji ini, bukan akurasi lapangan atau presisi umum."*

---

## 5. Desain evaluasi dampak kehilangan paket

Draf lama membandingkan dua jalur SST acak yang berbeda antar-tingkat loss, sehingga efek
loss tidak terisolasi. Desain yang dipakai sekarang:

| Butir | Nilai |
|---|---|
| Desain | Jalur SST sintetis **berpasangan per seed**; masker loss Bernoulli independen |
| Interval telemetri | 6 jam per langkah (Δt = 0,25 hari) |
| Panjang seri | 80 langkah (20 hari) |
| Perlakuan paket hilang | **Forward fill**; nilai awal hilang diisi HotSpot 0 |
| Ulangan | 100 seed per tingkat loss |
| Seed simulator | 1000 … 1099 |
| Seed masker | 500000 + 10·seed + indeks tingkat loss |
| Jam simulasi | Dipatok `2020-06-15T00:00Z`, langkah 6 jam |

**Mengapa jam dipatok:** simulator bawaan memakai `datetime.now()`, sehingga indeks
pencapaian Alert 1 bergeser antar-jalan dan hasil tidak dapat direproduksi. Dengan pin, dua
pemanggilan berturut-turut menghasilkan keluaran identik (diuji otomatis).

**Mengapa berpasangan:** setiap seed memakai jalur SST yang sama untuk referensi dan untuk
ketiga tingkat loss, sehingga selisih keluaran hanya disebabkan masker loss — bukan variasi
jalur.

**Yang diukur:** PDR, MAE dan bias maksimum DHW, serta penundaan pencapaian Alert Level 1.
PDR hanya membaca ulang loss yang disuntikkan; nilainya bukan temuan ilmiah. Yang bermakna
adalah MAE dan penundaan.

**Satuan waktu:** "hari" bermakna pada langkah 6 jam. Penundaan 0,018 hari ≈ 0,07 langkah —
pada sebagian besar seed tidak ada penundaan sama sekali.

**Batasan:** kanal radio tidak dimodelkan. Loss diasumsikan Bernoulli independen, bukan
*burst loss* akibat laut bergelombang atau gateway jenuh. Tidak ada pengukuran lapangan.

---

## 6. Peramalan multi-horizon: mengapa tidak dievaluasi

Metode: Holt's Linear Exponential Smoothing with Damped Trend (α = 0,35; β = 0,12; φ = 0,95)
dibandingkan baseline persistence ($\hat{y}_{t+h} = y_t$) dengan *rolling-origin backtesting*.

**Status: tidak dievaluasi.** Alasan:

1. Berkas acuan hanya berisi **17 sampel node 1** dengan jarak **5 hari**.
2. Dengan `step_days = 5.0`, horizon 1 hari dan 7 hari **runtuh ke jumlah langkah yang sama**
   (keduanya 1 langkah). Melaporkan MAE H=1 dan MAE H=7 sebagai dua horizon berbeda akan
   menyesatkan. Diuji eksplisit di `tests/test_evaluation.py`.
3. Pada kurva pemanasan buatan yang mulus, model tren hampir pasti mengalahkan persistence —
   uji semacam itu tidak informatif dan tidak sah dijadikan bukti kemampuan peramalan.
4. Angka lama (0,08 / 0,22 / 0,41 °C) berasal dari deret sintetis pengganti dan **dicabut**.
   Perhatikan juga: 0,41 °C pada H=14 hampir setengah ambang stres 1,0 °C.

**Syarat agar dapat dievaluasi:** deret SST harian minimal 30 sampel (idealnya 60+) dengan
provenance jelas, lalu jalankan
`evaluate_multi_horizon_forecasting(series, horizons=[1,7,14], step_days=1.0)`. Fungsi itu
sudah diuji dan berjalan pada deret harian sintetis 60 titik.

---

## 7. Latensi: apa yang diukur

**Cakupan:** *"Latensi Komputasi Dalam-Proses CPU (In-Process Execution Latency)"*.

Diukur: encode payload → decode → aturan QC → commit SQLite lokal, semuanya dalam satu proses
Python. 100 iterasi, mean/median/p95/p99.

Tidak diukur (estimasi literatur, bukan pengukuran):

1. Waktu pancar radio LoRaWAN fisik — ~50–300 ms (SF7–SF12).
2. Backhaul gateway ke network server — ~100–1000 ms.
3. Roundtrip soket broker MQTT eksternal — ~5–50 ms.

Angka latensi bervariasi antar-jalan karena bergantung pada beban mesin. Setiap pengutipan
harus menyebut run-nya. Klaim latensi end-to-end belum bisa dibuat.

---

## 8. Klaim yang tidak boleh dibuat

| Klaim | Alasan |
|---|---|
| "Terbukti identik dengan NOAA" | Pembanding berasal dari berkas yang sama dan melanggar definisi DHW. |
| "Presisi QC 100%" | Uji sintetis tanpa ground truth lapangan; aritmetika draf lama tidak konsisten. |
| "*Lead time* pemutihan 35 hari" | Selisih antar-level pada skenario buatan, bukan kejadian nyata. |
| "Cooldown mereduksi 98%" | 4 paket/jam dengan cooldown 1 jam → batas atas 75%. |
| "Latensi 2,45 ms" | In-process saja; tanpa jaringan dan tanpa TimescaleDB. |
| "MMM dari CRW v3.1" | Tidak ada berkas, tidak ada stasiun virtual, tidak ada tanggal akses. |
| "`docker compose up` berhasil" | Docker belum terpasang; yang valid hanya YAML-nya. |
| "MQTT teruji" | Yang dipakai adalah event bus in-process. |
| "Telegram terkirim" | Hanya dispatcher mock. |
| "TimescaleDB teruji" | Yang teruji SQLite. |
| "DHW tetap stabil" | Tanpa angka; hanya narasi. |