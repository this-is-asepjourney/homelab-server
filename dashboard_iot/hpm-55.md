/* =========================================================================
 *  PROJECT   : HEAT PRESS HPM-55 - IoT Monitoring
 *  BOARD     : LilyGO T-Display (ESP32 Dev V1) - external OLED SSD1306 dipakai
 *  IDE       : VS Code + PlatformIO
 *  VERSION   : HPM55-0006
 *
 *  ALUR SESUAI DIAGRAM KONSEP:
 *   - COUNTING    : HPM-55 (AC 220VAC, tombol tekan mesin)
 *                   -> Relay Omron MY4N-GS 220/240VAC (coil Pin13=A1,Pin14=A2)
 *                   -> kontak NO (Pin9=COM, Pin5=NO) -> resistor 10kOhm
 *                   -> ESP32 GPIO32 (PIN_COUNT), dibaca via POLLING di loop()
 *   - TEMPERATURE : HPM-55 -> Sensor MAX6675 (Calculating Temperature)
 *                   -> ESP32 (software SPI)
 *   - POWER       : Adaptor (Power Supply) -> ESP32
 *   - OUTPUT      : ESP32 -> Display (OLED: counting, MQTT, WiFi, jam, suhu)
 *                   ESP32 -> Send Data -> MQTT -> Node-RED -> DGS PKIGB2 -> PK MES
 *
 *  ARSITEKTUR TASK:
 *   - Core 0 : wifiTask  - hanya WiFi connect/reconnect + MQTT maintain
 *   - Core 1 : loop()    - semua logic: counting, sensor, display, publish
 *     (Seluruh akses mqtt client dari 1 core -> tidak ada race condition)
 *
 *  TOPIC MQTT:
 *   /SysCtrl          -> status device  (LWT: OFF, publish ON saat connect,
 *                        heartbeat ON tiap 60 detik)
 *   /Event/Cnt        -> 1 siklus press terhitung (langsung saat ditekan)
 *   /Event/Handling   -> heartbeat tiap 60 detik, nilai statis (tanpa trigger)
 *   /Event/Mchn_time  -> runtime mesin (tiap 60 detik)
 *   /Event/Teaching   -> parameter urutan (Stitch/Trigger/Delay), dikirim
 *                        sekali tiap kali MQTT baru connect (power on / reconnect)
 *   /Heatpress        -> PV vs SV suhu (tiap 5 detik)
 *
 *  =====================================================================
 *  PERUBAHAN v0006 - PERBAIKAN COUNTING (fix delay & dobel hitung)
 *  =====================================================================
 *  MASALAH DI LAPANGAN (v0005):
 *   - Counting kadang delay / tidak realtime
 *   - Counting kadang menghitung 2x untuk 1x penekanan tombol
 *
 *  PENYEBAB:
 *   [1] Debounce lama berbasis ISR CHANGE + cek waktu terhadap EDGE
 *       SEBELUMNYA saja ("now - v_lastEdgeMs < DEBOUNCE_MS"). Ini TIDAK
 *       memverifikasi level pin benar-benar stabil, cuma menahan interrupt
 *       yang terlalu rapat dengan interrupt sebelumnya. Kontak mekanik
 *       relay Omron MY4N-GS bisa "bouncing" (nyambung-putus-nyambung)
 *       dalam rentang waktu yang kadang > DEBOUNCE_MS -> tiap bounce yang
 *       lolos jeda waktu dianggap transisi baru yang valid -> DOBEL HITUNG.
 *   [2] DEBOUNCE_MS di v0005 nilainya 100 walau komentar bilang sudah
 *       dinaikkan ke 500 (tidak sinkron dengan kode aktual).
 *   [3] Tidak ada filter hardware (RC) di jalur sinyal -> noise dari
 *       switching relay AC 220VAC bisa ikut terbaca sebagai transisi.
 *
 *  PERBAIKAN (v0006):
 *   [1] Counting logic diubah total: dari ISR "baca sekali langsung putus"
 *       menjadi POLLING DEBOUNCE di loop() (fungsi pollCounting()).
 *       Prinsip: level baru dianggap SAH hanya kalau bertahan stabil
 *       selama >= DEBOUNCE_MS tanpa berubah lagi. Ini standar debounce
 *       paling tahan noise/bouncing untuk kontak mekanik.
 *   [2] ISR dihapus sepenuhnya untuk PIN_COUNT. Tidak perlu lagi karena
 *       loop() berjalan puluhan-ratusan kali per detik (jauh lebih cepat
 *       dari durasi 1 siklus press mesin heat press yang hitungan detik),
 *       jadi polling di loop() cukup responsif dan lebih sederhana/aman
 *       (tidak perlu portENTER/EXIT_CRITICAL untuk pin ini lagi).
 *   [3] DEBOUNCE_MS dinaikkan ke 50ms (cukup meredam bouncing relay
 *       mekanik tanpa terasa delay untuk siklus heat press yang berjarak
 *       detik-menit).
 *   [4] curCycle tetap naik SAAT DITEKAN (falling, sesuai requirement
 *       "langsung output 1 saat ditekan" dari versi sebelumnya), tapi kini
 *       lewat konfirmasi debounce -> tidak akan dobel karena bouncing.
 *   [5] actTimeSec kini dihitung dari durasi aktual (v_pressStartMs s/d
 *       release yang terkonfirmasi), tidak lagi selalu 0 seperti di v0005
 *       (bug lama: durMs di-set 0 di titik increment, sehingga
 *       actTimeSec += durMs/1000 tidak pernah bertambah).
 *   [6] REKOMENDASI HARDWARE (opsional tapi disarankan): tambahkan
 *       kapasitor keramik 100nF (0.1uF) dari GPIO32 ke GND, membentuk
 *       filter RC low-pass bersama resistor 10kOhm yang sudah ada.
 *       Ini meredam noise/bouncing di sisi elektrik SEBELUM sampai ke
 *       ESP32, melengkapi debounce software di atas.
 *
 *  PERUBAHAN v0005 (relay 5V module -> Omron MY4N-GS 220/240VAC):
 *   [1] Material relay diganti dari "Relay Module 5V" ke relay industrial
 *       Omron MY4N-GS 220/240VAC yang dipasang di socket PYF14A.
 *       Relay dikontrol langsung oleh sinyal AC 220VAC dari tombol
 *       internal HPM-55 (coil Pin13=A1, Pin14=A2 dihubungkan ke 220VAC
 *       dari mesin).
 *   [2] Wiring kontak relay ke ESP32:
 *       - Gunakan Pole 1 saja: Pin9=COM, Pin5=NO (Normally Open)
 *       - Pin9(COM) -> GND ESP32 (WAJIB, common ground)
 *       - Pin5(NO)  -> resistor 10kOhm -> GPIO32 (PIN_COUNT)
 *       - GPIO32 dikonfigurasi INPUT_PULLUP (internal pullup 3.3V)
 *       - Relay OFF (tombol tidak ditekan): NO terbuka -> GPIO32 HIGH
 *       - Relay ON  (tombol ditekan):       NO menutup -> GPIO32 LOW
 *   [3] Isolasi galvanik: MY4N-GS memisahkan sisi AC 220VAC (HPM-55)
 *       dari sisi DC 3.3V (ESP32) secara aman.
 *
 *  PERUBAHAN v0004 (sebelumnya):
 *   [1] FIX BUG saveCounters() nama variabel NVS salah ketik.
 *   [2] Hapus simulasi press cycle (kini murni dari hardware).
 *   [3] Hapus fallback suhu simulasi (NAN apa adanya).
 *
 *  MASIH TODO:
 *   - SV (setTemperature) masih konstanta, belum bisa diubah dari luar
 *     lewat MQTT subscribe
 *   - MCID & PROCESS_ID masih placeholder "-" / "0-0", isi manual sesuai
 *     ID mesin sebenarnya sebelum deploy
 * ========================================================================= */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 64 // OLED display height, in pixels
