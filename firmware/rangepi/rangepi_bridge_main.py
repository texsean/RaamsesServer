# Raamses RangePi Bridge Firmware
# Upload this as main.py to the RangePi using mpremote or Thonny.
#
# This firmware turns the RangePi into a bidirectional LoRa modem:
#   USB serial (115200 baud) <-> LoRa UART (9600 baud)
#
# The Pi host writes raw Raamses binary packets to /dev/ttyACM0,
# the RangePi forwards them to the LoRa module for transmission.
# Incoming LoRa packets are forwarded back to the Pi over USB serial.
#
# Protocol: raw binary, same wire format as rgs.lora.protocol:
#   [cmd:u8] [len:u8] [payload:len bytes]
#
# The host Python code handles framing/deframing via parse_packet().
# The RangePi just pipes bytes both directions.
#
# Hardware:
#   - RP2040 (Pico) with LoRa module on UART(0) at 9600 baud
#   - LoRa mode pins: Mode0=Pin(2), Mode1=Pin(3)
#   - Normal/transparent mode: Mode0=0, Mode1=0
#   - 1.14" ST7789 LCD for status display

import utime
import time
from machine import UART, SPI, Pin
import sys

# --- LCD Setup (optional, fail gracefully) ---
try:
    import st7789
    import vga1_16x32 as font
    import vga1_16x16 as font2
    spi = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
    tft = st7789.ST7789(
        spi, 135, 240,
        reset=Pin(12, Pin.OUT), cs=Pin(9, Pin.OUT),
        dc=Pin(8, Pin.OUT), backlight=Pin(13, Pin.OUT),
        rotation=1
    )
    HAS_LCD = True
except Exception:
    HAS_LCD = False

# --- LoRa Mode pins ---
Mode0 = Pin(2, Pin.OUT)
Mode1 = Pin(3, Pin.OUT)
# Normal/transparent mode (M1=0, M0=0)
Mode0.value(0)
Mode1.value(0)

# --- LoRa UART (9600 baud to LoRa module) ---
lora = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))

# --- USB serial (use sys.stdin/sys.stdout buffer) ---
# On RP2040, USB CDC is the default stdin/stdout
# We use select on stdin for non-blocking reads
import select

# --- State ---
rx_count = 0      # packets received from LoRa
tx_count = 0      # packets sent to LoRa
last_display = 0

def init_display():
    if not HAS_LCD:
        return
    tft.init()
    utime.sleep(0.2)
    tft.fill(0)
    tft.text(font, "RAAMSES", 5, 5, st7789.CYAN)
    tft.text(font, "BRIDGE", 5, 35, st7789.CYAN)
    tft.text(font2, "USB<->LoRa", 5, 70, st7789.WHITE)
    tft.text(font2, "TX:0 RX:0", 5, 90, st7789.GREEN)

def update_display():
    if not HAS_LCD:
        return
    tft.fill_rect(0, 90, 240, 16, 0)  # clear old count
    tft.text(font2, "TX:{} RX:{}".format(tx_count, rx_count), 5, 90, st7789.GREEN)

def get_timestamp():
    t = time.ticks_ms()
    ms = t % 1000
    s = (t // 1000) % 60
    m = (t // 60000) % 60
    return "{:02d}:{:02d}.{:03d}".format(m, s, ms)

# --- Main ---
init_display()

print("=== Raamses RangePi Bridge Started ===")
print("USB serial (115200) <-> LoRa UART (9600)")
print("Transparent mode (M0=0, M1=0)")
print()

# Buffer for incomplete LoRa reads
lora_buf = bytearray()

while True:
    # --- USB -> LoRa (host writes binary packets) ---
    # Check if data is available on USB serial
    if select.select([sys.stdin], [], [], 0)[0]:
        # Read available data from USB serial
        data = sys.stdin.buffer.read(1)  # read one byte at a time
        if data:
            # Read more if available
            more = sys.stdin.buffer.read(256) if select.select([sys.stdin], [], [], 0)[0] else b''
            if more:
                data = data + more
            lora.write(data)
            tx_count += 1
            print("[{}] TX->LoRa: {} bytes {}".format(
                get_timestamp(), len(data),
                ' '.join('{:02x}'.format(b) for b in data[:20])
            ))
            update_display()

    # --- LoRa -> USB (incoming LoRa packets) ---
    if lora.any():
        data = lora.read()
        if data:
            rx_count += 1
            # Write raw bytes to USB serial
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            print()  # newline after binary data
            print("[{}] RX<-LoRa: {} bytes {}".format(
                get_timestamp(), len(data),
                ' '.join('{:02x}'.format(b) for b in data[:20])
            ))
            update_display()

    utime.sleep(0.005)  # 5ms — keep latency low but avoid busy loop