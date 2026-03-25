#include <AccelStepper.h>

// --- PINS (v5 Standard) ---
const int PIN_PUL_R = 10; 
const int PIN_DIR_R = 11; 
const int PIN_ENA_R = 12;

// --- KALIBRIERTE WERTE ---
const float STEPS_PER_DEGREE = 16.1599; 

// --- BACKLASH KORREKTUR ---
// 0.06mm an 15mm Hebelarm entspricht ca. 3.7 Steps -> wir nutzen 4.
const int BACKLASH_STEPS = 4; 
int last_dir_r = 0; // Speichert die letzte Richtung (1 = pos, -1 = neg)

AccelStepper stepper_r(AccelStepper::DRIVER, PIN_PUL_R, PIN_DIR_R);

void setup() {
  Serial.begin(115200); 
  pinMode(PIN_ENA_R, OUTPUT);
  digitalWrite(PIN_ENA_R, LOW);

  stepper_r.setMaxSpeed(2000); 
  stepper_r.setAcceleration(1000); 
  
  Serial.println("--- SGRT QA: Kalibrierung v6 (INKL. BACKLASH) ---");
  Serial.print("Korrekturwert: "); Serial.print(BACKLASH_STEPS); Serial.println(" Steps bei Richtungswechsel.");
}

void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    
    if (input.startsWith("m ")) {
      String values = input.substring(2);
      int spaceIndex = values.indexOf(' ');
      
      if (spaceIndex > 0) {
        float degrees = values.substring(0, spaceIndex).toFloat();
        float degPerSec = values.substring(spaceIndex + 1).toFloat();
        
        long stepsToMove = (long)(degrees * STEPS_PER_DEGREE);
        
        // --- BACKLASH LOGIK ---
        int current_dir = (stepsToMove > 0) ? 1 : (stepsToMove < 0 ? -1 : 0);
        
        // Wenn Richtung gewechselt wird und es nicht die erste Bewegung ist:
        if (current_dir != 0 && last_dir_r != 0 && current_dir != last_dir_r) {
            // Addiere die Backlash-Steps in die neue Bewegungsrichtung
            stepsToMove += (current_dir * BACKLASH_STEPS);
            Serial.print("[Kompensation: "); Serial.print(current_dir * BACKLASH_STEPS); Serial.println(" Steps]");
        }
        
        if (current_dir != 0) last_dir_r = current_dir;
        // ----------------------

        float speedInSteps = degPerSec * STEPS_PER_DEGREE;
        stepper_r.setMaxSpeed(speedInSteps);
        stepper_r.move(stepsToMove); 
        
        Serial.print("Fahre "); Serial.print(degrees); Serial.println(" Grad.");
      }
    } 
    else if (input == "stop") {
      stepper_r.stop();
      Serial.println("STOP.");
    }
  }
  stepper_r.run();
}