#define OLED_RESET    -1 // Reset pin # (or -1 if sharing Arduino reset pin)
#include <time.h>
#include <NTPClient.h>
#include <WiFiUdp.h>

// ============================================================
//  KONFIGURASI - Sesuaikan di sini
// ============================================================

// ---- WiFi ----
const char* WIFI_SSID = "Alamak";
const char* WIFI_PASS = "20251173";

// ---- MQTT Broker ----
const char* MQTT_SERVER = "10.109.25.10";
const int   MQTT_PORT   = 1883;

const char* MQTT_SERVER2 = "10.109.25.97";
const int   MQTT_PORT2   = 1883;

// ---- Topic MQTT (sesuai spek atasan) ----
const char* TOPIC_SYSCTRL   = "/SysCtrl";
const char* TOPIC_EVENT_CNT = "/Event/Cnt";
const char* TOPIC_HANDLING  = "/Event/Handling";
const char* TOPIC_MCHN_TIME = "/Event/Mchn_time";
const char* TOPIC_HEATPRESS = "/Heatpress";
const char* TOPIC_TEACHING  = "/Event/Teaching";

// ---- Identitas mesin ----
const char* IOT_SPPL_CD = "SSFT";
const char* IOT_MODEL   = "HPM-55";
const char* MCID        = "-";   // TODO: ID mesin ini
const char* FW_VER      = "HPM55-0001";
const char* PROCESS_ID  = "0-0";         // TODO: sesuaikan format

// ---- Target suhu SV (bisa dibuat dinamis via MQTT subscribe nanti) ----
int setTemperature = 50;

// ---- Parameter /Event/Teaching (dikirim sekali tiap MQTT connect) ----
// TODO: ganti dengan nilai aktual sesuai SOP/parameter mesin sebenarnya
const int TEACH_STI_VALUE = 1;   // Stitch
const int TEACH_TRI_VALUE = 2;   // Trigger
const int TEACH_DLY_VALUE = 3;   // Delay

// ---- UID NFC Tag ----
// HPM-55 tidak memiliki NFC reader -> kirim string kosong
const char* NFC_UID = "";

// ---- Pin LED indikator status ----
// CATATAN: Pin 21 (SDA) dan 22 (SCL) dipakai OLED I2C!
#define PIN_LED_R  33
#define PIN_LED_G  15
#define PIN_LED_B  12

