#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- Hardware Pins ----------
#define ONE_WIRE_PIN_A 2     // Sensor für Pad A an Pin 2
#define ONE_WIRE_PIN_B 3     // Sensor für Pad B an Pin 3
#define MOSFET_A_PIN   5     // Heizung Pad A
#define MOSFET_B_PIN   6     // Heizung Pad B

// ---------- Sicherheits-Limit ----------
const float MAX_SAFE_TEMP = 50.0f;

// ---------- Regler-Parameter (Optimiert gegen Overshoot) ----------
const float KP = 0.15f;
const float KI = 0.005f;
const float MAX_I = 0.3f;
const unsigned long WINDOW_MS = 1000; // Schnelleres PWM-Fenster (1 Sekunde)

// Struktur zur Verwaltung der Pads
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

// Zwei separate Busse
OneWire oneWireA(ONE_WIRE_PIN_A);
DallasTemperature sensorsA(&oneWireA);

OneWire oneWireB(ONE_WIRE_PIN_B);
DallasTemperature sensorsB(&oneWireB);

// --- FUNKTION 1: Berechnung des Duty-Cycles (PI-Regler) ---
void updateHeater(Heater &h, float currentTemp) {
  // Sicherheits-Check
  if (isnan(currentTemp) || currentTemp > MAX_SAFE_TEMP || currentTemp < -50.0) {
    h.currentDuty = 0;
    digitalWrite(h.pin, LOW);
    return;
  }

  float error = h.setpoint - currentTemp;

  // Integral-Anteil nur im Nahbereich (1.0 Grad) nutzen
  if (fabs(error) < 1.0) {
    h.integral += error * KI;
    h.integral = constrain(h.integral, 0, MAX_I);
  } else {
    h.integral = 0;
  }

  // Duty Cycle berechnen
  h.currentDuty = (error * KP) + h.integral;
  h.currentDuty = constrain(h.currentDuty, 0.0, 1.0);

  // Anti-Overshoot: Sofort aus, wenn Sollwert erreicht/überschritten
  if (currentTemp >= h.setpoint) h.currentDuty = 0.0;
}

// --- FUNKTION 2: Ausführung der PWM-Steuerung (Zeitproportional) ---
void maintainPWM(Heater &h) {
  unsigned long now = millis();

  // Fenster-Timer
  if (now - h.windowStart >= WINDOW_MS) {
    h.windowStart = now;
  }

  // Soll-Zustand basierend auf Duty Cycle berechnen
  bool shouldBeOn = (now - h.windowStart) < (h.currentDuty * WINDOW_MS);

  // Pin schalten
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

  // Wichtig: Nicht auf Konvertierung warten (async)
  sensorsA.setWaitForConversion(false);
  sensorsB.setWaitForConversion(false);

  // Erste Messung direkt anstoßen
  sensorsA.requestTemperatures();
  sensorsB.requestTemperatures();
}

void loop() {
  static unsigned long lastUpdate = 0;
  unsigned long now = millis();

  // --- Teil A: Messung und Regelung (1Hz) ---
  if (now - lastUpdate >= 1000) {
    // 1. LESEN (Ergebnisse der Anfrage aus dem letzten Loop/Setup)
    float tA = sensorsA.getTempCByIndex(0);
    float tB = sensorsB.getTempCByIndex(0);

    // 2. REGEL-BERECHNUNG (Duty-Cycle anpassen)
    updateHeater(padA, tA);
    updateHeater(padB, tB);

    // 3. NEUE MESSUNG STARTEN (für den nächsten Loop in 1s)
    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();

    // Daten für Python-Logging
    Serial.print(now / 1000);
    Serial.print(","); Serial.print(tA, 2);
    Serial.print(","); Serial.println(tB, 2);

    lastUpdate = now;
  }

  // --- Teil B: PWM Aufrechterhalten (läuft bei jedem Loop-Durchlauf!) ---
  maintainPWM(padA);
  maintainPWM(padB);

  // --- Teil C: Befehle empfangen ---
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.startsWith("SPA")) {
      float val = cmd.substring(4).toFloat();
      padA.setpoint = constrain(val, 0, MAX_SAFE_TEMP);
    }
    if (cmd.startsWith("SPB")) {
      float val = cmd.substring(4).toFloat();
      padB.setpoint = constrain(val, 0, MAX_SAFE_TEMP);
    }
  }
}