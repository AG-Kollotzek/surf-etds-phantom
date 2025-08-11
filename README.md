# Test Unit – Mechatronik (3× NEMA23, Heizpads, VMA42, MATLAB)

Kurzbeschreibung: PC (MATLAB-App) steuert Arduino-Firmware (Motorik + Heizer + Touch).

## Inhalte
- firmware/ (Arduino: Motion, Heater, HMI, Comms)
- matlab_app/ (App Designer, Protokoll, Tests)
- docs/ (Protokoll, Pinout, Kalibrierung), hardware/

## Schnellstart
### Firmware
- Arduino IDE oder Arduino-CLI installieren.
- `firmware/arduino/` öffnen, `config.h` prüfen, flashen.

### MATLAB-App
- MATLAB R20xxb+, App Designer.
- `matlab_app/app/TestUnit.mlapp` öffnen.
- Serielle Schnittstelle in `matlab_app/lib/config.m` setzen.

### CLI/CI
- **Tests:** `matlab -batch "run('matlab_app/scripts/run_tests.m')"`
- **Build Firmware:** `arduino-cli compile --fqbn <board> firmware/arduino`
- **Flash:** `arduino-cli upload -p <COM> --fqbn <board> firmware/arduino`

## Entwicklung
- Branches: `feature/*` → PR nach `develop` → Release-PR nach `main`.
- Konvention: Conventional Commits (`feat:`, `fix:`, `chore:` …).
