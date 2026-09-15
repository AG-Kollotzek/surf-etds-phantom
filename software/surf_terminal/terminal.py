import sys
import time
import queue
import re
import threading
import csv
import os
from collections import deque
from datetime import datetime
import serial
import json

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QFileDialog

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QTextEdit, QPushButton, QGridLayout, QMessageBox, QDialog, QFormLayout, QDialogButtonBox,
    QInputDialog
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial.tools.list_ports


# ================= PORT-KONFIGURATION (AUTO-WEICHE) =================
import platform

if platform.system() == "Windows":
    # Deine Windows-Ports vom Messlaptop
    AXIS_PORT = "COM3"
    HEAT_PORT = "COM4"
    print(f"Lade Windows-Konfiguration: Axis={AXIS_PORT}, Heat={HEAT_PORT}")
else:
    # Deine Mac-Ports vom Entwickler-Rechner
    AXIS_PORT = "/dev/cu.usbserial-120"
    HEAT_PORT = "/dev/cu.usbserial-140"
    print(f"Lade Mac-Konfiguration: Axis={AXIS_PORT}, Heat={HEAT_PORT}")
# =====================================================================

# ================= KONFIGURATION & LIMITS =================
BAUD_RATE = 115200

# Physikalische Grenzen
LIMITS = {
    'h': (-45, 25),  # mm
    'v': (-35, 50),  # mm
    'r': (-30, 120)  # Grad
}

# ================= THERMISCHE KALIBRIERUNG =================
# Lineare Regression aus "Kalibration HP vorne 19.csv"
# Formel: T_innen = (T_aussen * CALIB_M) + CALIB_B
CALIB_M = 1.170
CALIB_B = -3.500

def target_to_internal(target_outer):
    """Konvertiert die gewünschte GUI-Außentemperatur in die Arduino-Innentemperatur."""
    return (target_outer * CALIB_M) + CALIB_B

def internal_to_outer(temp_internal):
    """Konvertiert die vom Arduino gemeldete Innentemperatur in die reale Außentemperatur."""
    return (temp_internal - CALIB_B) / CALIB_M
# ===========================================================

SIMULATION_MODE = False  # Auf False setzen, wenn Hardware angeschlossen ist
STEPS_PER_MM = 800.0
STEPS_PER_DEG = 16.156


# ================= PROTOKOLL DEFINITIONEN =================
class AxisOrder:
    LOG_DATA = 10
    MOVE_AXIS = 1
    HOME_AXIS = 2
    STOP_ALL = 3
    COMMAND_DONE = 4
    SET_BACKLASH = 5
    SET_ZERO = 6  # <--- Neu


class HeatOrder:
    LOG_DATA = 10
    SET_A = 1
    SET_B = 2


# ================= QA-SESSION: PARSER & DATEI-HELFER (NEU) =================
# Diese Sektion ist rein additiv. Ohne ausgewaehlte Config-Datei laeuft das
# Terminal exakt wie vorher ("alter Modus").

# "1_endposition_d1" -> Auslenkung 1 (frueher minVerschub) / "_d2" -> 2 (maxVerschub)
RE_ENDPOS = re.compile(r"endposition_d(\d+)", re.IGNORECASE)
# "6_endposition_d1_couch-90" -> Couchwinkel -90
RE_COUCH = re.compile(r"couch_?(-?\d+)", re.IGNORECASE)
# Rueckwaerts-Kompatibilitaet zu den alten Blueprints (vor der Umbenennung)
RE_LEGACY_DEFL = re.compile(r"(min|max)verschub", re.IGNORECASE)
# "..._T32.json" -> Heatingpads 32
RE_TEMP_IN_NAME = re.compile(r"_T(\d+)", re.IGNORECASE)


def parse_deflection(point_id):
    """Auslenkungs-Nummer aus der Point-ID. 1 = min, 2 = max. None = keine Endposition."""
    pid = str(point_id or "")
    m = RE_ENDPOS.search(pid)
    if m:
        return int(m.group(1))
    m = RE_LEGACY_DEFL.search(pid)  # alte Blueprints weiterhin unterstuetzen
    if m:
        return 1 if m.group(1).lower() == "min" else 2
    return None


def parse_couch_angle(point_id):
    """Couchwinkel aus der Point-ID ('..._couch-90' -> -90). Ohne Suffix -> 0."""
    m = RE_COUCH.search(str(point_id or ""))
    return int(m.group(1)) if m else 0


def scan_blueprint_meta(data, blueprint_path=""):
    """Ermittelt VOR dem Start die Config-Felder, die fuer den ganzen Blueprint gelten.

    meas_couch_type: 'multi angle' sobald der Blueprint mehr als eine Couchrotation braucht.
    heatingpads:     Prioritaet: explizites Feld im Blueprint > heat-Step > '_T32' im Dateinamen > 'OFF'.
    Beides ist im Blueprint per Top-Level-Key ueberschreibbar.
    """
    seq = data.get("sequence", [])

    angles = set()
    for s in seq:
        if s.get("type") == "qa_input":
            pid = str(s.get("point_id", ""))
            angles.add(int(s["couch_angle"]) if "couch_angle" in s else parse_couch_angle(pid))
    couch_type = "multi angle" if len(angles) > 1 else "single angle"

    pads = "OFF"
    heats = [s for s in seq if s.get("type") == "heat"]
    if heats:
        val = float(heats[0].get("a", heats[0].get("b", 0.0)))
        pads = f"{val:g}" if val > 0 else "OFF"
    else:
        m = RE_TEMP_IN_NAME.search(os.path.basename(str(blueprint_path)))
        if m:
            pads = m.group(1)

    # Explizite Angaben im Blueprint haben immer Vorrang
    if "meas_couch_type" in data:
        couch_type = str(data["meas_couch_type"])
    if "heatingpads" in data:
        pads = str(data["heatingpads"])

    return {"meas_couch_type": couch_type, "heatingpads": pads}


class QAConfigFile:
    """Haengt Eintraege an das Auswerte-Config-File an.

    Die Struktur bleibt unveraendert:
        {"1": {"Linac", "deflection", "meas_couch_type", "heatingpads",
               "etds_timestamp", "surf_timestamp", "couch_angle"}, ...}
    Es wird bei jedem Eintrag frisch gelesen und geschrieben, damit bei einem
    Absturz mitten in der Messung die bereits erfassten Eintraege erhalten bleiben.
    """
    KEY_ORDER = ["Linac", "deflection", "meas_couch_type", "heatingpads",
                 "etds_timestamp", "surf_timestamp", "couch_angle"]

    def __init__(self, path):
        self.path = path
        self.written_keys = []

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r", encoding="utf-8") as f:
            txt = f.read().strip()
        return json.loads(txt) if txt else {}

    def _save(self, cfg):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def append_entry(self, entry):
        """Schreibt einen neuen Eintrag unter dem naechsten freien Zahlen-Key."""
        cfg = self._load()
        nums = [int(k) for k in cfg.keys() if str(k).isdigit()]
        key = str(max(nums) + 1) if nums else "1"
        cfg[key] = {k: entry[k] for k in self.KEY_ORDER}
        self._save(cfg)
        self.written_keys.append(key)
        return key

    def patch_surf_timestamp(self, surf_ts):
        """Traegt den CSV-Zeitstempel in eigene Eintraege nach, die noch keinen haben.

        Noetig falls ein Blueprint die Sphere Detection VOR dem logging-Start hat.
        """
        cfg = self._load()
        changed = []
        for k in self.written_keys:
            if k in cfg and not cfg[k].get("surf_timestamp"):
                cfg[k]["surf_timestamp"] = surf_ts
                changed.append(k)
        if changed:
            self._save(cfg)
        return changed


