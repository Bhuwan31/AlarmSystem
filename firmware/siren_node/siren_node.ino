// AMHEWS siren node (ESP32, Arduino framework)
//
// Hardware: ESP32, relay module driving the siren contactor, momentary "manual activate" and "stop"
// buttons, status LED, Wi-Fi or SIM7600 modem, 12 V battery with charger (siren keeps working offline).
//
// Safety rules implemented here (SR-13, SR-14, SEC-10):
//  - Only commands with a valid HMAC-SHA256 signature (key = HMAC(master, device_id), flashed at
//    provisioning) are obeyed. Commands older than 120 s or with a reused nonce are rejected.
//  - In test mode the siren chirps briefly instead of sounding, so drills cannot be mistaken for alerts.
//  - The local manual button always works, even with no network (fail-safe).
//  - Every command is acknowledged on devices/<id>/ack.
// Status: written against the documented libraries; compile and bench-test before field use.
//
// Libraries: PubSubClient, ArduinoJson (v7). mbedTLS is part of the ESP32 core.

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "mbedtls/md.h"
#include "config.h"   // copy config.example.h -> config.h (never commit it)

static const char *FIRMWARE = "siren-0.1.0";
static const int RELAY_PIN = 26, BTN_ACTIVATE = 32, BTN_STOP = 33, LED_PIN = 2;
static const uint32_t MAX_AGE_S = 120;
static const uint32_t SOUND_MAX_MS = 10UL * 60 * 1000;   // auto-stop after 10 min unless re-commanded

WiFiClientSecure tls;
PubSubClient mqtt(tls);
String recentNonces[16];
int nonceIdx = 0;
uint32_t soundingSince = 0, lastBeat = 0;
bool sounding = false;

bool hexToBytes(const char *hex, uint8_t *out, size_t len) {
  for (size_t i = 0; i < len; i++) {
    if (sscanf(hex + 2 * i, "%2hhx", &out[i]) != 1) return false;
  }
  return true;
}

String hmacHex(const String &msg) {
  uint8_t key[32], mac[32];
  hexToBytes(COMMAND_KEY_HEX, key, 32);
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, key, 32);
  mbedtls_md_hmac_update(&ctx, (const uint8_t *)msg.c_str(), msg.length());
  mbedtls_md_hmac_finish(&ctx, mac);
  mbedtls_md_free(&ctx);
  char hex[65];
  for (int i = 0; i < 32; i++) sprintf(hex + 2 * i, "%02x", mac[i]);
  return String(hex);
}

bool constantTimeEquals(const String &a, const String &b) {
  if (a.length() != b.length()) return false;
  uint8_t diff = 0;
  for (size_t i = 0; i < a.length(); i++) diff |= a[i] ^ b[i];
  return diff == 0;
}

bool seenNonce(const String &n) {
  for (auto &s : recentNonces) if (s == n) return true;
  recentNonces[nonceIdx] = n; nonceIdx = (nonceIdx + 1) % 16;
  return false;
}

void ack(const String &nonce, const char *result) {
  JsonDocument doc;
  doc["nonce"] = nonce; doc["result"] = result; doc["ts"] = (uint32_t)time(nullptr);
  String s; serializeJson(doc, s);
  mqtt.publish((String("devices/") + DEVICE_ID + "/ack").c_str(), s.c_str());
}

void soundOn(bool testMode) {
  if (testMode) {               // short chirp only
    digitalWrite(RELAY_PIN, HIGH); delay(300); digitalWrite(RELAY_PIN, LOW);
    return;
  }
  digitalWrite(RELAY_PIN, HIGH); sounding = true; soundingSince = millis();
}

void soundOff() { digitalWrite(RELAY_PIN, LOW); sounding = false; }

void onMessage(char *topic, byte *payload, unsigned int len) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) return;
  String device = doc["device_id"] | "", command = doc["command"] | "", nonce = doc["nonce"] | "", sig = doc["signature"] | "";
  bool testMode = doc["test_mode"] | true;
  uint32_t issued = doc["issued_at"] | 0;
  uint32_t now = (uint32_t)time(nullptr);

  String canonical = device + "|" + command + "|" + (testMode ? "1" : "0") + "|" + nonce + "|" + String(issued);
  bool fresh = now > 1700000000 && (now > issued ? now - issued : issued - now) <= MAX_AGE_S;
  if (device != DEVICE_ID || !fresh || seenNonce(nonce) || !constantTimeEquals(hmacHex(canonical), sig)) {
    ack(nonce, "rejected");
    return;
  }
  if (command == "activate") { soundOn(testMode); ack(nonce, testMode ? "test_chirp" : "sounding"); }
  else if (command == "stop") { soundOff(); ack(nonce, "stopped"); }
  else if (command == "self_test") { soundOn(true); ack(nonce, "self_test_ok"); }
}

bool connectMqtt() {
  if (mqtt.connected()) return true;
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
    if (WiFi.status() != WL_CONNECTED) return false;
    configTime(0, 0, "pool.ntp.org", "time.google.com");
  }
  tls.setCACert(MQTT_CA_CERT);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  if (!mqtt.connect(DEVICE_ID, DEVICE_ID, DEVICE_SECRET)) return false;
  mqtt.subscribe((String("devices/") + DEVICE_ID + "/command").c_str(), 1);
  return true;
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT); digitalWrite(RELAY_PIN, LOW);
  pinMode(BTN_ACTIVATE, INPUT_PULLUP); pinMode(BTN_STOP, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  connectMqtt();
}

void loop() {
  // Manual controls always work, network or not (SR-14)
  if (digitalRead(BTN_ACTIVATE) == LOW) soundOn(false);
  if (digitalRead(BTN_STOP) == LOW) soundOff();
  if (sounding && millis() - soundingSince > SOUND_MAX_MS) soundOff();

  bool online = connectMqtt();
  digitalWrite(LED_PIN, online ? HIGH : (millis() / 500) % 2);
  if (online && millis() - lastBeat > 60000) {
    lastBeat = millis();
    JsonDocument doc;
    doc["ts"] = (uint32_t)time(nullptr); doc["rssi"] = WiFi.RSSI(); doc["firmware"] = FIRMWARE; doc["sounding"] = sounding;
    String s; serializeJson(doc, s);
    mqtt.publish((String("devices/") + DEVICE_ID + "/heartbeat").c_str(), s.c_str());
  }
  mqtt.loop();
  delay(20);
}
