# Sistem Peringatan Dini Pemutihan Karang (Berbasis Simulasi)

Lingkup: **sistem perangkat lunak saja**. Pelampung IoT disimulasikan, tidak dibuat fisik.

## 1. Gambaran Singkat

Sistem menerima data telemetri pelampung virtual (suhu, pH, salinitas, kekeruhan), memvalidasi kualitasnya, menghitung indikator stres termal karang (HotSpot dan Degree Heating Weeks), lalu menampilkan dashboard dan mengirim peringatan dini.

**Klaim yang bisa dipertahankan:** pipeline end-to-end terbukti bekerja, logika DHW benar, dan peringatan dini terukur terhadap data nyata historis. Klaim akurasi sensor fisik **tidak** dibuat.

## 2. Pertanyaan Penelitian

1. Seberapa dini sistem dapat mendeteksi stres termal karang dibanding ambang pemutihan?
2. Seberapa tahan pipeline terhadap kehilangan paket dan data sensor yang rusak?
3. Seberapa baik quality control otomatis menangkap lonjakan, sensor macet, dan drift?

## 3. Arsitektur

```
[Simulator Pelampung] -> MQTT (broker Mosquitto)
        -> [Ingestion + Decoder]
        -> [QC Otomatis]
        -> [TimescaleDB / PostgreSQL]
        -> [Mesin Analitik: HotSpot, DHW, anomali, forecast]
        -> [API FastAPI] -> [Dashboard React] + [Alert Telegram/email]
```

## 4. Struktur Repositori

```
coral-monitor/
├── docs/                 # spesifikasi payload, metodologi, laporan
├── simulator/            # generator data pelampung virtual
├── ingestion/            # subscriber MQTT + decoder payload
├── qc/                   # aturan quality control
├── analytics/            # HotSpot, DHW, anomali, forecasting
├── api/                  # FastAPI
├── dashboard/            # React + TypeScript
├── infra/                # docker-compose (mosquitto, db, api)
├── data/                 # data referensi (NOAA CRW, dll.)
└── tests/
```

## 5. Rangkaian Kerja per Fase

### Fase 1: Spesifikasi (minggu 1)
- [ ] Tulis pertanyaan penelitian dan batasan lingkup
- [ ] Tentukan parameter dan rentang fisik

| Parameter | Rentang | Satuan |
|---|---|---|
| Suhu | 20 - 35 | °C |
| pH | 7,5 - 8,5 | - |
| Salinitas | 30 - 37 | PSU |
| Kekeruhan | 0 - 100 | NTU |

- [ ] Rancang format payload biner ringkas (meniru batas LoRaWAN) dan dokumentasikan

| Field | Ukuran | Keterangan |
|---|---|---|
| node_id | 1 byte | ID pelampung |
| counter | 2 byte | deteksi paket hilang |
| suhu | 2 byte | °C x 100, bertanda |
| pH | 2 byte | x 100 |
| salinitas | 2 byte | PSU x 100 |
| kekeruhan | 2 byte | NTU x 10 |
| baterai | 1 byte | persen |

- [ ] Tetapkan interval kirim (misalnya 15 menit)

**Output:** `docs/payload-spec.md`

### Fase 2: Simulator dan MQTT (minggu 2)
- [ ] Setup Mosquitto lewat docker-compose
- [ ] Simulator Python menghasilkan data sintetis:
  - Suhu: siklus harian (sinus) + tren musiman + gelombang panas laut buatan
  - Noise sensor, drift pH, lonjakan acak
  - Kekeruhan naik saat "hujan/badai"
  - Paket hilang 5-20% dan keterlambatan
  - Sensor macet (nilai konstan) dan sensor rusak (nilai di luar rentang)
- [ ] Dukung banyak pelampung virtual (3-5 node)
- [ ] Mode skenario berulang (seed tetap) agar hasil bisa direproduksi
- [ ] **Mode replay data nyata**: putar ulang suhu laut historis (NOAA CRW / Copernicus) lewat simulator, supaya pengujian memakai pola alam yang sebenarnya

**Output:** data mengalir lewat MQTT dalam format biner

### Fase 3: Ingestion, QC, dan Database (minggu 3)
- [ ] Subscriber MQTT, decode payload, simpan ke database
- [ ] Skema tabel: `measurements`, `nodes`, `qc_flags`, `alerts`
- [ ] Aturan QC:
  - Cek rentang fisik
  - Deteksi lonjakan (selisih antarpembacaan)
  - Deteksi sensor macet (varians nol)
  - Deteksi drift (tren menyimpang dari referensi)
  - Deteksi paket hilang dari counter
- [ ] Simpan flag QC terpisah, jangan hapus data mentah

**Output:** data tersimpan dan berlabel kualitas