// ---- Pin MAX6675 (software SPI) ----
#define PIN_MAX_SCK  25
#define PIN_MAX_CS   26
#define PIN_MAX_SO   27

// ---- Pin Counting: kontak NO relay Omron MY4N-GS masuk ke sini ----
// Diagram: HPM-55 (220VAC) -> MY4N-GS coil (Pin13/14) -> kontak NO (Pin5,
//          Pin9=COM ke GND ESP32) -> resistor 10kOhm -> GPIO32 (PIN_COUNT)
// INPUT_PULLUP: HIGH = idle (NO terbuka), LOW = ditekan (NO menutup ke GND)
// REKOMENDASI: tambahkan kapasitor 100nF dari GPIO32 ke GND untuk filter
// RC tambahan yang meredam noise/bouncing relay secara elektrik.
#define PIN_COUNT    32

// ---- Interval (ms) ----
const uint32_t INTERVAL_TEMP_READ    = 2000;   // baca MAX6675
const uint32_t INTERVAL_HEATPRESS    = 5000;   // publish /Heatpress
const uint32_t INTERVAL_MCHN_TIME    = 500000; // publish /Mchn_time (+save NVS)
const uint32_t INTERVAL_HANDLING     = 60000;  // publish /Event/Handling
const uint32_t INTERVAL_SYSCTRL      = 60000;  // publish /SysCtrl periodik
const uint32_t INTERVAL_CLOCK_UPDATE = 500;    // refresh jam di OLED

// ---- Debounce counting (POLLING, lihat pollCounting()) ----
// Waktu minimal level GPIO32 harus stabil sebelum dianggap transisi sah.
// 50ms cukup meredam bouncing kontak mekanik relay & tidak terasa delay
// untuk siklus heat press yang jaraknya hitungan detik.
const uint32_t COUNT_DEBOUNCE_MS     = 50;

// ---- Handling time statis (sesuai SOP pabrik: 60 detik) ----
const uint32_t HANDLING_TIME_SEC     = 60;

// ============================================================
//  OBJEK GLOBAL
// ============================================================

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
WiFiUDP      ntpUDP;
NTPClient    ntpClient(ntpUDP, "time.windows.com", 7 * 3600, 60000);
Preferences  nvs;
WiFiClient   tcpClient;
PubSubClient mqtt(tcpClient);

WiFiClient   tcpClient2;
PubSubClient mqtt2(tcpClient2);

struct MqttMsg {
  char topic[32];
  char payload[512];
  bool retained;
};
QueueHandle_t mqttQueue;

void publishMqtt(const char* topic, const char* payload, bool retained = false) {
  if (mqttQueue == NULL) return;
  MqttMsg msg;
  strncpy(msg.topic, topic, sizeof(msg.topic) - 1);
  msg.topic[sizeof(msg.topic) - 1] = '\0';
  strncpy(msg.payload, payload, sizeof(msg.payload) - 1);
  msg.payload[sizeof(msg.payload) - 1] = '\0';
  msg.retained = retained;
  xQueueSend(mqttQueue, &msg, 0); // Non-blocking
}

TaskHandle_t hWifiTask;

// Variabel WiFi/status (ditulis wifiTask core0, dibaca loop core1)
String devMac    = "";
String devIP     = "";
String apMac     = "";
String wifiStatus= "OFF";
volatile bool ntpReady = false;
volatile bool isWifiConnected  = false;
volatile bool isMqtt1Connected = false;
volatile bool isMqtt2Connected = false;

// ============================================================
//  COUNTING - POLLING DEBOUNCE (dijalankan dari loop(), core 1)
//  Tidak lagi pakai interrupt/ISR. Alasan & penjelasan lihat header
//  v0006 di atas. Karena hanya diakses dari 1 core (loop/core 1),
//  tidak perlu mutex/critical section sama sekali.
// ============================================================

bool     v_pressState    = false;   // status stabil saat ini: sedang ditekan?
bool     v_lastRawState  = HIGH;    // pembacaan mentah terakhir (belum tentu stabil)
uint32_t v_lastRawChgMs  = 0;       // kapan pembacaan mentah terakhir berubah
uint32_t v_pressStartMs  = 0;

bool     v_cycleDone     = false;   // flag: ada 1 siklus baru terkonfirmasi (buat MQTT)
uint32_t v_cycleDurMs    = 0;       // durasi aktual siklus (untuk actTimeSec)

