/*
  2-Achsen Stepper Interface (h = horizontal, v = vertical)
  mit:
    - AccelStepper
    - Homing für h und v mit entprelltem Endschalter + 3x Backoff/Kantensuche
    - Move in mm (X in µm, V in mm/s)
    - prehome (Joggen in mm, +/-)

  Befehle (115200 Baud, case-insensitive):

    homing           -> Homing Achse h
    homing h         -> Homing Achse h
    homing v         -> Homing Achse v
    homing all       -> Homing h, dann v

    move h X V       -> Achse h: X in µm, V in mm/s
    move v X V       -> Achse v: X in µm, V in mm/s
    move X V         -> wie früher: Achse h

    prehome h D      -> Achse h relativ um D mm bewegen (Jog), +/- erlaubt
    prehome v D      -> Achse v relativ um D mm bewegen (Jog), +/- erlaubt

  Endschalter:
    - NC verschaltet: Ruhe = LOW, ausgelöst = HIGH
    - LED (D13) leuchtet, wenn h oder v ausgelöst ist
*/

#include <AccelStepper.h>

// --- Zustände ---
enum Mode { IDLE, MOVING, HOMING };
Mode mode_h = IDLE;
Mode mode_v = IDLE;
Mode mode_r = IDLE;
bool moveActive_h = false;
bool moveActive_v = false;
bool moveActive_r = false;

// --- Pins: Achse h (horizontal) ---
const int PIN_PUL_H = 2;
const int PIN_DIR_H = 3;
const int PIN_ENA_H = 4;
const int PIN_END_H = 5;
const int PIN_ALM_H = A0;

// --- Pins: Achse v (vertical) ---
const int PIN_PUL_V = 6;
const int PIN_DIR_V = 7;
const int PIN_ENA_V = 8;
const int PIN_END_V = 9;
const int PIN_ALM_V = A1;

// --- Pins: Achse r (Rotation) ---
const int PIN_PUL_R = 10;
const int PIN_DIR_R = 11;
const int PIN_ENA_R = 12;

// --- LED ---
const int PIN_LED   = 13;

// --- Mechanik / Kinematik (für beide Achsen gleich) ---
const float STEPS_PER_REV = 200.0f;
const float MICROSTEPS    = 16.0f;
const float LEAD_MM       = 4.0f;
const float STEPS_PER_MM  = (STEPS_PER_REV * MICROSTEPS) / LEAD_MM;

// --- Mechanik r (Rotation) ---
const float STEPS_REV_R_MOTOR = 200.0f;
const float MICROSTEPS_R      = 16.0f;
const float GEAR_RATIO_R      = 2.0f;

const float STEPS_REV_R_MECH = STEPS_REV_R_MOTOR * MICROSTEPS_R * GEAR_RATIO_R;
const float STEPS_PER_DEG_R  = STEPS_REV_R_MECH / 360.0f;

long degToStepsR(float d)  { return lround(d * STEPS_PER_DEG_R); }
float stepsToDegR(long s)  { return (float)s / STEPS_PER_DEG_R; }

// --- Logik --- 
const bool ENABLE_ACTIVE_LEVEL = LOW;^

// --- Arbeitsbereich (für move) ---
const float LIMIT_MIN_MM = -40.0;
const float LIMIT_MAX_MM = +40.0;
const float HOME_OFFSET_MM = 61.0;     // Schalterposition = +61 mm

// --- Homing-Richtung: +1 = Steps Richtung Schalter, -1 = entgegengesetzt ---
const int HOMING_SIGN_H = +1;   // Wenn h in die falsche Richtung homed -> auf -1 ändern
const int HOMING_SIGN_V = +1;   // Wenn v in die falsche Richtung homed -> auf -1 ändern

