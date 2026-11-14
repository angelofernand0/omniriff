# OmniRiff hardware mapping

Fill in this sheet during bring-up. The audio host is a Windows 11 laptop with a Focusrite Scarlett Solo (3rd gen). The Arduino model, switches, cables and camera are pending confirmation.

| Item | Actual hardware or setting |
| --- | --- |
| Arduino model and Arduino IDE board selection | TODO |
| USB data cable and Windows COM port | TODO |
| Footswitch count and contact type | TODO |
| Guitar, instrument cable and headphones or monitors | TODO |
| Webcam / position | TODO |

## Footswitch wiring and mapping

The draft assumes two normally open momentary switches with dry contacts. With the board unplugged, wire each switch between its input pin and Arduino GND. The sketch enables internal pull-ups, so a press reads LOW. Confirm the printed pin labels against the actual board. Check the contact pairs with a continuity meter if the switch terminals are unlabeled.

| Action | Draft pin | Confirmed pin and switch label |
| --- | --- | --- |
| Loop toggle | D2 | TODO |
| Bypass toggle | D3 | TODO |

Edit `kLoopPin`, `kBypassPin`, and the `switches` list in `firmware/arduino/Footswitch/Footswitch.ino` once the mapping is confirmed. If only one switch is available, remove the unused entry from `switches` and note which action remains available on the pedal.

## Flash and check

1. Open `firmware/arduino/Footswitch/Footswitch.ino` in Arduino IDE. Select the actual board and COM port, then verify and upload.
2. Open Serial Monitor at **115200 baud**. The first stable press after reset should print one line with `seq` 0. The second action should have `seq` 1 regardless of which switch was used.

   ```json
   {"seq":0,"type":"action","control":"loop"}
   {"seq":1,"type":"action","control":"bypass"}
   ```

3. Hold each switch, release it, and press again. Only presses that settle for 25 ms should emit a line. Reset with a switch held and check that it emits only after release and a new press. Reset again and confirm the sequence restarts at 0.
4. Close Serial Monitor before opening the engine's serial adapter. Check that each switch triggers its mapped action once, including across a reset or reconnect. The adapter adds the host timestamp, `version` and `source` per [the protocol](../protocol/README.md).

## Gesture notes for the vision owner

Record the playing hand and fretting hand, the positions that are usually visible while playing, and a deliberate clutch gesture that does not interrupt normal playing. Note the camera angle, lighting and any false triggers during strumming. Share those results with the `vision/` owner.
