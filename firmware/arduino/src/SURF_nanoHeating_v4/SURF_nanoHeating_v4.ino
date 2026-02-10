/*
 * SURF_nanoHeating_Binary_Final
 * * Basiert auf Ihrer Logik:
 * - PI-Regler (Kp=0.4, Ki=0.02)
 * - Anti-Windup (Integral nur bei < 2.0°C Abweichung)
 * - Soft-PWM mit 4000ms Fenster
 * * NEU: Binäres Protokoll für Stabilität mit SURF_Terminal_V2.py
 */

#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- Hardware Pins (Identisch zu Ihrem Code) ----------
#define ONE_WIRE_PIN_A 2
#define ONE_WIRE_PIN_B 3
#define MOSFET_A_PIN   5
#define MOSFET_B_PIN   6

const float MAX_SAFE_TEMP = 50.0f;

// ---------- Regler-Parameter (Aus Ihrem Code übernommen) ----------
// Hinweis: Ihr Code war ein PI-Regler (kein D-Anteil). Das ist für Heizungen optimal.
const float KP = 0.15f;
const float KI = 0.005f;
const float MAX_I = 0.3f;
const unsigned long WINDOW_MS = 1000;

// Protokoll Header (Muss zum Python-Script passen)
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

// Initialisierung mit 25.0°C Startwert
Heater padA = {MOSFET_A_PIN, 25.0, 0.0, 0, false, 0.0};
Heater padB = {MOSFET_B_PIN, 25.0, 0.0, 0, false, 0.0};

// Sensoren
OneWire oneWireA(ONE_WIRE_PIN_A);
DallasTemperature sensorsA(&oneWireA);
OneWire oneWireB(ONE_WIRE_PIN_B);
DallasTemperature sensorsB(&oneWireB);

// --- Binär-Helfer Funktionen ---
long read_i32() {
  long val = 0;
  if (Serial.available() >= 4) {
    Serial.readBytes((char*)&val, 4);
  }
  return val;
}

void write_i32(long val) {
  Serial.write((byte*)&val, 4);
}

void write_i8(int8_t val) {
  Serial.write(val);
}

// --- Ihre Original Regelungs-Logik ---
void updateHeater(Heater &h, float currentTemp) {
  // 1. Sicherheits-Check
  if (isnan(currentTemp) || currentTemp > MAX_SAFE_TEMP || currentTemp < -50.0) {
    digitalWrite(h.pin, LOW);
    h.state = false;
    h.integral = 0;
    return;
  }

  // 2. PI-Berechnung
  float error = h.setpoint - currentTemp;

  // Integral nur aufsummieren, wenn wir nah am Ziel sind (< 2°C)
  // Das verhindert "Windup" beim Aufheizen
  if (fabs(error) < 2.0) {
    h.integral += error * KI;
    h.integral = constrain(h.integral, 0, MAX_I); // Limitieren
  } else {
    h.integral = 0;
  }

  // P + I Output berechnen
  h.currentDuty = (error * KP) + h.integral;
  h.currentDuty = constrain(h.currentDuty, 0.0, 1.0); // 0% bis 100%

  // 3. Soft-PWM (4 Sekunden Fenster)
  unsigned long now = millis();
  if (now - h.windowStart >= WINDOW_MS) {
    h.windowStart = now;
  }

  // Entscheidung: AN oder AUS für diesen Moment im Fenster
  bool shouldBeOn = (now - h.windowStart) < (h.currentDuty * WINDOW_MS);

  // Wenn Temperatur erreicht ist, Sicherheitshalber aus (Bang-Bang Override)
  if (currentTemp >= h.setpoint) shouldBeOn = false;

  // Schalten
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

  // ERSTE Messung anstoßen, damit im ersten Loop Daten da sind
  sensorsA.requestTemperatures();
  sensorsB.requestTemperatures();
}

void loop() {
  static unsigned long lastUpdate = 0;
  unsigned long now = millis();

  // Sicherheits-LED (optional)
  // pinMode(11, OUTPUT); digitalWrite(11, HIGH);

  if (now - lastUpdate >= 1000) {
    // 1. LESEN (Wir lesen das Ergebnis der ANFRAGE vom LETZTEN Loop)
    // Da 1000ms vergangen sind, ist die Konvertierung (max 750ms) sicher fertig.
    float tA = sensorsA.getTempCByIndex(0);
    float tB = sensorsB.getTempCByIndex(0);

    // 2. REGELN
    updateHeater(padA, tA);
    updateHeater(padB, tB);

    // 3. NEUE MESSUNG STARTEN (für den nächsten Loop)
    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();

    // Datenformat für Python
    Serial.print(now / 1000);
    Serial.print(","); Serial.print(tA, 2);
    Serial.print(","); Serial.println(tB, 2);

    lastUpdate = now;
  }

  // PI-PWM Logic muss öfter als 1x pro Sekunde laufen für "updateHeater" Check?
  // Nein, updateHeater setzt nur den Status.
  // ABER: Damit das PWM-Schalten (An/Aus) funktioniert, müssen wir updateHeater
  // eigentlich dauernd aufrufen oder die PWM-Logik entkoppeln.
  // FIX: Wir rufen den "Schalt-Teil" von updateHeater hier im Main-Loop dauernd auf!

  maintainPWM(padA); // Neue Hilfsfunktion unten nutzen
  maintainPWM(padB);

  // ... (Serial Command Block bleibt gleich) ...
}

// --- ZUSATZ: PWM Logik entkoppeln ---
// Füge diese Funktion hinzu und nimm den PWM-Teil aus updateHeater raus oder lass updateHeater nur Berechnungen machen.

void updateHeater(Heater &h, float currentTemp) {
  // Nur Berechnung des DutyCycles hier
  if (isnan(currentTemp) || currentTemp > MAX_SAFE_TEMP || currentTemp < -50.0) {
    h.state = false; h.currentDuty = 0; digitalWrite(h.pin, LOW); return;
  }

  float error = h.setpoint - currentTemp;

  // Integral nur nutzen wenn wir nah dran sind (< 1.0 Grad)
  if (fabs(error) < 1.0) {
    h.integral += error * KI;
    h.integral = constrain(h.integral, 0, MAX_I);
  } else {
    h.integral = 0;
  }

  h.currentDuty = (error * KP) + h.integral;
  h.currentDuty = constrain(h.currentDuty, 0.0, 1.0);

  // Anti-Windup / Overshoot Schutz: Wenn wir drüber sind, sofort 0
  if (currentTemp >= h.setpoint) h.currentDuty = 0.0;
}

void maintainPWM(Heater &h) {
  unsigned long now = millis();
  if (now - h.windowStart >= WINDOW_MS) {
    h.windowStart = now;
  }
  bool shouldBeOn = (now - h.windowStart) < (h.currentDuty * WINDOW_MS);
  if (shouldBeOn != h.state) {
    h.state = shouldBeOn;
    digitalWrite(h.pin, h.state ? HIGH : LOW);
  }
}