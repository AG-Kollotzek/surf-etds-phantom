/* TestUnit.ino  –  Grundgerüst
   Setup: Arduino Mega 2560 + Velleman VMA412 (2.8" TFT, resistiv)
          3x HBS57 (STEP/DIR/ENA), Endschalter X/Y min, Z Hall/Index
          2x Heizpads über Relais, 2x DS18B20 (getrennte Pins)
   Funktionen:
     - Home aller Achsen
     - Jog X/Y/Z (Z = Drehtisch)
     - Speed Slow/Fast
     - Zwei getrennte Temperaturkanäle (Ist & Soll, je Pad)
     - Ein/Aus je Heizer, Bang‑Bang‑Regelung mit Hysterese
*/

#include <AccelStepper.h>
#include <Bounce2.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <MCUFRIEND_kbv.h>
#include <Adafruit_GFX.h>
#include <TouchScreen.h>

// ======================= CONFIG =======================
#define USE_ENABLE_HIGH   true     // HBS57 ENA-Logik: true = HIGH aktiviert
const long BAUD = 115200;

// Pins (Mega) – Step/Dir/Endschalter
const uint8_t X_STEP=22, X_DIR=23, X_MIN=30;
const uint8_t Y_STEP=25, Y_DIR=26, Y_MIN=31;
const uint8_t Z_STEP=27, Z_DIR=28, Z_HOME=32;  // Hall/Index
const uint8_t ENA=24;

// Heizer & Sensoren
const uint8_t HEAT1=33, HEAT2=34;  // Relais-Eingänge (typisch LOW-aktiv)
const uint8_t TEMP1_PIN=35;        // DS18B20 Pad 1
const uint8_t TEMP2_PIN=36;        // DS18B20 Pad 2

// Bewegungsparameter
const float JOG_SPEED_SLOW = 800.0;   // steps/s
const float JOG_SPEED_FAST = 2000.0;  // steps/s
const float JOG_ACCEL      = 3000.0;  // steps/s^2
const long  HOME_SPEED     = 600;     // steps/s
const long  HOME_BACKOFF   = 400;     // Schritte zurück nach Schalter-Treffer
const long  HOME_SEARCH_MAX= 200000;  // Sicherheitslimit

// Temperatur-Parameter
const unsigned TEMP_READ_MS = 500;
const float SETPOINT_MAX_C  = 50.0;
const float HYST_C          = 1.0;    // ±1°C
float ambientAtBoot = 20.0;

// Touchscreen-Pins für VMA412 (typisch)
#define YP A3
#define XM A2
#define YM 9
#define XP 8
const int TS_MINX = 100, TS_MAXX = 920;
const int TS_MINY = 120, TS_MAXY = 940;
TouchScreen ts = TouchScreen(XP, YP, XM, YM, 300);

// Display
MCUFRIEND_kbv tft;
uint16_t bg = 0xFFFF, fg = 0x0000;

// ======================= STATE & UI =======================
struct Btn { int x,y,w,h; const char* label; };

// Haupt-Buttons
Btn btnHome{10, 10, 90, 40, "HOME"};
Btn btnJogXn{10, 70, 90, 40, "X-"}, btnJogXp{110,70,90,40,"X+"};
Btn btnJogYn{10, 120,90,40, "Y-"}, btnJogYp{110,120,90,40,"Y+"};
Btn btnJogZn{10, 170,90,40, "Z-"}, btnJogZp{110,170,90,40,"Z+"};
Btn btnSpeed{10, 220,190,40, "Speed: SLOW"};

// Temperatur-UI (Pad 1 links, Pad 2 rechts)
Btn btnT1m{230, 70, 60, 40, "-"}, btnT1p{300,70,60,40,"+"};
Btn btnH1 {230, 120,130,40, "HEAT1 ON"};

Btn btnT2m{230, 180, 60, 40, "-"}, btnT2p{300,180,60,40,"+"};
Btn btnH2 {230, 230,130,40, "HEAT2 ON"};

// Stepper + Endschalter
AccelStepper axX(AccelStepper::DRIVER, X_STEP, X_DIR);
AccelStepper axY(AccelStepper::DRIVER, Y_STEP, Y_DIR);
AccelStepper axZ(AccelStepper::DRIVER, Z_STEP, Z_DIR);
Bounce swX = Bounce(), swY=Bounce(), swZ=Bounce();

