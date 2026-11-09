// Uji enkoder C terhadap vektor yang sama dengan hardware/test_vectors.json.
// Jalankan: pio test -e native  (dari hardware/firmware/node)
#include <stdio.h>
#include <string.h>
#include <unity.h>
#include "segara_payload.h"

typedef struct {
  segara_reading_t r;
  const char *hex;
} vector_t;

static const vector_t VECTORS[] = {
  {{1,   0,     29.20f, 8.05f, 34.00f, 2.5f,   95},  "0100000b6803250d4800195f"},
  {{3,   65535, 31.87f, 7.92f, 33.45f, 12.3f,  47},  "03ffff0c7303180d11007b2f"},
  {{255, 1234,  19.50f, 8.50f, 37.00f, 100.0f, 0},   "ff04d2079e03520e7403e800"},
  {{2,   7,     -1.25f, 0.00f, 0.00f,  0.0f,   100}, "020007ff8300000000000064"},
};

void setUp(void) {}
void tearDown(void) {}

static void test_vectors_match_python_encoder(void) {
  for (size_t i = 0; i < sizeof(VECTORS) / sizeof(VECTORS[0]); i++) {
    uint8_t frame[SEGARA_PAYLOAD_SIZE];
    char hex[2 * SEGARA_PAYLOAD_SIZE + 1];
    segara_encode(&VECTORS[i].r, frame);
    for (int b = 0; b < SEGARA_PAYLOAD_SIZE; b++) sprintf(&hex[2 * b], "%02x", frame[b]);
    TEST_ASSERT_EQUAL_STRING(VECTORS[i].hex, hex);
  }
}

static void test_clamping(void) {
  segara_reading_t r = {9, 1, 400.0f, -1.0f, 1000.0f, 9999.0f, 150.0f};
  uint8_t f[SEGARA_PAYLOAD_SIZE];
  segara_encode(&r, f);
  TEST_ASSERT_EQUAL_HEX8(0x7F, f[3]);   // suhu dibatasi ke 32767
  TEST_ASSERT_EQUAL_HEX8(0xFF, f[4]);
  TEST_ASSERT_EQUAL_HEX8(0x00, f[5]);   // pH negatif -> 0
  TEST_ASSERT_EQUAL_HEX8(0x00, f[6]);
  TEST_ASSERT_EQUAL_UINT8(100, f[11]);  // baterai maks 100
}

int main(void) {
  UNITY_BEGIN();
  RUN_TEST(test_vectors_match_python_encoder);
  RUN_TEST(test_clamping);
  return UNITY_END();
}
