"""Simulate a gauge node over MQTT so the system can be demoed without hardware.

Usage: python scripts/simulate_device.py gauge-001 --start 3.0 --rise 0.6 --interval 5
Publishes a reading every `interval` seconds, raising the level by `rise` metres per simulated hour
(one simulated hour per 12 real readings). Readings are marked as coming from a simulator in the payload;
the system must run in exercise mode while simulators are used (SR-12).
"""
import argparse
import json
import random
import time

import paho.mqtt.publish as publish

p = argparse.ArgumentParser()
p.add_argument("device_id")
p.add_argument("--host", default="localhost")
p.add_argument("--port", type=int, default=1883)
p.add_argument("--start", type=float, default=3.0)
p.add_argument("--rise", type=float, default=0.6, help="metres per simulated hour")
p.add_argument("--interval", type=float, default=5.0)
p.add_argument("--count", type=int, default=60)
a = p.parse_args()

level = a.start
for i in range(a.count):
    level += a.rise / 12 + random.uniform(-0.01, 0.01)
    msg = {"ts": int(time.time()), "level_m": round(level, 3), "rain_mm": round(random.uniform(0, 4), 1),
           "battery_v": 3.9, "rssi": -70, "simulated": True}
    publish.single(f"devices/{a.device_id}/readings", json.dumps(msg), qos=1, hostname=a.host, port=a.port)
    print(f"[{i + 1}/{a.count}] level {msg['level_m']} m")
    time.sleep(a.interval)