class MeasurementLog:
    """Messprotokoll eines Blueprint-Durchlaufs: schreibt log.json (maschinenlesbar)
    und log.txt (Messprotokoll zum Ausdrucken) in den data/<Datum>/-Ordner.

    Wird in BEIDEN Modi geschrieben und ist rein additiv: ein Fehler beim Schreiben
    darf eine laufende Messung niemals stoppen.
    """

    def __init__(self, target_dir, base_name):
        os.makedirs(target_dir, exist_ok=True)
        self.path_json = os.path.join(target_dir, base_name + "_log.json")
        self.path_txt = os.path.join(target_dir, base_name + "_log.txt")
        now = datetime.now()
        self.data = {
            "datum": now.strftime("%Y-%m-%d"),
            "start_messung": now.strftime("%H-%M"),
            "ende_messung": None,
            "modus": "alter Modus (ohne Config)",
            "config_file": None,
            "blueprint_file": None,
            "blueprint_name": None,
            "linac": None,
            "personal": None,
            "messzweck": None,
            "meas_couch_type": None,
            "heatingpads": None,
            "csv_file": None,
            "surf_timestamp": None,
            "bedingungen": {},
            "config_entries": [],
            "events": [],
        }

    def set(self, **kwargs):
        self.data.update(kwargs)
        self.save()

    def condition(self, key, value):
        self.data["bedingungen"][key] = value
        self.save()

    def event(self, ev_type, **kwargs):
        ev = {"zeit": datetime.now().strftime("%H:%M:%S"), "type": ev_type}
        ev.update(kwargs)
        self.data["events"].append(ev)
        self.save()
        return ev

    def config_entry(self, key, entry):
        self.data["config_entries"].append(dict(entry, config_key=key))
        self.save()

    def save(self):
        try:
            with open(self.path_json, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            with open(self.path_txt, "w", encoding="utf-8") as f:
                f.write(self.render_txt())
        except Exception as e:
            print(f"[LOG] Protokoll konnte nicht geschrieben werden: {e}")

    def render_txt(self):
        d = self.data
        L = []
        L.append("=" * 70)
        L.append(" MESSPROTOKOLL - ExacTrac Dynamic Surface")
        L.append("=" * 70)
        L.append(f"Datum der Messung : {d['datum']}")
        L.append(f"gemessen          : LINAC {d['linac'] if d['linac'] else '-'}")
        L.append(f"Messteam          : {d['personal'] or '-'}")
        L.append(f"Messzweck         : {d['messzweck'] or '-'}")
        L.append("")
        L.append(f"Modus             : {d['modus']}")
        L.append(f"Config-Datei      : {d['config_file'] or '- (nicht beschrieben)'}")
        L.append(f"Blueprint         : {d['blueprint_file'] or '-'}")
        L.append(f"Blueprint-Name    : {d['blueprint_name'] or '-'}")
        L.append(f"Messart           : {d['meas_couch_type'] or '-'}")
        L.append(f"Heatingpads       : {d['heatingpads'] or '-'}")
        L.append("")
        L.append(f"Start Messung     : {d['start_messung']}")
        L.append(f"Ende Messung      : {d['ende_messung'] or '- (laeuft noch / abgebrochen)'}")
        L.append(f"CSV Datei         : {d['csv_file'] or '-'}")
        L.append(f"surf_timestamp    : {d['surf_timestamp'] or '-'}")

        L.append("")
        L.append("--- BEDINGUNGEN " + "-" * 54)
        if d["bedingungen"]:
            for k, v in d["bedingungen"].items():
                L.append(f"  {k:<24}: {v}")
        else:
            L.append("  (keine)")

        L.append("")
        L.append("--- CONFIG-EINTRAEGE " + "-" * 49)
        if d["config_entries"]:
            for e in d["config_entries"]:
                L.append(
                    f"  [{e.get('config_key')}] deflection {e.get('deflection')} | "
                    f"couch {e.get('couch_angle')}deg | {e.get('meas_couch_type')} | "
                    f"pads {e.get('heatingpads')} | ETDS {e.get('etds_timestamp')} | "
                    f"CSV {e.get('surf_timestamp')}"
                )
        else:
            L.append("  (keine - alter Modus oder keine Endposition erreicht)")

        L.append("")
        L.append("--- ABLAUF " + "-" * 59)
        for ev in d["events"]:
            t = ev.get("zeit", "")
            typ = str(ev.get("type", "")).upper()
            if typ == "CHECKPOINT":
                L.append(f"  {t}  CHECKPOINT   {ev.get('msg', '')} -> {'JA' if ev.get('antwort') else 'NEIN'}")
            elif typ == "LOG_CHECKPOINT":
                L.append(f"  {t}  NOTIZ        {ev.get('key')}: {ev.get('wert')}   ({ev.get('msg', '')})")
            elif typ == "ETDS_TIMESTAMP":
                L.append(f"  {t}  ETDS         {ev.get('point_id')} -> {ev.get('etds_timestamp')}"
                         f" (Config-Key {ev.get('config_key')})")
            elif typ == "QA_INPUT":
                L.append(f"  {t}  SPHERE DET.  {ev.get('point_id')} [{ev.get('mode')}] {ev.get('werte', '')}")
            elif typ == "LOGGING":
                L.append(f"  {t}  LOGGING      {ev.get('action')} -> {ev.get('datei', '')}")
            else:
                L.append(f"  {t}  {typ:<12} {ev}")
        L.append("")
        return "\n".join(L)


# ================= SHARED STATE =================
class SystemState:
    def __init__(self):
        self.lock = threading.Lock()
        # Achsen
        self.pos = {'h': 0.0, 'v': 0.0, 'r': 0.0}
        self.axis_ready = True
        self.last_cmd_time = 0

        # Heizung
        self.temp = {'a': 0.0, 'b': 0.0}
        self.setpoint = {'a': 25.0, 'b': 25.0}
        self.stable = {'a': False, 'b': False}
        self.stable_reported = {'a': False, 'b': False}  # Spam-Schutz für Log

        # Stability Buffers (20 Sek bei ~1Hz Log-Rate)
        self.temp_history_a = deque(maxlen=120)
        self.temp_history_b = deque(maxlen=120)

        # Logging Status
        self.is_logging = False


state = SystemState()


# ================= BINARY HELPERS =================
def write_i8(ser, v): ser.write(int(v).to_bytes(1, 'little', signed=True))


def write_i32(ser, v): ser.write(int(v).to_bytes(4, 'little', signed=True))


def read_i8(ser): return int.from_bytes(ser.read(1), 'little', signed=True)


def read_i32(ser): return int.from_bytes(ser.read(4), 'little', signed=True)


# ================= WORKER: LOGGING =================
class LoggerThread(threading.Thread):
    def __init__(self, filename, interval=0.1, start_ref=None):
        super().__init__(daemon=True)
        self.filename = filename
        self.interval = interval
        self.running = True
        self.start_time = start_ref if start_ref else time.perf_counter()

    def stop(self):
        """Beendet die Schleife im Thread."""
        self.running = False
        # Optional: Falls der Thread in einem blockierenden seriellen Lesen hängt:
        # if hasattr(self, 'ser') and self.ser and self.ser.is_open:
        #     self.ser.close()

    def run(self):
        # Aktuelles Datum für Unterordner generieren (Format: YYYY-MM-DD)
        date_str = datetime.now().strftime('%Y-%m-%d')
        target_dir = os.path.join("data", date_str)

        # Ordner erstellen falls nicht vorhanden (inkl. Datums-Unterordner)
        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, self.filename)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            # Header
            writer.writerow([
                "Time_Sec",
                "Pos_H", "Pos_V", "Pos_R",
                "Temp_A", "Temp_B", "Set_A", "Set_B",
                "Stable_A", "Stable_B"
            ])

            print(f"[LOGGER] Starte Aufzeichnung in {filepath}")

            while self.running:
                now = time.perf_counter() - self.start_time
                with state.lock:
                    if not state.is_logging:
                        break

                    row = [
                        round(now, 3),
                        state.pos['h'], state.pos['v'], state.pos['r'],
                        state.temp['a'], state.temp['b'],
                        state.setpoint['a'], state.setpoint['b'],
                        int(state.stable['a']), int(state.stable['b'])
                    ]

                writer.writerow(row)
                f.flush()
                time.sleep(self.interval)
        print("[LOGGER] Aufzeichnung beendet.")


