#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- Hardware Pins ----------
#define ONE_WIRE_PIN_A 2     // Sensor für Pad A an Pin 2
#define ONE_WIRE_PIN_B 3     // Sensor für Pad B an Pin 3
#define MOSFET_A_PIN   5     // Heizung Pad A
#define MOSFET_B_PIN   6     // Heizung Pad B (korrigiert auf Pin 6 laut deinem Entwurf)

// ---------- Sicherheits-Limit ----------
const float MAX_SAFE_TEMP = 50.0f; 

// ---------- Regler-Parameter (PI-Regler) ----------
const float KP = 0.40f;          
const float KI = 0.02f;          
const float MAX_I = 0.5f;        
const unsigned long WINDOW_MS = 4000; 

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

// ZWEI separate Busse erstellen
OneWire oneWireA(ONE_WIRE_PIN_A);
DallasTemperature sensorsA(&oneWireA);

OneWire oneWireB(ONE_WIRE_PIN_B);
DallasTemperature sensorsB(&oneWireB);

void updateHeater(Heater &h, float currentTemp) {
  // 1. Killswitch / Sicherheits-Check
  if (isnan(currentTemp) || currentTemp > MAX_SAFE_TEMP || currentTemp < -50.0) {
    digitalWrite(h.pin, LOW);
    h.state = false;
    h.integral = 0;
    h.currentDuty = 0;
    return; 
  }

  // 2. PI-Regler Berechnung
  float error = h.setpoint - currentTemp;

  if (fabs(error) < 2.0) {
    h.integral += error * KI;
    h.integral = constrain(h.integral, 0, MAX_I);
  } else {
    h.integral = 0; 
  }

  h.currentDuty = (error * KP) + h.integral;
  h.currentDuty = constrain(h.currentDuty, 0.0, 1.0);

  // 3. Zeitproportionale Steuerung (PWM)
  unsigned long now = millis();
  if (now - h.windowStart >= WINDOW_MS) {
    h.windowStart = now;
  }

  bool shouldBeOn = (now - h.windowStart) < (h.currentDuty * WINDOW_MS);
  
  // Sofort aus, wenn über Sollwert
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
  pinMode(11, OUTPUT);
  digitalWrite(11, HIGH);

  if (now - lastUpdate >= 1000) {
    // Beide Busse separat abfragen
    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();
    
    // Jeweils den ersten Sensor am jeweiligen Bus nehmen (Index 0)
    float tA = sensorsA.getTempCByIndex(0);
    float tB = sensorsB.getTempCByIndex(0);

    updateHeater(padA, tA);
    updateHeater(padB, tB);

    // Datenformat für Python: Zeit, TempA, TempB
    Serial.print(now / 1000);
    Serial.print(","); Serial.print(tA, 2);
    Serial.print(","); Serial.println(tB, 2);
    
    lastUpdate = now;
  }
  
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