// Dipanggil setiap iterasi loop(). Ringan (cuma 1x digitalRead + beberapa
// pembanding), aman dipanggil sesering mungkin.
void pollCounting() {
  bool raw = digitalRead(PIN_COUNT);   // HIGH=idle, LOW=ditekan (lihat wiring di atas)
  uint32_t now = millis();

  if (raw != v_lastRawState) {
    // Pembacaan mentah baru saja berubah -> mulai/reset timer debounce.
    // Kalau ini cuma bouncing, raw akan berubah-ubah lagi sebelum
    // COUNT_DEBOUNCE_MS habis, dan blok di bawah tidak akan pernah lolos.
    v_lastRawState = raw;
    v_lastRawChgMs = now;
    return;
  }

  // raw sudah SAMA dengan pembacaan sebelumnya. Cek apakah sudah stabil
  // cukup lama (>= COUNT_DEBOUNCE_MS) DAN berbeda dari status stabil
  // saat ini -> baru dianggap transisi yang SAH.
  bool stableLow = (raw == LOW);
  if ((now - v_lastRawChgMs) >= COUNT_DEBOUNCE_MS) {
    if (stableLow && !v_pressState) {
      // ---- Transisi SAH: tombol mulai ditekan ----
      v_pressState   = true;
      v_pressStartMs = now;

      // Langsung trigger 1 hitungan siklus saat ditekan (requirement lama:
      // "langsung output 1 saat ditekan", supaya CUR_CYCLE naik seketika).
      v_cycleDurMs = 0;     // durasi aktual dihitung terpisah saat release (actTimeSec)
      v_cycleDone  = true;

    } else if (!stableLow && v_pressState) {
      // ---- Transisi SAH: tombol dilepas ----
      v_pressState = false;
      v_cycleDurMs = now - v_pressStartMs;  // durasi aktual, dipakai untuk actTimeSec

      // Tambahkan langsung ke actTimeSec di sini (bukan lewat v_cycleDone,
      // supaya tidak memicu publish /Event/Cnt kedua kalinya).
      extern uint32_t actTimeSec;
      actTimeSec += v_cycleDurMs / 1000;
    }
  }
}

// Dipanggil dari loop() untuk mengambil & clear event count yang baru
// terkonfirmasi (untuk publish MQTT /Event/Cnt).
bool takeCycleDone() {
  if (v_cycleDone) {
    v_cycleDone = false;
    return true;
  }
  return false;
}

// ============================================================
//  MAX6675 - Software SPI
//  Sumber: HPM-55 -> MAX6675 -> ESP32 (Calculating Temperature)
// ============================================================
float readMax6675() {
  uint16_t raw = 0;
  digitalWrite(PIN_MAX_CS, LOW);
  delayMicroseconds(10);

  for (int i = 15; i >= 0; i--) {
    digitalWrite(PIN_MAX_SCK, HIGH);
    delayMicroseconds(5);
    raw <<= 1;
    if (digitalRead(PIN_MAX_SO)) raw |= 1;
    digitalWrite(PIN_MAX_SCK, LOW);
    delayMicroseconds(5);
  }
  digitalWrite(PIN_MAX_CS, HIGH);

  if (raw & 0x4) {
    // Thermocouple open / tidak terpasang dengan benar -> NAN (bukan simulasi).
    return NAN;
  }

  return (raw >> 3) * 0.25f;
}

// ============================================================
//  HELPER - Waktu
// ============================================================
bool getNow(struct tm& ti) { return getLocalTime(&ti, 500); }

// ============================================================
//  BUILD PAYLOAD - snprintf ke local buffer (no heap, thread-safe)
// ============================================================
void payloadSysCtrl(char* buf, size_t n, const char* sts) {
  snprintf(buf, n,
    "{\"IOT_MAC\":\"%s\",\"AP_MAC\":\"%s\",\"IOT_SPPL_CD\":\"%s\","
    "\"IOT_MODEL\":\"%s\",\"MCIP\":\"%s\",\"MCID\":\"%s\","
    "\"STS\":\"%s\",\"VER\":\"%s\"}",
    devMac.c_str(), apMac.c_str(), IOT_SPPL_CD,
    IOT_MODEL, devIP.c_str(), MCID, sts, FW_VER);
}

void payloadEventCnt(char* buf, size_t n, const struct tm& ti,
                     uint32_t durMs, uint32_t cur, uint32_t sum) {
  snprintf(buf, n,
    "{\"YEAR\":%d,\"MON\":%d,\"DAY\":%d,"
    "\"HOUR\":%d,\"MIN\":%d,\"SEC\":%d,"
    "\"PROCESSID\":\"%s\",\"MAC\":\"%s\",\"TYPE\":\"OUTPUT\","
    "\"DATA\":%lu,\"CUR_CYCLE\":%lu,\"SUM_CYCLE\":%lu,"
    "\"UID\":\"%s\"}",
    ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
    ti.tm_hour, ti.tm_min, ti.tm_sec,
    PROCESS_ID, devMac.c_str(), durMs, cur, sum,
    NFC_UID);
}

void payloadHandling(char* buf, size_t n, uint32_t sec) {
  snprintf(buf, n,
    "{\"MAC\":\"%s\",\"PROCESS_ID\":\"%s\",\"HANDLING_TIME\":%lu}",
    devMac.c_str(), PROCESS_ID, sec);
}

// Dikirim sekali tiap kali MQTT baru connect (power on / reconnect).
void payloadTeaching(char* buf, size_t n) {
  snprintf(buf, n,
    "{\"MAC\":\"%s\",\"PROCESS_ID\":\"%s\",\"DATA\":["
    "{\"SEQ_NAME\":\"STI\",\"SEQ_VALUE\":%d},"
    "{\"SEQ_NAME\":\"TRI\",\"SEQ_VALUE\":%d},"
    "{\"SEQ_NAME\":\"DLY\",\"SEQ_VALUE\":%d}"
    "]}",
    devMac.c_str(), PROCESS_ID,
    TEACH_STI_VALUE, TEACH_TRI_VALUE, TEACH_DLY_VALUE);
}

