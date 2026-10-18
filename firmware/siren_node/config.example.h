// Copy to config.h and fill in. config.h is git-ignored: it holds device secrets.
#pragma once

#define DEVICE_ID       "siren-001"
#define DEVICE_SECRET   "paste mqtt_password from registration"
#define COMMAND_KEY_HEX "paste command_key_hex from registration (64 hex chars)"
#define WIFI_SSID       "your-wifi"
#define WIFI_PASSWORD   "your-wifi-password"
#define MQTT_HOST       "mqtt.example.org"
#define MQTT_PORT       8883

static const char *MQTT_CA_CERT = R"PEM(
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
)PEM";