// --- Homing Parameter ---
const float HOMING_V_MM_S_FAST = 10.0;
const float HOMING_V_MM_S_SLOW = 2.5;
const float DEFAULT_ACC_MM_S2  = 80.0;
const float BACKOFF_MM         = 2.0;
const int   BACKOFF_REPEATS    = 3;
const unsigned long HOMING_TIMEOUT_MS = 20000;

// --- Entprellzeit für Endstop im Homing ---
const unsigned long SW_DEBOUNCE_MS = 25;

// --- ALM-Level (autodetect) ---
bool g_ALM_ACTIVE_LEVEL_H = LOW;
bool g_ALM_ACTIVE_LEVEL_V = LOW;



// --- Rotationsachse Parameter ---
const float R_MAX_DEG_S   = 20.0;   // max 20°/s
const float R_ACC_DEG_S2  = 40.0;   // sehr sanft (präzise!)






// --- AccelStepper-Objekte ---
AccelStepper stepper_h(AccelStepper::DRIVER, PIN_PUL_H, PIN_DIR_H);
AccelStepper stepper_v(AccelStepper::DRIVER, PIN_PUL_V, PIN_DIR_V);
AccelStepper stepper_r(AccelStepper::DRIVER, PIN_PUL_R, PIN_DIR_R);


// --- Hilfsfunktionen allgemein --------------------------------------------------

long mmToSteps(float mm) {
  return (long)lround(mm * STEPS_PER_MM);
}
float stepsToMm(long steps) {
  return (float)steps / STEPS_PER_MM;
}

inline void setEnable_h(bool on) {
  digitalWrite(PIN_ENA_H, on ? ENABLE_ACTIVE_LEVEL : !ENABLE_ACTIVE_LEVEL);
}
inline void setEnable_v(bool on) {
  digitalWrite(PIN_ENA_V, on ? ENABLE_ACTIVE_LEVEL : !ENABLE_ACTIVE_LEVEL);
}

inline bool isAlarmActive_h() {
  return digitalRead(PIN_ALM_H) == g_ALM_ACTIVE_LEVEL_H;
}
inline bool isAlarmActive_v() {
  return digitalRead(PIN_ALM_V) == g_ALM_ACTIVE_LEVEL_V;
}

// Endstop-Auswertung (roh): HIGH = ausgelöst, LOW = nicht ausgelöst
inline bool readEndRawTriggered(int pinEnd) {
  return digitalRead(pinEnd) == HIGH;
}

// LED zeigt: irgendein Endstop ausgelöst?
void updateEndstopLEDGlobal() {
  bool trigH = readEndRawTriggered(PIN_END_H);
  bool trigV = readEndRawTriggered(PIN_END_V);
  digitalWrite(PIN_LED, (trigH || trigV) ? HIGH : LOW);
}

// Rampen setzen (mm/s, mm/s^2)
void setKinematics(AccelStepper &st, float v_mm_s, float acc_mm_s2) {
  if (v_mm_s < 0) v_mm_s = -v_mm_s;
  if (acc_mm_s2 < 1.0) acc_mm_s2 = 1.0;
  if (v_mm_s > 100.0) v_mm_s = 100.0;  // Hardlimit

  float v_steps_s    = v_mm_s   * STEPS_PER_MM;
  float acc_steps_s2 = acc_mm_s2* STEPS_PER_MM;
  st.setMaxSpeed(v_steps_s);
  st.setAcceleration(acc_steps_s2);
}

// Ziel begrenzen + auf 5 Steps runden
bool clampAndRoundTarget_mm(float &target_mm) {
  if (target_mm < LIMIT_MIN_MM || target_mm > LIMIT_MAX_MM) return false;
  long steps = mmToSteps(target_mm);
  steps = (steps/5) * 5;
  target_mm = stepsToMm(steps);
  return true;
}

// Serial-Parsing ---------------------------------------------------------------