// Sensoren
OneWire oneWire1(TEMP1_PIN);
DallasTemperature sensors1(&oneWire1);
OneWire oneWire2(TEMP2_PIN);
DallasTemperature sensors2(&oneWire2);

// Temperaturen & Sollwerte
float temp1C=20.0, temp2C=20.0;
float set1C=35.0, set2C=35.0;
bool heat1On=true, heat2On=true;   // individuelle Freigabe

bool speedFast=false;
unsigned long lastTempMs=0;

// ======================= UTILS =======================
void setEnable(bool en) {
  pinMode(ENA, OUTPUT);
  digitalWrite(ENA, USE_ENABLE_HIGH ? (en ? HIGH : LOW) : (en ? LOW : HIGH));
}

void drawBtn(const Btn& b, uint16_t color, uint16_t tcolor) {
  tft.fillRect(b.x, b.y, b.w, b.h, color);
  tft.drawRect(b.x, b.y, b.w, b.h, fg);
  tft.setTextColor(tcolor);
  tft.setTextSize(2);
  int16_t tx = b.x + 6;
  int16_t ty = b.y + (b.h/2 - 8);
  tft.setCursor(tx, ty);
  tft.print(b.label);
}

bool inBtn(const Btn& b, int px, int py) {
  return (px>=b.x && px<=b.x+b.w && py>=b.y && py<=b.y+b.h);
}

void textAt(int x,int y,const String& s){
  tft.setTextColor(fg); tft.setTextSize(2); tft.setCursor(x,y); tft.print(s);
}

void uiDraw() {
  tft.fillScreen(bg);
  // Haupt
  drawBtn(btnHome, 0x07E0, fg);
  drawBtn(btnJogXn, 0xC618, fg); drawBtn(btnJogXp, 0xC618, fg);
  drawBtn(btnJogYn, 0xC618, fg); drawBtn(btnJogYp, 0xC618, fg);
  drawBtn(btnJogZn, 0xC618, fg); drawBtn(btnJogZp, 0xC618, fg);
  drawBtn(btnSpeed, 0xFFFF, fg);

  // Temp Labels
  textAt(230, 20, "Pad1 Ist:");
  textAt(230, 40, String(temp1C,1) + " C");
  textAt(230, 155, "Pad2 Ist:");
  textAt(230, 175, String(temp2C,1) + " C");

  textAt(230, 120+50, "Soll1:");
  textAt(230, 140+50, String(set1C,1) + " C");
  textAt(230, 230+50, "Soll2:");
  textAt(230, 250+50, String(set2C,1) + " C"); // außerhalb sichtbar? (Display 320x240)
  // Hinweis: VMA412 ist 320x240; deshalb schreiben wir Soll2‑Anzeige höher nicht nochmal.
  // Wir halten uns im sichtbaren Bereich: Für Soll2 nutzen wir unten Platz.

  // Buttons Temp
  drawBtn(btnT1m, 0xFFE0, fg); drawBtn(btnT1p, 0xFFE0, fg);
  drawBtn(btnH1 , heat1On?0xF800:0xFFFF, fg); // rot=aktiv

  drawBtn(btnT2m, 0xFFE0, fg); drawBtn(btnT2p, 0xFFE0, fg);
  drawBtn(btnH2 , heat2On?0xF800:0xFFFF, fg);

  // leichte Korrektur der „Soll“-Positionen (sichtbar halten)
  tft.fillRect(230, 190, 120, 16, bg);
  tft.setCursor(230, 190); tft.print("Soll1: "); tft.print(set1C,1); tft.print(" C");

  tft.fillRect(230, 210, 120, 16, bg);
  tft.setCursor(230, 210); tft.print("Soll2: "); tft.print(set2C,1); tft.print(" C");
}

void uiUpdateTemps() {
  // Istwerte aktualisieren
  tft.fillRect(230, 40, 120, 16, bg);
  tft.setCursor(230, 40); tft.print(temp1C,1); tft.print(" C");
  tft.fillRect(230, 175, 120, 16, bg);
  tft.setCursor(230, 175); tft.print(temp2C,1); tft.print(" C");

  // Sollwerte
  tft.fillRect(230, 190, 120, 16, bg);
  tft.setCursor(230, 190); tft.print("Soll1: "); tft.print(set1C,1); tft.print(" C");
  tft.fillRect(230, 210, 120, 16, bg);
  tft.setCursor(230, 210); tft.print("Soll2: "); tft.print(set2C,1); tft.print(" C");
}

