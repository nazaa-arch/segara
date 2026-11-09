// Konfigurasi node pelampung SEGARA. Sesuaikan sebelum flashing.
#pragma once

// ---------- Identitas & jadwal ----------
#define NODE_ID              10        // 1-5 dipakai simulator; prototipe fisik mulai dari 10
#define CYCLE_SECONDS        (6UL * 3600UL)  // HARUS sama dengan cycle_hours di ingestion (6 jam)
#define DEBUG_CYCLE_SECONDS  60UL      // dipakai bila DEBUG_FAST_CYCLE = 1 (uji meja saja)
#define DEBUG_FAST_CYCLE     0

// ---------- Sensor terpasang (fase bertahap) ----------
// Sensor yang belum terpasang dikirim bernilai 0 -> QC menandai RANGE_FAIL untuk
// parameter itu saja; suhu tetap dipakai DHW (QC per parameter).
#define HAS_DS18B20          1   // Fase 1: suhu
#define HAS_EZO_PH           0   // Fase 3: Atlas Scientific EZO-pH (I2C 0x63)
#define HAS_EZO_EC           0   // Fase 3: Atlas Scientific EZO-EC, keluaran salinitas PSU (I2C 0x64)
#define HAS_TURBIDITY        0   // Fase 3: sensor kekeruhan analog

// ---------- Pin (ESP32 DevKit / FireBeetle ESP32) ----------
#define PIN_ONEWIRE          4
#define PIN_SENSOR_PWR       25   // HIGH = rel sensor menyala (via load switch / P-MOSFET)
#define PIN_BATT_ADC         35   // pembagi 470k/470k + 100 nF ke GND (arus bocor ~4 µA)
#define PIN_TURB_ADC         34   // keluaran sensor 0-4,5 V lewat pembagi ke <= 3,3 V
#define PIN_I2C_SDA          21
#define PIN_I2C_SCL          22

#define PIN_LORA_SCK         18
#define PIN_LORA_MISO        19
#define PIN_LORA_MOSI        23
#define PIN_LORA_NSS         5
#define PIN_LORA_RST         14
#define PIN_LORA_DIO0        26

// ---------- Radio LoRa (point-to-point ke gateway) ----------
// Indonesia: pita 920-923 MHz. Periksa batas daya terbaru dari regulator sebelum uji lapangan.
#define LORA_FREQ_HZ         922000000L
#define LORA_SF              9
#define LORA_BW_HZ           125000L
#define LORA_CR_DENOM        5          // 4/5
#define LORA_TX_DBM          14
#define LORA_SYNC_WORD       0x5E       // harus sama dengan gateway; bukan 0x34 (LoRaWAN publik)

// ---------- Baterai & kalibrasi ----------
#define BATT_DIVIDER_RATIO   2.0f       // (R1+R2)/R2
#define BATT_V_EMPTY         3.30f      // Li-ion 18650; LiFePO4: 2.90
#define BATT_V_FULL          4.15f      // Li-ion 18650; LiFePO4: 3.45

// Koreksi suhu dari kalibrasi terhadap termometer referensi: T = a*T_raw + b
#define TEMP_CAL_A           1.000f
#define TEMP_CAL_B           0.000f

// Kekeruhan: NTU = a*V + b (linier, dari kalibrasi larutan formazin/standar).
// Nilai default hanya placeholder dan TIDAK valid untuk pengukuran.
#define TURB_CAL_A           -40.0f
#define TURB_CAL_B           170.0f
#define TURB_DIVIDER_RATIO   1.5f       // pembagi 10k/20k: 4,5 V -> 3,0 V di pin ADC

#define SENSOR_WARMUP_MS     1500       // stabilisasi setelah rel sensor dinyalakan
