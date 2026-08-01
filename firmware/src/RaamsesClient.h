/*
 * RaamsesClient.h — Shared HTTP client for all Raamses display devices
 *
 * Handles WiFi connection, device registration, heartbeat, and
 * gateway stats parsing via the HTTP/JSON protocol on port 8765.
 *
 * All devices share this code. The device-specific main.cpp handles
 * display rendering and input (buttons/keyboard/touch).
 *
 * Protocol: POST /register, POST /heartbeat, GET /stats
 * See references/http-protocol.md in the skill for full API spec.
 */
#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ---- Configuration from build flags ----
#ifndef GATEWAY_IP
  #define GATEWAY_IP "192.168.6.230"
#endif
#ifndef GATEWAY_PORT
  #define GATEWAY_PORT 8765
#endif
#ifndef WIFI_SSID
  #define WIFI_SSID "CHANGE_ME"
#endif
#ifndef WIFI_PASS
  #define WIFI_PASS "CHANGE_ME"
#endif
#ifndef DEVICE_ID
  #define DEVICE_ID "unknown-001"
#endif
#ifndef DEVICE_TYPE
  #define DEVICE_TYPE "cyd"
#endif
#ifndef HEARTBEAT_INTERVAL_MS
  #define HEARTBEAT_INTERVAL_MS 15000
#endif
#ifndef REGISTER_RETRY_COUNT
  #define REGISTER_RETRY_COUNT 3
#endif
#ifndef REGISTER_RETRY_DELAY_MS
  #define REGISTER_RETRY_DELAY_MS 2000
#endif
#ifndef JSON_DOC_SIZE
  #define JSON_DOC_SIZE 1024
#endif

struct GatewayStats {
  float cpu_temp_c = 0;
  float cpu_percent = 0;
  float mem_used_percent = 0;
  int mem_free_mb = 0;
  int mem_total_mb = 0;
  int agents_registered = 0;
  int uptime_seconds = 0;
  bool valid = false;
};

struct RaamsesState {
  bool registered = false;
  bool wifi_connected = false;
  bool alert_active = false;
  int alert_seq = 0;
  String alert_msg = "";
  unsigned long last_heartbeat = 0;
  unsigned long last_register_attempt = 0;
  unsigned long boot_time = 0;
  GatewayStats stats;
  String status_line = "Booting...";
};

class RaamsesClient {
public:
  RaamsesState state;

  void begin() {
    state.boot_time = millis();
    state.status_line = "Connecting WiFi...";
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(DEVICE_ID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
      delay(500);
      attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
      state.wifi_connected = true;
      state.status_line = "WiFi OK. Registering...";
      register_device();
    } else {
      state.wifi_connected = false;
      state.status_line = "WiFi FAILED";
    }
  }

  void loop() {
    if (!state.wifi_connected) {
      // Try reconnect every 10s
      if (millis() - state.last_register_attempt > 10000) {
        state.last_register_attempt = millis();
        WiFi.begin(WIFI_SSID, WIFI_PASS);
        if (WiFi.status() == WL_CONNECTED) {
          state.wifi_connected = true;
          state.status_line = "WiFi reconnected";
          register_device();
        }
      }
      return;
    }

    if (!state.registered) {
      // Retry registration every 5s
      if (millis() - state.last_register_attempt > 5000) {
        register_device();
      }
      return;
    }

    // Heartbeat loop
    if (millis() - state.last_heartbeat > HEARTBEAT_INTERVAL_MS) {
      send_heartbeat();
    }
  }

  bool register_device() {
    state.last_register_attempt = millis();

    HTTPClient http;
    String url = "http://" + String(GATEWAY_IP) + ":" + String(GATEWAY_PORT) + "/register";

    WiFiClient client;
    if (!http.begin(client, url)) {
      state.status_line = "HTTP begin failed";
      return false;
    }
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);

    JsonDocument doc;
    doc["device_id"] = DEVICE_ID;
    doc["device_type"] = DEVICE_TYPE;
    doc["schema_version"] = "1.0";
    doc["firmware_version"] = "1.0.0";

    String json;
    serializeJson(doc, json);

    int code = http.POST(json);

