# Spesifikasi Protokol & Payload Telemetri Biner SEGARA

Dokumen ini mendefinisikan spesifikasi format payload biner kompak untuk pelampung pemantauan terumbu karang virtual pada sistem SEGARA (Sistem Early-warning Gangguan termal Atas terumbu kaRAng).

Format ini dirancang untuk meminimalkan konsumsi energi dan bandwidth transmisi nirkabel (meniru batasan paket radio LoRaWAN / Satelit IoT) dengan panjang tetap **12 byte**.

---

## 1. Parameter dan Rentang Fisik

| Parameter | Rentang Fisik Valid | Resolusi | Satuan | Deskripsi |
|---|---|---|---|---|
| Suhu Air Laut (SST) | 20.00 – 35.00 | 0.01 | °C | Parameter utama stres termal terumbu karang |
| pH Air Laut | 7.50 – 8.50 | 0.01 | - | Indikator keasaman / asidifikasi laut |
| Salinitas | 30.00 – 37.00 | 0.01 | PSU | Kestabilan osmolaritas ekosistem karang |
| Kekeruhan (*Turbidity*) | 0.0 – 100.0 | 0.1 | NTU | Penetrasi cahaya fotosintesis zooxanthellae |
| Baterai | 0 – 100 | 1 | % | Level daya sistem pelampung (*buoy*) |

---

## 2. Struktur Frame Biner (12 Byte)

Semua bilangan multi-byte dikodekan dalam representasi **Big-Endian** (*Network Byte Order*).

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Node ID    |         Sequence Counter      |   Suhu (x100) |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Suhu (cont.) |           pH (x100)           |Salinitas(x100)|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|Salinitas(cont)|      Kekeruhan (x10)          |  Baterai (%)  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Tabel Rincian Field

| Offset (Byte) | Field | Tipe Data | Faktor Skala | Rentang Terbaca | Rentang Mentah Biner | Keterangan |
|---|---|---|---|---|---|---|
| `0` | `node_id` | `uint8` | 1 | 1 – 255 | `0x01` – `0xFF` | Identifier unik unit pelampung |
| `1 – 2` | `counter` | `uint16` (BE) | 1 | 0 – 65,535 | `0x0000` – `0xFFFF` | Penghitung sekuens paket (*loss detection*) |
| `3 – 4` | `suhu` | `int16` (BE) | 0.01 | -327.68 – +327.67 °C | Nilai × 100 | Suhu permukaan laut bertanda |
| `5 – 6` | `ph` | `uint16` (BE) | 0.01 | 0.00 – 655.35 | Nilai × 100 | Derajat keasaman |
| `7 – 8` | `salinitas` | `uint16` (BE) | 0.01 | 0.00 – 655.35 PSU | Nilai × 100 | Salinitas praktis |
| `9 – 10` | `kekeruhan`| `uint16` (BE) | 0.1 | 0.0 – 6553.5 NTU | Nilai × 10 | Kekeruhan air |
| `11` | `baterai` | `uint8` | 1 | 0 – 100 % | `0x00` – `0x64` | Status kapasitas baterai |

---

## 3. Format Enkapsulasi & Decoding (Python Struct)

Format struct Python: `>BHhhHHB`
- `>`: Big-Endian
- `B`: uint8 (1 byte)
- `H`: uint16 (2 byte)
- `h`: int16 (2 byte)
- `H`: uint16 (2 byte)
- `H`: uint16 (2 byte)
- `H`: uint16 (2 byte)
- `B`: uint8 (1 byte)

Total ukuran: $1 + 2 + 2 + 2 + 2 + 2 + 1 = 12$ byte.

### Formula Dekode:
$$\text{suhu} = \frac{\text{raw\_suhu}}{100.0} \quad (^\circ\text{C})$$
$$\text{pH} = \frac{\text{raw\_ph}}{100.0}$$
$$\text{salinitas} = \frac{\text{raw\_salinitas}}{100.0} \quad (\text{PSU})$$
$$\text{kekeruhan} = \frac{\text{raw\_kekeruhan}}{10.0} \quad (\text{NTU})$$
$$\text{baterai} = \text{raw\_baterai} \quad (\%)$$

---

## 4. Topik MQTT

Format topik publikasi:
```
segara/telemetry/{node_id}
```
Contoh:
- `segara/telemetry/1` untuk Node 1 (Taman Nasional Bunaken)
- `segara/telemetry/2` untuk Node 2 (Kepulauan Raja Ampat)
- `segara/telemetry/3` untuk Node 3 (Taman Nasional Wakatobi)
- `segara/telemetry/4` untuk Node 4 (Kepulauan Karimunjawa)
- `segara/telemetry/5` untuk Node 5 (Taman Nasional Komodo)

QoS yang digunakan: **QoS 0** (meniru transmisi radio LoRaWAN *unconfirmed uplink* untuk menguji ketahanan pipeline terhadap *packet loss*).
