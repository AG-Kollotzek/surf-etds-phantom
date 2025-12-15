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
STEPS_PER_DEG = 16.515


# --- DEMO LIMITS (Hier Ihre Werte eintragen!) ---
LIMIT_H_MAX = 40.0  # mm
LIMIT_H_MIN = -40.0  # mm
LIMIT_V_MAX = 40.0  # mmh
LIMIT_V_MIN = -40.0  # mm
LIMIT_R_MAX = 90.0  # Grad
LIMIT_R_MIN = -90.0  # Grad


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
                            print("\n!!! ALARM DETEKTIERT !!!")
                        current_status["alm"] = is_alarm

            except Exception:
                pass


# --- HILFSFUNKTIONEN ---
def send_move(ser, axis_id, target_val, speed_val):
    """Sendet nur den Befehl (Non-blocking)"""
    if axis_id == Axis.R:
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
    """
    Berechnet die Fahrzeit, sendet Befehl und wartet, bis die Fahrt fertig ist.
    """
    # 1. Aktuelle Position holen (Steps)
    curr_steps = 0
    steps_unit = 0

    if axis_id == Axis.H:
        curr_steps = current_status["pos_h"]
        steps_unit = STEPS_PER_MM
    elif axis_id == Axis.V:
        curr_steps = current_status["pos_v"]
        steps_unit = STEPS_PER_MM
    elif axis_id == Axis.R:
        curr_steps = current_status["pos_r"]
        steps_unit = STEPS_PER_DEG

    # 2. Ziel (Steps)
    targ_steps = int(target_val * steps_unit)

    # 3. Distanz & Zeit berechnen
    dist_steps = abs(targ_steps - curr_steps)
    speed_steps = abs(speed_val * steps_unit)

    if speed_steps == 0: return  # Division durch 0 verhindern

    travel_time = dist_steps / speed_steps

    # 4. Senden & Warten (mit 0.2s Puffer für Rampe)
    print(f"-> Fahre zu {target_val} (Dauer ca. {travel_time:.1f}s)...")
    send_move(ser, axis_id, target_val, speed_val)
    time.sleep(travel_time + 0.2)


# --- DEMO FUNKTION ---
def run_demo_1(ser):
    print("\n--- STARTE DEMO 1 ---")
    print("Drücke STRG+C um jederzeit abzubrechen!")

    try:
        # --- H ACHSE ---
        move_blocking(ser, Axis.H, LIMIT_H_MAX, 20)
        print("Wait 1s...")
        time.sleep(1)

        move_blocking(ser, Axis.H, LIMIT_H_MIN, 20)
        print("Wait 1s...")
        time.sleep(1)

        move_blocking(ser, Axis.H, 0, 20)
        print("Wait 1s...")
        time.sleep(1)

        # --- V ACHSE ---
        move_blocking(ser, Axis.V, LIMIT_V_MAX, 20)
        print("Wait 1s...")
        time.sleep(1)

        move_blocking(ser, Axis.V, LIMIT_V_MIN, 20)
        print("Wait 1s...")
        time.sleep(1)

        move_blocking(ser, Axis.V, 0, 20)
        print("Wait 1s...")
        time.sleep(1)

        # --- R ACHSE ---
        move_blocking(ser, Axis.R, LIMIT_R_MAX, 30)
        print("Wait 1s...")
        time.sleep(1)

        move_blocking(ser, Axis.R, LIMIT_R_MIN, 30)
        print("Wait 1s...")
        time.sleep(1)

        move_blocking(ser, Axis.R, 0, 30)

        print("--- DEMO 1 ABGESCHLOSSEN ---")

    except KeyboardInterrupt:
        print("\nDEMO ABBRUCH! STOPPE ALLES.")
        write_i8(ser, Order.STOP_ALL)


# --- HAUPTPROGRAMM ---
def main():
    try:
        ser = open_serial_port(serial_port=PORT, baudrate=BAUD_RATE)
    except Exception as e:
        print(f"Fehler: {e}")
        return

    t = threading.Thread(target=serial_listener, args=(ser,), daemon=True)
    t.start()

    print("-" * 50)
    print("ETD QA COMMANDER")
    print("Befehle: 'demo_1', 'h [h/v]', 'm [achse] [pos] [vel]', 'p', 's', 'q'")
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
                print("STOP!")

            elif cmd == 'p':
                print(
                    f"H={current_status['pos_h'] / STEPS_PER_MM:.1f} | V={current_status['pos_v'] / STEPS_PER_MM:.1f} | R={current_status['pos_r'] / STEPS_PER_DEG:.1f}")

            elif cmd == 'demo_1':
                run_demo_1(ser)

            elif cmd == 'h':  # Homing
                if len(parts) < 2:
                    print("Achse? (h, v)")
                else:
                    write_i8(ser, Order.HOME_AXIS)
                    if parts[1] == 'h':
                        write_i8(ser, Axis.H)
                    elif parts[1] == 'v':
                        write_i8(ser, Axis.V)

            elif cmd == 'm':  # Move
                if len(parts) < 4:
                    print("Syntax: m [h/v/r] [ziel] [speed]")
                else:
                    try:
                        ax = parts[1]
                        tgt = float(parts[2])
                        spd = float(parts[3])
                        if ax == 'h':
                            send_move(ser, Axis.H, tgt, spd)
                        elif ax == 'v':
                            send_move(ser, Axis.V, tgt, spd)
                        elif ax == 'r':
                            send_move(ser, Axis.R, tgt, spd)
                    except:
                        print("Zahlen bitte!")

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        time.sleep(0.5)
        ser.close()


if __name__ == "__main__":
    main()