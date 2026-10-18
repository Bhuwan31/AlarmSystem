// AMHEWS river-gauge node (ESP32, Arduino framework)
//
// Hardware: ESP32 DevKit, JSN-SR04T waterproof ultrasonic sensor (or a radar level sensor with UART),
// tipping-bucket rain gauge on a reed switch, 3.7 V Li-ion + solar charger, Wi-Fi or a SIM7600 modem.
// The sensor hangs above the river at a surveyed height; water level = MOUNT_HEIGHT_M - distance.
//
// Publishes (MQTT over TLS, username = device id, password from registration):
//   devices/<id>/readings   every READ_INTERVAL_S
//   devices/<id>/heartbeat  every HEARTBEAT_S
// Readings taken while offline are buffered in RTC/flash and re-sent with their original timestamps
// (NFR-HW2, SR-14). Status: written against the documented libraries; compile and bench-test before field use.
//
// Libraries: PubSubClient, ArduinoJson (v7), LittleFS (bundled with ESP32 core).

#include <algorithm>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <time.h>
#include "config.h"   // copy config.example.h -> config.h (never commit it)

static const char *FIRMWARE = "gauge-0.1.0";
static const int TRIG_PIN = 5, ECHO_PIN = 18, RAIN_PIN = 27, BATTERY_ADC = 34;
static const float RAIN_MM_PER_TIP = 0.2f;
static const char *BUFFER_FILE = "/buffer.jsonl";
static const size_t BUFFER_MAX_LINES = 24 * 60 * 60 / READ_INTERVAL_S;   // 24 h of readings

WiFiClientSecure tls;
PubSubClient mqtt(tls);
volatile uint32_t rainTips = 0;
uint32_t lastRead = 0, lastBeat = 0;

void IRAM_ATTR onRainTip() {
  static uint32_t last = 0;
  uint32_t now = millis();
  if (now - last > 200) { rainTips++; last = now; }   // debounce reed switch
}

float readDistanceM() {
  // Median of 7 pings to reject splashes and debris
  float samples[7];
  for (int i = 0; i < 7; i++) {
    digitalWrite(TRIG_PIN, LOW); delayMicroseconds(5);
    digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(20);
    digitalWrite(TRIG_PIN, LOW);
    unsigned long us = pulseIn(ECHO_PIN, HIGH, 60000);
    samples[i] = us == 0 ? NAN : (us * 0.000343f) / 2.0f;
    delay(60);
  }
  std::sort(samples, samples + 7, [](float a, float b) { return isnan(b) || (!isnan(a) && a < b); });
  return samples[3];
}

float batteryVolts() { return analogReadMilliVolts(BATTERY_ADC) * 2.0f / 1000.0f; }   // 1:2 divider

bool connectNetwork() {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
  if (WiFi.status() != WL_CONNECTED) return false;
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  return true;
}

bool connectMqtt() {
  if (mqtt.connected()) return true;
  if (!connectNetwork()) return false;
  tls.setCACert(MQTT_CA_CERT);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(1024);
  return mqtt.connect(DEVICE_ID, DEVICE_ID, DEVICE_SECRET);
}

void bufferLine(const String &line) {
  File f = LittleFS.open(BUFFER_FILE, FILE_APPEND);
  if (f) { f.println(line); f.close(); }
  // Trim oldest lines when over capacity
  File r = LittleFS.open(BUFFER_FILE, FILE_READ);
  size_t lines = 0;
  while (r && r.available()) { r.readStringUntil('\n'); lines++; }
  if (r) r.close();
  if (lines > BUFFER_MAX_LINES) {
    File in = LittleFS.open(BUFFER_FILE, FILE_READ), out = LittleFS.open("/tmp.jsonl", FILE_WRITE);
    size_t skip = lines - BUFFER_MAX_LINES;
    while (in.available()) { String l = in.readStringUntil('\n'); if (skip) { skip--; continue; } out.println(l); }
    in.close(); out.close();
    LittleFS.remove(BUFFER_FILE); LittleFS.rename("/tmp.jsonl", BUFFER_FILE);
  }
}

void flushBuffer() {
  if (!LittleFS.exists(BUFFER_FILE)) return;
  File in = LittleFS.open(BUFFER_FILE, FILE_READ);
  String topic = String("devices/") + DEVICE_ID + "/readings";
  bool ok = true;
  while (in.available() && ok) {
    String l = in.readStringUntil('\n');
    l.trim();
    if (l.length()) ok = mqtt.publish(topic.c_str(), l.c_str());
    mqtt.loop();
  }
  in.close();
  if (ok) LittleFS.remove(BUFFER_FILE);
}

void takeReading() {
  float d = readDistanceM();
  uint32_t tips = rainTips; rainTips = 0;
  JsonDocument doc;
  doc["ts"] = (uint32_t)time(nullptr);
  if (!isnan(d)) doc["level_m"] = roundf((MOUNT_HEIGHT_M - d) * 1000) / 1000;
  doc["rain_mm"] = tips * RAIN_MM_PER_TIP;
  doc["battery_v"] = batteryVolts();
  doc["rssi"] = WiFi.RSSI();
  String line; serializeJson(doc, line);

  if (connectMqtt()) {
    flushBuffer();
    String topic = String("devices/") + DEVICE_ID + "/readings";
    if (!mqtt.publish(topic.c_str(), line.c_str())) bufferLine(line);
  } else {
    bufferLine(line);   // store-and-forward when the network is down
  }
}

void heartbeat() {
  if (!connectMqtt()) return;
  JsonDocument doc;
  doc["ts"] = (uint32_t)time(nullptr);
  doc["battery_v"] = batteryVolts();
  doc["rssi"] = WiFi.RSSI();
  doc["firmware"] = FIRMWARE;
  String s; serializeJson(doc, s);
  mqtt.publish((String("devices/") + DEVICE_ID + "/heartbeat").c_str(), s.c_str());
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT); pinMode(ECHO_PIN, INPUT);
  pinMode(RAIN_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(RAIN_PIN), onRainTip, FALLING);
  LittleFS.begin(true);
  connectMqtt();
}

void loop() {
  uint32_t now = millis();
  if (now - lastRead >= READ_INTERVAL_S * 1000UL || lastRead == 0) { lastRead = now; takeReading(); }
  if (now - lastBeat >= HEARTBEAT_S * 1000UL || lastBeat == 0) { lastBeat = now; heartbeat(); }
  mqtt.loop();
  delay(50);
}
