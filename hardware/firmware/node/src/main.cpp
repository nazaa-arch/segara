// Firmware node pelampung SEGARA (draft prototipe).
// Siklus: bangun -> nyalakan sensor -> ukur -> kirim 12 byte via LoRa -> deep sleep.
// Seluruh logika berjalan di setup(); loop() tidak pernah tercapai.
#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <LoRa.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Preferences.h>
#include <driver/gpio.h>
#include <esp_sleep.h>

#include "config.h"
#include "segara_payload.h"

static OneWire oneWire(PIN_ONEWIRE);
static DallasTemperature ds18b20(&oneWire);
static Preferences prefs;

// ---------- Sensor ----------

static float readTemperature() {
#if HAS_DS18B20
  ds18b20.begin();
  ds18b20.setResolution(12);           // 0,0625 °C, konversi ~750 ms
  ds18b20.requestTemperatures();
  float t = ds18b20.getTempCByIndex(0);
  if (t == DEVICE_DISCONNECTED_C) {
    // -127 °C dikirim apa adanya: QC menandai RANGE_FAIL, bukan dianggap valid.
    return t;
  }
  return TEMP_CAL_A * t + TEMP_CAL_B;
#else
  return 0.0f;
#endif
}

// Protokol I2C Atlas Scientific EZO: tulis perintah ASCII, tunggu, baca
// [kode status][teks ASCII diakhiri NUL]. Kode 1 = sukses.
static bool ezoQuery(uint8_t addr, const char *cmd, uint16_t waitMs, float *out) {
  Wire.beginTransmission(addr);
  Wire.write((const uint8_t *)cmd, strlen(cmd));
  if (Wire.endTransmission() != 0) return false;
  delay(waitMs);

  Wire.requestFrom(addr, (uint8_t)32);
  if (!Wire.available()) return false;
  uint8_t code = Wire.read();
  char buf[32] = {0};
  uint8_t i = 0;
  while (Wire.available() && i < sizeof(buf) - 1) {
    char c = Wire.read();
    if (c == 0) break;
    buf[i++] = c;
  }
  if (code != 1) return false;
  if (out) *out = atof(buf);
  return true;
}

static float readPh(float tempC) {
#if HAS_EZO_PH
  char cmd[16];
  snprintf(cmd, sizeof(cmd), "RT,%.2f", tempC);  // baca dengan kompensasi suhu
  float v;
  return ezoQuery(0x63, cmd, 1000, &v) ? v : 0.0f;
#else
  (void)tempC;
  return 0.0f;
#endif
}

static void configureEc() {
#if HAS_EZO_EC
  // Hanya keluarkan salinitas (PSU). Setelan tersimpan di EZO, cukup sekali per cold boot.
  ezoQuery(0x64, "O,EC,0", 300, nullptr);
  ezoQuery(0x64, "O,TDS,0", 300, nullptr);
  ezoQuery(0x64, "O,SG,0", 300, nullptr);
  ezoQuery(0x64, "O,S,1", 300, nullptr);
#endif
}

static float readSalinity(float tempC) {
#if HAS_EZO_EC
  char cmd[16];
  snprintf(cmd, sizeof(cmd), "RT,%.2f", tempC);
  float v;
  return ezoQuery(0x64, cmd, 1000, &v) ? v : 0.0f;
#else
  (void)tempC;
  return 0.0f;
#endif
}

static float readTurbidity() {
#if HAS_TURBIDITY
  uint32_t sum = 0;
  for (int i = 0; i < 32; i++) {
    sum += analogReadMilliVolts(PIN_TURB_ADC);
    delay(5);
  }
  float v = (sum / 32.0f) / 1000.0f * TURB_DIVIDER_RATIO;
  float ntu = TURB_CAL_A * v + TURB_CAL_B;
  return ntu < 0 ? 0 : ntu;
#else
  return 0.0f;
#endif
}

