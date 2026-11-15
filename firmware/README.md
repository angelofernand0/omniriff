# OmniRiff Pedal Firmware

This directory contains the Arduino firmware for the OmniRiff physical pedal controller. The sketch runs on standard Arduino boards (Uno, Nano, Mega, or compatible) and communicates with the OmniRiff engine over USB Serial at **115200 baud**.

<!-- TODO(Aditya): Confirm the switch count, board pin labels and action mapping on the physical hardware build. -->

---

## 1. Hardware Parts List

- **Microcontroller:** Arduino Uno, Nano, or compatible ATmega328P board
- **Pedal Switches:** 2× momentary SPST footswitches (normally open / push-to-make)
  - Switch 1: Loop / Practice switch
  - Switch 2: Bypass toggle switch
- **Wiring:** Hookup wire (22–24 AWG stranded or solid core)
- **Host Connection:** USB cable (USB-A to Type-B / Mini / Micro depending on board)
- **Optional:** Breadboard or sturdy stompbox pedal enclosure

---

## 2. Wiring Diagram

Both pedal switches use the internal ATmega pull-up resistors (`INPUT_PULLUP`). One lug connects to the designated digital input pin; the other lug connects to `GND`. No external pull-up or pull-down resistors are required.

```
       +------------------------------------+
       |            Arduino Board           |
       |                                    |
       |  [Pin 2] --------+                 |
       |                  |                 |
       |  [Pin 3] ------------------+       |
       |                  |         |       |
       |  [ GND ] --------+---------+       |
       +------------------|---------|-------+
                          |         |
                  +-------+         +-------+
                  |                         |
            +------------+            +------------+
            |  SW1 (NO)  |            |  SW2 (NO)  |
            |   [Loop]   |            |  [Bypass]  |
            +------------+            +------------+
                  |                         |
                  +-----------+-------------+
                              |
                            (GND)
```

### Pin Assignment Table

| Pin | Switch Name | Function | Normal State | Pressed State | Internal Resistor |
|---|---|---|---|---|---|
| **Pin 2** | Loop / Practice | Tap: `loop`<br>Hold (≥700 ms): `practice` | `HIGH` (3.3V / 5V) | `LOW` (GND) | `INPUT_PULLUP` |
| **Pin 3** | Bypass | Press: `bypass` | `HIGH` (3.3V / 5V) | `LOW` (GND) | `INPUT_PULLUP` |
| **GND** | Common Ground | Shared return rail for both switches | 0V | 0V | — |

---

## 3. Flashing Firmware (Windows / macOS / Linux)

### Using Arduino IDE

1. **Install Arduino IDE:** Download from [arduino.cc](https://www.arduino.cc/en/software) if not already installed.
2. **Open the Sketch:** Open [`firmware/arduino/Footswitch/Footswitch.ino`](arduino/Footswitch/Footswitch.ino).
3. **Select Board:** Go to **Tools → Board → Arduino AVR Boards → Arduino Uno** (or **Arduino Nano**).
4. **Select Port:** Go to **Tools → Port** and choose your device:
   - Windows: `COM3`, `COM4`, etc. (check Windows Device Manager if uncertain)
   - macOS: `/dev/cu.usbserial-*` or `/dev/cu.usbmodem*`
   - Linux: `/dev/ttyUSB0` or `/dev/ttyACM0`
5. **Verify & Upload:** Click the **Upload** button (or press `Ctrl+U` / `Cmd+U`).
6. **Baud Rate:** The firmware operates at **115200 baud** (`kBaudRate = 115200`).

---

## 4. Serial Protocol & Expected Lines

The sketch emits single-line JSON action objects terminated by `\n` (`LF`):

```json
{"seq":0,"type":"action","control":"loop"}
```

Each event increments the monotonic sequence counter `seq`.

### Action Mappings & Timing

- **Tap Loop Switch (Pin 2):**
  - Hold duration: **< 700 ms** (released before hold threshold)
  - Emits: `{"seq":N,"type":"action","control":"loop"}` on release edge.
- **Hold Loop Switch (Pin 2):**
  - Hold duration: **≥ 700 ms** (`kPracticeHoldMs = 700`)
  - Emits: `{"seq":N,"type":"action","control":"practice"}` as soon as the 700 ms threshold is reached (before release).
- **Press Bypass Switch (Pin 3):**
  - Emits: `{"seq":N,"type":"action","control":"bypass"}` immediately on debounced press edge.
- **Debounce Window:** 25 ms (`kDebounceMs = 25`) on all state transitions to prevent mechanical contact bounce.
- **Boot/Reset Protection:** If a switch is held down while plugging in or resetting the Arduino, the firmware marks it as stable and ignores it until released, preventing accidental latching.

---

## 5. Verification

### Step 1: Footswitch / Pedal Tester (`tools.serialcheck`)
Before starting the full audio engine, test the pedal with the standalone serial tester:
```bash
# Windows
python -m tools.serialcheck --port COM3

# macOS / Linux
python -m tools.serialcheck --port /dev/cu.usbserial-10
```
Expected output:
- Tapping Pin 2 displays: `TAP → loop (+0.0ms)`
- Holding Pin 2 displays: `HOLD → practice (+702.4ms)`
- Pressing Pin 3 displays: `PRESS → bypass (+0.0ms)`

### Step 2: Audio Engine Integration
Run the audio engine with serial enabled:
```bash
python -m engine --serial-port COM3
```
Or start the full demo:
```bash
python -m engine.demo --serial-port COM3
```

---

## 6. Troubleshooting

| Symptom | Cause | Solution |
|---|---|---|
| **No COM port in IDE or Device Manager** | Missing USB-to-UART driver or bad cable | Check cable is data-capable (not power-only). Install CH340 or FTDI drivers for clone boards. Check Windows Device Manager under *Ports (COM & LPT)*. |
| **Garbage / gibberish characters in Serial Monitor** | Baud rate mismatch | Ensure receiver/monitor is configured to **115200 baud** (sketch default). |
| **No event emitted when pressing switch** | Loose ground or open circuit | Verify continuity between Arduino GND rail and switch terminal. Confirm Pin 2 or Pin 3 connection. |
| **Switch doesn't trigger on boot** | Held down during reset | Normal safety behavior: release the switch completely; subsequent presses will register cleanly. |
| **Access denied / port busy** | Port locked by another program | Close Arduino Serial Monitor, Cura, or existing engine instances before running `tools.serialcheck` or `engine`. |
