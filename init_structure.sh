#!/usr/bin/env bash
set -euo pipefail

# Optional: Zielverzeichnis als 1. Argument (Standard: aktuelles Verzeichnis)
ROOT="${1:-.}"
cd "$ROOT"

echo "→ Erzeuge firmware/arduino Struktur …"
mkdir -p firmware/arduino/{src,include,lib,test}
# Platzhalter/Startdateien
touch firmware/arduino/src/.gitkeep
touch firmware/arduino/include/config.h
touch firmware/arduino/lib/.gitkeep
touch firmware/arduino/test/.gitkeep
# Mini-README
cat > firmware/arduino/README.md <<'EOF'
# Arduino-Firmware
- `src/`      Hauptsketch & Module (.ino/.cpp/.h)
- `include/`  Header & config.h (Pins, Limits, PID)
- `lib/`      Eigene/3rd-Party Libraries (falls lokal)
- `test/`     Mocks/Simulation (optional)
EOF

echo "→ Erzeuge hardware Struktur …"
mkdir -p hardware/{schematics,pcb,wiring,pinout,enclosure,suppliers,safety}
touch hardware/schematics/.gitkeep \
      hardware/pcb/.gitkeep \
      hardware/wiring/.gitkeep \
      hardware/pinout/.gitkeep \
      hardware/enclosure/.gitkeep \
      hardware/suppliers/.gitkeep \
      hardware/safety/.gitkeep

cat > hardware/README.md <<'EOF'
# Hardware
- schematics/  Schaltpläne (Quelle + PDF)
- pcb/         Layout, Gerber, BoM
- wiring/      Verdrahtungs-/Klemmenpläne, Kabelbaum
- pinout/      Pinbelegungen Arduino/Shield/Treiber
- enclosure/   Gehäuse/Frontplatten (STEP/STL/DXF)
- suppliers/   Datenblätter, BoM, Bestelllinks
- safety/      E-Stop, Sicherungen, Grenzwerte
EOF

echo "✅ Fertig."