void payloadMchnTime(char* buf, size_t n, const struct tm& ti,
                     uint32_t powT, uint32_t motoT, uint32_t actT, uint32_t sti) {
  snprintf(buf, n,
    "{\"YEAR\":%d,\"MON\":%d,\"DAY\":%d,"
    "\"HOUR\":%d,\"MIN\":%d,\"SEC\":%d,"
    "\"MAC\":\"%s\",\"POW_TIME\":%lu,\"MOTO_TIME\":%lu,"
    "\"ACT_TIME\":%lu,\"SUM_STI\":%lu}",
    ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
    ti.tm_hour, ti.tm_min, ti.tm_sec,
    devMac.c_str(), powT, motoT, actT, sti);
}

void payloadHeatpress(char* buf, size_t n, const struct tm& ti, int pv, int sv) {
  snprintf(buf, n,
    "{\"YEAR\":%d,\"MON\":%d,\"DAY\":%d,"
    "\"HOUR\":%d,\"MIN\":%d,\"SEC\":%d,"
    "\"MAC\":\"%s\",\"PV\":%d,\"SV\":%d}",
    ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
    ti.tm_hour, ti.tm_min, ti.tm_sec,
    devMac.c_str(), pv, sv);
}

// ============================================================
//  NVS - Counter persisten
//  saveCounters() HANYA dipanggil tiap 60 detik + saat daily reset
// ============================================================
uint32_t curCycle    = 0;
uint32_t sumCycle    = 0;
uint32_t powTimeSec  = 0;
uint32_t actTimeSec  = 0;   // diisi oleh pollCounting() saat tombol dilepas
uint32_t motoTimeSec = 0;
uint32_t sumSti      = 0;
int      lastDay     = -1;

void loadCounters() {
  nvs.begin("runtime", true);
  curCycle    = nvs.getULong("curCycle",  0);
  sumCycle    = nvs.getULong("sumCycle",  0);
  powTimeSec  = nvs.getULong("powTime",   0);
  actTimeSec  = nvs.getULong("actTime",   0);
  motoTimeSec = nvs.getULong("motoTime",  0);
  sumSti      = nvs.getULong("sumSti",    0);
  lastDay     = nvs.getInt("lastDay",    -1);
  nvs.end();
}

void saveCounters() {
  nvs.begin("runtime", false);
  nvs.putULong("curCycle",  curCycle);
  nvs.putULong("sumCycle",  sumCycle);
  nvs.putULong("powTime",   powTimeSec);
  nvs.putULong("actTime",   actTimeSec);
  nvs.putULong("motoTime",  motoTimeSec);
  nvs.putULong("sumSti",    sumSti);
  nvs.putInt("lastDay",     lastDay);
  nvs.end();
}

void checkDailyReset() {
  struct tm ti;
  if (!getNow(ti)) return;
  int today = ti.tm_mday;
  if (lastDay == -1) { lastDay = today; return; }
  if (today != lastDay) {
    curCycle = powTimeSec = actTimeSec = motoTimeSec = sumSti = 0;
    lastDay  = today;
    saveCounters();
    Serial.println("[DAILY] Counter harian direset (SUM_CYCLE tetap).");
  }
}

// ============================================================
//  DISPLAY - OLED 0.96" SSD1306 (128x64)
// ============================================================
float    lastTemperature  = NAN;

void drawStaticLayout() {
  display.clearDisplay();
  display.display();
}