# ================= WORKER: ACHSEN =================
class AxisThread(QThread):
    log_msg = Signal(str)

    def __init__(self, port, cmd_queue):
        super().__init__()
        self.port, self.cmd_queue = port, cmd_queue
        self.running = True  

    def stop(self):
        self.running = False

    def run(self):
        ser = None
        if not SIMULATION_MODE:
            try:
                ser = serial.Serial(self.port, BAUD_RATE, timeout=0.05)
                time.sleep(2)
                ser.reset_input_buffer()
                self.log_msg.emit(f"Achsen-Arduino verbunden ({self.port}).")
            except Exception as e:
                self.log_msg.emit(f"Fehler: Gerät nicht gefunden. Erzwungene Simulation! ({e})")
        try:
            while self.running:
                # Watchdog
                with state.lock:
                    if not state.axis_ready and (time.time() - state.last_cmd_time > 60.0):
                        state.axis_ready = True
                        self.log_msg.emit("!! Watchdog: Axis Ready Reset (Timeout) !!")

                # 1. Lesen (wie bisher)
                if ser and ser.is_open and ser.in_waiting >= 18:
                    try:
                        hdr = read_i8(ser)
                        if hdr == AxisOrder.LOG_DATA:
                            _millis = read_i32(ser)
                            rh = read_i32(ser)
                            rv = read_i32(ser)
                            rr = read_i32(ser)
                            _stat = read_i8(ser)

                            with state.lock:
                                state.pos['h'] = rh / STEPS_PER_MM
                                state.pos['v'] = rv / STEPS_PER_MM
                                state.pos['r'] = rr / STEPS_PER_DEG

                        elif hdr == AxisOrder.COMMAND_DONE:
                            with state.lock:
                                state.axis_ready = True
                            self.log_msg.emit(">> Achse: Bewegung abgeschlossen.")
                    except Exception as e:
                        ser.reset_input_buffer()

                # 2. Senden
                can_send = False
                with state.lock:
                    can_send = state.axis_ready

                if can_send and not self.cmd_queue.empty():
                    cmd, args = self.cmd_queue.get()

                    # FIX: Wir setzen den Status SOFORT auf False, sobald wir den Befehl aus der Queue nehmen!
                    with state.lock:
                        state.axis_ready = False
                        state.last_cmd_time = time.time()

                    # --- 2. EIGENTLICHES SENDEN AN DEN ARDUINO ---
                    if ser and ser.is_open:
                        try:
                            # Sende Kommando-Header (1 Byte)
                            write_i8(ser, cmd)

                            # Das erste Argument (Achse) ist 1 Byte. Alle anderen Argumente sind 4 Bytes.
                            if len(args) > 0:
                                write_i8(ser, args[0])  # Achsen-ID (i8)
                                for a in args[1:]:
                                    write_i32(ser, a)  # Target und Speed (i32)

                        except Exception as e:
                            self.log_msg.emit(f"Axis Send Error: {e}")
                            with state.lock:
                                state.axis_ready = True  # Bei Fehler sofort wieder freigeben

                    elif SIMULATION_MODE or ser is None:
                        time.sleep(0.5)  # Simuliere Fahrzeit
                        with state.lock:
                            state.axis_ready = True  # Simulation sofort abschließen
                time.sleep(0.01)

        except Exception as e:
            self.log_msg.emit(f"AXIS CRITICAL: {e} (Port prüfen!)")

# ================= WORKER: HEIZUNG =================
class HeatThread(QThread):
    log_msg = Signal(str)
    def __init__(self, port, cmd_queue):
        super().__init__()
        self.port, self.cmd_queue = port, cmd_queue
        self.running = True

    def stop(self):
        """Beendet die Schleife im Thread."""
        self.running = False
        # Optional: Falls der Thread in einem blockierenden seriellen Lesen hängt:
        # if hasattr(self, 'ser') and self.ser and self.ser.is_open:
        #     self.ser.close()

    def run(self):
        ser = None
        if not SIMULATION_MODE:
            try:
                ser = serial.Serial(self.port, BAUD_RATE, timeout=0.05)
                time.sleep(2)
                ser.reset_input_buffer()
                self.log_msg.emit(f"HeatingPad-Arduino verbunden ({self.port}).")
                # ... (Init Hardware) ...
            except Exception:
                self.log_msg.emit("Heiz-Simulation aktiv.")
        try:
            while self.running:
                    # 1. LESEN & STABILITÄT BERECHNEN (Für echte Hardware)
                    if ser and ser.is_open and ser.in_waiting >= 13:
                        try:
                            hdr = read_i8(ser)
                            if hdr == HeatOrder.LOG_DATA:
                                # Wir erwarten exakt 12 Bytes (4x Time, 4x TempA, 4x TempB)
                                # serial timeout=0.05 fängt Verzögerungen ab
                                _millis = read_i32(ser)
                                ra = read_i32(ser)
                                rb = read_i32(ser)

                                with state.lock:
                                    state.temp['a'] = internal_to_outer(ra / 100.0)
                                    state.temp['b'] = internal_to_outer(rb / 100.0)

                                    # Werte in Historie für Stabilitäts-Check schieben
                                    state.temp_history_a.append(state.temp['a'])
                                    state.temp_history_b.append(state.temp['b'])

                                    # Berechnung der Stabilität
                                    for p in ['a', 'b']:
                                        hist = state.temp_history_a if p == 'a' else state.temp_history_b
                                        if len(hist) == hist.maxlen:
                                            diff = [abs(x - state.setpoint[p]) for x in hist]
                                            state.stable[p] = max(diff) <= 0.2
                                        else:
                                            state.stable[p] = False

                        except Exception as e:
                            # Puffer leeren bei einem Lesefehler / Timeout
                            # print(f"Heat Read Error: {e}")
                            ser.reset_input_buffer()

                    # 2. SENDEN
                    while not self.cmd_queue.empty():
                        p_idx, val = self.cmd_queue.get()
                        with state.lock:
                            state.setpoint['a' if p_idx == 1 else 'b'] = val
                            state.stable_reported['a' if p_idx == 1 else 'b'] = False

                        if ser and ser.is_open:
                            try:
                                write_i8(ser, p_idx)
                                val_inner = target_to_internal(val)
                                write_i32(ser, int(val_inner * 100))
                            except Exception as e:
                                self.log_msg.emit(f"Heat Send Error: {e}")

                    # 3. --- SIMULATION (Nur aktiv wenn KEIN 'ser' vorhanden) ---
                    if SIMULATION_MODE or ser is None:
                        with state.lock:
                            state.temp['a'] = state.setpoint['a']
                            state.temp['b'] = state.setpoint['b']
                            # WICHTIG: Damit der Interpreter weiterfährt!
                            state.stable['a'] = True
                            state.stable['b'] = True

                    time.sleep(0.1)
        except Exception as e:
            self.log_msg.emit(f"HEAT THREAD ERROR: {e}")


