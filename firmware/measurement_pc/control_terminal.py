import serial
import threading
import time
import csv
import sys
from datetime import datetime

# Versuch, die Bibliothek zu importieren
try:
    from robust_serial import write_i8, write_i32, read_i8, read_i32
    from robust_serial.utils import open_serial_port
except ImportError:
    print("Bitte installieren Sie die Bibliothek: pip install robust_serial")
    sys.exit(1)

# --- KONFIGURATION ---
PORT = "/dev/cu.usbserial-120"  # <--- BITTE ANPASSEN!
BAUD_RATE = 115200
LOG_FILE = f"qa_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# --- MECHANIK ---
STEPS_PER_MM = 800.0
STEPS_PER_DEG = 16.156

# --- ESTRO/SGRT LIMITS (KORRIGIERT) ---
LIMIT_H_MAX = 41.0
LIMIT_H_MIN = -5.0
LIMIT_V_MAX = 61.5
LIMIT_V_MIN = -5.0
LIMIT_R_MAX = 20.0  # Begrenzung für Kabelschutz
LIMIT_R_MIN = -20.0  # Begrenzung für Kabelschutz


# --- PROTOKOLL DEFINITIONEN ---
class Order:
    HELLO = 0
    MOVE_AXIS = 1
    HOME_AXIS = 2
    STOP_ALL = 3
    LOG_DATA = 10


class Axis:
    H = 0
    V = 1
    R = 2


# --- GLOBALE STATUS VARIABLEN ---
current_status = {"pos_h": 0, "pos_v": 0, "pos_r": 0, "alm": False, "homing": False}
r_axis_ready = False  # Sicherheits-Flag für die Rotation
stop_event = threading.Event()


# --- HINTERGRUND THREAD: Logging & Empfang ---
def serial_listener(ser):
    print(f"[System] Logging startet in: {LOG_FILE}")
    with open(LOG_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["PC_Time", "Arduino_Time", "Pos_H_Steps", "Pos_V_Steps", "Pos_R_Steps", "Status_Bits"])

        while not stop_event.is_set():
            try:
                if ser.in_waiting:
                    order = read_i8(ser)
                    if order == Order.LOG_DATA:
                        ard_time = read_i32(ser)
                        pos_h = read_i32(ser)
                        pos_v = read_i32(ser)
                        pos_r = read_i32(ser)
                        status_byte = read_i8(ser)

                        writer.writerow([time.time(), ard_time, pos_h, pos_v, pos_r, status_byte])

                        current_status["pos_h"] = pos_h
                        current_status["pos_v"] = pos_v
                        current_status["pos_r"] = pos_r

                        is_alarm = (status_byte & 0b00001110) > 0
                        if is_alarm and not current_status["alm"]:
                            print("\n!!! ALARM DETEKTIERT (Treiber-Fehler) !!!")
                        current_status["alm"] = is_alarm
            except Exception:
                pass


# --- HILFSFUNKTIONEN ---
def send_move(ser, axis_id, target_val, speed_val):
    """Überprüft Limits und sendet Move-Befehl"""
    # Software-Limit Check in Python
    if axis_id == Axis.R:
        if not (LIMIT_R_MIN <= target_val <= LIMIT_R_MAX):
            print(f"Abbruch: Ziel {target_val}° außerhalb Limit ({LIMIT_R_MIN} bis {LIMIT_R_MAX})")
            return
        steps = int(target_val * STEPS_PER_DEG)
        speed = int(speed_val * STEPS_PER_DEG)
    else:
        steps = int(target_val * STEPS_PER_MM)
        speed = int(speed_val * STEPS_PER_MM)

    write_i8(ser, Order.MOVE_AXIS)
    write_i8(ser, axis_id)
    write_i32(ser, steps)
    write_i32(ser, speed)


def move_blocking(ser, axis_id, target_val, speed_val):
    """Berechnet Fahrzeit und wartet (Blocking)"""
    curr_steps = 0
    steps_unit = STEPS_PER_MM

    if axis_id == Axis.H:
        curr_steps = current_status["pos_h"]
    elif axis_id == Axis.V:
        curr_steps = current_status["pos_v"]
    elif axis_id == Axis.R:
        curr_steps = current_status["pos_r"]
        steps_unit = STEPS_PER_DEG

    targ_steps = int(target_val * steps_unit)
    dist_steps = abs(targ_steps - curr_steps)
    speed_steps = abs(speed_val * steps_unit)

    if speed_steps == 0: return

    travel_time = dist_steps / speed_steps
    print(f"-> Fahre Achse {axis_id} zu {target_val} (ca. {travel_time:.1f}s)...")
    send_move(ser, axis_id, target_val, speed_val)
    time.sleep(travel_time + 0.3)  # Puffer für Beschleunigungsrampe


