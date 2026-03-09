import serial
import threading
import queue
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
LIMIT_R_MAX = 45.0  # Begrenzung für Kabelschutz
LIMIT_R_MIN = -45.0  # Begrenzung für Kabelschutz

# Globale Warteschlange für Befehle
command_queue = queue.Queue()
# Event, das signalisiert, ob der Arduino bereit für den nächsten Befehl ist
arduino_ready_event = threading.Event()
arduino_ready_event.set()  # Initial auf True setzen

# --- PROTOKOLL DEFINITIONEN ---
class Order:
    HELLO = 0
    MOVE_AXIS = 1
    HOME_AXIS = 2
    STOP_ALL = 3
    COMMAND_DONE = 4  # NEU: Synchronisations-ID
    LOG_DATA = 10


class Axis:
    H = 0
    V = 1
    R = 2


# --- GLOBALE STATUS VARIABLEN ---
current_status = {"pos_h": 0, "pos_v": 0, "pos_r": 0, "alm": False, "homing": False}
r_axis_ready = False  # Sicherheits-Flag für die Rotation
stop_event = threading.Event()


def command_worker(ser):
    """Verarbeitet die Warteschlange mit korrekten Datentypen."""
    while True:
        item = command_queue.get()
        if item is None: break

        order_type, payload = item

        # Warten auf Freigabe vom vorherigen Befehl
        if not arduino_ready_event.wait(timeout=45.0):  # Timeout erhöhen für lange Fahrten
            print(f"\n[FEHLER] Timeout: Arduino reagiert nicht auf Order {order_type}. Überspringe...")
            arduino_ready_event.set()  # Reset für nächsten Befehl
            command_queue.task_done()
            continue

        arduino_ready_event.clear()

        try:
            write_i8(ser, order_type)

            if order_type == Order.MOVE_AXIS:
                # Payload: [axis_id (i8), target (i32), speed (i32)]
                write_i8(ser, payload[0])
                write_i32(ser, payload[1])
                write_i32(ser, payload[2])

            elif order_type == Order.HOME_AXIS:
                # Payload: [axis_id (i8)]
                write_i8(ser, payload[0])

            elif order_type == Order.STOP_ALL:
                pass  # Keine Payload

        except Exception as e:
            print(f"Fehler beim Senden: {e}")
            arduino_ready_event.set()

        command_queue.task_done()

# --- HINTERGRUND THREAD: Logging & Empfang ---
def serial_listener(ser):
    """Liest ständig vom Arduino und verarbeitet Rückmeldungen."""
    print(f"[System] Logging gestartet in: {LOG_FILE}")

    # Datei einmalig öffnen und Header schreiben
    with open(LOG_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["PC_Time", "Arduino_Time", "Pos_H_Steps", "Pos_V_Steps", "Pos_R_Steps", "Status_Bits"])

        while not stop_event.is_set():
            if ser.in_waiting > 0:
                try:
                    # Wir lesen immer nur EINE Message-ID pro Durchlauf
                    msg_id = read_i8(ser)

                    # FALL 1: Bestätigung für abgeschlossene Bewegung/Homing
                    if msg_id == Order.COMMAND_DONE:
                        print("\n[Arduino] Aktion abgeschlossen.")
                        arduino_ready_event.set()

                    # FALL 2: Ein einzelner Log-Datensatz vom Arduino
                    elif msg_id == Order.LOG_DATA:
                        ard_time = read_i32(ser)
                        pos_h = read_i32(ser)
                        pos_v = read_i32(ser)
                        pos_r = read_i32(ser)
                        status_byte = read_i8(ser)

                        # In CSV schreiben
                        writer.writerow([time.time(), ard_time, pos_h, pos_v, pos_r, status_byte])
                        f.flush()  # Sicherstellen, dass Daten auf Festplatte landen

                        # Status-Update für UI/Terminal
                        current_status["pos_h"] = pos_h
                        current_status["pos_v"] = pos_v
                        current_status["pos_r"] = pos_r

                        is_alarm = (status_byte & 0b00001110) > 0
                        if is_alarm and not current_status["alm"]:
                            print("\n!!! ALARM DETEKTIERT (Treiber-Fehler) !!!")
                        current_status["alm"] = is_alarm

                except Exception as e:
                    # Nur ausgeben, wenn es kein Timeout ist
                    if "timeout" not in str(e).lower():
                        print(f"Fehler beim Lesen: {e}")

            time.sleep(0.001)  # Kürzere Pause für höhere Log-Frequenz






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