# ================= WORKER: JSON INTERPRETER =================
class InterpreterThread(QThread):
    log_msg = Signal(str)
    show_prompt = Signal(str, str)
    request_qa_input = Signal(str, str, str)
    finished = Signal()
    log_ctrl = Signal(str, str)
    # --- NEU (QA-Session) ---
    request_etds_timestamp = Signal(str, int, int, str)   # point_id, deflection, couch_angle, msg
    request_log_input = Signal(str, str, str, bool)       # key, mode, msg, abort_on_no
    log_event = Signal(object)                            # dict -> Messprotokoll

    def __init__(self, sequence_data, axis_q, heat_q):
        super().__init__()
        self.sequence_data = sequence_data
        self.axis_q = axis_q
        self.heat_q = heat_q
        self.wait_event = threading.Event()
        self.running = True
        self.proceed_flag = True  # NEU: Bestimmt, ob der Blueprint fortgesetzt wird
        # NEU: nur True wenn eine Config-Datei gewaehlt wurde. False = exakt altes Verhalten.
        self.qa_mode = False

    def stop(self):
        """Beendet die Schleife im Thread."""
        self.running = False
        # Optional: Falls der Thread in einem blockierenden seriellen Lesen hängt:
        # if hasattr(self, 'ser') and self.ser and self.ser.is_open:
        #     self.ser.close()

    def run(self):
        name = self.sequence_data.get("name", "Unbekannte Messreihe")
        self.log_msg.emit(f">>> STARTE BLUEPRINT: {name} <<<")

        for step in self.sequence_data.get("sequence", []):
            if not self.running:
                break

            cmd_type = step.get("type")

            # --- NEUER BEFEHL: QA INPUT ---
            if cmd_type == "qa_input":
                mode = step.get("mode", "surface_tracking")
                point_id = str(step.get("point_id", "Unknown"))
                msg = step.get("msg", "Bitte QA-Werte eintragen.")

                # --- NEU: ETDS-Timestamp ZWINGEND vor der Sphere Detection an einer Endposition ---
                # Nur im QA-Modus. Auslenkung/Couchwinkel kommen aus der Point-ID
                # ("1_endposition_d1", "6_endposition_d1_couch-90") oder aus expliziten Feldern.
                if self.qa_mode:
                    defl = step.get("deflection", parse_deflection(point_id))
                    if defl is not None:
                        couch = int(step.get("couch_angle", parse_couch_angle(point_id)))
                        self.log_msg.emit(f"Warte auf ETDS-Timestamp fuer {point_id}...")

                        self.proceed_flag = False
                        self.wait_event.clear()
                        self.request_etds_timestamp.emit(
                            point_id, int(defl), couch,
                            step.get("etds_msg", "Zeitstempel (HHMMSS) des ExacTrac Tracking Files eingeben.")
                        )
                        self.wait_event.wait()

                        if not self.proceed_flag:
                            self.log_msg.emit("!! Blueprint bei der ETDS-Timestamp-Eingabe abgebrochen !!")
                            self.running = False
                            break

                self.log_msg.emit(f"Warte auf manuelle Eingabe ({mode})...")

                self.proceed_flag = False
                self.qa_data = None  # Temporärer Speicher
                self.wait_event.clear()

                # Signal an die GUI schicken
                self.request_qa_input.emit(mode, point_id, msg)
                self.wait_event.wait()

                if not self.proceed_flag:
                    self.log_msg.emit("!! Blueprint durch Benutzer am QA-Input abgebrochen !!")
                    self.running = False
                    break

                self.log_msg.emit(f"Eingabe für {point_id} gespeichert.")

            # --- BEFEHL: CHECKPOINT ---
            if cmd_type == "checkpoint":
                msg = step.get("msg", "Checkpoint erreichen und bestätigen.")
                self.log_msg.emit(f"PAUSE: {msg}")

                self.proceed_flag = False
                self.wait_event.clear()
                self.show_prompt.emit("Checkpoint", msg)
                self.wait_event.wait()

                # NEU: Antwort jedes normalen Checkpoints wandert ins Messprotokoll
                self.log_event.emit({"type": "checkpoint", "msg": msg, "antwort": bool(self.proceed_flag)})

                if not self.proceed_flag:
                    self.log_msg.emit("!! Blueprint durch Benutzer am Checkpoint abgebrochen !!")
                    self.running = False
                    break

                self.log_msg.emit("Checkpoint bestätigt, fahre fort...")

            # --- BEFEHL: ACHSEN BEWEGEN ---
            elif cmd_type == "move":
                speed = step.get("speed", 20.0)
                for ax_char in ['H', 'V', 'R']:
                    if ax_char in step:
                        target = float(step[ax_char])
                        ax_id = {'H': 0, 'V': 1, 'R': 2}[ax_char]
                        factor = STEPS_PER_DEG if ax_id == 2 else STEPS_PER_MM

                        # 1. Warten, bis das System für einen neuen Befehl bereit ist
                        while not state.axis_ready and self.running:
                            time.sleep(0.05)

                        if not self.running: break

                        self.log_msg.emit(f"Auto-Move: {ax_char} -> {target}")

                        # 2. Befehl in die Queue legen (NICHT den Status hier ändern!)
                        self.axis_q.put((AxisOrder.MOVE_AXIS, [ax_id, int(target * factor), int(speed * factor)]))

                        # 3. WICHTIG: Warten, bis der AxisThread den Befehl gegriffen und das ready-Flag auf False gesetzt hat
                        while state.axis_ready and self.running:
                            time.sleep(0.01)

                        # 4. Jetzt warten wir ganz entspannt, bis das Hardware-Feedback (Arduino) das Flag wieder auf True setzt
                        while not state.axis_ready and self.running:
                            time.sleep(0.05)

            # --- BEFEHL: HEIZUNG ---
            elif cmd_type == "heat":
                if "a" in step:
                    self.heat_q.put((1, float(step["a"])))
                if "b" in step:
                    self.heat_q.put((2, float(step["b"])))

                if step.get("wait_steady", False):
                    self.log_msg.emit("Warte auf Temperaturstabilität (max. 120 Sekunden)...")
                    wait_time = 0
                    is_stable = False

                    # 120s Timeout Schleife
                    while self.running and wait_time < 120:
                        with state.lock:
                            a_ok = state.stable['a'] if "a" in step else True
                            b_ok = state.stable['b'] if "b" in step else True
                            if a_ok and b_ok:
                                is_stable = True
                                break
                        time.sleep(1.0)
                        wait_time += 1

                    if self.running and not is_stable:
                        self.log_msg.emit("Temperatur-Timeout (120s). Warte auf Benutzereingabe...")
                        self.proceed_flag = False
                        self.wait_event.clear()
                        self.show_prompt.emit(
                            "Temperatur-Timeout",
                            "Die Temperatur ist nach 120 Sekunden noch nicht stabil.\n\nFür Simulationszwecke ignorieren und Blueprint fortsetzen?"
                        )
                        self.wait_event.wait()

                        if not self.proceed_flag:
                            self.log_msg.emit("!! Blueprint wegen instabiler Temperatur abgebrochen !!")
                            self.running = False
                            break
                        else:
                            self.log_msg.emit("Temperatur-Check übersprungen. Fahre fort...")

                    elif is_stable:
                        self.log_msg.emit("Temperatur stabil!")

            # --- BEFEHL: PAUSE (DELAY) ---
            elif cmd_type == "delay":
                delay_sec = float(step.get("time", 2.0))
                self.log_msg.emit(f"Pausiere für {delay_sec} Sekunden...")

                # Unterbrechbarer Sleep für sofortigen Abbruch bei 'exit bp'
                slept = 0.0
                while slept < delay_sec and self.running:
                    time.sleep(0.1)
                    slept += 0.1

            # --- BEFEHL: LOGGING STEUERN ---
            elif cmd_type == "logging":
                action = step.get("action", "start")
                prefix = step.get("prefix", "messung")
                self.log_ctrl.emit(action, prefix)
                time.sleep(0.5)

            # --- NEUER BEFEHL: LOG_CHECKPOINT ---
            # Erfassender Checkpoint: schreibt eine Bedingung/Notiz ins Messprotokoll.
            # Anders als "checkpoint" ist das KEIN Abbruch-Gate (ausser abort_on_no: true).
            #   mode "yesno" -> Ja/Nein wird als True/False protokolliert (z.B. Raumlicht aus?)
            #   mode "text"  -> Freitext-Notiz (z.B. Tracking-Qualitaet)
            elif cmd_type == "log_checkpoint":
                key = str(step.get("key", "notiz"))
                msg = step.get("msg", "Bitte bestaetigen.")
                lmode = str(step.get("mode", "yesno")).lower()
                abort_on_no = bool(step.get("abort_on_no", False))

                self.log_msg.emit(f"PROTOKOLL-EINTRAG: {msg}")
                self.proceed_flag = False
                self.wait_event.clear()
                self.request_log_input.emit(key, lmode, msg, abort_on_no)
                self.wait_event.wait()

                if not self.proceed_flag:
                    self.log_msg.emit(f"!! Blueprint abgebrochen (log_checkpoint '{key}') !!")
                    self.running = False
                    break

        self.log_msg.emit(">>> BLUEPRINT BEENDET/GESTOPPT <<<")
        self.finished.emit()

    def confirm_prompt(self, proceed):
        """Wird von der GUI aufgerufen, um Ja/Nein Antworten zu übergeben."""
        self.proceed_flag = proceed
        self.wait_event.set()


class QAInputDialog(QDialog):
    def __init__(self, mode, point_id, msg, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"QA Eingabe: {mode.replace('_', ' ').title()} (ID: {point_id})")
        self.setMinimumWidth(300)

        self.layout = QVBoxLayout(self)
        if msg:
            self.layout.addWidget(QLabel(f"<b>{msg}</b>"))

        self.form_layout = QFormLayout()
        self.inputs = {}

        # Felder definieren
        fields = ['x', 'y', 'z']
        if mode == 'surface_tracking' or mode == 'both':
            fields.extend(['pitch', 'yaw', 'roll'])

        for field in fields:
            line_edit = QLineEdit()
            # Erlaube nur Zahlen, nutze Platzhalter
            line_edit.setPlaceholderText("0.00")
            self.inputs[field] = line_edit
            # Großschreibung für Label
            self.form_layout.addRow(f"{field.upper()} [mm/°]:", line_edit)

        self.layout.addLayout(self.form_layout)

        # OK / Abbrechen Buttons
        self.btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        self.layout.addWidget(self.btns)

    def get_data(self):
        """Liest die Felder aus, wandelt Kommas in Punkte um und gibt ein Dict zurück."""
        data = {}
        for key, widget in self.inputs.items():
            val_str = widget.text().strip().replace(',', '.')
            try:
                data[key] = float(val_str) if val_str else ""
            except ValueError:
                data[key] = ""  # Bei leerer/falscher Eingabe
        return data