void setSpeedMode(bool fast) {
  speedFast = fast;
  float v = fast ? JOG_SPEED_FAST : JOG_SPEED_SLOW;
  axX.setMaxSpeed(v); axY.setMaxSpeed(v); axZ.setMaxSpeed(v);
  axX.setAcceleration(JOG_ACCEL); axY.setAcceleration(JOG_ACCEL); axZ.setAcceleration(JOG_ACCEL);
  btnSpeed.label = fast ? "Speed: FAST" : "Speed: SLOW";
  drawBtn(btnSpeed, 0xFFFF, fg);
}

// ======================= HOMING =======================
bool homeAxis(AccelStepper& ax, Bounce& sw, int dir, long searchMax) {
  ax.setMaxSpeed(HOME_SPEED);
  ax.setAcceleration(JOG_ACCEL);
  ax.moveTo(ax.currentPosition() + dir*searchMax);
  unsigned long startMs = millis();
  while (ax.distanceToGo()!=0) {
    ax.run();
    sw.update();
    if (sw.read()==LOW) {       // LOW = aktiv (bei NC mit INPUT_PULLUP)
      ax.stop(); while (ax.isRunning()) ax.run();
      ax.move(-dir*HOME_BACKOFF);
      while (ax.distanceToGo()!=0) ax.run();
      ax.setCurrentPosition(0);
      return true;
    }
    if (millis()-startMs > 20000) break;
  }
  return false;
}

bool doHoming() {
  bool okX = homeAxis(axX, swX, -1, HOME_SEARCH_MAX);
  bool okY = homeAxis(axY, swY, -1, HOME_SEARCH_MAX);
  bool okZ = homeAxis(axZ, swZ, -1, HOME_SEARCH_MAX);
  return okX && okY && okZ;
}

// ======================= SETUP =======================
void setup() {
  Serial.begin(BAUD);

  // Display init
  uint16_t id = tft.readID();
  tft.begin(id);
  tft.setRotation(1); // Landscape
  tft.fillScreen(bg);

  // Endschalter
  pinMode(X_MIN, INPUT_PULLUP); swX.attach(X_MIN); swX.interval(5);
  pinMode(Y_MIN, INPUT_PULLUP); swY.attach(Y_MIN); swY.interval(5);
  pinMode(Z_HOME,INPUT_PULLUP); swZ.attach(Z_HOME); swZ.interval(5);

  // Heizer
  pinMode(HEAT1, OUTPUT); digitalWrite(HEAT1, HIGH); // HIGH = aus (bei LOW-aktivem Board)
  pinMode(HEAT2, OUTPUT); digitalWrite(HEAT2, HIGH);

  // Sensoren
  sensors1.begin();
  sensors2.begin();
  sensors1.requestTemperatures();
  sensors2.requestTemperatures();
  float amb1 = sensors1.getTempCByIndex(0);
  float amb2 = sensors2.getTempCByIndex(0);
  // Plausibilisierung
  if (amb1<-30 || amb1>120 || isnan(amb1)) amb1=20.0;
  if (amb2<-30 || amb2>120 || isnan(amb2)) amb2=20.0;
  ambientAtBoot = (amb1 + amb2) / 2.0;
  // Setpoints begrenzen
  if (set1C < ambientAtBoot) set1C = ambientAtBoot;
  if (set2C < ambientAtBoot) set2C = ambientAtBoot;
  if (set1C > SETPOINT_MAX_C) set1C = SETPOINT_MAX_C;
  if (set2C > SETPOINT_MAX_C) set2C = SETPOINT_MAX_C;

  // Stepper
  setEnable(true);
  setSpeedMode(false);

  uiDraw();
}