def wait_for_completion(ser):
    print("-> Warte auf Abschluss der Bewegung...")
    while True:
        if ser.in_waiting > 0:
            try:
                response = read_i8(ser)
                if response == 4: # COMMAND_DONE
                    print("-> Aktion erfolgreich abgeschlossen.")
                    break
            except Exception as e:
                pass
        time.sleep(0.01)


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
        # Kurze Pause, damit der Arduino nach dem Reset bereit ist
        time.sleep(2)
    except Exception as e:
        print(f"Fehler: {e}")
        return

    # Start der beiden Hintergrund-Threads
    threading.Thread(target=serial_listener, args=(ser,), daemon=True).start()
    threading.Thread(target=command_worker, args=(ser,), daemon=True).start()

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
                stop_event.set()
                break

            elif cmd == 's':
                # Notstopp: Sofort senden (am Worker vorbei) und Queue löschen
                write_i8(ser, Order.STOP_ALL)
                with command_queue.mutex:
                    command_queue.queue.clear()
                arduino_ready_event.set()  # Worker entsperren
                print("!!! STOP-Befehl gesendet & Warteschlange geleert !!!")

            elif cmd == 'p':
                # Sofortige Abfrage des aktuellen Status (aus dem Listener-Update)
                print(f"POSITIONEN: H={current_status['pos_h'] / STEPS_PER_MM:.2f}mm | "
                      f"V={current_status['pos_v'] / STEPS_PER_MM:.2f}mm | "
                      f"R={current_status['pos_r'] / STEPS_PER_DEG:.2f}°")

            elif cmd == 'demo_1':
                # Hinweis: run_demo_1 sollte idealerweise intern auch command_queue.put nutzen
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
                        command_queue.put((Order.HOME_AXIS, [Axis.R]))
                        r_axis_ready = True
                        print("-> R-Homing (Reset) eingereiht.")
                    else:
                        print("-> Homing abgebrochen.")
                else:
                    target_ax = Axis.H if parts[1] == 'h' else Axis.V
                    print(f"-> Homing {parts[1]} eingereiht.")
                    command_queue.put((Order.HOME_AXIS, [target_ax]))

            elif cmd == 'm':
                # Zero Position: Fährt alle Achsen nacheinander auf 0
                if len(parts) >= 2 and parts[1] == 'zp':
                    if not r_axis_ready:
                        print("FEHLER: R-Achse nicht bereit! Bitte erst 'h r' ausführen.")
                        continue
                    speed = float(parts[2]) if len(parts) >= 3 else 20.0
                    print(f"-> Sequenzielles Fahren auf Nullpunkt eingereiht (Speed={speed}).")

                    # Alle drei Achsen nacheinander in die Queue legen
                    for ax in [Axis.H, Axis.V, Axis.R]:
                        spd_raw = int(speed * (STEPS_PER_DEG if ax == Axis.R else STEPS_PER_MM))
                        command_queue.put((Order.MOVE_AXIS, [ax, 0, spd_raw]))

                elif len(parts) == 4:
                    ax_char, tgt, spd = parts[1], float(parts[2]), float(parts[3])
                    if ax_char == 'r' and not r_axis_ready:
                        print("GESPERRT: Bitte zuerst 'h r' (Laser-Homing) durchführen.")
                        continue

                    target_axis = Axis.H if ax_char == 'h' else (Axis.V if ax_char == 'v' else Axis.R)

                    # Umrechnung in Steps basierend auf Achsentyp
                    conv = STEPS_PER_DEG if ax_char == 'r' else STEPS_PER_MM
                    tgt_raw = int(tgt * conv)
                    spd_raw = int(spd * conv)

                    print(f"-> Bewegung {ax_char} auf {tgt} eingereiht.")
                    command_queue.put((Order.MOVE_AXIS, [target_axis, tgt_raw, spd_raw]))
                else:
                    print("Syntax: m [h/v/r] [ziel] [speed] ODER m zp")

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        time.sleep(0.5)
        ser.close()
        print("[System] Verbindung geschlossen.")


if __name__ == "__main__":
    main()