bool nextToken(const String& s, int &idx, String &tok){
  while (idx < (int)s.length() && (s[idx]==' '||s[idx]=='\t'||s[idx]=='\r')) idx++;
  if (idx >= (int)s.length()) return false;
  int start = idx;
  while (idx < (int)s.length() && !(s[idx]==' '||s[idx]=='\t'||s[idx]=='\r')) idx++;
  tok = s.substring(start, idx);
  return tok.length() > 0;
}

bool parseMoveArgs(String args, long &Xum, float &Vmm){
  args.trim();
  args.replace(',', '.');
  int i = 0; String t1, t2;
  if (!nextToken(args, i, t1)) return false;
  if (!nextToken(args, i, t2)) return false;
  Xum = (long)t1.toFloat();
  Vmm = t2.toFloat();
  bool ok1 = false, ok2 = false;
  for (unsigned k=0; k<t1.length(); k++) if (isDigit(t1[k])) { ok1=true; break; }
  for (unsigned k=0; k<t2.length(); k++) if (isDigit(t2[k])) { ok2=true; break; }
  return ok1 && ok2;
}

// Move & prehome ---------------------------------------------------------------

bool startMoveTo_mm(AccelStepper &st, Mode &mode, bool &moveActive,
                    char axisId, float target_mm, float velocity_mm_s) {
  if (!clampAndRoundTarget_mm(target_mm)) {
    Serial.print("[");
    Serial.print(axisId);
    Serial.println(F("] Ziel außerhalb −40..+40 mm!"));
    return false;
  }
  setKinematics(st, velocity_mm_s, DEFAULT_ACC_MM_S2);
  long targetSteps = mmToSteps(target_mm);
  st.moveTo(targetSteps);
  moveActive = true;
  mode = MOVING;

  Serial.print("[");
  Serial.print(axisId);
  Serial.print(F("] Move to "));
  Serial.print(target_mm, 3);
  Serial.print(F(" mm @ "));
  Serial.print(velocity_mm_s, 3);
  Serial.println(F(" mm/s"));

  return true;
}

// --- Enable für r ---
inline void setEnable_r(bool on){
  digitalWrite(PIN_ENA_R, on ? ENABLE_ACTIVE_LEVEL : !ENABLE_ACTIVE_LEVEL);
}

// --- Move r (Rotation) ---
bool startMoveR(float targetDeg, float velDeg){
  if (velDeg <= 0 || velDeg > R_MAX_DEG_S){
    Serial.println(F("[r] Error: Speed must be 0 < v <= 20°/s"));
    return false;
  }

  setEnable_r(true);

  long tgtSteps = degToStepsR(targetDeg);
  float spdSteps = velDeg * STEPS_PER_DEG_R;
  float accSteps = R_ACC_DEG_S2 * STEPS_PER_DEG_R;

  stepper_r.setMaxSpeed(spdSteps);
  stepper_r.setAcceleration(accSteps);
  stepper_r.moveTo(tgtSteps);

  mode_r = MOVING;
  moveActive_r = true;

  Serial.print(F("[r] Move to "));
  Serial.print(targetDeg);
  Serial.print(F("° @ "));
  Serial.print(velDeg);
  Serial.println(F("°/s"));

  return true;
}


// prehome = Joggen relativ in mm, +/- erlaubt
bool prehomeShift(AccelStepper &st, Mode &mode, bool &moveActive,
                  char axisId, float dist_mm) {
  if (dist_mm == 0.0f) {
    Serial.println(F("Distance must be non-zero."));
    return false;
  }
  long delta = mmToSteps(dist_mm);
  long target = st.currentPosition() + delta;
  setKinematics(st, 5.0, DEFAULT_ACC_MM_S2); // konservativ
  st.moveTo(target);
  moveActive = true;
  mode = MOVING;

  Serial.print("[");
  Serial.print(axisId);
  Serial.print(F("] prehome shift: "));
  Serial.print(dist_mm);
  Serial.println(F(" mm (relativ)."));

  return true;
}

