/*
 * CYD (Cheap Yellow Display) — Raamses Agent Monitor
 *
 * ESP32 + ILI9341 320x240 TFT with resistive touch.
 * Shows gateway health, agent status, and alert state.
 *
 * Hardware: ESP32 DevKit + 2.8" TFT (SPI, ILI9341)
 *   MOSI=13, MISO=12, SCLK=14, CS=15, DC=2, BL=21
 *
 * Display layout (320x240):
 *   ┌────────────────────────────────┐
 *   │  RAAMSES MONITOR         [ALERT]│  ← header bar (red if alert)
 *   ├────────────────────────────────┤
 *   │  Gateway: 192.168.6.230         │
 *   │  CPU: 57.9°C  2.5%              │
 *   │  RAM: 12.8%  14133MB free       │
 *   │  Agents: 3                     │
 *   │  Uptime: 1d 2h 15m              │
 *   ├────────────────────────────────┤
 *   │  Status: Registered OK          │
 *   │  Last HB: 5s ago                │
 *   └────────────────────────────────┘
 */
#include <TFT_eSPI.h>
#include "RaamsesClient.h"

TFT_eSPI tft = TFT_eSPI();
RaamsesClient raamses;

unsigned long last_screen_update = 0;
int screen_rotation = 1;  // landscape

void setup() {
  Serial.begin(115200);

  // Initialize display
  tft.init();
  tft.setRotation(screen_rotation);
  tft.fillScreen(TFT_BLACK);

  // Boot screen
  tft.setTextColor(TFT_CYAN, TFT_BLACK);
  tft.setTextSize(2);
  tft.setCursor(10, 100);
  tft.println("RAAMSES Monitor");
  tft.setTextSize(1);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setCursor(10, 130);
  tft.println("CYD-001 booting...");

  // Connect WiFi + register
  raamses.begin();

  delay(1000);
  draw_screen();
}

void loop() {
  raamses.loop();
  draw_screen();
  delay(100);
}

void draw_screen() {
  unsigned long now = millis();
  if (now - last_screen_update < SCREEN_UPDATE_INTERVAL_MS) return;
  last_screen_update = now;

  // Header bar
  uint16_t header_color = raamses.state.alert_active ? TFT_RED : TFT_NAVY;
  tft.fillRect(0, 0, 320, 30, header_color);
  tft.setTextColor(TFT_WHITE, header_color);
  tft.setTextSize(2);
  tft.setCursor(8, 8);
  tft.print("RAAMSES Monitor");

  if (raamses.state.alert_active) {
    tft.setTextColor(TFT_YELLOW, TFT_RED);
    tft.setTextSize(1);
    tft.setCursor(260, 12);
    tft.print("[!ALERT]");
  }

  // Stats panel
  int y = 40;
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextSize(1);

  tft.setCursor(10, y); tft.print("Gateway: " + String(GATEWAY_IP));
  y += 20;

  tft.setCursor(10, y);
  if (raamses.state.stats.valid) {
    tft.printf("CPU: %.1fC  %.1f%%", raamses.state.stats.cpu_temp_c, raamses.state.stats.cpu_percent);
  } else {
    tft.print("CPU: ---");
  }
  y += 20;

  tft.setCursor(10, y);
  if (raamses.state.stats.valid) {
    tft.printf("RAM: %.1f%%  %dMB free", raamses.state.stats.mem_used_percent, raamses.state.stats.mem_free_mb);
  } else {
    tft.print("RAM: ---");
  }
  y += 20;

  tft.setCursor(10, y);
  tft.printf("Agents: %d", raamses.state.stats.agents_registered);
  y += 20;

  tft.setCursor(10, y);
  if (raamses.state.stats.valid) {
    tft.print("Uptime: " + format_uptime(raamses.state.stats.uptime_seconds));
  } else {
    tft.print("Uptime: ---");
  }
  y += 25;

  // Divider
  tft.drawLine(10, y, 310, y, TFT_DARKGREY);
  y += 8;

  // Status panel
  tft.setTextColor(TFT_GREEN, TFT_BLACK);
  tft.setCursor(10, y);
  if (raamses.state.wifi_connected) {
    tft.print("WiFi: OK  IP: " + WiFi.localIP().toString());
  } else {
    tft.setTextColor(TFT_RED, TFT_BLACK);
    tft.print("WiFi: DISCONNECTED");
  }
  y += 20;

  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setCursor(10, y);
  tft.print("State: " + raamses.state.status_line);
  y += 20;

  // Heartbeat age
  if (raamses.state.registered && raamses.state.last_heartbeat > 0) {
    int hb_age = (now - raamses.state.last_heartbeat) / 1000;
    tft.setCursor(10, y);
    tft.printf("Last HB: %ds ago", hb_age);
  }

  // Alert box
  if (raamses.state.alert_active) {
    tft.fillRect(10, 200, 300, 35, TFT_DARKRED);
    tft.drawRect(10, 200, 300, 35, TFT_RED);
    tft.setTextColor(TFT_YELLOW, TFT_DARKRED);
    tft.setTextSize(2);
    tft.setCursor(20, 210);
    tft.print("AGENT NEEDS HELP");
  } else {
    tft.fillRect(10, 200, 300, 35, TFT_BLACK);
  }
}

String format_uptime(int seconds) {
  int d = seconds / 86400;
  int h = (seconds % 86400) / 3600;
  int m = (seconds % 3600) / 60;
  if (d > 0) return String(d) + "d " + String(h) + "h " + String(m) + "m";
  if (h > 0) return String(h) + "h " + String(m) + "m";
  return String(m) + "m";
}