class SessionInfoDialog(QDialog):
    """Sammelt zu Beginn einer Messung die zentralen Infos in EINEM Formular.

    Linac / Personal / Messzweck werden abgefragt, Messart und Heatingpads sind
    aus dem Blueprint vorbelegt und koennen korrigiert werden (sie landen so im
    Config-File wie sie hier stehen).
    """

    def __init__(self, blueprint_file, blueprint_name, config_path, meta, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Messung starten - Zentrale Messungsinfos")
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            f"<b>Blueprint:</b> {os.path.basename(blueprint_file)}<br>"
            f"<span style='color:#555'>{blueprint_name}</span><br>"
            f"<b>Config-Datei:</b> {os.path.basename(config_path)}"
        ))
        lay.addWidget(QLabel("<i>Diese Angaben werden ins Messprotokoll und in das Config-File geschrieben.</i>"))

        form = QFormLayout()
        self.in_linac = QLineEdit()
        self.in_linac.setPlaceholderText("z.B. 0 oder 1")
        self.in_personal = QLineEdit()
        self.in_personal.setPlaceholderText("z.B. QMP1, Student1")
        self.in_zweck = QLineEdit("QA")
        self.in_pads = QLineEdit(str(meta.get("heatingpads", "OFF")))
        self.in_couch = QLineEdit(str(meta.get("meas_couch_type", "single angle")))

        form.addRow("Linac:", self.in_linac)
        form.addRow("Personal:", self.in_personal)
        form.addRow("Messzweck:", self.in_zweck)
        form.addRow("Heatingpads (autom.):", self.in_pads)
        form.addRow("Messart (autom.):", self.in_couch)
        lay.addLayout(form)

        self.btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btns.accepted.connect(self.try_accept)
        self.btns.rejected.connect(self.reject)
        lay.addWidget(self.btns)

    def try_accept(self):
        if not self.in_linac.text().strip() or not self.in_personal.text().strip():
            QMessageBox.warning(self, "Eingabe fehlt", "Linac und Personal muessen ausgefuellt sein.")
            return
        self.accept()

    def get_data(self):
        return {
            "linac": self.in_linac.text().strip(),
            "personal": self.in_personal.text().strip(),
            "messzweck": self.in_zweck.text().strip() or "QA",
            "heatingpads": self.in_pads.text().strip() or "OFF",
            "meas_couch_type": self.in_couch.text().strip() or "single angle",
        }


class EtdsTimestampDialog(QDialog):
    """Fragt den Zeitstempel des ExacTrac-Tracking-Files ab (HHMMSS)."""

    def __init__(self, point_id, deflection, couch_angle, msg, surf_timestamp, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"ExacTrac Datensatz - {point_id}")
        self.setMinimumWidth(420)
        self.value = ""

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{msg}</b>"))
        lay.addWidget(QLabel(
            f"Punkt: <b>{point_id}</b><br>"
            f"Auslenkung (deflection): <b>{deflection}</b> "
            f"({'min' if deflection == 1 else 'max' if deflection == 2 else '?'})<br>"
            f"Couchwinkel: <b>{couch_angle}&deg;</b><br>"
            f"Zugehoerige Phantom-CSV: <b>{surf_timestamp or '- noch kein Logging gestartet -'}</b>"
        ))

        form = QFormLayout()
        self.in_ts = QLineEdit()
        self.in_ts.setPlaceholderText("HHMMSS  (z.B. 162919)")
        form.addRow("ETDS Datensatz:", self.in_ts)
        lay.addLayout(form)

        self.btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btns.accepted.connect(self.try_accept)
        self.btns.rejected.connect(self.reject)
        lay.addWidget(self.btns)

    def try_accept(self):
        # Tolerant: "16:29:19" / "16.29.19" werden zu "162919"
        digits = re.sub(r"\D", "", self.in_ts.text())
        if len(digits) != 6:
            QMessageBox.warning(self, "Ungueltig",
                                "Bitte genau 6 Ziffern im Format HHMMSS eingeben (z.B. 162919).")
            return
        self.value = digits
        self.accept()

    def get_timestamp(self):
        return self.value


