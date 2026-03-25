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
  COMMAND_DONE = 4,
  SET_BACKLASH = 5,
  SET_ZERO = 6,     // <--- Neu: Aktuelle Position zu Null definieren
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
const float STEPS_PER_DEG_R = 16.156f;
// --- SPEED LIMITS (SAFETY) ---
const float MAX_SPEED_MM_S = 50.0;    // Limit für Linearachsen
const float MAX_SPEED_DEG_S = 90.0;  // Limit für Rotationsachse
// --- BACKLASH KONFIGURATION ---
bool backlash_on = false;                     // Standardmäßig aus
const int backlash_steps[3] = {0, 0, 4};      // Steps für [H, V, R]
int last_dir[3] = {0, 0, 0};                  // Speichert letzte Laufrichtung

// Vorausberechnete Limits in Steps/Sec
const long MAX_STEPS_PER_SEC_LIN = (long)(MAX_SPEED_MM_S * STEPS_PER_MM);
const long MAX_STEPS_PER_SEC_ROT = (long)(MAX_SPEED_DEG_S * STEPS_PER_DEG_R);

// HIER SIND DIE GRENZEN der Achsen DEFINIERT (JETZT SEPARAT):
// Horizontal
const float LIMIT_H_MAX = 25.0;
const float LIMIT_H_MIN = -45.0;
const long LIMIT_STEPS_H_MAX = (long)(LIMIT_H_MAX * STEPS_PER_MM); 
const long LIMIT_STEPS_H_MIN = (long)(LIMIT_H_MIN * STEPS_PER_MM); 

// Vertikal
const float LIMIT_V_MAX = 50.0;   // Beispiel: größerer Bereich oben
const float LIMIT_V_MIN = -35.0;   // Beispiel: Darf nicht tief runter
const long LIMIT_STEPS_V_MAX = (long)(LIMIT_V_MAX * STEPS_PER_MM); 
const long LIMIT_STEPS_V_MIN = (long)(LIMIT_V_MIN * STEPS_PER_MM); 

//Rotation
const float LIMIT_R_MAX = 120.0;   // Maximaler Winkel
const float LIMIT_R_MIN = -30.0;  // Minimaler Winkel
const long LIMIT_STEPS_R_MAX = (long)(LIMIT_R_MAX * STEPS_PER_DEG_R); // Umrechnung in Steps (basierend auf deinen 16.156 STEPS_PER_DEG_R)
const long LIMIT_STEPS_R_MIN = (long)(LIMIT_R_MIN * STEPS_PER_DEG_R);


// --- HOMING PARAMETER ---
const float HOMING_V_MM_S_FAST = 10.0;
const float HOMING_V_MM_S_SLOW = 2.0;
const float BACKOFF_MM = 3.0;
const int BACKOFF_REPEATS = 2;       // 2x tasten für Präzision
const unsigned long HOMING_TIMEOUT_MS = 20000;
const unsigned long SW_DEBOUNCE_MS = 30;
const float HOME_OFFSET_MM_H = 33.0; 
const float HOME_OFFSET_MM_V = 62.0; 
const int HOMING_SIGN_H = +1;
const int HOMING_SIGN_V = +1;

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
bool rAxisInitialized = false;
bool hAxisInitialized = false;
bool vAxisInitialized = false;
bool wasMoving = false;

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
inline bool readEndRawTriggered(int pinEnd) { 
  return digitalRead(pinEnd) == HIGH; // LOW = Gedrückt (bei Schalter gegen GND)
}

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

