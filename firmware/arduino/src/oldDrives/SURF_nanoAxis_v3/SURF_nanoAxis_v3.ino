/*
 * SURF_nanoAxis_v4_Final
 * ----------------------
 * MERGE aus v3.0 (Non-Blocking Struktur) und v1.2 (Exakte Limits & Safety)
 * - Limits: H(+/-35), V(-35/+50), R(+/-45)
 * - Homing: 2-Stufen (Fast/Slow) mit Backoff
 * - Safety: Speed-Capping & Alarm-Pins
 */

#include <AccelStepper.h>

// --- PROTOKOLL ---
enum OrderID : uint8_t { HELLO=0, MOVE_AXIS=1, HOME_AXIS=2, STOP_ALL=3, COMMAND_DONE=4, LOG_DATA=10 };
enum AxisID : uint8_t { AXIS_H=0, AXIS_V=1, AXIS_R=2 };

// --- PINS (Identisch zu v1.2) ---
const int PIN_PUL_H=2, PIN_DIR_H=3, PIN_ENA_H=4, PIN_END_H=5, PIN_ALM_H=A0;
const int PIN_PUL_V=6, PIN_DIR_V=7, PIN_ENA_V=8, PIN_END_V=9, PIN_ALM_V=A1;
const int PIN_PUL_R=10, PIN_DIR_R=11, PIN_ENA_R=12; // R hat keinen Endstop/Alarm

// --- MECHANIK KONSTANTEN (Aus v1.2) ---
const float STEPS_PER_MM = 800.0f;
const float STEPS_PER_DEG = 16.156f;

// --- SOFT LIMITS (Aus v1.2 übernommen) ---
// Horizontal
const float LIMIT_H_MAX_MM = 35.0;
const float LIMIT_H_MIN_MM = -35.0;
// Vertikal
const float LIMIT_V_MAX_MM = 50.0;
const float LIMIT_V_MIN_MM = -35.0;
// Rotation
const float LIMIT_R_MAX_DEG = 45.0;
const float LIMIT_R_MIN_DEG = -45.0;

// Vorausberechnete Limits in Steps
const long LIMIT_STEPS_H_MAX = (long)(LIMIT_H_MAX_MM * STEPS_PER_MM);
const long LIMIT_STEPS_H_MIN = (long)(LIMIT_H_MIN_MM * STEPS_PER_MM);
const long LIMIT_STEPS_V_MAX = (long)(LIMIT_V_MAX_MM * STEPS_PER_MM);
const long LIMIT_STEPS_V_MIN = (long)(LIMIT_V_MIN_MM * STEPS_PER_MM);
const long LIMIT_STEPS_R_MAX = (long)(LIMIT_R_MAX_DEG * STEPS_PER_DEG);
const long LIMIT_STEPS_R_MIN = (long)(LIMIT_R_MIN_DEG * STEPS_PER_DEG);

// --- SPEED LIMITS (Aus v1.2) ---
const float MAX_SPEED_MM_S = 100.0;
const float MAX_SPEED_DEG_S = 90.0;
const long MAX_STEPS_PER_SEC_LIN = (long)(MAX_SPEED_MM_S * STEPS_PER_MM);
const long MAX_STEPS_PER_SEC_ROT = (long)(MAX_SPEED_DEG_S * STEPS_PER_DEG);

// --- HOMING PARAMETER (Aus v1.2) ---
const float HOMING_SPEED_FAST = 10.0; // mm/s
const float HOMING_SPEED_SLOW = 2.0;  // mm/s
const float BACKOFF_MM = 3.0;
const float HOME_OFFSET_MM_H = 41.0;
const float HOME_OFFSET_MM_V = 62.5;
const int HOMING_SIGN_H = 1; // +1
const int HOMING_SIGN_V = 1; // +1

// --- OBJEKTE ---
AccelStepper stepper_h(1, PIN_PUL_H, PIN_DIR_H);
AccelStepper stepper_v(1, PIN_PUL_V, PIN_DIR_V);
AccelStepper stepper_r(1, PIN_PUL_R, PIN_DIR_R);

