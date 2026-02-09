#include <OneWire.h>
#include <DallasTemperature.h>
#include <math.h>

// -------- Pins --------
#define ONE_WIRE_PIN 2
#define MOSFET_PIN   5

// -------- Parameter (tuning) --------
float SETPOINT_C            = 27.0f;   // live änderbar
const float SENSOR_OFFSET_C = 0.0f;

// Zeitproportionaler Regler
const unsigned long WINDOW_MS  = 4000;    // Fensterlänge
const float KP                 = 0.35f;   // etwas kleiner als vorher

// Mindestzeiten (symmetrischer & kürzer => feinere Dosierung)
const unsigned long MIN_ON_MS  = 700;
const unsigned long MIN_OFF_MS = 700;

// Deadband um Setpoint (kein Heizen, wenn nahe genug)
const float DEADBAND_C         = 0.05f;   // ±0.05 °C

// Wie früh wir beim Hochheizen bremsen (in °C unterhalb des Setpoints)
const float APPROACH_MARGIN_C  = 1.5f;    // früheres „Gas weg“ als vorher

// Duty-Softlimit nach Setpoint-Wechsel (gegen Overshoot)
const float DUTY_START_LIMIT   = 0.25f;   // direkt nach Setpoint-Änderung
const float DUTY_LIMIT_RAMP    = 0.10f;   // +0.10 pro Sekunde bis 1.0

const bool MOSFET_ACTIVE_HIGH  = true;

// -------- Globals --------
OneWire oneWire(ONE_WIRE_PIN);
DallasTemperature sensors(&oneWire);

enum HeatState { HEAT_OFF, HEAT_ON };
HeatState state = HEAT_OFF;

unsigned long lastSwitchMs  = 0;
unsigned long windowStartMs = 0;

String cmdBuf;
bool sp_pending = false;
float lastGoodTempC = NAN;

float duty_limit = 1.0f;
unsigned long lastDutyRampMs = 0;

void setHeater(bool on) {
  bool level = MOSFET_ACTIVE_HIGH ? on : !on;
  digitalWrite(MOSFET_PIN, level ? HIGH : LOW);
}

bool sensorOk(float t) {
  if (t <= -100.0) return false;            // -127 °C
  if (fabs(t - 85.0) < 0.01) return false;  // 85 °C
  return true;
}

void logLine(const char* note, float tempC, bool heaterOn, float duty) {
  static unsigned long t0 = millis();
  unsigned long t = (millis() - t0) / 1000;

  Serial.print(t);
  Serial.print(","); Serial.print(tempC, 2);
  Serial.print(","); Serial.print(heaterOn ? 1 : 0);
  Serial.print(","); Serial.print(state == HEAT_ON ? "ON" : "OFF");
  Serial.print(",");
  Serial.print(note);
  Serial.print(" (duty=");
  Serial.print(duty, 3);
  Serial.println(")");
}

void handleSerialCommands() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      cmdBuf.trim();
      if (cmdBuf.length() > 0) {
        String up = cmdBuf; up.toUpperCase(); up.replace(":", " ");
        if (up.startsWith("SP")) {
          int sp = up.indexOf(' ');
          if (sp >= 0 && sp + 1 < up.length()) {
            float val = up.substring(sp + 1).toFloat();
            if (val >= 0.0f && val <= 90.0f) {
              SETPOINT_C = val;
              sp_pending = true;                 // erst nach nächster gültiger Messung loggen
              duty_limit = DUTY_START_LIMIT;     // Softstart gegen Overshoot
              lastDutyRampMs = millis();
              Serial.print(F("# SETPOINT_C="));  // Metadatenzeile
              Serial.println(SETPOINT_C, 2);
            }
          }
        }
      }
      cmdBuf = "";
    } else {
      cmdBuf += c;
      if (cmdBuf.length() > 80) cmdBuf.remove(0, 40);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(MOSFET_PIN, OUTPUT);
  setHeater(false);
  sensors.begin();

  windowStartMs = millis();
  lastDutyRampMs = millis();

  Serial.println(F("# Thermostat start (zeitproportional)"));
  Serial.print(F("# SETPOINT_C="));      Serial.println(SETPOINT_C, 2);
  Serial.print(F("# WINDOW_MS="));       Serial.println(WINDOW_MS);
  Serial.print(F("# KP="));              Serial.println(KP, 3);
  Serial.print(F("# MIN_ON_MS="));       Serial.println(MIN_ON_MS);
  Serial.print(F("# MIN_OFF_MS="));      Serial.println(MIN_OFF_MS);
  Serial.print(F("# DEADBAND_C="));      Serial.println(DEADBAND_C, 2);
  Serial.println(F("t_s,tempC,heater,state,note"));
}