// --- SAFETY: LIMIT CHECK FUNCTION ---
bool isTargetSafe(uint8_t axis, int32_t target_raw) {
    if (axis == AXIS_H) {
        return (target_raw >= LIMIT_STEPS_H_MIN && target_raw <= LIMIT_STEPS_H_MAX);
    }
    else if (axis == AXIS_V) {
        return (target_raw >= LIMIT_STEPS_V_MIN && target_raw <= LIMIT_STEPS_V_MAX);
    }
    else if (axis == AXIS_R) {
        // Rotationsachse darf nur bewegt werden, wenn sie gehomed wurde (rAxisInitialized = true)
        if (!rAxisInitialized) return false;
        return (target_raw >= LIMIT_STEPS_R_MIN && target_raw <= LIMIT_STEPS_R_MAX);
    }
    return false; // Unbekannte Achse ist unsicher
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

bool doHomingAxis(AccelStepper &st, int pinEnd, int homingSign, float homeOffset) {
  // 1. Freifahren, falls Schalter belegt
  if (readEndRawTriggered(pinEnd)) {
    setKinematics(st, HOMING_V_MM_S_SLOW, DEFAULT_ACC_MM_S2);
    st.move(-homingSign * mmToSteps(BACKOFF_MM + 5.0)); 
    while (st.distanceToGo() != 0) { 
        st.run(); 
        if (millis() - lastLogTime >= LOG_INTERVAL_MS) { sendStatusLog(); lastLogTime = millis(); }
    }
  }

  // 2. Schnelle Suche
  st.setSpeed(homingSign * mmToSteps(HOMING_V_MM_S_FAST));
  if (!waitForEndstopState(pinEnd, true, HOMING_TIMEOUT_MS, st)) return false; // FAIL

  // 3. Feintuning
  for (int i = 0; i < BACKOFF_REPEATS; i++) {
    st.setSpeed(-homingSign * mmToSteps(HOMING_V_MM_S_SLOW));
    if (!waitForEndstopState(pinEnd, false, HOMING_TIMEOUT_MS, st)) return false; // FAIL
    
    delay(100); // Kurz zur Ruhe kommen lassen
    
    st.setSpeed(homingSign * mmToSteps(HOMING_V_MM_S_SLOW));
    if (!waitForEndstopState(pinEnd, true, HOMING_TIMEOUT_MS, st)) return false; // FAIL
  }

  // 4. Nullpunkt setzen
  st.setCurrentPosition(mmToSteps(homeOffset));
  
  // 5. Zur Arbeits-Null fahren
  setKinematics(st, 15.0, DEFAULT_ACC_MM_S2);
  st.moveTo(0);
  while (st.distanceToGo() != 0) { 
      st.run(); 
      if (millis() - lastLogTime >= LOG_INTERVAL_MS) { sendStatusLog(); lastLogTime = millis(); } 
  }
  return true; // SUCCESS
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

  if (millis() - lastLogTime >= LOG_INTERVAL_MS) { sendStatusLog(); lastLogTime = millis();

  // --- COMMAND DONE DETEKTION ---
  bool isMoving = (stepper_h.distanceToGo() != 0 ||
                   stepper_v.distanceToGo() != 0 ||
                   stepper_r.distanceToGo() != 0);

  // Wenn er vorher fuhr und jetzt steht -> Signal senden
  if (wasMoving && !isMoving) {
      write_i8(COMMAND_DONE);
  }
  wasMoving = isMoving;
  }

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

        // --- SAFETY: SPEED LIMITING ---
        if (axis == AXIS_H || axis == AXIS_V) {
            if (speed_raw > MAX_STEPS_PER_SEC_LIN) speed_raw = MAX_STEPS_PER_SEC_LIN;
        } else if (axis == AXIS_R) {
            if (speed_raw > MAX_STEPS_PER_SEC_ROT) speed_raw = MAX_STEPS_PER_SEC_ROT;
        }

        // --- LIMIT CHECK ---
        bool limits_ok = isTargetSafe(axis, target_raw);

      // --- AUSFÜHRUNG ---
        if (limits_ok) {
            AccelStepper* selectedStepper = nullptr;
            if (axis == AXIS_H) selectedStepper = &stepper_h;
            else if (axis == AXIS_V) selectedStepper = &stepper_v;
            else if (axis == AXIS_R) selectedStepper = &stepper_r;

            if (selectedStepper != nullptr) {

                // --- NEU: BACKLASH COMPENSATION ---
                if (backlash_on && backlash_steps[axis] > 0) {
                    long current_pos = selectedStepper->currentPosition();

                    int new_dir = 0;
                    if (target_raw > current_pos) new_dir = 1;
                    else if (target_raw < current_pos) new_dir = -1;

                    // Richtungswechsel erkannt?
                    if (new_dir != 0 && last_dir[axis] != 0 && new_dir != last_dir[axis]) {
                        long correction = backlash_steps[axis] * new_dir;

                        // 1. Physisch das Spiel ausgleichen
                        selectedStepper->setMaxSpeed(50.0); // Moderates Tempo für den Korrektur-Ruck
                        selectedStepper->move(correction);
                        while (selectedStepper->distanceToGo() != 0) {
                            selectedStepper->run();
                        }

                        // 2. WICHTIG: Die logische Position für Python wiederherstellen!
                        // Verhindert den Drift-Fehler komplett.
                        selectedStepper->setCurrentPosition(current_pos);
                    }

                    if (new_dir != 0) {
                        last_dir[axis] = new_dir;
                    }
                }
                // --- ENDE BACKLASH ---

                // --- URSPRÜNGLICHER BEWEGUNGSBEFEHL ---
                selectedStepper->setMaxSpeed((float)speed_raw);
                selectedStepper->moveTo((long)target_raw);

                while (selectedStepper->distanceToGo() != 0) {
                    selectedStepper->run();
                    if (millis() - lastLogTime >= LOG_INTERVAL_MS) {
                        sendStatusLog();
                        lastLogTime = millis();
                    }
                }
            }
        }
        write_i8(COMMAND_DONE);
        break;
      }

      case HOME_AXIS: {
        int8_t axis = read_i8();
        isHoming = true;
        bool success = false;
        
        if (axis == AXIS_H) {
            success = doHomingAxis(stepper_h, PIN_END_H, HOMING_SIGN_H, HOME_OFFSET_MM_H);
            last_dir[AXIS_H] = 0;
        } else if (axis == AXIS_V) {
            success = doHomingAxis(stepper_v, PIN_END_V, HOMING_SIGN_V, HOME_OFFSET_MM_V);
            last_dir[AXIS_V] = 0;
        } else if (axis == AXIS_R) {
            stepper_r.setCurrentPosition(0);
            rAxisInitialized = true; 
            success = true;
            last_dir[AXIS_R] = 0;
        }

        isHoming = false;
        // WICHTIG: Sende IMMER eine Antwort, damit Python weitermacht
        write_i8(COMMAND_DONE); 
        break;
      }

      case SET_BACKLASH: {
        int8_t state = read_i8();     // 1 = On, 0 = Off
        backlash_on = (state == 1);
        write_i8(COMMAND_DONE);
        break;
      }

      case SET_ZERO: {
        int8_t axis = read_i8();
        if (axis == AXIS_H) {
            stepper_h.setCurrentPosition(0);
            last_dir[AXIS_H] = 0;
        } else if (axis == AXIS_V) {
            stepper_v.setCurrentPosition(0);
            last_dir[AXIS_V] = 0;
        } else if (axis == AXIS_R) {
            stepper_r.setCurrentPosition(0);
            last_dir[AXIS_R] = 0;
            rAxisInitialized = true; // Wichtig für die Sicherheitsprüfung
        }
        write_i8(COMMAND_DONE);
        break;
      }

      case STOP_ALL: {
        stepper_h.stop(); stepper_v.stop(); stepper_r.stop();
        break;
      }
    }
  }
}