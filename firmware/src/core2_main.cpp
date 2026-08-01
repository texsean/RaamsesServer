/*
 * M5Stack Core2 — Raamses Agent Monitor with Touch
 *
 * ESP32 + 2" capacitive touch LCD (320x240, ILI9341).
 * Shows agent stats with touch buttons for actions.
 *
 * Hardware: M5Stack Core2
 *   - 2" capacitive touch (FT6336U)
 *   - Built-in IMU, mic, RTC, AXP192 power
 *   - SD card slot
 *
 * Touch zones:
 *   Top half    — Monitor view (stats display)
 *   Btn "STATS" — Force refresh GET /stats
 *   Btn "ALERT" — Trigger test alert
 *   Btn "CLR"   — Clear alert
 */
#include <M5Core2.h>
#include "RaamsesClient.h"

RaamsesClient raamses;
unsigned long last_screen_update = 0;
bool screen_dirty = true;

// Touch button regions (x, y, w, h)
struct Btn { int x, y, w, h; const char* label; uint16_t color; };
Btn buttons[] = {
  {10,  200, 95, 35, "STATS", BLUE},
  {115, 200, 95, 35, "ALERT", RED},
  {220, 200, 90, 35, "CLR",   GREEN},
};

void setup() {
  M5.begin(true, true, true, true);  // LCD, SD, Serial, I2C
  M5.Lcd.setRotation(1);
  M5.Lcd.fillScreen(BLACK);

  M5.Lcd.setTextColor(CYAN, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(80, 100);
  M5.Lcd.println("RAAMSES");
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(60, 125);
  M5.Lcd.println("Core2 booting...");

  Serial.begin(115200);
  raamses.begin();
  delay(500);
  draw_screen();
}

void loop() {
  raamses.loop();
  M5.update();

  // Touch handling
  if (M5.Touch.wasPressed) {
    TouchPoint tp = M5.Touch.getPressPoint();
    for (int i = 0; i < 3; i++) {
      if (tp.x >= buttons[i].x && tp.x < buttons[i].x + buttons[i].w &&
          tp.y >= buttons[i].y && tp.y < buttons[i].y + buttons[i].h) {
        handle_button(i);
        screen_dirty = true;
        break;
      }
    }
  }

  if (screen_dirty || (millis() - last_screen_update > SCREEN_UPDATE_INTERVAL_MS)) {
    draw_screen();
  }
  delay(50);
}

void handle_button(int idx) {
  switch (idx) {
    case 0:  // STATS — force refresh
      raamses.fetch_stats();
      break;
    case 1:  // ALERT — trigger test alert
      raamses.send_update("test alert from Core2", -1, "Agent needs help");
      break;
    case 2:  // CLR — clear alert
      raamses.send_update("", -1, "");  // empty alert clears
      break;
  }
}

void draw_screen() {
  last_screen_update = millis();
  screen_dirty = false;

  auto& lcd = M5.Lcd;

  // Header
  uint16_t hdr = raamses.state.alert_active ? RED : NAVY;
  lcd.fillRect(0, 0, 320, 28, hdr);
  lcd.setTextColor(WHITE, hdr);
  lcd.setTextSize(2);
  lcd.setCursor(8, 6);
  lcd.print("RAAMSES Monitor");
  if (raamses.state.alert_active) {
    lcd.setTextColor(YELLOW, RED);
    lcd.setTextSize(1);
    lcd.setCursor(255, 10);
    lcd.print("[!ALERT]");
  }

  // Stats panel
  int y = 35;
  lcd.setTextColor(WHITE, BLACK);
  lcd.setTextSize(1);

  lcd.setCursor(8, y);
  lcd.printf("Gateway: %s:%d", GATEWAY_IP, GATEWAY_PORT);
  y += 18;

  lcd.setCursor(8, y);
  if (raamses.state.stats.valid) {
    lcd.printf("CPU: %.1fC  %.1f%%", raamses.state.stats.cpu_temp_c, raamses.state.stats.cpu_percent);
  } else {
    lcd.print("CPU: waiting...");
  }
  y += 18;

  lcd.setCursor(8, y);
  if (raamses.state.stats.valid) {
    lcd.printf("RAM: %.1f%%  %dMB free", raamses.state.stats.mem_used_percent, raamses.state.stats.mem_free_mb);
  }
  y += 18;

  lcd.setCursor(8, y);
  lcd.printf("Agents: %d", raamses.state.stats.agents_registered);
  y += 18;

  lcd.setCursor(8, y);
  if (raamses.state.stats.valid) {
    lcd.print("Uptime: " + format_uptime(raamses.state.stats.uptime_seconds));
  }
  y += 22;

  // Status
  lcd.setTextColor(raamses.state.wifi_connected ? GREEN : RED, BLACK);
  lcd.setCursor(8, y);
  lcd.printf("WiFi: %s", raamses.state.wifi_connected ? "OK" : "FAIL");
  y += 18;

  lcd.setTextColor(WHITE, BLACK);
  lcd.setCursor(8, y);
  lcd.print(raamses.state.status_line);
  y += 18;

  // Alert box
  if (raamses.state.alert_active) {
    lcd.fillRect(8, 150, 304, 40, MAROON);
    lcd.drawRect(8, 150, 304, 40, RED);
    lcd.setTextColor(YELLOW, MAROON);
    lcd.setTextSize(2);
    lcd.setCursor(15, 160);
    lcd.print("AGENT NEEDS HELP");
    lcd.setTextSize(1);
  } else {
    lcd.fillRect(8, 150, 304, 40, BLACK);
  }

  // Touch buttons
  for (int i = 0; i < 3; i++) {
    lcd.fillRect(buttons[i].x, buttons[i].y, buttons[i].w, buttons[i].h, buttons[i].color);
    lcd.setTextColor(WHITE, buttons[i].color);
    lcd.setTextSize(2);
    lcd.setCursor(buttons[i].x + 15, buttons[i].y + 10);
    lcd.print(buttons[i].label);
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