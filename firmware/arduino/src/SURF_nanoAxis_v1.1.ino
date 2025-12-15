/*
  ETD QA Test Unit - DRIVER COMPLETE
  ----------------------------------
  Hardware: Arduino Nano, CL57T Drivers
  Status:   Fixed Homing + Safety Limits + ActiveLow Endstops
*/

#include <AccelStepper.h>

// --- PROTOCOL ---
enum OrderID : uint8_t {
  HELLO = 0,
  MOVE_AXIS = 1,
  HOME_AXIS = 2,
  STOP_ALL = 3,
  LOG_DATA = 10
};

enum AxisID : uint8_t {
  AXIS_H = 0,
  AXIS_V = 1,
  AXIS_R = 2
};

// --- PINS ---
const int PIN_PUL_H = 2; const int PIN_DIR_H = 3; const int PIN_ENA_H = 4;
const int PIN_END_H = 5; const int PIN_ALM_H = A0;

const int PIN_PUL_V = 6; const int PIN_DIR_V = 7; const int PIN_ENA_V = 8;
const int PIN_END_V = 9; const int PIN_ALM_V = A1;

const int PIN_PUL_R = 10; const int PIN_DIR_R = 11; const int PIN_ENA_R = 12;
const int PIN_LED = 13;

// --- MECHANIK & LIMITS ---
const float STEPS_PER_MM = 800.0f; 
const float STEPS_PER_DEG_R = 16.515f;

// HIER SIND DIE GRENZEN DEFINIERT (JETZT SEPARAT):
// Horizontal
const float LIMIT_H_MAX = 35.0;
const float LIMIT_H_MIN = -35.0;
const long LIMIT_STEPS_H_MAX = (long)(LIMIT_H_MAX * STEPS_PER_MM); 
const long LIMIT_STEPS_H_MIN = (long)(LIMIT_H_MIN * STEPS_PER_MM); 

// Vertikal
const float LIMIT_V_MAX = 50.0;   // Beispiel: Kleinerer Bereich oben
const float LIMIT_V_MIN = -35.0;   // Beispiel: Darf nicht tief runter
const long LIMIT_STEPS_V_MAX = (long)(LIMIT_V_MAX * STEPS_PER_MM); 
const long LIMIT_STEPS_V_MIN = (long)(LIMIT_V_MIN * STEPS_PER_MM); 

const float HOME_OFFSET_MM_H = 41.0; 
const float HOME_OFFSET_MM_V = 61.5; 
const int HOMING_SIGN_H = +1;
const int HOMING_SIGN_V = +1;

// --- HOMING PARAMETER (Waren im Schnipsel gefehlt) ---
const float HOMING_V_MM_S_FAST = 10.0;
const float HOMING_V_MM_S_SLOW = 2.0;
const float BACKOFF_MM = 3.0;
const int BACKOFF_REPEATS = 2;       // 2x tasten für Präzision
const unsigned long HOMING_TIMEOUT_MS = 20000;
const unsigned long SW_DEBOUNCE_MS = 30;

// --- SPEED SETUP ---
const float DEFAULT_ACC_MM_S2 = 80.0;
const float R_ACC_DEG_S2 = 40.0;

// --- OBJEKTE ---
AccelStepper stepper_h(AccelStepper::DRIVER, PIN_PUL_H, PIN_DIR_H);
AccelStepper stepper_v(AccelStepper::DRIVER, PIN_PUL_V, PIN_DIR_V);
AccelStepper stepper_r(AccelStepper::DRIVER, PIN_PUL_R, PIN_DIR_R);

// --- STATUS ---
unsigned long lastLogTime = 0;
const unsigned long LOG_INTERVAL_MS = 50; 
bool isHoming = false; 
bool isAlarmState = false;

// --- SERIAL HELPERS ---
void write_i8(int8_t v) { Serial.write((uint8_t)v); }
void write_i32(int32_t v) {
  Serial.write((uint8_t)(v & 0xFF));
  Serial.write((uint8_t)((v >> 8) & 0xFF));
  Serial.write((uint8_t)((v >> 16) & 0xFF));
  Serial.write((uint8_t)((v >> 24) & 0xFF));
}
int8_t read_i8() { while(!Serial.available()); return (int8_t)Serial.read(); }
int32_t read_i32() {
  int32_t v = 0;
  for (int i=0; i<4; i++) {
    while(!Serial.available());
    v |= ((int32_t)Serial.read()) << (i*8);
  }
  return v;
}

// --- UTILS ---
long mmToSteps(float mm) { return (long)lround(mm * STEPS_PER_MM); }

// WICHTIG: Hier auf LOW gesetzt, da Ihre Schalter Active Low sind (INPUT_PULLUP)
inline bool readEndRawTriggered(int pinEnd) { return digitalRead(pinEnd) == HIGH; }