static float readBatteryPercent() {
  uint32_t sum = 0;
  for (int i = 0; i < 16; i++) sum += analogReadMilliVolts(PIN_BATT_ADC);
  float v = (sum / 16.0f) / 1000.0f * BATT_DIVIDER_RATIO;
  float pct = (v - BATT_V_EMPTY) / (BATT_V_FULL - BATT_V_EMPTY) * 100.0f;
  return constrain(pct, 0.0f, 100.0f);
}

// ---------- Daya & radio ----------

static void sensorPower(bool on) {
  gpio_hold_dis((gpio_num_t)PIN_SENSOR_PWR);
  pinMode(PIN_SENSOR_PWR, OUTPUT);
  digitalWrite(PIN_SENSOR_PWR, on ? HIGH : LOW);
}

static bool loraBegin() {
  SPI.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_NSS);
  LoRa.setPins(PIN_LORA_NSS, PIN_LORA_RST, PIN_LORA_DIO0);
  if (!LoRa.begin(LORA_FREQ_HZ)) return false;
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW_HZ);
  LoRa.setCodingRate4(LORA_CR_DENOM);
  LoRa.setTxPower(LORA_TX_DBM);
  LoRa.setSyncWord(LORA_SYNC_WORD);
  LoRa.enableCrc();
  return true;
}

static void goToSleep(uint32_t awakeMs) {
  LoRa.sleep();
  sensorPower(false);
  gpio_hold_en((gpio_num_t)PIN_SENSOR_PWR);  // tahan LOW selama deep sleep
  gpio_deep_sleep_hold_en();

  uint64_t cycleUs = (uint64_t)(DEBUG_FAST_CYCLE ? DEBUG_CYCLE_SECONDS : CYCLE_SECONDS) * 1000000ULL;
  uint64_t awakeUs = (uint64_t)awakeMs * 1000ULL;
  uint64_t sleepUs = cycleUs > awakeUs ? cycleUs - awakeUs : cycleUs;
  esp_sleep_enable_timer_wakeup(sleepUs);
  Serial.flush();
  esp_deep_sleep_start();
}

void setup() {
  uint32_t t0 = millis();
  Serial.begin(115200);
  bool coldBoot = esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TIMER;

  // Counter disimpan di NVS agar berlanjut setelah baterai habis / reset.
  // 4 tulis per hari -> keausan flash dapat diabaikan.
  prefs.begin("segara", false);
  uint16_t counter = prefs.getUShort("counter", 0);

  sensorPower(true);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  delay(SENSOR_WARMUP_MS);
  if (coldBoot) configureEc();

  segara_reading_t r;
  r.node_id     = NODE_ID;
  r.counter     = counter;
  r.temperature = readTemperature();
  float tComp   = (r.temperature > 0 && r.temperature < 40) ? r.temperature : 25.0f;
  r.ph          = readPh(tComp);
  r.salinity    = readSalinity(tComp);
  r.turbidity   = readTurbidity();
  r.battery     = readBatteryPercent();
  sensorPower(false);  // matikan sensor sebelum TX, kurangi derau & arus puncak

  uint8_t frame[SEGARA_PAYLOAD_SIZE];
  segara_encode(&r, frame);

  Serial.printf("[SEGARA] node=%u ctr=%u T=%.2f pH=%.2f S=%.2f NTU=%.1f bat=%.0f%%\n",
                r.node_id, r.counter, r.temperature, r.ph, r.salinity, r.turbidity, r.battery);

  if (loraBegin()) {
    LoRa.beginPacket();
    LoRa.write(frame, sizeof(frame));
    bool ok = LoRa.endPacket() == 1;  // blocking sampai TX selesai
    Serial.printf("[SEGARA] TX %s\n", ok ? "ok" : "gagal");
  } else {
    Serial.println("[SEGARA] radio LoRa tidak terdeteksi");
  }

  // Counter tetap maju walau TX gagal: pipeline membaca selisih sebagai paket hilang
  // dan tetap memajukan jam observasi 6 jam per langkah.
  prefs.putUShort("counter", (uint16_t)(counter + 1));
  prefs.end();

  goToSleep(millis() - t0);
}

void loop() {}