void updateDisplay() {
  static bool blink = false;
  blink = !blink;

  uint32_t now = millis();
  uint32_t epoch;
  if (isWifiConnected && ntpReady) {
    epoch = ntpClient.getEpochTime();
  } else {
    epoch = now / 1000;
  }
  uint32_t ss = epoch % 60;
  uint32_t mm = (epoch / 60) % 60;
  uint32_t hh = (epoch / 3600) % 24;
  char timeBuf[9];
  snprintf(timeBuf, sizeof(timeBuf), "%02lu:%02lu:%02lu", hh, mm, ss);

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // HEADER
  if (wifiStatus == "ON") {
    display.fillCircle(4, 4, 3, SSD1306_WHITE);
  } else {
    display.drawCircle(4, 4, 3, SSD1306_WHITE);
    display.drawLine(1, 1, 7, 7, SSD1306_WHITE);
  }
  display.setTextSize(1);
  display.setCursor(12, 0);
  display.print("HPM-55 IoT");
  display.setCursor(128 - 54, 0);
  display.print(timeBuf);
  display.drawFastHLine(0, 10, 128, SSD1306_WHITE);
  display.drawFastVLine(63, 11, 35, SSD1306_WHITE);

  // PANEL KIRI: COUNT
  display.setTextSize(1);
  display.setCursor(0, 12);
  display.print("COUNT");
  display.setTextSize(2);
  char cntStr[7];
  snprintf(cntStr, sizeof(cntStr), "%5lu", curCycle);
  display.setCursor(0, 22);
  display.print(cntStr);

  // PANEL KANAN: SUHU
  display.setTextSize(1);
  display.setCursor(66, 12);
  display.print("SUHU[\xF8" "C]");
  display.setTextSize(2);
  if (isnan(lastTemperature)) {
    display.setCursor(66, 22);
    display.print("ERR");
  } else {
    int pv = (int)roundf(lastTemperature);
    char pvStr[5];
    snprintf(pvStr, sizeof(pvStr), "%3d", pv);
    display.setCursor(66, 22);
    display.print(pvStr);
  }
  display.setTextSize(1);
  display.setCursor(100, 28);
  display.print("/");
  char svStr[5];
  snprintf(svStr, sizeof(svStr), "%d", setTemperature);
  display.setCursor(107, 28);
  display.print(svStr);

  display.drawFastHLine(0, 52, 128, SSD1306_WHITE);

  // STATUS BAR
  bool mqttOk = isMqtt1Connected || isMqtt2Connected;
  display.setTextSize(1);
  display.setCursor(0, 57);
  display.print("MQTT:");
  if (mqttOk) {
    if (blink) display.fillRect(31, 58, 5, 5, SSD1306_WHITE);
    else       display.drawRect(31, 58, 5, 5, SSD1306_WHITE);
    display.setCursor(39, 57);
    display.print("OK");
  } else {
    display.drawRect(31, 58, 5, 5, SSD1306_WHITE);
    display.drawLine(31, 58, 35, 62, SSD1306_WHITE);
    display.drawLine(35, 58, 31, 62, SSD1306_WHITE);
    display.setCursor(39, 57);
    display.print("--");
  }
  display.setCursor(60, 57);
  char sumStr[16];
  snprintf(sumStr, sizeof(sumStr), "S:%lu", sumCycle);
  display.print(sumStr);

  display.display();
}

void printLocalTime() {
  static uint32_t lastUpdate = 0;
  uint32_t now = millis();
  if (now - lastUpdate < INTERVAL_CLOCK_UPDATE) return;
  lastUpdate = now;
  updateDisplay();
}

// ============================================================
//  NTP
// ============================================================
static void syncNTP() {
  configTime(7 * 3600, 0, "time.windows.com", "pool.ntp.org");
  Serial.print("[NTP] Sinkronisasi");
  struct tm ti;
  uint32_t t0 = millis();
  while (!getLocalTime(&ti) && millis() - t0 < 10000) {
    Serial.print(".");
    vTaskDelay(500 / portTICK_PERIOD_MS);
  }
  ntpReady = getLocalTime(&ti);
  Serial.println(ntpReady ? " OK" : " TIMEOUT (gunakan millis)");
  if (ntpReady) ntpClient.begin();
}

// ============================================================
//  WiFi - hanya dipanggil dari wifiTask (core 0)
// ============================================================
static void wifiConnect() {
  wifiStatus = "OFF";
  ntpReady   = false;
  digitalWrite(PIN_LED_R, HIGH);
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_B, LOW);

  WiFi.disconnect(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("[WiFi] Menghubungkan ke %s", WIFI_SSID);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 30000) {
    vTaskDelay(500 / portTICK_PERIOD_MS);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    isWifiConnected = true;
    devIP  = WiFi.localIP().toString();
    devMac = WiFi.macAddress();
    wifiStatus = "ON";

    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
      char m[18];
      snprintf(m, sizeof(m), "%02X:%02X:%02X:%02X:%02X:%02X",
               ap.bssid[0], ap.bssid[1], ap.bssid[2],
               ap.bssid[3], ap.bssid[4], ap.bssid[5]);
      apMac = m;
    }
    Serial.printf("\n[WiFi] OK - IP=%s  MAC=%s\n",
                  devIP.c_str(), devMac.c_str());
    digitalWrite(PIN_LED_R, LOW);
    digitalWrite(PIN_LED_G, LOW);
    digitalWrite(PIN_LED_B, HIGH);
    syncNTP();
  } else {
    isWifiConnected = false;
    Serial.println("\n[WiFi] GAGAL - akan coba lagi.");
  }
}

// ============================================================
//  TASK - WiFi (core 0, prioritas 2)
// ============================================================
static void mqttMaintain();

void wifiTask(void*) {
  wifiConnect();
  for (;;) {
    vTaskDelay(20 / portTICK_PERIOD_MS);

    static uint32_t lastWifiCheck = 0;
    if (millis() - lastWifiCheck >= 2000) {
      lastWifiCheck = millis();
      isWifiConnected = (WiFi.status() == WL_CONNECTED);
      if (!isWifiConnected) {
        Serial.println("[WiFi] Terputus, reconnect...");
        wifiConnect();
      }
    }

    mqttMaintain();
    isMqtt1Connected = mqtt.connected();
    isMqtt2Connected = mqtt2.connected();

    if (mqttQueue != NULL) {
      MqttMsg msg;
      while (xQueueReceive(mqttQueue, &msg, 0) == pdTRUE) {
        if (mqtt.connected()) mqtt.publish(msg.topic, msg.payload, msg.retained);
        if (mqtt2.connected()) mqtt2.publish(msg.topic, msg.payload, msg.retained);
      }
    }
  }
}

