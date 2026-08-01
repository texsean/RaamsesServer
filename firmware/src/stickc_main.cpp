/*
 * M5Stack StickC Plus2 — Raamses Pocket Monitor
 *
 * ESP32-PICO + 0.96" TFT (80x160, ST7735) + buttons.
 * Compact display: shows CPU temp, agents, alert state.
 *
 * Hardware: M5Stack StickC Plus2
 *   - 0.96" TFT (80x160, ST7735)
 *   - Button A (M5 button) + Button B (side)
 *   - IMU (MPU6886), mic, IR, RTC
 *   - Battery (AXP192)
 *
 * Button A: Force stats refresh
 * Button B: Toggle rotation
 */
#include <M5StickCPlus2.h>
#include "RaamsesClient.h"

RaamsesClient raamses;
unsigned long last_screen_update = 0;
bool screen_dirty = true;
int rotation = 3;  // portrait mode for StickC

void setup() {
  M5.begin();
  M5.Lcd.setRotation(rotation);
  M5.Lcd.fillScreen(BLACK);

  M5.Lcd.setTextColor(GREEN, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(5, 30);
  M5.Lcd.println("RAAMSES");
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(5, 55);
  M5.Lcd.println("StickC boot...");

  Serial.begin(115200);
  raamses.begin();
  delay(500);
  draw_screen();
}

void loop() {
  raamses.loop();
  M5.update();

  // Button A — force stats refresh
  if (M5.BtnA.wasPressed()) {
    raamses.fetch_stats();
    screen_dirty = true;
  }

  // Button B — toggle rotation
  if (M5.BtnB.wasPressed()) {
    rotation = (rotation == 3) ? 1 : 3;
    M5.Lcd.setRotation(rotation);
    M5.Lcd.fillScreen(BLACK);
    screen_dirty = true;
  }

  if (screen_dirty || (millis() - last_screen_update > SCREEN_UPDATE_INTERVAL_MS)) {
    draw_screen();
  }
  delay(50);
}

void draw_screen() {
  last_screen_update = millis();
  screen_dirty = false;

  auto& lcd = M5.Lcd;

  // Header
  uint16_t hdr = raamses.state.alert_active ? RED : NAVY;
  lcd.fillRect(0, 0, 160, 14, hdr);
  lcd.setTextColor(WHITE, hdr);
  lcd.setTextSize(1);
  lcd.setCursor(2, 3);
  lcd.print("RAAMSES");
  if (raamses.state.alert_active) {
    lcd.setTextColor(YELLOW, RED);
    lcd.setCursor(130, 3);
    lcd.print("!");
  }

  // Stats — compact for 80x160 (portrait)
  int y = 18;
  lcd.setTextColor(WHITE, BLACK);
  lcd.setTextSize(1);

  lcd.setCursor(2, y);
  lcd.printf("CPU:%.1fC", raamses.state.stats.valid ? raamses.state.stats.cpu_temp_c : 0);
  y += 12;

  lcd.setCursor(2, y);
  lcd.printf("Agt:%d", raamses.state.stats.valid ? raamses.state.stats.agents_registered : 0);
  y += 12;

  lcd.setCursor(2, y);
  lcd.printf("RAM:%.0f%%", raamses.state.stats.valid ? raamses.state.stats.mem_used_percent : 0);
  y += 15;

  // Status
  lcd.setTextColor(raamses.state.wifi_connected ? GREEN : RED, BLACK);
  lcd.setCursor(2, y);
  lcd.printf("WiFi:%s", raamses.state.wifi_connected ? "OK" : "FL");
  y += 12;

  lcd.setTextColor(WHITE, BLACK);
  lcd.setCursor(2, y);
  // Truncate status to fit
  String st = raamses.state.status_line;
  if (st.length() > 20) st = st.substring(0, 20);
  lcd.print(st);
  y += 12;

  // Alert zone
  if (raamses.state.alert_active) {
    lcd.fillRect(2, 100, 156, 30, MAROON);
    lcd.drawRect(2, 100, 156, 30, RED);
    lcd.setTextColor(YELLOW, MAROON);
    lcd.setTextSize(1);
    lcd.setCursor(8, 108);
    lcd.print("AGENT NEEDS");
    lcd.setCursor(8, 120);
    lcd.print("HELP!");
  } else {
    lcd.fillRect(2, 100, 156, 30, BLACK);
  }

  // Footer
  lcd.setTextColor(DARKGREY, BLACK);
  lcd.setCursor(2, 148);
  lcd.print("A:ref B:rot");
}