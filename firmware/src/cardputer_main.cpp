/*
 * M5Stack Cardputer — Raamses Agent Monitor with Keyboard
 *
 * ESP32-S3 + keyboard + 1.14" IPS (240x135).
 * Shows agent stats AND lets you type messages to the agent.
 *
 * Hardware: M5Stack Cardputer
 *   - Built-in keyboard (56 keys, I2C)
 *   - 1.14" IPS LCD (240x135, ST7789)
 *   - microSD slot
 *
 * Modes:
 *   MONITOR — shows gateway stats + alert state (default)
 *   COMPOSE — type a message to send to the agent via POST /update
 *
 * Press Fn+Enter to toggle modes. In COMPOSE, type message, Enter to send.
 */
#include <M5Cardputer.h>
#include "RaamsesClient.h"

RaamsesClient raamses;

enum Mode { MODE_MONITOR, MODE_COMPOSE };
Mode current_mode = MODE_MONITOR;

String compose_buf = "";
unsigned long last_screen_update = 0;
bool screen_dirty = true;

void setup() {
  M5Cardputer.begin();
  M5Cardputer.Display.setRotation(1);
  M5Cardputer.Display.fillScreen(BLACK);

  M5Cardputer.Display.setTextColor(GREEN, BLACK);
  M5Cardputer.Display.setTextSize(2);
  M5Cardputer.Display.setCursor(5, 50);
  M5Cardputer.Display.println("RAAMSES");
  M5Cardputer.Display.setTextSize(1);
  M5Cardputer.Display.setCursor(5, 75);
  M5Cardputer.Display.println("Cardputer booting...");

  Serial.begin(115200);
  raamses.begin();
  delay(500);
  draw_screen();
}

void loop() {
  raamses.loop();

  // Handle keyboard
  M5Cardputer.update();
  if (M5Cardputer.Keyboard.isChange() && M5Cardputer.Keyboard.isPressed()) {
    Keyboard_Class::KeysState status = M5Cardputer.Keyboard.keysState();
    for (char c : status.word) {
      handle_key(c, status.fn);
    }
    screen_dirty = true;
  }

  if (screen_dirty || (millis() - last_screen_update > SCREEN_UPDATE_INTERVAL_MS)) {
    draw_screen();
  }
  delay(50);
}

void handle_key(char c, bool fn) {
  if (fn && (c == '\n' || c == '\r')) {
    // Fn+Enter — toggle mode
    current_mode = (current_mode == MODE_MONITOR) ? MODE_COMPOSE : MODE_MONITOR;
    compose_buf = "";
    return;
  }

  if (current_mode != MODE_COMPOSE) return;

  if (c == '\n' || c == '\r') {
    // Enter — send message
    if (compose_buf.length() > 0) {
      raamses.send_update(compose_buf, -1);
      compose_buf = "";
      current_mode = MODE_MONITOR;
    }
    return;
  }

  if (c == 8) {  // Backspace
    if (compose_buf.length() > 0) compose_buf.remove(compose_buf.length() - 1);
    return;
  }

  if (c >= 32 && c < 127) {
    if (compose_buf.length() < 120) compose_buf += c;
  }
}

void draw_screen() {
  last_screen_update = millis();
  screen_dirty = false;

  auto& d = M5Cardputer.Display;

  // Header
  uint16_t hdr = raamses.state.alert_active ? RED : NAVY;
  d.fillRect(0, 0, 240, 18, hdr);
  d.setTextColor(WHITE, hdr);
  d.setTextSize(1);
  d.setCursor(3, 4);
  d.print("RAAMSES");
  if (raamses.state.alert_active) {
    d.setTextColor(YELLOW, RED);
    d.setCursor(190, 4);
    d.print("[!ALERT]");
  }

  if (current_mode == MODE_MONITOR) {
    draw_monitor(d);
  } else {
    draw_compose(d);
  }

  // Footer
  d.fillRect(0, 125, 240, 10, DARKGREY);
  d.setTextColor(WHITE, DARKGREY);
  d.setTextSize(1);
  d.setCursor(3, 127);
  d.print("Fn+Enter: ");
  d.print(current_mode == MODE_MONITOR ? "Compose" : "Monitor");
}

void draw_monitor(M5Display& d) {
  int y = 22;
  d.setTextColor(WHITE, BLACK);
  d.setTextSize(1);

  d.setCursor(3, y);
  d.printf("GW:%s:%d", GATEWAY_IP, GATEWAY_PORT);
  y += 12;

  d.setCursor(3, y);
  if (raamses.state.stats.valid) {
    d.printf("CPU:%.1fC %.1f%%  Agt:%d",
      raamses.state.stats.cpu_temp_c,
      raamses.state.stats.cpu_percent,
      raamses.state.stats.agents_registered);
  } else {
    d.print("Waiting for stats...");
  }
  y += 12;

  d.setCursor(3, y);
  if (raamses.state.stats.valid) {
    d.printf("RAM:%.1f%% %dMB free",
      raamses.state.stats.mem_used_percent,
      raamses.state.stats.mem_free_mb);
  }
  y += 12;

  d.setCursor(3, y);
  d.setTextColor(raamses.state.wifi_connected ? GREEN : RED, BLACK);
  d.printf("WiFi:%s", raamses.state.wifi_connected ? "OK" : "FAIL");
  d.setTextColor(WHITE, BLACK);
  y += 12;

  d.setCursor(3, y);
  d.print(raamses.state.status_line);
  y += 15;

  // Alert box
  if (raamses.state.alert_active) {
    d.fillRect(3, 95, 234, 25, MAROON);
    d.drawRect(3, 95, 234, 25, RED);
    d.setTextColor(YELLOW, MAROON);
    d.setTextSize(2);
    d.setCursor(10, 100);
    d.print("AGENT NEEDS HELP");
    d.setTextSize(1);
  } else {
    d.fillRect(3, 95, 234, 25, BLACK);
  }
}

void draw_compose(M5Display& d) {
  d.fillRect(0, 20, 240, 100, BLACK);
  d.setTextColor(CYAN, BLACK);
  d.setTextSize(1);
  d.setCursor(3, 22);
  d.print("COMPOSE MSG TO AGENT:");
  d.setTextColor(WHITE, BLACK);
  d.setCursor(3, 38);

  // Word-wrap simple
  String line = "";
  int lineY = 38;
  for (int i = 0; i < compose_buf.length() && lineY < 115; i++) {
    line += compose_buf[i];
    if (line.length() >= 28) {
      d.setCursor(3, lineY);
      d.print(line);
      line = "";
      lineY += 12;
    }
  }
  if (line.length() > 0 && lineY < 115) {
    d.setCursor(3, lineY);
    d.print(line);
  }

  // Cursor
  if (millis() % 1000 < 500) {
    d.print("_");
  }
}