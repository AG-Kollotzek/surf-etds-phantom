/*
 * SURF_nanoHeating_Binary.ino
 * Binäre Firmware für Brainlab ExacTrac TestUnit - Heizung
 * * Protokoll:
 * - Empfang (PC -> Arduino):
 * Header 0x01: Setze Sollwert A (gefolgt von int32 in centi-degree)
 * Header 0x02: Setze Sollwert B (gefolgt von int32 in centi-degree)
 * - Senden (Arduino -> PC):
 * Header 0x0A: Log Daten [Time(i32), TempA(i32), TempB(i32)] (alle centi-degree)
 */

#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- Hardware Pins ----------
#define ONE_WIRE_PIN_A 2
#define ONE_WIRE_PIN_B 3
#define MOSFET_A_PIN   5
#define MOSFET_B_PIN   6

const float MAX_SAFE_TEMP = 50.0f;

// ---------- Regler ----------
const float KP = 0.40f;
const float KI = 0.02f;
const float MAX_I = 0.5f;
const unsigned long WINDOW_MS = 4000;

// Protokoll Definitionen
#define CMD_SET_A 1
#define CMD_SET_B 2
#define RES_LOG   10

struct Heater {
  int pin;
  float setpoint;
  float integral;
  unsigned long windowStart;
  bool state;
  float currentDuty;
};

Heater padA = {MOSFET_A_PIN, 25.0, 0.0, 0, false, 0.0};
Heater padB = {MOSFET_B_PIN, 25.0, 0.0, 0, false, 0.0};

OneWire oneWireA(ONE_WIRE_PIN_A);
DallasTemperature sensorsA(&oneWireA);
OneWire oneWireB(ONE_WIRE_PIN_B);
DallasTemperature sensorsB(&oneWireB);

// --- Binär-Helfer ---
long read_i32() {
  long val = 0;
  Serial.readBytes((char*)&val, 4);
  return val;
}

void write_i32(long val) {
  Serial.write((byte*)&val, 4);
}

void write_i8(int8_t val) {
  Serial.write(val);
}

void updateHeater(Heater &h, float currentTemp) {
  if (isnan(currentTemp) || currentTemp > MAX_SAFE_TEMP || currentTemp < -50.0) {
    digitalWrite(h.pin, LOW);
    h.state = false;
    h.integral = 0;
    return;
  }

  float error = h.setpoint - currentTemp;
  if (fabs(error) < 2.0) {
    h.integral += error * KI;
    h.integral = constrain(h.integral, 0, MAX_I);
  } else {
    h.integral = 0;
  }

  h.currentDuty = (error * KP) + h.integral;
  h.currentDuty = constrain(h.currentDuty, 0.0, 1.0);

  unsigned long now = millis();
  if (now - h.windowStart >= WINDOW_MS) h.windowStart = now;

  bool shouldBeOn = (now - h.windowStart) < (h.currentDuty * WINDOW_MS);
  if (currentTemp >= h.setpoint) shouldBeOn = false;

  if (shouldBeOn != h.state) {
    h.state = shouldBeOn;
    digitalWrite(h.pin, h.state ? HIGH : LOW);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(padA.pin, OUTPUT);
  pinMode(padB.pin, OUTPUT);
  digitalWrite(padA.pin, LOW);
  digitalWrite(padB.pin, LOW);

  sensorsA.begin();
  sensorsB.begin();
  sensorsA.setWaitForConversion(false);
  sensorsB.setWaitForConversion(false);
}

void loop() {
  static unsigned long lastUpdate = 0;
  unsigned long now = millis();

  // --- 1. Regelung & Logging (1 Hz) ---
  if (now - lastUpdate >= 1000) {
    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();

    float tA = sensorsA.getTempCByIndex(0);
    float tB = sensorsB.getTempCByIndex(0);

    updateHeater(padA, tA);
    updateHeater(padB, tB);

    // BINÄRER LOG: Header + Time + TempA + TempB (als Integer * 100)
    write_i8(RES_LOG);
    write_i32((long)now);
    write_i32((long)(tA * 100)); // z.B. 25.50 -> 2550
    write_i32((long)(tB * 100));

    lastUpdate = now;
  }

  // --- 2. Befehle Empfangen (Binär) ---
  if (Serial.available() > 0) {
    int8_t cmd = Serial.read(); // Header lesen

    // Warte kurz auf Payload (4 Bytes für int32)
    unsigned long timeout = millis();
    while(Serial.available() < 4 && millis() - timeout < 100);

    if (Serial.available() >= 4) {
      long val = read_i32(); // Wert lesen (in centi-degree)
      float target = (float)val / 100.0;
      target = constrain(target, 0, MAX_SAFE_TEMP);

      if (cmd == CMD_SET_A) {
        padA.setpoint = target;
      } else if (cmd == CMD_SET_B) {
        padB.setpoint = target;
      }
    }
  }
}