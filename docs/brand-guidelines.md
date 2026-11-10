# Panduan Merek SEGARA

Sumber visual: [Logo/SEGARA Brand Guideline Board.png](../Logo/SEGARA%20Brand%20Guideline%20Board.png).
Berkas logo: [Logo/SEGARA Logo Utama.png](../Logo/SEGARA%20Logo%20Utama.png) (logo dengan teks) dan
[Logo/SEGARA Logo Emblem.png](../Logo/SEGARA%20Logo%20Emblem.png) (emblem saja), keduanya berlatar transparan.

## Logo utama

Emblem lingkaran berisi ombak, terumbu karang, dan matahari oranye, dipasangkan dengan teks **SEGARA**
dan subjudul *Sistem Early-warning Gangguan Termal Atas Terumbu KaRAng*.

| Elemen | Makna |
|---|---|
| Ombak | Dinamika laut dan pergerakan data yang terus dipantau secara real-time |
| Terumbu karang | Ekosistem yang dijaga dan menjadi fokus utama sistem peringatan dini |
| Matahari / titik panas | Deteksi dini terhadap kenaikan suhu dan gangguan termal di laut |
| Bentuk lingkaran | Kesatuan, keberlanjutan, dan siklus ekosistem laut yang saling terhubung |

## Variasi logo

- Logo utama (vertikal), warna penuh
- Logo horizontal, warna penuh
- Logo monokrom satu warna, versi gelap (di latar terang)
- Logo monokrom satu warna, versi putih (di latar navy)

## Palet warna

| Peran | Nama | Hex |
|---|---|---|
| Utama | Navy | `#0B2A44` |
| Sekunder | Blue | `#0756A5` |
| Aksen | Cyan | `#0798D5` |
| Aksen | Orange | `#FF8A1F` |
| Aksen | Coral | `#EB505B` |
| Highlight | Yellow | `#FFD84D` |

Dashboard memakai palet ini lewat `dashboard/tailwind.config.js` (objek `brand`). Skala Tailwind
`coral` dan `orange` diturunkan dari Coral dan Orange di atas; Aqua `#45C5E8` dan netral `#F5F8FC`
dipertahankan sebagai warna pendukung.

## Tipografi

| Penggunaan | Huruf |
|---|---|
| Judul dan logo | Montserrat ExtraBold |
| Subjudul | Montserrat SemiBold |
| Teks isi | Montserrat Regular |

Gaya huruf: modern, bersih, mudah dibaca, profesional. Dashboard memuat Montserrat dari paket
`@fontsource/montserrat` (bobot 300 sampai 800), tanpa CDN.

## Penggunaan logo

- **Ruang kosong:** beri jarak bebas minimal setinggi huruf "S" di setiap sisi logo.
- **Ukuran minimal:** cetak lebar 2 cm, digital lebar 120 px.
- **Benar:** pada latar terang, pada latar gelap (navy) dengan versi putih, dan dengan ruang kosong yang cukup.
- **Salah:** meregangkan proporsi, mengubah warna logo, menambahkan efek bayangan, memiringkan logo,
  menempatkan di latar yang ramai, dan memakai kontras rendah.

## Aset di dashboard

Ikon aplikasi dan favicon di `dashboard/public/brand/` dibuat dari emblem pada latar putih bersudut membulat
(`segara-icon-512.png`, `segara-icon-192.png`, `apple-touch-icon.png`, `favicon-64.png`, `favicon-32.png`).
Emblem diambil dari papan guideline beresolusi 1536×1024, sehingga ikon 512 px terlihat sedikit lembut.
Untuk hasil tajam, ganti dengan berkas logo asli (vektor atau PNG resolusi tinggi).