// --- HELPER ---
void write_i8(int8_t v) { Serial.write(v); }
void write_i32(long v) { Serial.write((byte*)&v, 4); }
long read_i32() {
  long v=0; unsigned long t=millis();
  while(Serial.available()<4 && millis()-t<50);
  if(Serial.available()>=4) Serial.readBytes((char*)&v, 4);
  return v;
}

// --- SAFETY CHECK ---
bool isTargetSafe(int8_t axis, long target_steps) {
  if (axis == AXIS_H) {
    return (target_steps >= LIMIT_STEPS_H_MIN && target_steps <= LIMIT_STEPS_H_MAX);
  } else if (axis == AXIS_V) {
    return (target_steps >= LIMIT_STEPS_V_MIN && target_steps <= LIMIT_STEPS_V_MAX);
  } else if (axis == AXIS_R) {
    return (target_steps >= LIMIT_STEPS_R_MIN && target_steps <= LIMIT_STEPS_R_MAX);
  }
  return false;
}

// --- MOVE FUNKTION (Non-Blocking) ---
void moveAxis(int8_t axis, long target, long speed) {
  AccelStepper* st = (axis==AXIS_H)?&stepper_h : (axis==AXIS_V)?&stepper_v : &stepper_r;

  // 1. Speed Capping
  long max_s = (axis==AXIS_R) ? MAX_STEPS_PER_SEC_ROT : MAX_STEPS_PER_SEC_LIN;
  if (speed > max_s) speed = max_s;

  // 2. Limit Check
  if (st && isTargetSafe(axis, target)) {
    st->setMaxSpeed((float)speed);
    st->moveTo(target);
    // Sofort-Check: Falls wir schon da sind -> DONE
    if (st->distanceToGo() == 0) write_i8(COMMAND_DONE);
  } else {
    // Limit verletzt -> Fehler abfangen, aber GUI nicht blockieren
    write_i8(COMMAND_DONE);
  }
}

// --- HOMING FUNKTION (Robust & Blockierend wie in v1.2) ---
void doHoming(int axisIdx) {
  // Zeiger auf den korrekten Stepper und Pin-Auswahl
  AccelStepper* stepper;
  int switchPin;
  long dir_factor; // 1 oder -1, bestimmt Suchrichtung
  long backoff_steps;

  // --- MAPPING auf die Variablen aus deinem v3-Sketch ---
  if (axisIdx == 0) {
    stepper = &stepper_h;       // Name in v3
    switchPin = PIN_END_H;      // Name in v3
    dir_factor = -1;            // Homing nach Links/Negativ
    backoff_steps = 2000;       // Freifahren nach Rechts
  }
  else if (axisIdx == 1) {
    stepper = &stepper_v;       // Name in v3
    switchPin = PIN_END_V;      // Name in v3
    dir_factor = 1;             // Homing nach Oben/Positiv (Vertikalachse)
    backoff_steps = -2000;      // Freifahren nach Unten
  }
  else {
    // Achse R (2) hat keinen Sensor -> Nur Position nullen
    stepper_r.setCurrentPosition(0);
    return;
  }

  // Geschwindigkeiten
  float searchSpeed = 400.0 * dir_factor;
  float creepSpeed = 50.0 * dir_factor;

  Serial.print("Homing Axis "); Serial.println(axisIdx);

  // --- PHASE 1: Grob zum Schalter fahren ---
  stepper->setSpeed(searchSpeed);

  // WICHTIG: Wir fahren, solange der Schalter NICHT gedrückt ist.
  // Bei NC Schaltern an GND ist: Frei = LOW, Gedrückt/Offen = HIGH?
  // Oder INPUT_PULLUP gegen GND: Frei = HIGH, Gedrückt = LOW?
  // Da du sagtest "Gedrückt = HIGH", muss er fahren solange LOW ist.
  // Sollte er sofort stoppen, ändere "== LOW" zu "== HIGH".
  while (digitalRead(switchPin) == LOW) {
    stepper->runSpeed();
  }

  stepper->setCurrentPosition(0);
  delay(100);

  // --- PHASE 2: Freifahren (Backoff) ---
  // runToNewPosition ist blockierend und sicher
  stepper->runToNewPosition(backoff_steps);
  delay(100);

  // --- PHASE 3: Langsam zum Schalter (Fein-Homing) ---
  stepper->setSpeed(creepSpeed);
  while (digitalRead(switchPin) == LOW) {
    stepper->runSpeed();
  }

  // --- PHASE 4: Nullpunkt setzen ---
  stepper->setCurrentPosition(0);
  stepper->setSpeed(0);

  // Optional: Etwas freifahren, damit der Schalter nicht dauerhaft gedrückt ist
  // stepper->runToNewPosition(-backoff_steps / 2);

  // MaxSpeed wiederherstellen (wichtig, da setSpeed das überschreibt)
  stepper->setMaxSpeed(2000);

  Serial.println("Done.");
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_ENA_H, OUTPUT); digitalWrite(PIN_ENA_H, LOW);
  pinMode(PIN_ENA_V, OUTPUT); digitalWrite(PIN_ENA_V, LOW);
  pinMode(PIN_ENA_R, OUTPUT); digitalWrite(PIN_ENA_R, LOW);

  pinMode(PIN_END_H, INPUT_PULLUP);
  pinMode(PIN_END_V, INPUT_PULLUP);

  pinMode(PIN_ALM_H, INPUT_PULLUP);
  pinMode(PIN_ALM_V, INPUT_PULLUP);
  pinMode(13, OUTPUT);

  // Default Beschleunigung aus v1.2
  stepper_h.setAcceleration(80.0 * STEPS_PER_MM);
  stepper_v.setAcceleration(80.0 * STEPS_PER_MM);
  stepper_r.setAcceleration(40.0 * STEPS_PER_DEG);

  stepper_h.setMaxSpeed(MAX_STEPS_PER_SEC_LIN);
  stepper_v.setMaxSpeed(MAX_STEPS_PER_SEC_LIN);
  stepper_r.setMaxSpeed(MAX_STEPS_PER_SEC_ROT);
}

