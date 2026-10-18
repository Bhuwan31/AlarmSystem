// Copy to config.h and fill in. config.h is git-ignored: it holds the device secret.
#pragma once

#define DEVICE_ID      "gauge-001"
#define DEVICE_SECRET  "paste mqtt_password from registration"
#define WIFI_SSID      "your-wifi"
#define WIFI_PASSWORD  "your-wifi-password"
#define MQTT_HOST      "mqtt.example.org"
#define MQTT_PORT      8883

// Surveyed height of the sensor face above the gauge zero (metres)
#define MOUNT_HEIGHT_M 8.50f

#define READ_INTERVAL_S 300
#define HEARTBEAT_S     60

// CA certificate of the MQTT broker (PEM)
static const char *MQTT_CA_CERT = R"PEM(
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
)PEM";