### Fase 4: Analitik Ilmiah (minggu 4-5)
- [ ] Hitung **MMM** (rata-rata suhu bulan terpanas klimatologis) dari data historis lokasi
- [ ] Hitung **HotSpot** = suhu - MMM
- [ ] Hitung **DHW**: akumulasi HotSpot yang ≥ 1 °C selama jendela 12 minggu (satuan °C-minggu)
- [ ] Tetapkan tingkat peringatan (mengikuti pola NOAA CRW: Watch, Warning, Alert Level 1 dan 2)
- [ ] Indikator pendukung: pH rendah dan kekeruhan tinggi sebagai stres tambahan
- [ ] Deteksi anomali (z-score bergulir atau Isolation Forest)
- [ ] Forecasting jangka pendek (Prophet atau LSTM) dan bandingkan dengan baseline sederhana (persistence)
- [ ] Validasi DHW hitungan Anda terhadap produk DHW resmi NOAA CRW pada lokasi yang sama

**Output:** modul `analytics/` dengan unit test dan notebook validasi

### Fase 5: API dan Dashboard (minggu 5-6)
- [ ] Endpoint: data terbaru, riwayat, status node, DHW, alert
- [ ] Dashboard:
  - Grafik real-time per parameter
  - Peta lokasi pelampung virtual
  - Status baterai dan kualitas sinyal simulasi
  - Panel DHW dan level peringatan
  - Riwayat alert dan flag QC
- [ ] Alert ke Telegram atau email saat ambang terlampaui (dengan penekanan duplikasi)

**Output:** sistem end-to-end berjalan lewat `docker compose up`

### Fase 6: Evaluasi (minggu 7)

| Metrik | Cara ukur |
|---|---|
| Packet Delivery Ratio | Variasikan loss 5/10/20%, hitung paket diterima vs dikirim |
| Latensi pipeline | Waktu dari publish sampai tampil di dashboard |
| Presisi/recall QC | Suntikkan anomali berlabel, ukur deteksi |
| Lead time peringatan | Selisih waktu peringatan dengan kejadian ambang pemutihan pada data historis |
| Akurasi DHW | Bandingkan dengan DHW resmi NOAA CRW (MAE, korelasi) |
| Ketahanan | Uji node mati, broker restart, data terlambat |

- [ ] Uji skenario ekstrem: gelombang panas panjang, badai, sensor gagal bersamaan
- [ ] Anggaran energi **teoretis** (opsional): hitung konsumsi per siklus dari datasheet komponen, tanpa membeli hardware

### Fase 7: Dokumentasi dan Laporan (minggu 8)
- [ ] README dan panduan instalasi
- [ ] Diagram arsitektur
- [ ] Laporan metodologi dan hasil evaluasi
- [ ] Bagian **Keterbatasan** yang jujur (lihat bagian 7)
- [ ] Demo video atau live demo

## 6. Teknologi yang Disarankan

| Lapisan | Pilihan |
|---|---|
| Simulator | Python (numpy, paho-mqtt) |
| Broker | Mosquitto |
| Backend | FastAPI |
| Database | TimescaleDB (atau PostgreSQL biasa) |
| Analitik | pandas, scikit-learn, Prophet |
| Dashboard | React + TypeScript + Recharts/ECharts |
| Peta | Leaflet |
| Deploy | Docker Compose |
| Pengujian | pytest |

## 7. Keterbatasan yang Perlu Dinyatakan

- Data sensor adalah sintetis, jadi tidak ada klaim akurasi sensor, kedap air, biofouling, atau umur baterai.
- Model kehilangan paket adalah asumsi, bukan hasil ukur di lapangan.
- Validasi ilmiah bergantung pada data historis publik, bukan pengukuran sendiri.
- Hardware dan uji lapangan diposisikan sebagai **pekerjaan lanjutan** (suhu dulu, lalu pH, salinitas, kekeruhan).

## 8. Rencana Pengembangan Lanjutan

1. Prototipe suhu nyata (ESP32 + LoRa + sensor suhu waterproof)
2. Kalibrasi terhadap termometer referensi
3. Uji perairan dangkal
4. Penambahan sensor pH, salinitas (konduktivitas), dan kekeruhan

## 9. Ringkasan Timeline

| Minggu | Fokus |
|---|---|
| 1 | Spesifikasi dan payload |
| 2 | Simulator + MQTT |
| 3 | Ingestion, QC, database |
| 4-5 | Analitik DHW, anomali, forecasting |
| 5-6 | API dan dashboard |
| 7 | Evaluasi |
| 8 | Dokumentasi dan demo |

## 10. Kriteria Selesai

- [ ] `docker compose up` menjalankan seluruh sistem
- [ ] Simulator mengirim data dengan loss dan anomali terkontrol
- [ ] DHW hitungan cocok dengan NOAA CRW pada lokasi uji
- [ ] Alert terkirim saat ambang terlampaui
- [ ] Metrik evaluasi terdokumentasi
- [ ] Keterbatasan dituliskan