// Entprelltes Warten auf Endstop-Zustand --------------------------------------
// target = true  -> warten bis ausgelöst (HIGH)
// target = false -> warten bis nicht ausgelöst (LOW)
bool waitForEndstopState(int pinEnd, bool target,
                         unsigned long timeout_ms,
                         AccelStepper &st,
                         bool (*isAlarmActiveFunc)(),
                         char axisId) {

  unsigned long tStart = millis();
  bool last = readEndRawTriggered(pinEnd);
  unsigned long tChange = millis();

  while (true) {
    bool cur = readEndRawTriggered(pinEnd);
    if (cur != last) {
      last = cur;
      tChange = millis();
    }

    if (cur == target && (millis() - tChange) >= SW_DEBOUNCE_MS) {
      return true;
    }

    if (millis() - tStart > timeout_ms) {
      Serial.print("[");
      Serial.print(axisId);
      Serial.println(F("] Endstop Wait Timeout."));
      return false;
    }

    // Stepper konstant mit runSpeed bewegen (Speed muss vorher gesetzt sein)
    st.runSpeed();

    // LED live aktualisieren
    updateEndstopLEDGlobal();

    if (isAlarmActiveFunc && isAlarmActiveFunc()) {
      Serial.print("[");
      Serial.print(axisId);
      Serial.println(F("] ALM aktiv während Endstop-Wait."));
      // ggf. return false; wenn du abbrechen willst
    }
  }
}

// Homing mit 3x Backoff/Kantensuche ------------------------------------------