# ================= GUI =================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SURF Terminal - QA for SGRT Scanner")
        self.resize(1200, 800)

        self.axis_q = queue.Queue()
        self.heat_q = queue.Queue()
        self.logger_thread = None

        self.t_data = deque(maxlen=1000)
        self.ta_data = deque(maxlen=1000)
        self.tb_data = deque(maxlen=1000)
        self.start_t = time.time()

        self.setup_ui()

        # Threads starten
        self.axis_thread = AxisThread(AXIS_PORT, self.axis_q)
        self.axis_thread.log_msg.connect(self.log)  # Signal mit Log-Funktion verknüpfen
        self.axis_thread.start()

        self.heat_thread = HeatThread(HEAT_PORT, self.heat_q)
        self.heat_thread.log_msg.connect(self.log)  # Signal mit Log-Funktion verknüpfen
        self.heat_thread.start()


        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(100)

        self.qa_csv_filepath = None  # Speichert den Pfad zur QA-Datei

        # --- NEU: QA-Session (nur aktiv wenn eine Config-Datei gewaehlt wurde) ---
        self.qa_config = None       # QAConfigFile oder None (= alter Modus)
        self.meas_log = None        # MeasurementLog des aktuellen Blueprints
        self.session = {}           # Linac / Personal / Messzweck / Messart / Heatingpads
        self.surf_timestamp = None  # HHMMSS der laufenden Phantom-CSV

    def setup_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        main_layout = QHBoxLayout(cw)

        # --- LEFT PANEL: Controls ---
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        # 1. Status Label
        self.status_lbl = QLabel("Initialisiere...")
        self.status_lbl.setStyleSheet(
            "font-size: 14px; font-weight: bold; background: #222; color: #fff; padding: 5px;")
        self.status_lbl.setFrameStyle(QFrame.StyledPanel)
        left_panel.addWidget(self.status_lbl)

        # 2. Heizung Steuerung (aus FuckYeah2 übernommen)
        heat_grp = QFrame()
        heat_grp.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        heat_layout = QVBoxLayout(heat_grp)
        heat_layout.addWidget(QLabel("<b>HEATING PAD SURFACE TEMPERATUREN SOLLWERTE</b>"))

        h_inputs = QHBoxLayout()
        h_inputs.addWidget(QLabel("A [°C]:"))
        self.input_a = QLineEdit("25.0")
        h_inputs.addWidget(self.input_a)

        h_inputs.addWidget(QLabel("B [°C]:"))
        self.input_b = QLineEdit("25.0")
        h_inputs.addWidget(self.input_b)

        self.btn_heat = QPushButton("Setzen")
        self.btn_heat.clicked.connect(self.apply_heat_gui)
        self.btn_heat.setStyleSheet("background: #d35400; color: white; font-weight: bold;")
        h_inputs.addWidget(self.btn_heat)

        heat_layout.addLayout(h_inputs)
        left_panel.addWidget(heat_grp)

        # 3. Logging Steuerung
        log_grp = QFrame()
        log_grp.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        log_layout = QVBoxLayout(log_grp)
        log_layout.addWidget(QLabel("<b>MESSUNG / LOGGING</b>"))

        l_btns = QHBoxLayout()
        self.btn_start = QPushButton("START MESSUNG")
        self.btn_start.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 10px;")
        self.btn_start.clicked.connect(lambda: self.handle_logging("start"))

        self.btn_stop = QPushButton("STOP & SPEICHERN")
        self.btn_stop.setStyleSheet("background: #c0392b; color: white; font-weight: bold; padding: 10px;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(lambda: self.handle_logging("stop"))

        l_btns.addWidget(self.btn_start)
        l_btns.addWidget(self.btn_stop)
        log_layout.addLayout(l_btns)
        # --- NEU: JSON Button ---
        self.btn_load_json = QPushButton("BLUEPRINT LADEN (JSON)")
        self.btn_load_json.setStyleSheet(
            "background: #8e44ad; color: white; font-weight: bold; padding: 10px; margin-top: 10px;")
        self.btn_load_json.clicked.connect(self.load_blueprint)
        log_layout.addWidget(self.btn_load_json)

        left_panel.addWidget(log_grp)


        # 4. Console & Input
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background: #111; color: #0f0; font-family: 'Courier New'; font-size: 11px;")
        left_panel.addWidget(self.console)

        input_layout = QHBoxLayout()
        self.cmd_line = QLineEdit()
        self.cmd_line.setPlaceholderText("Befehl (z.B. m h 50 10 | m zp | t a 30)")
        self.cmd_line.returnPressed.connect(self.parse_input)
        input_layout.addWidget(self.cmd_line)

        # Not-Aus Button
        self.btn_stop_all = QPushButton("STOP ALL")
        self.btn_stop_all.setStyleSheet("background: red; color: white; font-weight: bold;")
        self.btn_stop_all.clicked.connect(lambda: self.axis_q.put((AxisOrder.STOP_ALL, [])))
        input_layout.addWidget(self.btn_stop_all)

        left_panel.addLayout(input_layout)

        main_layout.addLayout(left_panel, 1)

        # --- RIGHT PANEL: Plot ---
        self.fig = Figure(facecolor='#222')
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#111')
        self.ax.tick_params(colors='white')
        self.ax.grid(alpha=0.2)
        main_layout.addWidget(self.canvas, 2)

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console.append(f"[{ts}] {msg}")
        # Auto-Scroll
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def apply_heat_gui(self):
        try:
            va = float(self.input_a.text().replace(',', '.'))
            vb = float(self.input_b.text().replace(',', '.'))
            if 10 <= va <= 50 and 10 <= vb <= 50:
                self.heat_q.put((1, va))
                self.heat_q.put((2, vb))
                self.log(f"GUI Set: A={va}°C, B={vb}°C")
            else:
                self.log("!! TEMP LIMIT: 10-50°C")
        except ValueError:
            self.log("!! Ungültige Zahleneingabe")

    def handle_logging(self, action):
        if action == "start":
            if state.is_logging: return

            # Zeitstempel beim START fixieren und in der Klasse speichern
            self.current_m_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Der gemeinsame Nullpunkt für ALLE Dateien dieser Messung
            self.measurement_start_ref = time.perf_counter()
            # Dateiname für CSV (Prefix ist hier immer "messung")
            fname = f"messung_{self.current_m_timestamp}.csv"

            with state.lock:
                state.is_logging = True
            self.logger_thread = LoggerThread(fname, start_ref=self.measurement_start_ref)
            self.logger_thread.start()

            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.log(f"LOGGING GESTARTET: {fname}")

        elif action == "stop":
            if not state.is_logging: return
            with state.lock:
                state.is_logging = False
            if self.logger_thread:
                self.logger_thread.join()

            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

            # Screenshot speichern mit DEMSELBEN Zeitstempel vom Start
            try:
                os.makedirs("data", exist_ok=True)
                # Wir nutzen die Variable, die wir beim 'start' angelegt haben
                plot_name = os.path.join("data", f"plot_{self.current_m_timestamp}.png")
                self.fig.savefig(plot_name)
                self.log(f"LOGGING GESTOPPT. Plot gespeichert: {plot_name}")
                QMessageBox.information(self, "Info", "Messung und Plot gespeichert.")
            except Exception as e:
                self.log(f"Fehler beim Speichern des Plots: {e}")

    def parse_input(self):
        text = self.cmd_line.text().strip().lower()
        self.cmd_line.clear()
        p = text.split()
        if not p: return

        try:
            # === MOVEMENT ===
            # m zp (Zero Position)
            if p[0] == 'm' and len(p) >= 2 and p[1] == 'zp':
                speed = 20.0
                if len(p) > 2: speed = float(p[2])
                self.log(f"Fahre Nullposition an (Seq: R->V->H), Speed={speed}")

                # Sequenz in Queue: R, V, H auf 0
                for ax_char in ['r', 'v', 'h']:
                    ax_id = {'h': 0, 'v': 1, 'r': 2}[ax_char]
                    fac = STEPS_PER_DEG if ax_id == 2 else STEPS_PER_MM
                    self.axis_q.put((AxisOrder.MOVE_AXIS, [ax_id, 0, int(speed * fac)]))

            # m [h/v/r] [pos] [speed]
            elif p[0] == 'm' and len(p) == 4:
                ax_char = p[1]
                if ax_char not in LIMITS: raise ValueError(f"Achse '{ax_char}' unbekannt.")
                target = float(p[2])
                speed = float(p[3])

                min_v, max_v = LIMITS[ax_char]
                if not (min_v <= target <= max_v):
                    self.log(f"!! LIMIT ERROR: {ax_char} Bereich {min_v} bis {max_v}")
                    return

                ax_id = {'h': 0, 'v': 1, 'r': 2}[ax_char]
                factor = STEPS_PER_DEG if ax_id == 2 else STEPS_PER_MM
                self.axis_q.put((AxisOrder.MOVE_AXIS, [ax_id, int(target * factor), int(speed * factor)]))
                self.log(f"Sende Move: {ax_char} auf {target}")

            # === HOMING ===
            # h all mit Sicherheitsabfrage
            elif p[0] == 'h' and len(p) == 2 and p[1] == 'all':
                reply = QMessageBox.question(
                    self, 'Sicherheitscheck',
                    "Phantom ausgerichtet und alle Kabel vom Phantom frei?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    self.log(">> Starte Homing-Sequenz für ALLE Achsen...")
                    # Sicherheits-Reihenfolge:
                    # 1. V (Achse 1) hochfahren, um Kollisionen zu vermeiden
                    # 2. R (Achse 2) rotieren
                    # 3. H (Achse 0) horizontal fahren
                    self.axis_q.put((AxisOrder.HOME_AXIS, [1]))
                    self.axis_q.put((AxisOrder.HOME_AXIS, [2]))
                    self.axis_q.put((AxisOrder.HOME_AXIS, [0]))
                else:
                    self.log("!! Homing abgebrochen: Sicherheitscheck nicht bestätigt.")
            elif p[0] == 'h' and len(p) == 2:
                ax_id = {'h': 0, 'v': 1, 'r': 2}.get(p[1])
                if ax_id is not None:
                    self.axis_q.put((AxisOrder.HOME_AXIS, [ax_id]))
                    self.log(f"Homing {p[1]}...")

            # === HEATING ===
            # t [a/b] [temp]
            elif p[0] == 't' and len(p) == 3:
                pad_char = p[1]
                pad = 1 if pad_char == 'a' else 2
                val = float(p[2])
                if 10 <= val <= 50:
                    self.heat_q.put((pad, val))
                    self.log(f"Setze Temp {pad_char.upper()} auf {val}°C")
                else:
                    self.log("!! TEMP LIMIT: Bereich 10-50°C")

            # === SET ZERO ===
            elif text == "set r zero":
                self.axis_q.put((AxisOrder.SET_ZERO, [2]))  # 2 entspricht AXIS_R
                self.log(">> Sende: Setze aktuelle R-Position als 0")
            elif text == "set h zero":
                self.axis_q.put((AxisOrder.SET_ZERO, [0]))  # 2 entspricht AXIS_R
                self.log(">> Sende: Setze aktuelle R-Position als 0")
            elif text == "set v zero":
                self.axis_q.put((AxisOrder.SET_ZERO, [1]))  # 2 entspricht AXIS_R
                self.log(">> Sende: Setze aktuelle R-Position als 0")
            # === LOGGING (CMD LINE) ===
            elif text == "start measurement":
                self.handle_logging("start")
            elif text == "stop measurement":
                self.handle_logging("stop")

            # === BLUEPRINT ABBRUCH ===
            elif text == "exit bp":
                if hasattr(self, 'interpreter') and self.interpreter.isRunning():
                    self.interpreter.running = False
                    self.interpreter.confirm_prompt(False)  # Befreit den Thread, falls er auf eine Bestätigung wartet
                    self.log("!! Blueprint manuell über Konsole abgebrochen !!")
                else:
                    self.log("!! Kein Blueprint aktiv.")

            # === BACKLASH CONTROL ===
            elif text == "backlash on":
                self.axis_q.put((AxisOrder.SET_BACKLASH, [1]))
                self.log(">> Sende Backlash AKTIVIERT an Arduino")
            elif text == "backlash off":
                self.axis_q.put((AxisOrder.SET_BACKLASH, [0]))
                self.log(">> Sende Backlash DEAKTIVIERT an Arduino")

            else:
                self.log("!! SYNTAX: m [h/v/r] [pos] [spd] | m zp | t [a/b] [temp] | start/stop measurement")
        except Exception as e:
            self.log(f"Fehler: {e}")

    def load_blueprint(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Blueprint laden", "", "JSON Files (*.json)")
        if not file_name:
            return

        try:
            with open(file_name, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.log(f"Fehler beim Laden der JSON: {e}")
            return

        # === NEU: WEICHE QA-MODUS <-> ALTER MODUS ==========================
        # Config-Datei waehlen -> QA-Modus. Abbrechen -> alter Modus, es wird
        # KEINE Config beschrieben (Sphere Detections laufen trotzdem normal).
        self.qa_config = None
        self.meas_log = None
        self.session = {}
        self.surf_timestamp = None

        meta = scan_blueprint_meta(data, file_name)
        cfg_path, _ = QFileDialog.getOpenFileName(
            self,
            "Config-Datei fuer die Auswertung waehlen  (ABBRECHEN = alter Modus ohne Config)",
            "", "JSON Files (*.json)"
        )

        if cfg_path:
            dlg = SessionInfoDialog(file_name, data.get("name", ""), cfg_path, meta, self)
            if dlg.exec() != QDialog.Accepted:
                self.log("!! Blueprint-Start abgebrochen (Messungsinfos nicht bestaetigt).")
                return
            self.session = dlg.get_data()
            self.qa_config = QAConfigFile(cfg_path)
            self.log(f">> QA-MODUS: Config-Datei '{os.path.basename(cfg_path)}' wird erweitert.")
            self.log(f">> Linac {self.session['linac']} | {self.session['personal']} | "
                     f"{self.session['meas_couch_type']} | Pads {self.session['heatingpads']}")
        else:
            self.session = dict(meta)
            self.log(">> ALTER MODUS: Es wird KEINE Config-Datei beschrieben.")

        # --- Messprotokoll anlegen (in BEIDEN Modi, rein additiv) ---
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            base = f"{os.path.splitext(os.path.basename(file_name))[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.meas_log = MeasurementLog(os.path.join("data", date_str), base)
            self.meas_log.set(
                modus="QA (Config wird beschrieben)" if self.qa_config else "alter Modus (ohne Config)",
                config_file=os.path.basename(cfg_path) if cfg_path else None,
                blueprint_file=os.path.basename(file_name),
                blueprint_name=data.get("name"),
                linac=self.session.get("linac"),
                personal=self.session.get("personal"),
                messzweck=self.session.get("messzweck"),
                meas_couch_type=self.session.get("meas_couch_type"),
                heatingpads=self.session.get("heatingpads"),
            )
            self.log(f">> Messprotokoll: {self.meas_log.path_txt}")
        except Exception as e:
            self.meas_log = None
            self.log(f"!! Messprotokoll konnte nicht angelegt werden: {e}")
        # ===================================================================

        try:
            self.interpreter = InterpreterThread(data, self.axis_q, self.heat_q)
            self.interpreter.qa_mode = self.qa_config is not None
            self.interpreter.log_msg.connect(self.log)
            self.interpreter.show_prompt.connect(self.handle_prompt)
            self.interpreter.log_ctrl.connect(self.handle_blueprint_logging)
            self.interpreter.request_qa_input.connect(self.handle_qa_input)
            # --- NEU ---
            self.interpreter.request_etds_timestamp.connect(self.handle_etds_timestamp)
            self.interpreter.request_log_input.connect(self.handle_log_input)
            self.interpreter.log_event.connect(self.handle_log_event)

            self.btn_load_json.setEnabled(False)
            self.interpreter.finished.connect(self.on_blueprint_finished)
            self.interpreter.start()

        except Exception as e:
            self.log(f"Fehler beim Starten des Blueprints: {e}")
            self.btn_load_json.setEnabled(True)

    # ================= NEU: HANDLER DER QA-SESSION =================
    def on_blueprint_finished(self):
        """Ersetzt das frühere Lambda: Button freigeben + Protokoll abschliessen."""
        self.btn_load_json.setEnabled(True)
        if self.meas_log:
            try:
                self.meas_log.set(ende_messung=datetime.now().strftime("%H-%M"))
                self.log(f">> Messprotokoll gespeichert: {self.meas_log.path_txt}")
            except Exception as e:
                self.log(f"!! Protokoll-Abschluss fehlgeschlagen: {e}")

    def handle_log_event(self, ev):
        """Nimmt Ereignisse des Interpreters (z.B. Checkpoint-Antworten) ins Protokoll auf."""
        if not self.meas_log:
            return
        try:
            ev = dict(ev)
            self.meas_log.event(ev.pop("type", "event"), **ev)
        except Exception as e:
            self.log(f"!! Protokoll-Eintrag fehlgeschlagen: {e}")

    def handle_log_input(self, key, mode, msg, abort_on_no):
        """log_checkpoint: erfasst eine Bedingung (Ja/Nein) oder eine Freitext-Notiz."""
        proceed = True
        value = None
        try:
            if mode == "text":
                text, ok = QInputDialog.getText(self, "Notiz fuer das Messprotokoll", msg)
                value = text.strip() if ok else None
                # Abbrechen heisst hier nur "keine Notiz" - die Messung laeuft weiter.
            else:
                reply = QMessageBox.question(self, "Protokoll-Eintrag", msg,
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                value = (reply == QMessageBox.Yes)
                if abort_on_no and not value:
                    proceed = False

            if self.meas_log and value is not None:
                self.meas_log.condition(key, value)
                self.meas_log.event("log_checkpoint", key=key, wert=value, msg=msg)
            self.log(f">> Protokoll: {key} = {value}")
        except Exception as e:
            self.log(f"!! Fehler beim Protokoll-Eintrag: {e}")

        self.interpreter.confirm_prompt(proceed)

    def handle_etds_timestamp(self, point_id, deflection, couch_angle, msg):
        """Fragt den ExacTrac-Zeitstempel ab und haengt einen Eintrag ans Config-File."""
        dlg = EtdsTimestampDialog(point_id, deflection, couch_angle, msg, self.surf_timestamp, self)
        if dlg.exec() != QDialog.Accepted:
            self.log("!! ETDS-Timestamp-Eingabe abgebrochen.")
            self.interpreter.confirm_prompt(False)
            return

        ts = dlg.get_timestamp()
        entry = {
            "Linac": str(self.session.get("linac", "")),
            "deflection": int(deflection),
            "meas_couch_type": str(self.session.get("meas_couch_type", "single angle")),
            "heatingpads": str(self.session.get("heatingpads", "OFF")),
            "etds_timestamp": ts,
            "surf_timestamp": self.surf_timestamp or "",
            "couch_angle": int(couch_angle),
        }

        key = None
        try:
            key = self.qa_config.append_entry(entry)
            self.log(f">> Config-Eintrag [{key}]: deflection {deflection}, couch {couch_angle} deg, "
                     f"ETDS {ts}, CSV {entry['surf_timestamp'] or '(fehlt noch)'}")
            if not self.surf_timestamp:
                self.log("!! WARNUNG: Logging laeuft noch nicht - surf_timestamp wird nachgetragen.")
        except Exception as e:
            # Eine teure Messung darf an einem Datei-Fehler nicht scheitern.
            self.log(f"!! FEHLER beim Schreiben der Config: {e} (Messung laeuft weiter!)")

        if self.meas_log:
            try:
                if key:
                    self.meas_log.config_entry(key, entry)
                self.meas_log.event("etds_timestamp", point_id=point_id, deflection=int(deflection),
                                    couch_angle=int(couch_angle), etds_timestamp=ts, config_key=key)
            except Exception:
                pass

        self.interpreter.confirm_prompt(True)

    def handle_prompt(self, title, msg):
        # Zeigt einen Dialog mit Yes und No Button
        reply = QMessageBox.question(
            self, title, msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if hasattr(self, 'interpreter'):
            # True bei 'Yes', False bei 'No'
            self.interpreter.confirm_prompt(reply == QMessageBox.Yes)

    def handle_blueprint_logging(self, action, prefix):
        if action == "start":
            if state.is_logging: return

            # Zeitstempel beim START fixieren
            self.current_m_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.measurement_start_ref = time.perf_counter()
            # Hier nutzen wir das 'prefix' aus der JSON-Datei
            fname = f"{prefix}_{self.current_m_timestamp}.csv"

            # NEU: Pfad für die zugehörige QA-Datei definieren (gleicher Timestamp!)
            date_str = datetime.now().strftime('%Y-%m-%d')
            self.qa_csv_filepath = os.path.join("data", date_str, f"{prefix}_{self.current_m_timestamp}_QA.csv")

            # Schreibe den Header für die QA CSV direkt beim Start
            os.makedirs(os.path.dirname(self.qa_csv_filepath), exist_ok=True)
            with open(self.qa_csv_filepath, 'w', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(
                    ["Time_Sec", "Point_ID", "Mode", "H_pos", "V_pos", "R_pos", "Sphere_X", "Sphere_Y", "Sphere_Z",
                     "Surf_X", "Surf_Y", "Surf_Z", "Pitch", "Yaw", "Roll"])

            with state.lock:
                state.is_logging = True
            self.logger_thread = LoggerThread(fname, start_ref=self.measurement_start_ref)
            self.logger_thread.start()

            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.log(f"LOGGING VIA BLUEPRINT GESTARTET: {fname}")

            # --- NEU: CSV-Zeitstempel merken (= surf_timestamp der Auswertung) ---
            self.surf_timestamp = self.current_m_timestamp.split('_')[-1]
            self.log(f">> surf_timestamp der Messung: {self.surf_timestamp}")
            if self.meas_log:
                self.meas_log.set(csv_file=fname, surf_timestamp=self.surf_timestamp)
                self.meas_log.event("logging", action="start", datei=fname)
            if self.qa_config:
                # Falls Eintraege schon vor dem Logging-Start entstanden sind
                patched = self.qa_config.patch_surf_timestamp(self.surf_timestamp)
                if patched:
                    self.log(f">> surf_timestamp in Config-Eintraege {patched} nachgetragen.")

        elif action == "stop":
            if self.meas_log:
                self.meas_log.event("logging", action="stop", datei=self.qa_csv_filepath or "")
            # Wir rufen einfach die obige stop-Logik auf, die speichert dann auch den Plot
            self.handle_logging("stop")

    def handle_qa_input(self, mode, point_id, msg):
        """Öffnet den Dialog und speichert die Daten in die QA-CSV"""
        dialog = QAInputDialog(mode, point_id, msg, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()

            # 1. Daten in die Datei schreiben
            if self.qa_csv_filepath:
                cur_t = round(time.perf_counter() - self.measurement_start_ref, 3)
                # Aktuelle physikalische Achsenpositionen holen
                with state.lock:
                    ph, pv, pr = state.pos['h'], state.pos['v'], state.pos['r']

                with open(self.qa_csv_filepath, 'a', newline='') as f:
                    writer = csv.writer(f, delimiter=';')
                    # Sicheres Auslesen der Keys (leerer String falls nicht vorhanden)
                    writer.writerow([
                        cur_t, point_id, mode, ph, pv, pr,
                        data.get('x', ''), data.get('y', ''), data.get('z', ''),
                        data.get('x', '') if mode == 'surface_tracking' else '',
                        # Logik um zwischen Sphere und Tracking Spalten zu trennen
                        data.get('y', '') if mode == 'surface_tracking' else '',
                        data.get('z', '') if mode == 'surface_tracking' else '',
                        data.get('pitch', ''), data.get('yaw', ''), data.get('roll', '')
                    ])

            # NEU: Sphere Detection zusaetzlich im Messprotokoll vermerken
            if self.meas_log:
                try:
                    self.meas_log.event("qa_input", point_id=point_id, mode=mode, werte=data)
                except Exception:
                    pass

            # 2. Dem Interpreter sagen, dass es weitergehen kann
            self.interpreter.confirm_prompt(True)
        else:
            if self.meas_log:
                try:
                    self.meas_log.event("qa_input", point_id=point_id, mode=mode, werte="ABGEBROCHEN")
                except Exception:
                    pass
            # Bei Abbruch den Blueprint stoppen
            self.interpreter.confirm_prompt(False)

    def closeEvent(self, event):
        """Wird aufgerufen, wenn das Fenster geschlossen wird."""
        self.log("Beende Anwendung... Warte auf Threads.")

        # Sicheres Sammeln aller aktiven Threads
        threads_to_stop = [self.axis_thread, self.heat_thread]

        if self.logger_thread:
            threads_to_stop.append(self.logger_thread)

        if hasattr(self, 'interpreter'):
            threads_to_stop.append(self.interpreter)

        for t in threads_to_stop:
            if t and t.isRunning():
                t.stop()  # Flag auf False setzen
                t.wait()  # BLOCKIERT, bis der Thread wirklich fertig ist (WICHTIG!)

        event.accept()  # Fenster darf jetzt wirklich zugehen

    def update_ui(self):
        with state.lock:
            ph, pv, pr = state.pos['h'], state.pos['v'], state.pos['r']
            ta, tb = state.temp['a'], state.temp['b']
            sa, sb = state.stable['a'], state.stable['b']
            rdy = state.axis_ready

            # --- FEEDBACK STABILITÄT ---
            if sa and not state.stable_reported['a']:
                self.log(f"*** ZIEL ERREICHT: Heizpad A stabil ({ta:.2f}°C) ***")
                state.stable_reported['a'] = True
            elif not sa and abs(ta - state.setpoint['a']) > 0.5:
                state.stable_reported['a'] = False

            if sb and not state.stable_reported['b']:
                self.log(f"*** ZIEL ERREICHT: Heizpad B stabil ({tb:.2f}°C) ***")
                state.stable_reported['b'] = True
            elif not sb and abs(tb - state.setpoint['b']) > 0.5:
                state.stable_reported['b'] = False

        # Status Label Update
        ready_col = "#2ecc71" if rdy else "#e67e22"  # Green / Orange
        stab_a = "<font color='#2ecc71'>STABIL</font>" if sa else "<font color='#e74c3c'>...</font>"
        stab_b = "<font color='#2ecc71'>STABIL</font>" if sb else "<font color='#e74c3c'>...</font>"
        rec_txt = "<font color='red'>[REC]</font> " if state.is_logging else ""

        self.status_lbl.setText(
            f"{rec_txt}ACHSEN: H:{ph:5.1f} V:{pv:5.1f} R:{pr:5.1f} | <font color='{ready_col}'>{'BEREIT' if rdy else 'BEWEGT'}</font><br>"
            f"TEMP A: {ta:5.2f}°C ({stab_a}) | TEMP B: {tb:5.2f}°C ({stab_b})"
        )

        # Plot Update
        cur_t = time.time() - self.start_t
        self.t_data.append(cur_t)
        self.ta_data.append(ta)
        self.tb_data.append(tb)

        if len(self.t_data) % 5 == 0:  # Nicht jeden Cycle zeichnen
            self.ax.clear()
            self.ax.grid(alpha=0.3)
            self.ax.plot(self.t_data, self.ta_data, 'r-', label='Pad A', linewidth=1.5)
            self.ax.plot(self.t_data, self.tb_data, 'b-', label='Pad B', linewidth=1.5)

            # Soll-Linien
            with state.lock:
                spa, spb = state.setpoint['a'], state.setpoint['b']
            self.ax.axhline(y=spa, color='r', linestyle=':', alpha=0.5)
            self.ax.axhline(y=spb, color='b', linestyle=':', alpha=0.5)

            self.ax.legend(loc='upper left', fontsize='small', facecolor='#222', labelcolor='white')
            self.ax.set_xlabel("Zeit [s]", color='white')
            self.ax.set_ylabel("Temp [°C]", color='white')
            self.canvas.draw()


def main():
    """Entry point. Behaviour is identical to running this module as a script."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