void updateEndstopLEDGlobal() {
  bool trigH = readEndRawTriggered(PIN_END_H);
  bool trigV = readEndRawTriggered(PIN_END_V);
  // LED an, wenn irgendein Schalter gedrückt ist
  digitalWrite(PIN_LED, (trigH || trigV) ? HIGH : LOW);
}

void setKinematics(AccelStepper &st, float v_mm_s, float acc_mm_s2) {
  st.setMaxSpeed(v_mm_s * STEPS_PER_MM);
  st.setAcceleration(acc_mm_s2 * STEPS_PER_MM);
}

// --- LOGGING ---
void sendStatusLog() {
  write_i8(LOG_DATA);
  write_i32(millis());
  write_i32(stepper_h.currentPosition());
  write_i32(stepper_v.currentPosition());
  write_i32(stepper_r.currentPosition());
  
  uint8_t status = 0;
  if (isHoming) status |= (1 << 0);
  if (digitalRead(PIN_ALM_H) == LOW) status |= (1 << 1); 
  if (digitalRead(PIN_ALM_V) == LOW) status |= (1 << 2);
  if (isAlarmState) status |= (1 << 3); 
  
  write_i8(status);
}

// --- HOMING LOGIC (Wiederhergestellt) ---
bool waitForEndstopState(int pinEnd, bool target, unsigned long timeout_ms, AccelStepper &st) {
  unsigned long tStart = millis();
  unsigned long tChange = millis();
  bool last = readEndRawTriggered(pinEnd);

  while (true) {
    if (millis() - lastLogTime >= LOG_INTERVAL_MS) { sendStatusLog(); lastLogTime = millis(); }

    // Safety Abfrage auch während Homing
    if (digitalRead(PIN_ALM_H) == LOW || digitalRead(PIN_ALM_V) == LOW) return false;

    // Endschalter lesen
    bool cur = readEndRawTriggered(pinEnd);
    
    // LED Update für visuelles Feedback
    updateEndstopLEDGlobal();

    // Debounce Logik
    if (cur != last) { last = cur; tChange = millis(); }
    if (cur == target && (millis() - tChange) >= SW_DEBOUNCE_MS) return true;
    
    // Timeout
    if (millis() - tStart > timeout_ms) return false;

    st.runSpeed();
  }
}

void doHomingAxis(AccelStepper &st, int pinEnd, int homingSign, float homeOffset) {
  // 1. Falls Schalter schon gedrückt, erst freifahren
  if (readEndRawTriggered(pinEnd)) {
    st.stop(); st.setCurrentPosition(0);
    setKinematics(st, HOMING_V_MM_S_SLOW, DEFAULT_ACC_MM_S2);
    // Fahre weg (Gegenteil von Homing Sign)
    st.moveTo(-homingSign * mmToSteps(BACKOFF_MM + 2.0)); 
    while (st.distanceToGo() != 0) { 
        st.run(); 
        if (millis() - lastLogTime >= LOG_INTERVAL_MS) { sendStatusLog(); lastLogTime = millis(); }
    }
  }

  // 2. Schnelle Suche zum Schalter
  st.stop(); st.setCurrentPosition(0); // Temporärer Nullpunkt
  setKinematics(st, HOMING_V_MM_S_FAST, DEFAULT_ACC_MM_S2);
  st.setSpeed(homingSign * mmToSteps(HOMING_V_MM_S_FAST));
  if (!waitForEndstopState(pinEnd, true, HOMING_TIMEOUT_MS, st)) return;

  // 3. Feintuning (Backoff + Langsam ran)
  for (int i = 0; i < BACKOFF_REPEATS; i++) {
    st.stop(); st.setCurrentPosition(0);
    setKinematics(st, HOMING_V_MM_S_SLOW, DEFAULT_ACC_MM_S2);
    
    // Wegfahren
    st.setSpeed(-homingSign * mmToSteps(HOMING_V_MM_S_SLOW));
    if (!waitForEndstopState(pinEnd, false, HOMING_TIMEOUT_MS, st)) return;

    // Ein Stück weiter wegfahren für sauberen Anlauf
    st.moveTo(st.currentPosition() - homingSign * mmToSteps(BACKOFF_MM)); 
    while(st.distanceToGo() != 0) { st.run(); }

    // Langsam wieder ranfahren
    st.stop(); st.setCurrentPosition(0);
    st.setSpeed(homingSign * mmToSteps(HOMING_V_MM_S_SLOW));
    if (!waitForEndstopState(pinEnd, true, HOMING_TIMEOUT_MS, st)) return;
  }

  // 4. Nullpunkt setzen (Offset anwenden)
  // HIER IST DIE ÄNDERUNG: Wir nutzen die übergebene Variable homeOffset
  st.setCurrentPosition(mmToSteps(homeOffset));
  
  // 5. Zur Null fahren (Arbeitsposition)
  setKinematics(st, 10.0, DEFAULT_ACC_MM_S2);
  st.moveTo(0);
  while (st.distanceToGo() != 0) { 
      st.run(); 
      if (millis() - lastLogTime >= LOG_INTERVAL_MS) { sendStatusLog(); lastLogTime = millis(); } 
  }
}