bool doHomingAxis(AccelStepper &st,
                  int pinEnd,
                  bool (*isAlarmActiveFunc)(),
                  char axisId,
                  int homingSign) {

  Serial.print("[");
  Serial.print(axisId);
  Serial.println(F("] Starte Homing..."));

  // 0) Sicherstellen, dass Enable aktiv ist
  if (axisId == 'h') setEnable_h(true);
  else               setEnable_v(true);

  // 1) Falls wir schon am Schalter stehen -> erst ein Stück wegfahren
  if (readEndRawTriggered(pinEnd)) {
    Serial.print("[");
    Serial.print(axisId);
    Serial.println(F("] Starte auf Schalter -> fahre kurz weg."));
    st.stop();
    st.setCurrentPosition(st.currentPosition());
    setKinematics(st, HOMING_V_MM_S_SLOW, DEFAULT_ACC_MM_S2);

    long backSteps = mmToSteps(BACKOFF_MM);
    long tgt = st.currentPosition() - homingSign * backSteps; // weg vom Schalter
    st.moveTo(tgt);

    while (st.distanceToGo() != 0) {
      st.run();
      updateEndstopLEDGlobal();
      if (isAlarmActiveFunc && isAlarmActiveFunc()) {
        Serial.print("[");
        Serial.print(axisId);
        Serial.println(F("] ALM aktiv beim Wegfahren."));
        return false;
      }
    }
  }

  // 2) Schnell ZUM Schalter
  Serial.print("[");
  Serial.print(axisId);
  Serial.println(F("] Fahre zum Schalter (FAST)..."));

  st.stop();
  st.setCurrentPosition(st.currentPosition());
  setKinematics(st, HOMING_V_MM_S_FAST, DEFAULT_ACC_MM_S2);

  long speedFast = mmToSteps(HOMING_V_MM_S_FAST);
  st.setSpeed(homingSign * speedFast);

  if (!waitForEndstopState(pinEnd, true, HOMING_TIMEOUT_MS, st, isAlarmActiveFunc, axisId)) {
    Serial.print("[");
    Serial.print(axisId);
    Serial.println(F("] Schalter beim Anfahren nicht erreicht."));
    return false;
  }

  Serial.print("[");
  Serial.print(axisId);
  Serial.println(F("] Schalterkontakt erkannt. Starte 3x Backoff..."));

  long lastHit = 0;

  // 3) Dreifache Backoff/Kantensuche
  for (int i = 0; i < BACKOFF_REPEATS; i++) {
    Serial.print("[");
    Serial.print(axisId);
    Serial.print(F("] Backoff-Runde "));
    Serial.println(i + 1);

    // 3a) Langsam vom Schalter wegfahren bis nicht ausgelöst
    st.stop();
    st.setCurrentPosition(st.currentPosition());
    setKinematics(st, HOMING_V_MM_S_SLOW, DEFAULT_ACC_MM_S2);

    long speedSlow = mmToSteps(HOMING_V_MM_S_SLOW);
    st.setSpeed(-homingSign * speedSlow);   // weg vom Schalter

    if (!waitForEndstopState(pinEnd, false, HOMING_TIMEOUT_MS, st, isAlarmActiveFunc, axisId)) {
      Serial.print("[");
      Serial.print(axisId);
      Serial.println(F("] Schalter nicht sauber verlassen."));
      return false;
    }

    // 3b) kleiner Backoff in Richtung Schalter
    long backSteps = mmToSteps(BACKOFF_MM);
    long tgt = st.currentPosition() - homingSign * backSteps; // wieder in Richtung Schalter
    st.moveTo(tgt);
    while (st.distanceToGo() != 0) {
      st.run();
      updateEndstopLEDGlobal();
      if (isAlarmActiveFunc && isAlarmActiveFunc()) {
        Serial.print("[");
        Serial.print(axisId);
        Serial.println(F("] ALM aktiv während Backoff-Bewegung."));
        return false;
      }
    }

    // 3c) Wieder Kante finden (langsam zum Schalter)
    st.stop();
    st.setCurrentPosition(st.currentPosition());
    st.setSpeed(homingSign * speedSlow); // hin zum Schalter

    if (!waitForEndstopState(pinEnd, true, HOMING_TIMEOUT_MS, st, isAlarmActiveFunc, axisId)) {
      Serial.print("[");
      Serial.print(axisId);
      Serial.println(F("] Kante in Backoff-Runde nicht gefunden."));
      return false;
    }

    lastHit = st.currentPosition();
    Serial.print("[");
    Serial.print(axisId);
    Serial.print(F("] Kante gefunden bei Steps = "));
    Serial.println(lastHit);
  }

  // 4) Home-Offset setzen
  long offsetSteps = mmToSteps(HOME_OFFSET_MM);
  st.setCurrentPosition(offsetSteps);
  Serial.print("[");
  Serial.print(axisId);
  Serial.print(F("] Position auf +"));
  Serial.print(HOME_OFFSET_MM);
  Serial.println(F(" mm gesetzt."));

  // 5) Auf 0 mm fahren
  Serial.print("[");
  Serial.print(axisId);
  Serial.println(F("] Fahre von Offset auf 0 mm..."));

  setKinematics(st, 10.0, DEFAULT_ACC_MM_S2);
  st.moveTo(mmToSteps(0.0));
  while (st.distanceToGo() != 0) {
    st.run();
    updateEndstopLEDGlobal();
    if (isAlarmActiveFunc && isAlarmActiveFunc()) {
      Serial.print("[");
      Serial.print(axisId);
      Serial.println(F("] ALM aktiv beim Positionieren auf 0 mm."));
      return false;
    }
  }

  Serial.print("[");
  Serial.print(axisId);
  Serial.println(F("] Homing abgeschlossen. Position = 0 mm."));
  return true;
}

// Setup -----------------------------------------------------------------------

// Setup -----------------------------------------------------------------------