    if (code == 200) {
      String response = http.getString();
      http.end();

      JsonDocument resp;
      DeserializationError err = deserializeJson(resp, response);
      if (!err) {
        state.registered = true;
        state.status_line = "Registered OK";
        parse_stats(resp);
        if (resp["alert"].is<String>() || resp["alert"].is<const char*>()) {
          state.alert_active = true;
          state.alert_msg = resp["alert"].as<String>();
          state.alert_seq = resp["alert_seq"] | 0;
        }
        return true;
      }
      state.status_line = "Parse error";
      return false;
    }

    http.end();
    state.status_line = "Register failed: " + String(code);
    return false;
  }

  bool send_heartbeat() {
    state.last_heartbeat = millis();

    HTTPClient http;
    String url = "http://" + String(GATEWAY_IP) + ":" + String(GATEWAY_PORT) + "/heartbeat";

    WiFiClient client;
    if (!http.begin(client, url)) return false;
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);

    JsonDocument doc;
    doc["device_id"] = DEVICE_ID;

    String json;
    serializeJson(doc, json);

    int code = http.POST(json);

    if (code == 200) {
      String response = http.getString();
      http.end();

      JsonDocument resp;
      DeserializationError err = deserializeJson(resp, response);
      if (!err) {
        parse_stats(resp);
        if (resp["alert"].is<String>() || resp["alert"].is<const char*>()) {
          state.alert_active = true;
          state.alert_msg = resp["alert"].as<String>();
          state.alert_seq = resp["alert_seq"] | 0;
        } else {
          state.alert_active = false;
          state.alert_msg = "";
        }
      }
      return true;
    }

    http.end();
    if (code == 404) {
      state.registered = false;
      state.status_line = "Re-registering...";
    }
    return false;
  }

  bool send_update(const String& task, int progress_pct, const String& alert = "") {
    HTTPClient http;
    String url = "http://" + String(GATEWAY_IP) + ":" + String(GATEWAY_PORT) + "/update";

    WiFiClient client;
    if (!http.begin(client, url)) return false;
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);

    JsonDocument doc;
    doc["device_id"] = DEVICE_ID;
    if (task.length() > 0) doc["task"] = task;
    if (progress_pct >= 0) doc["progress"] = String(progress_pct) + "%";
    if (alert.length() > 0) doc["alert"] = alert;

    String json;
    serializeJson(doc, json);

    int code = http.POST(json);
    http.end();
    return code == 200;
  }

  bool fetch_stats() {
    HTTPClient http;
    String url = "http://" + String(GATEWAY_IP) + ":" + String(GATEWAY_PORT) + "/stats";

    WiFiClient client;
    if (!http.begin(client, url)) return false;
    http.setTimeout(5000);

    int code = http.GET();
    if (code == 200) {
      String response = http.getString();
      http.end();

      JsonDocument resp;
      DeserializationError err = deserializeJson(resp, response);
      if (!err) {
        parse_stats(resp);
        return true;
      }
    }
    http.end();
    return false;
  }

private:
  void parse_stats(JsonDocument& resp) {
    JsonObject stats = resp["gateway_stats"].as<JsonObject>();
    if (stats.size() == 0) {
      // /stats endpoint returns fields at top level, not nested
      stats = resp.as<JsonObject>();
    }
    if (stats.containsKey("cpu_temp_c")) state.stats.cpu_temp_c = stats["cpu_temp_c"];
    if (stats.containsKey("cpu_percent")) state.stats.cpu_percent = stats["cpu_percent"];
    if (stats.containsKey("mem_used_percent")) state.stats.mem_used_percent = stats["mem_used_percent"];
    if (stats.containsKey("mem_free_mb")) state.stats.mem_free_mb = stats["mem_free_mb"];
    if (stats.containsKey("mem_total_mb")) state.stats.mem_total_mb = stats["mem_total_mb"];
    if (stats.containsKey("agents_registered")) state.stats.agents_registered = stats["agents_registered"];
    if (stats.containsKey("uptime_seconds")) state.stats.uptime_seconds = stats["uptime_seconds"];
    state.stats.valid = true;
  }
};