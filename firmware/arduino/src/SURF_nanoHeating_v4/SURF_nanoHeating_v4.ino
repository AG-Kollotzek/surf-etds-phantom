#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- Protokoll Definitionen (Binär) ----------
const uint8_t LOG_DATA = 10;
const uint8_t CMD_SET_A = 1;
const uint8_t CMD_SET_B = 2;

// ---------- Hardware Pins ----------
#define ONE_WIRE_PIN_A 2
#define ONE_WIRE_PIN_B 3
#define MOSFET_A_PIN   5
#define MOSFET_B_PIN   6

// ---------- Sicherheits-Limit ----------
const float MAX_SAFE_TEMP = 50.0f;

// ---------- Regler-Parameter (Optimiert gegen Overshoot) ----------
const float KP = 0.15f;
const float KI = 0.005f;
const float MAX_I = 0.3f;
const unsigned long WINDOW_MS = 1000; // Schnelleres Fenster

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

// --- BINÄR HELPER ---
void write_i32(long v) {
  Serial.write((uint8_t*)&v, 4);
}

long read_i32() {
  long v = 0;
  Serial.readBytes((char*)&v, 4);
  return v;
}

// --- LOGIK ---
void updateHeater(Heater &h, float currentTemp) {
  if (isnan(currentTemp) || currentTemp > MAX_SAFE_TEMP || currentTemp < -50.0) {
    h.currentDuty = 0; digitalWrite(h.pin, LOW); return;
  }

  float error = h.setpoint - currentTemp;

  if (fabs(error) < 1.0) {
    h.integral += error * KI;
    h.integral = constrain(h.integral, 0, MAX_I);
  } else {
    h.integral = 0;
  }

  h.currentDuty = (error * KP) + h.integral;
  h.currentDuty = constrain(h.currentDuty, 0.0, 1.0);
  if (currentTemp >= h.setpoint) h.currentDuty = 0.0;
}

void maintainPWM(Heater &h) {
  unsigned long now = millis();
  if (now - h.windowStart >= WINDOW_MS) h.windowStart = now;
  bool shouldBeOn = (now - h.windowStart) < (h.currentDuty * WINDOW_MS);
  if (shouldBeOn != h.state) {
    h.state = shouldBeOn;
    digitalWrite(h.pin, h.state ? HIGH : LOW);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(padA.pin, OUTPUT); pinMode(padB.pin, OUTPUT);
  digitalWrite(padA.pin, LOW); digitalWrite(padB.pin, LOW);

  sensorsA.begin(); sensorsB.begin();
  sensorsA.setWaitForConversion(false);
  sensorsB.setWaitForConversion(false);

  sensorsA.requestTemperatures();
  sensorsB.requestTemperatures();
}

void loop() {
  static unsigned long lastUpdate = 0;
  unsigned long now = millis();

  // 1. Messen & Senden (1 Hz)
  if (now - lastUpdate >= 1000) {
    float tA = sensorsA.getTempCByIndex(0);
    float tB = sensorsB.getTempCByIndex(0);

    updateHeater(padA, tA);
    updateHeater(padB, tB);

    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();

    // BINÄR SENDEN
    Serial.write(LOG_DATA);       // Header (1 Byte)
    write_i32(0);                 // Dummy Timestamp (Python macht eigenen) oder millis()
    write_i32((long)(tA * 100));  // Temp A als Int (z.B. 2550 für 25.50°C)
    write_i32((long)(tB * 100));  // Temp B als Int

    lastUpdate = now;
  }

  // 2. PWM Update (Immer)
  maintainPWM(padA);
  maintainPWM(padB);

  // 3. Befehle Empfangen (Binär: Header + 4 Byte)
  if (Serial.available() >= 5) {
    uint8_t cmd = Serial.read();
    long val = read_i32(); // Wert kommt als int * 100 an

    float target = (float)val / 100.0;
    target = constrain(target, 0, MAX_SAFE_TEMP);

    if (cmd == CMD_SET_A) padA.setpoint = target;
    if (cmd == CMD_SET_B) padB.setpoint = target;
  }
}