void loop() {
  handleSerialCommands();

  static unsigned long lastSample = 0;
  unsigned long now = millis();
  if (now - lastSample < 1000) return;  // 1 Hz
  lastSample = now;

  // Messung (blocking conversion via Dallas lib)
  sensors.requestTemperatures();
  float tC = sensors.getTempCByIndex(0) + SENSOR_OFFSET_C;

  // Fehlerwerte niemals loggen
  if (!sensorOk(tC)) {
    setHeater(false);
    state = HEAT_OFF;
    return;
  }

  lastGoodTempC = tC;

  // --- Steigung bestimmen (steigt die Temperatur gerade?) ---
  static float prevTempC = NAN;
  bool rising = false;
  if (!isnan(prevTempC)) {
    rising = (tC > prevTempC + 0.01f);   // kleine Hysterese gegen Rauschen
  }
  prevTempC = tC;

  // Duty-Limit langsam hochfahren (Softstart)
  unsigned long dt_ms = now - lastDutyRampMs;
  if (dt_ms >= 1000) {
    duty_limit = min(1.0f, duty_limit + DUTY_LIMIT_RAMP * (dt_ms / 1000.0f));
    lastDutyRampMs = now;
  }

  // -------- Regler --------
  float error = SETPOINT_C - tC;
  float absErr = fabs(error);

  // Deadband
  if (absErr < DEADBAND_C) {
    error = 0.0f;
    absErr = 0.0f;
  }

  float duty = KP * error;

  // Basis-Clamp (nur Heizen, nicht Kühlen)
  if (duty < 0.0f) duty = 0.0f;

  // Zonenbegrenzung: je näher am Setpoint, desto kleinere Duty-Werte
  float maxDuty = duty_limit;          // weit weg: volle erlaubte Leistung
  if (absErr < 3.0f)  maxDuty = min(maxDuty, 0.50f);  // <= 3 °C Abstand
  if (absErr < 1.5f)  maxDuty = min(maxDuty, 0.30f);  // <= 1.5 °C Abstand
  if (absErr < 0.7f)  maxDuty = min(maxDuty, 0.15f);  // ganz nah dran

  if (duty > maxDuty) duty = maxDuty;

  // --- Frühabschalten / "Coasten" zum Setpoint ---
  // 1) Niemals heizen, wenn wir schon über dem Setpoint sind
  if (tC >= SETPOINT_C) {
    duty = 0.0f;
  }
  // 2) Beim Annähern von unten und steigender Temperatur -> früher Gas weg
  else if (rising && (SETPOINT_C - tC) < APPROACH_MARGIN_C) {
    duty = 0.0f;
  }

  // Duty -> On-Zeit im Fenster
  unsigned long onTime = (unsigned long)(duty * WINDOW_MS);

  if (now - windowStartMs >= WINDOW_MS) {
    windowStartMs = now;
  }

  bool shouldBeOn = ((now - windowStartMs) < onTime);
  bool canSwitchOn  = (now - lastSwitchMs >= MIN_OFF_MS);
  bool canSwitchOff = (now - lastSwitchMs >= MIN_ON_MS);

  if (shouldBeOn && state == HEAT_OFF && canSwitchOn) {
    setHeater(true); state = HEAT_ON; lastSwitchMs = now;
    logLine("PWM_SWITCH_ON", tC, true, duty);
  } else if (!shouldBeOn && state == HEAT_ON && canSwitchOff) {
    setHeater(false); state = HEAT_OFF; lastSwitchMs = now;
    logLine("PWM_SWITCH_OFF", tC, false, duty);
  } else {
    logLine("PWM_HOLD", tC, (state == HEAT_ON), duty);
  }

  // Setpoint-Update nach gültiger Messung protokollieren
  if (sp_pending) {
    logLine("SETPOINT_UPDATE", lastGoodTempC, (state == HEAT_ON), duty);
    sp_pending = false;
  }
}