// ======================= LOOP =======================
void loop() {
  // Touch lesen
  TSPoint p = ts.getPoint();
  // Shield setzt Pinmodes um – zurückstellen:
  pinMode(XM, OUTPUT); pinMode(YP, OUTPUT);
  if (p.z > 200 && p.z < 1000) {
    int16_t px = map(p.y, TS_MINY, TS_MAXY, 0, tft.width());
    int16_t py = map(p.x, TS_MINX, TS_MAXX, 0, tft.height());

    // Buttons
    if (inBtn(btnHome, px, py)) {
      uiDraw();
      tft.setCursor(10,270); tft.print("Homing...");
      bool ok = doHoming();
      tft.fillRect(10,270,200,16,bg);
      tft.setCursor(10,270); tft.print(ok?"Home OK":"Home FAIL");
    } else if (inBtn(btnJogXn, px, py)) {
      axX.move(axX.currentPosition()-400);
    } else if (inBtn(btnJogXp, px, py)) {
      axX.move(axX.currentPosition()+400);
    } else if (inBtn(btnJogYn, px, py)) {
      axY.move(axY.currentPosition()-400);
    } else if (inBtn(btnJogYp, px, py)) {
      axY.move(axY.currentPosition()+400);
    } else if (inBtn(btnJogZn, px, py)) {
      axZ.move(axZ.currentPosition()-200);
    } else if (inBtn(btnJogZp, px, py)) {
      axZ.move(axZ.currentPosition()+200);
    } else if (inBtn(btnSpeed, px, py)) {
      setSpeedMode(!speedFast);
    }
    // Temp Pad1
    else if (inBtn(btnT1m, px, py)) {
      set1C -= 0.5; if (set1C < ambientAtBoot) set1C = ambientAtBoot; uiUpdateTemps();
    } else if (inBtn(btnT1p, px, py)) {
      set1C += 0.5; if (set1C > SETPOINT_MAX_C) set1C = SETPOINT_MAX_C; uiUpdateTemps();
    } else if (inBtn(btnH1, px, py)) {
      heat1On = !heat1On; btnH1.label = heat1On ? "HEAT1 ON" : "HEAT1 OFF";
      drawBtn(btnH1, heat1On?0xF800:0xFFFF, fg);
    }
    // Temp Pad2
    else if (inBtn(btnT2m, px, py)) {
      set2C -= 0.5; if (set2C < ambientAtBoot) set2C = ambientAtBoot; uiUpdateTemps();
    } else if (inBtn(btnT2p, px, py)) {
      set2C += 0.5; if (set2C > SETPOINT_MAX_C) set2C = SETPOINT_MAX_C; uiUpdateTemps();
    } else if (inBtn(btnH2, px, py)) {
      heat2On = !heat2On; btnH2.label = heat2On ? "HEAT2 ON" : "HEAT2 OFF";
      drawBtn(btnH2, heat2On?0xF800:0xFFFF, fg);
    }
  }

  // Endschalter live (nur stoppen, wenn in Schließrichtung)
  swX.update(); swY.update(); swZ.update();
  if (swX.read()==LOW && axX.speed()<0) { axX.stop(); }
  if (swY.read()==LOW && axY.speed()<0) { axY.stop(); }
  if (swZ.read()==LOW && axZ.speed()<0) { axZ.stop(); }

  // Stepper bewegen
  axX.run(); axY.run(); axZ.run();

  // Temperaturen & Heizung
  unsigned long now = millis();
  if (now - lastTempMs >= TEMP_READ_MS) {
    lastTempMs = now;
    sensors1.requestTemperatures();
    sensors2.requestTemperatures();
    temp1C = sensors1.getTempCByIndex(0);
    temp2C = sensors2.getTempCByIndex(0);
    uiUpdateTemps();

    // Pad 1
    bool r1=false;
    if (heat1On && !isnan(temp1C)) {
      if (temp1C < set1C - HYST_C) r1 = true;
      if (temp1C > set1C + HYST_C) r1 = false;
    }
    // Pad 2
    bool r2=false;
    if (heat2On && !isnan(temp2C)) {
      if (temp2C < set2C - HYST_C) r2 = true;
      if (temp2C > set2C + HYST_C) r2 = false;
    }
    // Relais ansteuern (LOW-aktiv üblich)
    digitalWrite(HEAT1, r1 ? LOW : HIGH);
    digitalWrite(HEAT2, r2 ? LOW : HIGH);
  }
}
