// Gateway SEGARA (draft prototipe): terima frame LoRa 12 byte, teruskan apa adanya
// ke MQTT topik segara/telemetry/{node_id} (format yang sudah dibaca ingestion/subscriber.py).
// Kualitas link (RSSI/SNR) dikirim terpisah ke segara/gateway/link/{node_id} sebagai JSON;
// ingestion hanya berlangganan segara/telemetry/+, jadi topik ini tidak mengganggu pipeline.
#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <PubSubClient.h>

#include "secrets.h"

// Pin LoRa TTGO LoRa32 v2.1 (SX1276)
#define PIN_LORA_SCK   5
#define PIN_LORA_MISO  19
#define PIN_LORA_MOSI  27
#define PIN_LORA_NSS   18
#define PIN_LORA_RST   23
#define PIN_LORA_DIO0  26

// Harus sama dengan node (hardware/firmware/node/include/config.h)
#define LORA_FREQ_HZ   922000000L
#define LORA_SF        9
#define LORA_BW_HZ     125000L
#define LORA_CR_DENOM  5
#define LORA_SYNC_WORD 0x5E

#define FRAME_SIZE     12
#define NODE_ID_MIN    10   // tolak ID simulator (1-5) agar data fisik & sintetis tidak tercampur
#define NODE_ID_MAX    49

static WiFiClient net;
static PubSubClient mqtt(net);
static uint32_t rxOk = 0, rxRejected = 0;

static void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[GW] Wi-Fi");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(250);
    Serial.print('.');
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " ok" : " gagal");
}

static void ensureMqtt() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  String id = "segara-gw-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  bool ok = strlen(MQTT_USER) ? mqtt.connect(id.c_str(), MQTT_USER, MQTT_PASSWORD)
                              : mqtt.connect(id.c_str());
  Serial.printf("[GW] MQTT %s:%d %s\n", MQTT_HOST, MQTT_PORT, ok ? "ok" : "gagal");
}

void setup() {
  Serial.begin(115200);
  SPI.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_NSS);
  LoRa.setPins(PIN_LORA_NSS, PIN_LORA_RST, PIN_LORA_DIO0);
  while (!LoRa.begin(LORA_FREQ_HZ)) {
    Serial.println("[GW] radio LoRa tidak terdeteksi, coba lagi");
    delay(2000);
  }
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW_HZ);
  LoRa.setCodingRate4(LORA_CR_DENOM);
  LoRa.setSyncWord(LORA_SYNC_WORD);
  LoRa.enableCrc();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  ensureWifi();
  ensureMqtt();
  Serial.println("[GW] siap menerima");
}

void loop() {
  static uint32_t lastCheck = 0;
  if (millis() - lastCheck > 5000) {  // cek ulang koneksi tanpa memblokir penerimaan
    lastCheck = millis();
    ensureWifi();
    ensureMqtt();
  }
  mqtt.loop();

  int len = LoRa.parsePacket();
  if (len == 0) return;

  uint8_t frame[FRAME_SIZE];
  int rssi = LoRa.packetRssi();
  float snr = LoRa.packetSnr();

  if (len != FRAME_SIZE) {
    while (LoRa.available()) LoRa.read();
    rxRejected++;
    Serial.printf("[GW] tolak: panjang %d byte\n", len);
    return;
  }
  for (int i = 0; i < FRAME_SIZE; i++) frame[i] = LoRa.read();

  uint8_t nodeId = frame[0];
  if (nodeId < NODE_ID_MIN || nodeId > NODE_ID_MAX) {
    rxRejected++;
    Serial.printf("[GW] tolak: node_id %u di luar rentang\n", nodeId);
    return;
  }
  uint16_t counter = ((uint16_t)frame[1] << 8) | frame[2];
  rxOk++;

  char topic[40];
  snprintf(topic, sizeof(topic), "segara/telemetry/%u", nodeId);
  bool pubOk = mqtt.publish(topic, frame, FRAME_SIZE, false);  // QoS 0, tanpa retain

  char linkTopic[40], json[160];
  snprintf(linkTopic, sizeof(linkTopic), "segara/gateway/link/%u", nodeId);
  snprintf(json, sizeof(json),
           "{\"node_id\":%u,\"counter\":%u,\"rssi\":%d,\"snr\":%.1f,\"rx_ok\":%lu,\"rx_rejected\":%lu}",
           nodeId, counter, rssi, snr, (unsigned long)rxOk, (unsigned long)rxRejected);
  mqtt.publish(linkTopic, json);

  // Tanpa buffer: bila MQTT putus, paket ini hilang dan terdeteksi sebagai PACKET_LOSS
  // oleh QC. Buffer di flash adalah perbaikan lanjutan.
  Serial.printf("[GW] node=%u ctr=%u rssi=%d snr=%.1f mqtt=%s\n",
                nodeId, counter, rssi, snr, pubOk ? "ok" : "gagal");
}
