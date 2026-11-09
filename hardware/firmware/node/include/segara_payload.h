// Enkoder payload telemetri SEGARA, 12 byte, big-endian.
// Harus identik dengan simulator/encoder.py (struct ">BHhHHHB") dan docs/payload-spec.md.
// Header-only dan tanpa dependensi Arduino, agar bisa diuji di PC (pio test -e native).
#pragma once
#include <stdint.h>
#include <math.h>

#define SEGARA_PAYLOAD_SIZE 12

typedef struct {
  uint8_t  node_id;
  uint16_t counter;
  float    temperature;  // °C
  float    ph;
  float    salinity;     // PSU
  float    turbidity;    // NTU
  float    battery;      // %
} segara_reading_t;

static inline long segara_clamp(long v, long lo, long hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

// Pembulatan setara round() Python untuk nilai x.xx5 yang umum dipakai;
// lround() membulatkan menjauhi nol, Python membulatkan ke genap. Selisih hanya
// muncul tepat di titik tengah biner, yang praktis tidak terjadi pada float sensor.
static inline long segara_scale(float v, float k) {
  return lroundf(v * k);
}

static inline void segara_put_u16(uint8_t *p, uint16_t v) {
  p[0] = (uint8_t)(v >> 8);
  p[1] = (uint8_t)(v & 0xFF);
}

// Menulis tepat SEGARA_PAYLOAD_SIZE byte ke out.
static inline void segara_encode(const segara_reading_t *r, uint8_t out[SEGARA_PAYLOAD_SIZE]) {
  int16_t  suhu = (int16_t)segara_clamp(segara_scale(r->temperature, 100.0f), -32768, 32767);
  uint16_t ph   = (uint16_t)segara_clamp(segara_scale(r->ph, 100.0f), 0, 65535);
  uint16_t sal  = (uint16_t)segara_clamp(segara_scale(r->salinity, 100.0f), 0, 65535);
  uint16_t turb = (uint16_t)segara_clamp(segara_scale(r->turbidity, 10.0f), 0, 65535);
  uint8_t  bat  = (uint8_t)segara_clamp(lroundf(r->battery), 0, 100);

  out[0] = r->node_id;
  segara_put_u16(&out[1], r->counter);
  segara_put_u16(&out[3], (uint16_t)suhu);  // int16 dua-komplemen
  segara_put_u16(&out[5], ph);
  segara_put_u16(&out[7], sal);
  segara_put_u16(&out[9], turb);
  out[11] = bat;
}
