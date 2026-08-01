/*
 * Watchy 2.0 — Raamses E-Paper Watch Monitor
 *
 * ESP32 + 1.28" e-paper (200x200, SSD1680).
 * Ultra-low power: wakes every 5 min, registers, heartbeats, displays, sleeps.
 *
 * Hardware: Watchy 2.0
 *   - 1.28" e-paper display (200x200, SSD1680)
 *   - RTC (PCF8563), buttons (4), buzzer, IMU (MPU6050)
 *   - Battery powered (CR2025 or LiPo)
 *
 * Power profile:
 *   - Wake from deep sleep every DEEP_SLEEP_SEC (300 = 5 min)
 *   - Connect WiFi, register/heartbeat, fetch stats
 *     - Display: time, CPU temp, agent count, alert
 *   - Deep sleep
 *   - Total awake time: ~8-12 seconds per cycle
 *
 * Button actions (during awake window):
 *   - MENU: Force stats refresh + stay awake 30s
 *   - BACK: Immediate sleep
 *   - UP: Trigger alert
 *   - DOWN: Clear alert
 */
#include "RaamsesClient.h"
#include <driver/rtc_io.h>

// E-paper driver for Watchy 2.0 (SSD1680)
// Using GxEPD2 library for the 1.28" display
#include <GxEPD2_BW.h>
#include <GxEPD2_3C.h>
#include <Adafruit_GFX.h>

// Watchy 2.0 pin definitions
#define EPD_CS    5
#define EPD_DC    10
#define EPD_RST   9
#define EPD_BUSY  19
#define EPD_SCK   18
#define EPD_MOSI  23

// Button pins (active low)
#define BTN_1 26   // MENU
#define BTN_2 25    // BACK
#define BTN_3 32    // UP
#define BTN_4 33    // DOWN

GxEPD2_BW<GxEPD2_154_D67, GxEPD2_154_D67::HEIGHT> display(
  GxEPD2_154_D67(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY)
);

RaamsesClient raamses;
unsigned long wake_time = 0;
bool stay_awake = false;

void setup() {
  Serial.begin(115200);

  // Initialize e-paper
  display.init();
  display.setRotation(0);
  display.fillScreen(GxEPD_WHITE);
  display.setTextColor(GxEPD_BLACK);
  display.setTextSize(2);
  display.setCursor(30, 90);
  display.println("RAAMSES");
  display.setTextSize(1);
  display.setCursor(30, 110);
  display.println("Watchy booting...");
  display.display(true);  // partial refresh

  // Wake timestamp
  wake_time = millis();

  // Connect and register
  raamses.begin();
  delay(500);

  // Try fetch stats
  raamses.fetch_stats();
  draw_screen();
}

void loop() {
  raamses.loop();

  // Check buttons (active low)
  if (digitalRead(BTN_1) == LOW) {
    // MENU — refresh + stay awake
    raamses.fetch_stats();
    draw_screen();
    stay_awake = true;
  }
  if (digitalRead(BTN_2) == LOW) {
    // BACK — immediate sleep
    go_sleep();
  }
  if (digitalRead(BTN_3) == LOW) {
    // UP — trigger alert
    raamses.send_update("alert from watch", -1, "Agent needs help");
    delay(500);
    raamses.send_heartbeat();
    draw_screen();
  }
  if (digitalRead(BTN_4) == LOW) {
    // DOWN — clear alert
    raamses.send_update("", -1, "");
    delay(500);
    raamses.send_heartbeat();
    draw_screen();
  }

  // Auto-sleep after 15s unless button pressed
  if (!stay_awake && (millis() - wake_time > 15000)) {
    go_sleep();
  }

  // If staying awake, refresh screen periodically
  if (stay_awake && (millis() - wake_time > 30000)) {
    stay_awake = false;
    go_sleep();
  }

  delay(200);
}

void draw_screen() {
  display.fillScreen(GxEPD_WHITE);
  display.setTextColor(GxEPD_BLACK);

  // Header
  display.setTextSize(2);
  display.setCursor(10, 20);
  display.println("RAAMSES");

  display.setTextSize(1);
  display.setCursor(10, 40);
  if (raamses.state.alert_active) {
    display.fillRect(5, 38, 190, 16, GxEPD_BLACK);
    display.setTextColor(GxEPD_WHITE);
    display.print(" !! AGENT NEEDS HELP !!");
    display.setTextColor(GxEPD_BLACK);
  } else {
    display.print("All clear");
  }

  // Time
  display.setCursor(10, 62);
  display.printf("%02d:%02d", hour(), minute());

  // Stats
  display.setCursor(10, 80);
  if (raamses.state.stats.valid) {
    display.printf("CPU: %.1fC", raamses.state.stats.cpu_temp_c);
  } else {
    display.print("CPU: ---");
  }

  display.setCursor(10, 95);
  display.printf("Agents: %d", raamses.state.stats.agents_registered);

  display.setCursor(10, 110);
  display.printf("RAM: %.1f%%", raamses.state.mem_used_percent);

  // Status
  display.setCursor(10, 130);
  display.setTextColor(raamses.state.wifi_connected ? GxEPD_BLACK : GxEPD_RED);
  display.printf("WiFi: %s", raamses.state.wifi_connected ? "OK" : "FAIL");

  display.setCursor(10, 145);
  display.setTextColor(GxEPD_BLACK);
  String st = raamses.state.status_line;
  if (st.length() > 25) st = st.substring(0, 25);
  display.print(st);

  // Footer
  display.setCursor(10, 175);
  display.setTextColor(GxEPD_DARKGREY);
  display.printf("GW:%s", GATEWAY_IP);

  display.display(false);  // full refresh for e-paper
}

void go_sleep() {
  display.hibernate();
  WiFi.mode(WIFI_OFF);
  btStop();

  // Configure wake sources
  esp_sleep_enable_timer_wakeup(DEEP_SLEEP_SEC * 1000000ULL);

  // Button wake (active low)
  esp_sleep_enable_ext0_wakeup(GPIO_NUM_26, 0);  // BTN_1

  esp_deep_sleep_start();
}

// Simple time (no RTC lib — just use compile time offset)
int hour() {
  return ((millis() / 1000) / 3600) % 24;
}
int minute() {
  return ((millis() / 1000) / 60) % 60;
}