// ============================================================
//  MQTT maintain
// ============================================================
static void mqttMaintain() {
  const uint32_t INTERVAL_MQTT_RETRY = 5000;
  bool wifiOk  = isWifiConnected;

  if (!wifiOk) {
    if (mqtt.connected()) {
      char offBuf[512];
      payloadSysCtrl(offBuf, sizeof(offBuf), "OFF");
      mqtt.publish(TOPIC_SYSCTRL, offBuf, true);
      mqtt.disconnect();
    }
    if (mqtt2.connected()) {
      char offBuf[512];
      payloadSysCtrl(offBuf, sizeof(offBuf), "OFF");
      mqtt2.publish(TOPIC_SYSCTRL, offBuf, true);
      mqtt2.disconnect();
    }
    if (!mqtt.connected() && !mqtt2.connected()) {
      digitalWrite(PIN_LED_R, LOW);
      digitalWrite(PIN_LED_G, LOW);
      digitalWrite(PIN_LED_B, HIGH);
    }
    return;
  }

  static uint32_t lastMqttRetryMs = 0;
  uint32_t now = millis();
  bool timeToRetry = (now - lastMqttRetryMs >= INTERVAL_MQTT_RETRY);

  char clientID1[40], clientID2[40];
  snprintf(clientID1, sizeof(clientID1), "ESP32-1-%s", devIP.c_str());
  snprintf(clientID2, sizeof(clientID2), "ESP32-2-%s", devIP.c_str());

  char lwtBuf[512];
  payloadSysCtrl(lwtBuf, sizeof(lwtBuf), "OFF");

  bool retryAttempted = false;

  if (mqtt.connected()) {
    mqtt.loop();
  } else if (timeToRetry) {
    retryAttempted = true;
    Serial.print("[MQTT 1] Reconnect...");
    if (mqtt.connect(clientID1, TOPIC_SYSCTRL, 1, true, lwtBuf)) {
      Serial.println(" OK!");
      char onBuf[512];
      payloadSysCtrl(onBuf, sizeof(onBuf), "ON");
      mqtt.publish(TOPIC_SYSCTRL, onBuf, true);
      char teachBuf[256];
      payloadTeaching(teachBuf, sizeof(teachBuf));
      mqtt.publish(TOPIC_TEACHING, teachBuf);
    } else {
      Serial.println(" GAGAL");
    }
  }

  if (mqtt2.connected()) {
    mqtt2.loop();
  } else if (timeToRetry) {
    retryAttempted = true;
    Serial.print("[MQTT 2] Reconnect...");
    if (mqtt2.connect(clientID2, TOPIC_SYSCTRL, 1, true, lwtBuf)) {
      Serial.println(" OK!");
      char onBuf[512];
      payloadSysCtrl(onBuf, sizeof(onBuf), "ON");
      mqtt2.publish(TOPIC_SYSCTRL, onBuf, true);
      char teachBuf[256];
      payloadTeaching(teachBuf, sizeof(teachBuf));
      mqtt2.publish(TOPIC_TEACHING, teachBuf);
    } else {
      Serial.println(" GAGAL");
    }
  }

  if (retryAttempted) lastMqttRetryMs = now;

  if (mqtt.connected() || mqtt2.connected()) {
    digitalWrite(PIN_LED_R, LOW);
    digitalWrite(PIN_LED_G, HIGH);
    digitalWrite(PIN_LED_B, LOW);
  } else {
    digitalWrite(PIN_LED_R, LOW);
    digitalWrite(PIN_LED_G, LOW);
    digitalWrite(PIN_LED_B, HIGH);
  }
}

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== HEAT PRESS HPM-55 IoT Monitoring v0001 ===");

  pinMode(PIN_LED_R, OUTPUT); digitalWrite(PIN_LED_R, HIGH);
  pinMode(PIN_LED_G, OUTPUT); digitalWrite(PIN_LED_G, LOW);
  pinMode(PIN_LED_B, OUTPUT); digitalWrite(PIN_LED_B, LOW);

  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 allocation failed"));
  }
  display.clearDisplay();
  display.display();
  drawStaticLayout();

  pinMode(PIN_MAX_CS,  OUTPUT); digitalWrite(PIN_MAX_CS,  HIGH);
  pinMode(PIN_MAX_SCK, OUTPUT); digitalWrite(PIN_MAX_SCK, LOW);
  pinMode(PIN_MAX_SO,  INPUT);

  // --- Counting: PURE POLLING, tidak ada attachInterrupt lagi ---
  // Lihat pollCounting() + header v0006 untuk alasan & penjelasan.
  pinMode(PIN_COUNT, INPUT_PULLUP);
  v_lastRawState = digitalRead(PIN_COUNT);   // inisialisasi sesuai kondisi awal riil
  v_lastRawChgMs = millis();

  loadCounters();
  Serial.printf("[NVS] CUR_CYCLE=%lu  SUM_CYCLE=%lu\n", curCycle, sumCycle);

  mqttQueue = xQueueCreate(10, sizeof(MqttMsg));

  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setKeepAlive(10);
  mqtt.setBufferSize(512);

  mqtt2.setServer(MQTT_SERVER2, MQTT_PORT2);
  mqtt2.setKeepAlive(10);
  mqtt2.setBufferSize(512);

  xTaskCreatePinnedToCore(wifiTask, "WiFiTask", 4096, NULL, 2, &hWifiTask, 0);
}

