// Salin menjadi secrets.h (sudah di-.gitignore) lalu isi.
#pragma once
#define WIFI_SSID      "nama-wifi"
#define WIFI_PASSWORD  "kata-sandi-wifi"
#define MQTT_HOST      "192.168.1.10"   // IP komputer yang menjalankan Mosquitto
#define MQTT_PORT      1883
#define MQTT_USER      ""               // kosong = anonim (sesuai infra/mosquitto.conf saat ini)
#define MQTT_PASSWORD  ""