void setup() {
  // h
  pinMode(PIN_PUL_H, OUTPUT); digitalWrite(PIN_PUL_H, LOW);
  pinMode(PIN_DIR_H, OUTPUT); digitalWrite(PIN_DIR_H, LOW);
  pinMode(PIN_ENA_H, OUTPUT);
  pinMode(PIN_END_H, INPUT_PULLUP);
  pinMode(PIN_ALM_H, INPUT_PULLUP);

  // v
  pinMode(PIN_PUL_V, OUTPUT); digitalWrite(PIN_PUL_V, LOW);
  pinMode(PIN_DIR_V, OUTPUT); digitalWrite(PIN_DIR_V, LOW);
  pinMode(PIN_ENA_V, OUTPUT);
  pinMode(PIN_END_V, INPUT_PULLUP);
  pinMode(PIN_ALM_V, INPUT_PULLUP);

  // r
  pinMode(PIN_PUL_R, OUTPUT); digitalWrite(PIN_PUL_R, LOW);
  pinMode(PIN_DIR_R, OUTPUT); digitalWrite(PIN_DIR_R, LOW);
  pinMode(PIN_ENA_R, OUTPUT);

  // LED
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  Serial.begin(115200);
  Serial.println(F("3-Achsen Stepper Interface bereit."));
  Serial.println(F("Befehle: homing h|v|all | move h|v X V | move r deg vel | prehome h|v D"));

  delay(10);
  g_ALM_ACTIVE_LEVEL_H = (digitalRead(PIN_ALM_H) == HIGH) ? LOW : HIGH;
  g_ALM_ACTIVE_LEVEL_V = (digitalRead(PIN_ALM_V) == HIGH) ? LOW : HIGH;

  updateEndstopLEDGlobal();

  stepper_h.setPinsInverted(false, false, false);
  stepper_v.setPinsInverted(false, false, false);
  stepper_r.setPinsInverted(false, false, false);

  setEnable_h(true);
  setEnable_v(true);
  setEnable_r(true);

  setKinematics(stepper_h, 10.0, DEFAULT_ACC_MM_S2);
  setKinematics(stepper_v, 10.0, DEFAULT_ACC_MM_S2);

  // Rotation: Start = 0°
  stepper_r.setMaxSpeed(0);
  stepper_r.setAcceleration(R_ACC_DEG_S2 * STEPS_PER_DEG_R);
  stepper_r.setCurrentPosition(0);
}

// Loop ------------------------------------------------------------------------

