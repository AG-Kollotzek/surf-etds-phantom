#include <AccelStepper.h>

// --- KONFIGURATION LED & LOGIK ---
const int PIN_LED = 13; 
const int SWITCH_TRIGGERED = LOW; // Falls NC Schalter: HIGH
const int SWITCH_FREE      = HIGH; // Falls NC Schalter: LOW

// --- PROTOKOLL ---
const uint8_t LOG_DATA = 10;
const uint8_t CMD_MOVE = 1;
const uint8_t CMD_HOME = 2;
const uint8_t CMD_STOP = 3;
const uint8_t CMD_DONE = 4;

// --- PINS ---
const int PIN_PUL_H=2, PIN_DIR_H=3, PIN_ENA_H=4, PIN_END_H=5, PIN_ALM_H=A0;
const int PIN_PUL_V=6, PIN_DIR_V=7, PIN_ENA_V=8, PIN_END_V=9, PIN_ALM_V=A1;
const int PIN_PUL_R=10, PIN_DIR_R=11, PIN_ENA_R=12; 

// --- MECHANIK ---
const float STEPS_PER_MM = 800.0f;
const float STEPS_PER_DEG = 16.156f;
const float MAX_SPEED_LIN = 2000.0;
const float ACCEL_LIN = 1000.0;

AccelStepper stepper_h(AccelStepper::DRIVER, PIN_PUL_H, PIN_DIR_H);
AccelStepper stepper_v(AccelStepper::DRIVER, PIN_PUL_V, PIN_DIR_V);
AccelStepper stepper_r(AccelStepper::DRIVER, PIN_PUL_R, PIN_DIR_R);

void write_i8(int8_t v) { Serial.write((uint8_t)v); }
void write_i32(long v) { Serial.write((uint8_t*)&v, 4); }
long read_i32() { long v=0; Serial.readBytes((char*)&v, 4); return v; }

// --- HOMING ---
void doHoming(int axisIdx) {
  AccelStepper* stp;
  int switchPin;
  int dir = (axisIdx == 0) ? -1 : 1; // H negative, V positive
  
  if (axisIdx == 0) { stp = &stepper_h; switchPin = PIN_END_H; }
  else if (axisIdx == 1) { stp = &stepper_v; switchPin = PIN_END_V; }
  else { stepper_r.setCurrentPosition(0); write_i8(CMD_DONE); return; }

  stp->setSpeed(400.0 * dir);
  
  // LED blinkt während Homing (manuell da blocking)
  while (digitalRead(switchPin) == SWITCH_FREE) {
    stp->runSpeed();
    digitalWrite(PIN_LED, (millis() / 100 % 2)); // Schnelles Blinken
  }
  
  stp->setCurrentPosition(0);
  delay(100);
  stp->runToNewPosition((long)(3.0 * STEPS_PER_MM * -dir));
  
  stp->setSpeed(50.0 * dir);
  while (digitalRead(switchPin) == SWITCH_FREE) {
    stp->runSpeed();
    digitalWrite(PIN_LED, (millis() / 50 % 2)); // Noch schneller beim Fein-Homing
  }

  stp->setCurrentPosition(0);
  stp->setMaxSpeed(MAX_SPEED_LIN);
  digitalWrite(PIN_LED, HIGH); // Danach wieder AN
  write_i8(CMD_DONE);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, HIGH); // Start-Signal

  pinMode(PIN_ENA_H, OUTPUT); digitalWrite(PIN_ENA_H, LOW);
  pinMode(PIN_ENA_V, OUTPUT); digitalWrite(PIN_ENA_V, LOW);
  pinMode(PIN_ENA_R, OUTPUT); digitalWrite(PIN_ENA_R, LOW);
  
  pinMode(PIN_END_H, INPUT_PULLUP);
  pinMode(PIN_END_V, INPUT_PULLUP);
  pinMode(PIN_ALM_H, INPUT_PULLUP);
  pinMode(PIN_ALM_V, INPUT_PULLUP);

  stepper_h.setMaxSpeed(MAX_SPEED_LIN); stepper_h.setAcceleration(ACCEL_LIN);
  stepper_v.setMaxSpeed(MAX_SPEED_LIN); stepper_v.setAcceleration(ACCEL_LIN);
  stepper_r.setMaxSpeed(MAX_SPEED_LIN); stepper_r.setAcceleration(ACCEL_LIN);
}

void loop() {
  // 1. ALARM CHECK
  bool error = (digitalRead(PIN_ALM_H) == LOW || digitalRead(PIN_ALM_V) == LOW);
  
  if (Serial.available() > 0) {
    uint8_t cmd = Serial.read();
    if (cmd == CMD_MOVE) {
      while(Serial.available() < 9);
      int8_t ax = Serial.read();
      long pos = read_i32();
      long spd = read_i32();
      AccelStepper* s = (ax==0)? &stepper_h : ((ax==1)? &stepper_v : &stepper_r);
      s->setMaxSpeed((float)spd);
      s->moveTo(pos);
    }
    else if (cmd == CMD_HOME) {
      while(Serial.available() < 1);
      doHoming(Serial.read());
    }
    else if (cmd == CMD_STOP) {
      stepper_h.stop(); stepper_v.stop(); stepper_r.stop();
    }
  }

  stepper_h.run();
  stepper_v.run();
  stepper_r.run();

  // 2. LED LOGIK & TELEMETRIE
  bool isMoving = (stepper_h.distanceToGo()!=0 || stepper_v.distanceToGo()!=0 || stepper_r.distanceToGo()!=0);
  
  if (error) {
    digitalWrite(PIN_LED, LOW); // LED AUS bei Fehler
  } else {
    // Blinken bei Bewegung, AN bei Stillstand
    digitalWrite(PIN_LED, isMoving ? (millis() / 200 % 2) : HIGH);
  }

  static unsigned long lastLog = 0;
  if (millis() - lastLog > 100) {
    write_i8(LOG_DATA);
    write_i32(millis());
    write_i32(stepper_h.currentPosition());
    write_i32(stepper_v.currentPosition());
    write_i32(stepper_r.currentPosition());
    write_i8(isMoving ? 1 : (error ? 2 : 0)); // 2 = Error Status für Python
    
    static bool wasMoving = false;
    if (wasMoving && !isMoving) write_i8(CMD_DONE);
    wasMoving = isMoving;
    lastLog = millis();
  }
}