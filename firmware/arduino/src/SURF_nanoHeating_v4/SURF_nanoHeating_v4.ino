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
const float KP = 0.40f;
const float KI = 0.02f;
const float MAX_I = 0.5f;        // Anti-Windup Limit
const unsigned long WINDOW_MS = 4000; // PWM Fensterbreite

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
  Serial.begin(115200); // Wichtig: Muss mit Python BAUD übereinstimmen

  pinMode(padA.pin, OUTPUT);
  pinMode(padB.pin, OUTPUT);
  digitalWrite(padA.pin, LOW);
  digitalWrite(padB.pin, LOW);

  sensorsA.begin();
  sensorsB.begin();
  // Nicht blockieren beim Lesen der Temperatur
  sensorsA.setWaitForConversion(false);
  sensorsB.setWaitForConversion(false);
}

void loop() {
  pinMode(11, OUTPUT);
  digitalWrite(11, HIGH);
  static unsigned long lastUpdate = 0;
  unsigned long now = millis();

  // --- A. Regelung & Logging (1 Hz) ---
  if (now - lastUpdate >= 1000) {
    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();

    // Temperaturen lesen
    float tA = sensorsA.getTempCByIndex(0);
    float tB = sensorsB.getTempCByIndex(0);

    // Heizelemente aktualisieren
    updateHeater(padA, tA);
    updateHeater(padB, tB);

    // --- B. Daten Senden (Binär) ---
    // Paket: [Header(1)] [Zeit(4)] [TempA(4)] [TempB(4)]
    write_i8(RES_LOG);
    write_i32((long)now);
    write_i32((long)(tA * 100)); // Float -> Int (z.B. 25.50 -> 2550)
    write_i32((long)(tB * 100));

    lastUpdate = now;
  }

  // --- C. Befehle Empfangen (Binär & Schnell) ---
  if (Serial.available() > 0) {
    int8_t cmd = Serial.read(); // Header lesen

    // Kurz warten falls Payload noch unterwegs ist (timeout 10ms)
    unsigned long timeout = millis();
    while(Serial.available() < 4 && millis() - timeout < 10);

    if (Serial.available() >= 4) {
      long val = read_i32(); // Payload lesen (Sollwert * 100)
      float target = (float)val / 100.0;
      target = constrain(target, 0, MAX_SAFE_TEMP);

      if (cmd == CMD_SET_A) {
        padA.setpoint = target;
      } else if (cmd == CMD_SET_B) {
        padB.setpoint = target;
      }
    }
  }

  // Kontinuierliches Update der PWM (muss oft aufgerufen werden!)
  // Da updateHeater() Zeit-basiert ist, rufen wir es hier für das Schalten auf,
  // aber die Berechnung (PID) passiert nur oben im 1s Takt.
  // Um ganz sicher zu gehen, dass das Schalten "weich" ist, rufen wir die Schaltlogik oft auf:
  // (Wir nutzen hier einfache Logik: state wird oben gesetzt. Aber für SoftPWM müssen wir
  //  permanent prüfen, ob wir im Fenster umschalten müssen.)

  // Optimierung: Wir rufen die Schalt-Logik öfter auf, ohne PID neu zu berechnen.
  // Das machen wir, indem wir die vorhandenen Duty-Werte nutzen.
  unsigned long winTimeA = now - padA.windowStart;
  bool stateA = winTimeA < (padA.currentDuty * WINDOW_MS);
  if (padA.state != stateA) { digitalWrite(padA.pin, stateA); padA.state = stateA; }

  unsigned long winTimeB = now - padB.windowStart;
  bool stateB = winTimeB < (padB.currentDuty * WINDOW_MS);
  if (padB.state != stateB) { digitalWrite(padB.pin, stateB); padB.state = stateB; }
}