// --- SETUP ---
void setup() {
  pinMode(PIN_PUL_H, OUTPUT); pinMode(PIN_DIR_H, OUTPUT); pinMode(PIN_ENA_H, OUTPUT);
  pinMode(PIN_END_H, INPUT_PULLUP); pinMode(PIN_ALM_H, INPUT_PULLUP);

  pinMode(PIN_PUL_V, OUTPUT); pinMode(PIN_DIR_V, OUTPUT); pinMode(PIN_ENA_V, OUTPUT);
  pinMode(PIN_END_V, INPUT_PULLUP); pinMode(PIN_ALM_V, INPUT_PULLUP);

  pinMode(PIN_PUL_R, OUTPUT); pinMode(PIN_DIR_R, OUTPUT); pinMode(PIN_ENA_R, OUTPUT);
  pinMode(PIN_LED, OUTPUT);

  Serial.begin(115200);

  // Enable Drivers
  digitalWrite(PIN_ENA_H, LOW); digitalWrite(PIN_ENA_V, LOW); digitalWrite(PIN_ENA_R, LOW);

  stepper_h.setPinsInverted(false, false, false);
  stepper_v.setPinsInverted(false, false, false);
  stepper_r.setPinsInverted(false, false, false);

  setKinematics(stepper_h, 10.0, DEFAULT_ACC_MM_S2);
  setKinematics(stepper_v, 10.0, DEFAULT_ACC_MM_S2);
  
  stepper_r.setMaxSpeed(20.0 * STEPS_PER_DEG_R);
  stepper_r.setAcceleration(R_ACC_DEG_S2 * STEPS_PER_DEG_R);
}

// --- MAIN LOOP ---
void loop() {
  // 1. SAFETY & LOGGING
  if (digitalRead(PIN_ALM_H) == LOW || digitalRead(PIN_ALM_V) == LOW) {
      if (!isAlarmState) { stepper_h.stop(); stepper_v.stop(); stepper_r.stop(); isAlarmState = true; }
  } else { if (isAlarmState) isAlarmState = false; }

  // LED Status aktualisieren (damit man Endschalter testen kann)
  if (!isHoming) updateEndstopLEDGlobal();

  if (!isHoming) { stepper_h.run(); stepper_v.run(); stepper_r.run(); }

  if (millis() - lastLogTime >= LOG_INTERVAL_MS) { sendStatusLog(); lastLogTime = millis(); }

  // 2. BEFEHLE
  if (Serial.available() > 0) {
    int8_t order = read_i8();
    
    // Safety: Befehle bei Alarm ignorieren
    if (isAlarmState && (order == MOVE_AXIS || order == HOME_AXIS)) {
       if (order == MOVE_AXIS) { read_i8(); read_i32(); read_i32(); }
       if (order == HOME_AXIS) { read_i8(); }
       return; 
    }

    switch (order) {
      case HELLO: break;

      case MOVE_AXIS: {
        int8_t axis = read_i8();
        int32_t target_raw = read_i32(); 
        int32_t speed_raw = read_i32();  

        // --- LIMIT CHECK (SEPARAT FÜR H UND V) ---
        bool limits_ok = true;

        if (axis == AXIS_H) {
            if (target_raw > LIMIT_STEPS_H_MAX) limits_ok = false;
            if (target_raw < LIMIT_STEPS_H_MIN) limits_ok = false;
        } 
        else if (axis == AXIS_V) {
            if (target_raw > LIMIT_STEPS_V_MAX) limits_ok = false;
            if (target_raw < LIMIT_STEPS_V_MIN) limits_ok = false;
        }
        // R-Achse hat keine Limits

        // --- AUSFÜHRUNG ---
        if (limits_ok) {
            if (axis == AXIS_H) {
              stepper_h.setMaxSpeed((float)speed_raw);
              stepper_h.moveTo((long)target_raw);
            } else if (axis == AXIS_V) {
              stepper_v.setMaxSpeed((float)speed_raw);
              stepper_v.moveTo((long)target_raw);
            } else if (axis == AXIS_R) {
              stepper_r.setMaxSpeed((float)speed_raw);
              stepper_r.moveTo((long)target_raw);
            }
        }
        break; // <--- WICHTIG! Ohne das hier rennt er ins Homing!
      }

      case HOME_AXIS: {
        int8_t axis = read_i8();
        isHoming = true;
        
        // HIER SIND DIE SEPARATEN OFFSETS DRIN:
        if (axis == AXIS_H) doHomingAxis(stepper_h, PIN_END_H, HOMING_SIGN_H, HOME_OFFSET_MM_H);
        if (axis == AXIS_V) doHomingAxis(stepper_v, PIN_END_V, HOMING_SIGN_V, HOME_OFFSET_MM_V);
        
        isHoming = false;
        break;
      }
      
      case STOP_ALL: {
        stepper_h.stop(); stepper_v.stop(); stepper_r.stop();
        break;
      }
    }
  }
}