void loop() {

  updateEndstopLEDGlobal();

  // --- Bewegungen weiterführen --------------------------------------------------

  // h
  if (mode_h == MOVING) {
    stepper_h.run();
    if (stepper_h.distanceToGo() == 0) {
      if (moveActive_h) {
        Serial.print(F("[h] Move fertig. Pos = "));
        Serial.print(stepsToMm(stepper_h.currentPosition()), 3);
        Serial.println(F(" mm."));
        moveActive_h = false;
      }
      mode_h = IDLE;
    }
  }

  // v
  if (mode_v == MOVING) {
    stepper_v.run();
    if (stepper_v.distanceToGo() == 0) {
      if (moveActive_v) {
        Serial.print(F("[v] Move fertig. Pos = "));
        Serial.print(stepsToMm(stepper_v.currentPosition()), 3);
        Serial.println(F(" mm."));
        moveActive_v = false;
      }
      mode_v = IDLE;
    }
  }

  // r  (NEU)
  if (mode_r == MOVING) {
    stepper_r.run();
    if (stepper_r.distanceToGo() == 0) {
      if (moveActive_r) {
        Serial.print(F("[r] Move fertig. Pos = "));
        Serial.print(stepsToDegR(stepper_r.currentPosition()), 2);
        Serial.println(F(" °."));
        moveActive_r = false;
      }
      mode_r = IDLE;
    }
  }

  // --- ALARM-Prüfungen ---------------------------------------------------------

  if (isAlarmActive_h() && mode_h == MOVING) {
    Serial.println(F("[h] ALM aktiv -> Move gestoppt."));
    stepper_h.stop();
    moveActive_h = false;
    mode_h = IDLE;
  }

  if (isAlarmActive_v() && mode_v == MOVING) {
    Serial.println(F("[v] ALM aktiv -> Move gestoppt."));
    stepper_v.stop();
    moveActive_v = false;
    mode_v = IDLE;
  }

  // Rotation hat keinen ALM-Pin → nichts tun


  // --- SERIELLE BEFEHLE --------------------------------------------------------

  if (Serial.available()) {

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toLowerCase();

    // MOVE r
    if (cmd.startsWith("move r")) {
      String args = cmd.substring(6);
      args.trim();
      int i = 0;
      String t1, t2;
      if (!nextToken(args, i, t1) || !nextToken(args, i, t2)) {
        Serial.println(F("[r] Syntax: move r <deg> <deg_per_s>"));
      } else {
        float deg = t1.toFloat();
        float vel = t2.toFloat();
        startMoveR(deg, vel);
      }
    }

    // HOMING
    else if (cmd.startsWith("homing")) {

      String args = cmd.substring(6);
      args.trim();

      if (args.length() == 0 || args == "h") {
        stepper_h.stop();
        doHomingAxis(stepper_h, PIN_END_H, &isAlarmActive_h, 'h', HOMING_SIGN_H);
      }
      else if (args == "v") {
        stepper_v.stop();
        doHomingAxis(stepper_v, PIN_END_V, &isAlarmActive_v, 'v', HOMING_SIGN_V);
      }
      else if (args == "all") {
        stepper_h.stop();
        doHomingAxis(stepper_h, PIN_END_H, &isAlarmActive_h, 'h', HOMING_SIGN_H);

        stepper_v.stop();
        doHomingAxis(stepper_v, PIN_END_V, &isAlarmActive_v, 'v', HOMING_SIGN_V);
      }
      else {
        Serial.println(F("Syntax: homing h|v|all"));
      }
    }

    // PREHOME
    else if (cmd.startsWith("prehome")) {
      String args = cmd.substring(7);
      args.trim();
      String tok;
      int idx = 0;

      if (!nextToken(args, idx, tok)) {
        Serial.println(F("Syntax: prehome h|v D"));
      }
      else {
        char a = tok[0];
        String tdist;
        if (!nextToken(args, idx, tdist)) {
          Serial.println(F("Syntax: prehome h|v D"));
        } else {
          float dist = tdist.toFloat();
          if (a == 'h')
            prehomeShift(stepper_h, mode_h, moveActive_h, 'h', dist);
          else if (a == 'v')
            prehomeShift(stepper_v, mode_v, moveActive_v, 'v', dist);
          else
            Serial.println(F("Unknown axis for prehome."));
        }
      }
    }

    // MOVE h/v
    else if (cmd.startsWith("move")) {
      String args = cmd.substring(4);
      args.trim();

      char axisId = 'h';
      long Xum;
      float Vmm;

      String tok;
      int idx = 0;

      if (nextToken(args, idx, tok)) {

        if (tok == "h" || tok == "v") {
          axisId = tok[0];
          String rest = args.substring(idx);
          if (!parseMoveArgs(rest, Xum, Vmm)) {
            Serial.println(F("Syntax: move h|v X V"));
          } else {
            float Xmm = Xum / 1000.0f;
            if (axisId == 'h')
              startMoveTo_mm(stepper_h, mode_h, moveActive_h, 'h', Xmm, Vmm);
            else
              startMoveTo_mm(stepper_v, mode_v, moveActive_v, 'v', Xmm, Vmm);
          }
        }

        else {
          // Legacy: move X V -> h
          if (!parseMoveArgs(args, Xum, Vmm)) {
            Serial.println(F("Syntax: move h|v X V"));
          } else {
            float Xmm = Xum / 1000.0f;
            startMoveTo_mm(stepper_h, mode_h, moveActive_h, 'h', Xmm, Vmm);
          }
        }

      } else {
        Serial.println(F("Syntax: move h|v X V"));
      }
    }

    // UNKNOWN
    else {
      Serial.print(F("Unknown command: "));
      Serial.println(cmd);
    }
  }

} // <- WICHTIG! loop() korrekt geschlossen