void loop() {
// TEST-FUNKTION: LED 13 leuchtet, wenn Schalter H ODER Schalter V gedrückt ist
  // Da du NC-Schalter nutzt (HIGH = Gedrückt/Unterbrochen), prüfen wir auf HIGH:
  if (digitalRead(PIN_END_H) == HIGH || digitalRead(PIN_END_V) == HIGH) {
    digitalWrite(13, HIGH);
  } else {
    digitalWrite(13, LOW);
  }
  // 1. Alarm Überwachung (CL57T ALM ist LOW bei Fehler)
  if (digitalRead(PIN_ALM_H) == LOW || digitalRead(PIN_ALM_V) == LOW) {
    stepper_h.stop(); stepper_v.stop(); stepper_r.stop();
  }

  // 2. Motor Update
  stepper_h.run(); stepper_v.run(); stepper_r.run();

  // 3. DONE Detection
  static bool wasMoving = false;
  bool isMoving = (stepper_h.distanceToGo()!=0 || stepper_v.distanceToGo()!=0 || stepper_r.distanceToGo()!=0);
  if (wasMoving && !isMoving) write_i8(COMMAND_DONE);
  wasMoving = isMoving;

  // 4. Telemetrie
  static unsigned long lastLog=0;
  if (millis()-lastLog > 100) {
    write_i8(LOG_DATA); write_i32(millis());
    write_i32(stepper_h.currentPosition()); write_i32(stepper_v.currentPosition());
    write_i32(stepper_r.currentPosition()); write_i8(isMoving?1:0);
    lastLog = millis();
  }

  // 5. Befehle
  if (Serial.available() > 0) {
    int8_t cmd = Serial.read();
    if (cmd == MOVE_AXIS) {
      unsigned long s = millis(); while(Serial.available()<9 && millis()-s<50);
      if(Serial.available()>=9) {
        int8_t ax = Serial.read(); long trg = read_i32(); long spd = read_i32();
        moveAxis(ax, trg, spd);
      }
    } else if (cmd == HOME_AXIS) {
      unsigned long s = millis(); while(Serial.available()<1 && millis()-s<50);
      if(Serial.available()>=1) {
        int8_t ax = Serial.read(); doHoming(ax); write_i8(COMMAND_DONE);
      }
    } else if (cmd == STOP_ALL) {
      stepper_h.stop(); stepper_v.stop(); stepper_r.stop();
      write_i8(COMMAND_DONE);
    }
  }
}