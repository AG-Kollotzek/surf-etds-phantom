/*
 * SURF_nanoHeating_Binary_Final
 * - PI-Regler (Kp=0.15, Ki=0.005)
 * - Anti-Windup & Soft-PWM
 * - Robustes binäres Protokoll (Handshake-kompatibel)
 */

#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- NEU: Protokoll-Enum für Konsistenz mit Axis-Treiber ----------
enum HeatOrder : uint8_t {
  CMD_SET_A = 1,
  CMD_SET_B = 2,
  LOG_DATA  = 10   // Entspricht deinem RES_LOG
};

// ---------- Hardware Pins ----------
#define ONE_WIRE_PIN_A 2
#define ONE_WIRE_PIN_B 3
#define MOSFET_A_PIN   5
#define MOSFET_B_PIN   6

const float MAX_SAFE_TEMP = 51.0f;
const unsigned long WINDOW_MS = 1000;
const float KP = 0.15f;
const float KI = 0.005f;
const float MAX_I = 0.3f;

struct Heater {
  int pin;
  float setpoint;
  float integral;
  unsigned long windowStart;
  bool state;
  float currentDuty;
};

// --- IDEALSTAND: Start mit 0.0°C für maximale Sicherheit ---
Heater padA = {MOSFET_A_PIN, 0.0, 0.0, 0, false, 0.0};
Heater padB = {MOSFET_B_PIN, 0.0, 0.0, 0, false, 0.0};

// Sensoren initialisieren
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

void write_i32(long val) { Serial.write((byte*)&val, 4); }
void write_i8(int8_t val) { Serial.write(val); }

void updateHeater(Heater &h, float currentTemp) {
  if (isnan(currentTemp) || currentTemp > MAX_SAFE_TEMP || currentTemp < -50.0) {
    digitalWrite(h.pin, LOW);
    h.state = false; h.integral = 0; h.currentDuty = 0;
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
  if (currentTemp >= h.setpoint) h.currentDuty = 0.0;
}

void setup() {
  Serial.begin(115200);
  pinMode(11,OUTPUT); digitalWrite(11,HIGH);
  pinMode(padA.pin, OUTPUT); pinMode(padB.pin, OUTPUT);
  digitalWrite(padA.pin, LOW); digitalWrite(padB.pin, LOW);
  sensorsA.begin(); sensorsB.begin();
  sensorsA.setWaitForConversion(false);
  sensorsB.setWaitForConversion(false);
}

void loop() {
  static unsigned long lastUpdate = 0;
  unsigned long now = millis();

  // --- A. Regelung & Logging (1 Hz) ---
  if (now - lastUpdate >= 1000) {
    float tA = sensorsA.getTempCByIndex(0);
    float tB = sensorsB.getTempCByIndex(0);
    updateHeater(padA, tA);
    updateHeater(padB, tB);

    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();

    write_i8(LOG_DATA);
    write_i32((long)now);
    write_i32((long)(tA * 100));
    write_i32((long)(tB * 100));
    lastUpdate = now;
  }

  // --- B. Befehle Empfangen mit Robustheits-Schutz ---
  if (Serial.available() >= 5) {
    uint8_t cmd = Serial.read();

    if (cmd != CMD_SET_A && cmd != CMD_SET_B) {
        while(Serial.available()) Serial.read(); // Puffer leeren bei Sync-Verlust
        return;
    }

    long val = read_i32();
    float target = (float)val / 100.0;
    target = constrain(target, 0, MAX_SAFE_TEMP);

    if (cmd == CMD_SET_A) padA.setpoint = target;
    else if (cmd == CMD_SET_B) padB.setpoint = target;
  }

  // --- C. Kontinuierliches Soft-PWM Update ---
  if (now - padA.windowStart >= WINDOW_MS) padA.windowStart = now;
  bool stateA = (now - padA.windowStart) < (padA.currentDuty * WINDOW_MS);
  if (padA.state != stateA) { digitalWrite(padA.pin, stateA); padA.state = stateA; }

  if (now - padB.windowStart >= WINDOW_MS) padB.windowStart = now;
  bool stateB = (now - padB.windowStart) < (padB.currentDuty * WINDOW_MS);
  if (padB.state != stateB) { digitalWrite(padB.pin, stateB); padB.state = stateB; }
}