// ============================================================
//  LOOP - Semua business logic (core 1)
// ============================================================
void loop() {
  static uint32_t lastTempReadMs      = 0;
  static uint32_t lastHeatpressMs     = 0;
  static uint32_t lastMchnTimeMs      = 0;
  static uint32_t lastHandlingEventMs = 0;
  static uint32_t lastPowTickMs       = 0;
  static uint32_t lastSysCtrlMs       = 0;

  uint32_t now = millis();

  // --- Polling counting (dipanggil tiap iterasi loop, ringan) ---
  pollCounting();

  if (isWifiConnected && ntpReady) ntpClient.update();

  printLocalTime();

  // --- Publish /SysCtrl (heartbeat) tiap 60 detik ---
  if (now - lastSysCtrlMs >= INTERVAL_SYSCTRL) {
    lastSysCtrlMs = now;
    if (isMqtt1Connected || isMqtt2Connected) {
      char onBuf[512];
      payloadSysCtrl(onBuf, sizeof(onBuf), "ON");
      publishMqtt(TOPIC_SYSCTRL, onBuf, true);
    }
  }

  checkDailyReset();

  // --- Akumulasi POW_TIME & MOTO_TIME tiap detik ---
  if (now - lastPowTickMs >= 1000) {
    lastPowTickMs = now;
    powTimeSec++;
    if (v_pressState) {
      motoTimeSec++;
    }
  }

  // --- Baca suhu dari MAX6675 (tiap 2 detik) ---
  if (now - lastTempReadMs >= INTERVAL_TEMP_READ) {
    lastTempReadMs  = now;
    lastTemperature = readMax6675();
    updateDisplay();
  }

  // --- Siklus press terkonfirmasi (dari pollCounting()) -> /Event/Cnt ---
  if (takeCycleDone()) {
    curCycle++;
    sumCycle++;
    sumSti = curCycle;

    nvs.begin("runtime", false);
    nvs.putULong("curCycle", curCycle);
    nvs.putULong("sumCycle", sumCycle);
    nvs.end();
    Serial.printf("[NVS] Quick-save CUR=%lu SUM=%lu\n", curCycle, sumCycle);

    Serial.printf("[Cnt] CUR=%lu  SUM=%lu  (WiFi=%s MQTT=%s)\n",
                  curCycle, sumCycle,
                  isWifiConnected ? "ON" : "OFF",
                  (isMqtt1Connected || isMqtt2Connected) ? "ON" : "OFF");

    struct tm ti;
    if (getNow(ti) && (isMqtt1Connected || isMqtt2Connected)) {
      char buf[512];
      payloadEventCnt(buf, sizeof(buf), ti, 0, curCycle, sumCycle);
      publishMqtt(TOPIC_EVENT_CNT, buf);
    }
    updateDisplay();
  }

  // --- Publish /Event/Handling tiap 60 detik (heartbeat statis) ---
  if (now - lastHandlingEventMs >= INTERVAL_HANDLING) {
    lastHandlingEventMs = now;
    if (isMqtt1Connected || isMqtt2Connected) {
      char buf[512];
      payloadHandling(buf, sizeof(buf), HANDLING_TIME_SEC);
      publishMqtt(TOPIC_HANDLING, buf);
      Serial.printf("[Handling] %lu detik (statis SOP)\n", HANDLING_TIME_SEC);
    }
  }

  // --- Publish /Heatpress (PV/SV) tiap 5 detik ---
  if (now - lastHeatpressMs >= INTERVAL_HEATPRESS) {
    lastHeatpressMs = now;
    struct tm ti;
    if (getNow(ti) && (mqtt.connected() || mqtt2.connected())) {
      int pv = isnan(lastTemperature) ? 0 : (int)roundf(lastTemperature);
      char buf[512];
      payloadHeatpress(buf, sizeof(buf), ti, pv, setTemperature);
      publishMqtt(TOPIC_HEATPRESS, buf);
      Serial.printf("[Heatpress] PV=%d  SV=%d\n", pv, setTemperature);
    }
  }

  // --- Publish /Event/Mchn_time tiap 60 detik + simpan NVS ---
  if (now - lastMchnTimeMs >= INTERVAL_MCHN_TIME) {
    lastMchnTimeMs = now;
    saveCounters();
    struct tm ti;
    if (getNow(ti) && (isMqtt1Connected || isMqtt2Connected)) {
      char buf[512];
      payloadMchnTime(buf, sizeof(buf), ti,
                      powTimeSec, motoTimeSec, actTimeSec, sumSti);
      publishMqtt(TOPIC_MCHN_TIME, buf);
      Serial.printf("[MchnTime] POW=%lu  ACT=%lu\n", powTimeSec, actTimeSec);
    }
  }
}