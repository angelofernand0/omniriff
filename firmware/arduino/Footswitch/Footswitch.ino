#include <Arduino.h>
#include <stdint.h>

constexpr unsigned long kBaudRate = 115200;
constexpr unsigned long kDebounceMs = 25;
// TODO(Aditya): Confirm the switch count, board pin labels and action mapping.
constexpr uint8_t kLoopPin = 2;
constexpr uint8_t kBypassPin = 3;

struct Switch {
  uint8_t pin;
  const char* control;
  bool rawPressed;
  bool stablePressed;
  unsigned long changedAt;
};

Switch switches[] = {
    {kLoopPin, "loop", false, false, 0},
    {kBypassPin, "bypass", false, false, 0},
};
unsigned long nextSequence = 0;

void sendAction(const char* control) {
  Serial.print(F("{\"seq\":"));
  Serial.print(nextSequence++);
  Serial.print(F(",\"type\":\"action\",\"control\":\""));
  Serial.print(control);
  Serial.print(F("\"}\n"));
}

void setup() {
  Serial.begin(kBaudRate);
  for (Switch& button : switches) {
    pinMode(button.pin, INPUT_PULLUP);
    // A switch held during reset must be released before it can toggle again.
    button.rawPressed = digitalRead(button.pin) == LOW;
    button.stablePressed = button.rawPressed;
    button.changedAt = millis();
  }
}

void loop() {
  const unsigned long now = millis();
  for (Switch& button : switches) {
    const bool pressed = digitalRead(button.pin) == LOW;
    if (pressed != button.rawPressed) {
      button.rawPressed = pressed;
      button.changedAt = now;
    }
    if (pressed != button.stablePressed && now - button.changedAt >= kDebounceMs) {
      button.stablePressed = pressed;
      if (pressed) {
        sendAction(button.control);
      }
    }
  }
}
