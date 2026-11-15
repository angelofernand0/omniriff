# OmniRiff Pedal Firmware

The [Arduino sketch](arduino/Footswitch/Footswitch.ino) sends loop, practice, and bypass actions to the laptop over USB serial at **115200 baud**.

<!-- TODO(Aditya): Confirm the switch count, board pin labels and action mapping on the physical hardware build. -->

## 1. Parts and wiring

- Arduino board with two digital inputs and USB serial. Select the exact model when flashing.
- Two normally open momentary switches with dry contacts, hookup wire, and a matching data-capable USB cable.
- Optional breadboard or pedal enclosure.

Unplug the Arduino before wiring. Each switch goes between its own digital input and shared Arduino GND. `INPUT_PULLUP` holds the input HIGH when the switch is open. Closing the switch pulls that input LOW. Confirm the pin labels on the actual board before connecting.

```text
Digital pin 2 ---- normally open loop/practice switch ---- GND
Digital pin 3 ---- normally open bypass switch ----------- GND
```

If using a Grove button module and shield, verify the module's pinout, supply voltage, and output polarity first. The wiring above is for dry contacts. An active-HIGH module will need a polarity change in the sketch before it will behave as described here.

## 2. Flash on Windows with Arduino IDE

1. Install [Arduino IDE](https://www.arduino.cc/en/software) and connect the board directly with a data-capable USB cable.
2. Open [`Footswitch.ino`](arduino/Footswitch/Footswitch.ino). Use the board selector to choose the exact board and its `COM` port. Install the board package if prompted. If more than one port appears, unplug and reconnect the Arduino to identify its port.
3. Quit any running engine, pedal tester, or other program using the port. Click **Verify**, then **Upload** and check for a successful upload. See [Arduino’s upload guide](https://support.arduino.cc/hc/en-us/articles/4733418441116-Upload-a-sketch-in-Arduino-IDE) for board selection details.
4. Open **Serial Monitor**, set **115200 baud**, and wait for the sketch to start. Opening a serial connection can reset some boards. Close Serial Monitor before opening the tester or engine.

## 3. Expected output

After a reset, try these actions in order. Each emits one newline-terminated JSON object. `seq` starts at 0 on reset and increments for each event.

| Input | Expected action |
| --- | --- |
| Release the loop switch after a tap shorter than 700 ms | `loop` on release |
| Hold the loop switch at least 700 ms | One `practice`, with no `loop` on release |
| Press the bypass switch | `bypass` on press |

```json
{"seq":0,"type":"action","control":"loop"}
{"seq":1,"type":"action","control":"practice"}
{"seq":2,"type":"action","control":"bypass"}
```

The sketch uses 25 ms debounce. A switch held during reset must be released and pressed again before it sends an action. In the full rig, `practice` can start a session or approve a pending change from Riff.

### Standalone serial test

If your checkout includes `tools.serialcheck`, close Serial Monitor and run these commands from the repository root. Replace `COM3` with the actual port.

```powershell
python -m pip install "pyserial>=3.5,<4"
python -m tools.serialcheck --port COM3
```

Expect `TAP -> loop`, `HOLD -> practice`, and `PRESS -> bypass`. The tester prints `seq`, time since listening started, and the gap since the previous valid event, all timed on the host. The board sends no press timestamp or duration. If the tester is unavailable, use the raw JSON in Serial Monitor instead.

Stop the tester with **Ctrl+C** before starting `python -m engine --serial-port COM3` or `python -m engine.demo --serial-port COM3`.

## 4. Troubleshooting

| Symptom | Check |
| --- | --- |
| No COM port | Try a known data cable and another USB port. Check **Device Manager → Ports (COM & LPT)** and follow the board vendor’s driver instructions if Windows shows an error. |
| Verify or upload fails | Confirm the board model, board package, and COM port. Close other programs using the port. See [Arduino’s upload troubleshooting](https://support.arduino.cc/hc/en-us/articles/4403365313810-If-your-sketch-doesn-t-upload). |
| Access denied or port busy | Close Serial Monitor, the tester, and the engine. Then start only the program you want to use. |
| Garbled output | Set Serial Monitor to **115200 baud** and verify that the port belongs to the pedal. |
| Missing or inverted events | Check the ground and pin mapping. Verify the contact closes on press, or check the Grove module’s output polarity. Release switches held through reset. |
| Tap works but hold emits no `practice` | Flash the current sketch, hold the loop switch for at least 700 ms, and check the raw output before starting the engine. |