# --- DEMO FUNKTION (AKTUALISIERT) ---
def run_demo_1(ser):
    if not r_axis_ready:
        print("\n[FEHLER] Demo kann nicht starten: R-Achse ist nicht initialisiert!")
        print("Bitte zuerst 'h r' ausführen (Laser-Ausrichtung).")
        return

    print("\n--- STARTE QA-DEMO 1 (ESTRO Validierung) ---")
    try:
        # Achsen nacheinander testen
        move_blocking(ser, Axis.H, 20.0, 10.0)
        move_blocking(ser, Axis.H, 0.0, 10.0)

        move_blocking(ser, Axis.V, 20.0, 10.0)
        move_blocking(ser, Axis.V, 0.0, 10.0)

        move_blocking(ser, Axis.R, 15.0, 5.0)
        move_blocking(ser, Axis.R, -15.0, 5.0)
        move_blocking(ser, Axis.R, 0.0, 5.0)

        print("--- DEMO 1 ERFOLGREICH BEENDET ---")
    except KeyboardInterrupt:
        write_i8(ser, Order.STOP_ALL)


# --- HAUPTPROGRAMM ---
def main():
    global r_axis_ready
    try:
        ser = open_serial_port(serial_port=PORT, baudrate=BAUD_RATE)
    except Exception as e:
        print(f"Fehler: {e}")
        return

    t = threading.Thread(target=serial_listener, args=(ser,), daemon=True)
    t.start()

    print("-" * 50)
    print("ETD QA COMMANDER v1.2 (SGRT Safety Enabled)")
    print("Befehle: 'h [h/v/r]', 'm [h/v/r] [pos] [spd]', 'm zp', 'demo_1', 'p', 's', 'q'")
    print("-" * 50)

    try:
        while True:
            cmd_str = input("CMD > ").strip().lower()
            parts = cmd_str.split()
            if not parts: continue
            cmd = parts[0]

            if cmd == 'q':
                break
            elif cmd == 's':
                write_i8(ser, Order.STOP_ALL)
                print("STOP-Befehl gesendet!")

            elif cmd == 'p':
                print(f"POSITIONEN: H={current_status['pos_h'] / STEPS_PER_MM:.2f}mm | "
                      f"V={current_status['pos_v'] / STEPS_PER_MM:.2f}mm | "
                      f"R={current_status['pos_r'] / STEPS_PER_DEG:.2f}°")

            elif cmd == 'demo_1':
                run_demo_1(ser)

            elif cmd == 'h':
                if len(parts) < 2:
                    print("Welche Achse? (h, v, r)")
                    continue

                if parts[1] == 'r':
                    print("\n[SICHERHEITS-CHECK ROTATION]")
                    print("1. Kabelverlauf geprüft? (Kein Abreißen bei +/- 20°?)")
                    print("2. Phantom waagerecht mit Lasern ausgerichtet?")
                    confirm = input("Bestätigen mit 'y': ")
                    if confirm.lower() == 'y':
                        write_i8(ser, Order.HOME_AXIS)
                        write_i8(ser, Axis.R)
                        r_axis_ready = True
                        print("-> R-Achse auf Null gesetzt und freigeschaltet.")
                    else:
                        print("-> Homing abgebrochen.")
                else:
                    write_i8(ser, Order.HOME_AXIS)
                    write_i8(ser, Axis.H if parts[1] == 'h' else Axis.V)

            elif cmd == 'm':
                if len(parts) >= 2 and parts[1] == 'zp':
                    if not r_axis_ready:
                        print("FEHLER: R-Achse nicht bereit! Bitte erst 'h r' ausführen.")
                        continue
                    speed = float(parts[2]) if len(parts) >= 3 else 20.0
                    print(f"-> Fahre simultan auf Null (Speed={speed})...")
                    send_move(ser, Axis.H, 0.0, speed)
                    send_move(ser, Axis.V, 0.0, speed)
                    send_move(ser, Axis.R, 0.0, speed)

                elif len(parts) == 4:
                    ax_char, tgt, spd = parts[1], float(parts[2]), float(parts[3])
                    if ax_char == 'r' and not r_axis_ready:
                        print("GESPERRT: Bitte zuerst 'h r' (Laser-Homing) durchführen.")
                        continue

                    target_axis = Axis.H if ax_char == 'h' else (Axis.V if ax_char == 'v' else Axis.R)
                    send_move(ser, target_axis, tgt, spd)
                else:
                    print("Syntax: m [h/v/r] [ziel] [speed] ODER m zp")

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        time.sleep(0.5)
        ser.close()


if __name__ == "__main__":
    main()