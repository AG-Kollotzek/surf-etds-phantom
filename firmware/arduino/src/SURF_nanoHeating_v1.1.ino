// --- Konfiguration ---
const int PWM_CONTROL_PIN = 5;      // Digital Pin D5 (PWM-fähig) -> Trigger FET-Modul
const int TACHO_PIN = 2;            // Digital Pin D2 (Interrupt-fähig) -> Fan FG-Signal
const long START_DELAY_MS = 5000;   // 5 Sekunden Verzögerung
const int PWM_START_VALUE = 255;    // Start-Drehzahl: 50% (von 0-255)
const unsigned int FAN_PULSES_PER_REV = 2; // Die meisten Lüfter senden 2 Impulse pro Umdrehung

// --- Variablen für Tacho-Messung ---
volatile unsigned int pulseCount = 0; 
unsigned long lastTachoTime = 0;      
unsigned long measurementInterval = 1000; // Messintervall in ms (1s)

// --- Interrupt Service Routine (ISR) ---
// Zählt die Impulse vom FG-Signal
void handleTachoInterrupt() {
  pulseCount++;
}

// --- Setup ---
void setup() {
  Serial.begin(9600);
  Serial.println("Projekt Assistent ETD QA: Fan Dimmung über FET-Modul.");
  Serial.println("WARNUNG: Dimmung der Lastspannung ist für 3-Pin-Lüfter oft UNSICHER.");

  // Konfiguriere den PWM-Pin als Ausgang und setze ihn initial auf 0 (Lüfter aus)
  pinMode(PWM_CONTROL_PIN, OUTPUT);
  analogWrite(PWM_CONTROL_PIN, 0); 
  
  // Konfiguriere den Tacho-Pin als Eingang mit Pullup
  pinMode(TACHO_PIN, INPUT_PULLUP);
  
  // Aktiviere den Interrupt an D2 (Interrupt 0 auf dem Nano)
  attachInterrupt(digitalPinToInterrupt(TACHO_PIN), handleTachoInterrupt, RISING);
}

// --- Haupt-Loop ---
void loop() {
  
  // 1. Wartezeit (Startverzögerung)
  if (millis() < START_DELAY_MS) {
    // Kurzes Feedback, um zu zeigen, dass gewartet wird
    static unsigned long lastWaitPrint = 0;
    if (millis() - lastWaitPrint > 1000) {
      Serial.print(".");
      lastWaitPrint = millis();
    }
    return;
  } 
  
  // 2. Lüfter einschalten
  static bool fanStarted = false;
  if (!fanStarted) {
    analogWrite(PWM_CONTROL_PIN, PWM_START_VALUE); // Start Dimmung/Versorgung bei 50%
    Serial.println("\nLüfter gestartet. Dimmung auf 50% (128/255).");
    fanStarted = true;
  }

  // 3. Drehzahlmessung und Ausgabe alle 1 Sekunde
  if (millis() - lastTachoTime >= measurementInterval) {
    
    // Unterbreche Interrupts für atomare Zähler-Operation
    noInterrupts();
    unsigned int currentPulses = pulseCount;
    pulseCount = 0; 
    interrupts();

    // Die Drehzahl wird berechnet, basierend auf den gezählten Impulsen pro Sekunde
    // RPM = (Impulse / Impulse_pro_Umdrehung) * 60
    float rpm = (float)currentPulses * 60.0 / FAN_PULSES_PER_REV * (1000.0 / measurementInterval);
    
    // Gib den Wert aus
    Serial.print(millis());
    Serial.print(" ms: ");
    Serial.print(rpm);
    Serial.println(" RPM");

    lastTachoTime = millis();
  }
}