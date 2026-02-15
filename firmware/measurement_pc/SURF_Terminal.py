import sys
import time
import queue
import threading
import csv
import os
from collections import deque
from datetime import datetime
import serial

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QTextEdit, QPushButton, QGridLayout, QMessageBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ================= KONFIGURATION & LIMITS =================
AXIS_PORT = "/dev/cu.usbserial-120"
HEAT_PORT = "/dev/cu.usbserial-140"
BAUD_RATE = 115200

# Physikalische Grenzen
LIMITS = {
    'h': (-35, 35),  # mm
    'v': (-35, 50),  # mm
    'r': (-45, 45)  # Grad
}

STEPS_PER_MM = 800.0
STEPS_PER_DEG = 16.156


# ================= PROTOKOLL DEFINITIONEN =================
class AxisOrder:
    LOG_DATA = 10
    MOVE_AXIS = 1
    HOME_AXIS = 2
    STOP_ALL = 3
    COMMAND_DONE = 4


class HeatOrder:
    LOG_DATA = 10
    SET_A = 1
    SET_B = 2


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
        self.temp_history_a = deque(maxlen=20)
        self.temp_history_b = deque(maxlen=20)

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
    def __init__(self, filename, interval=0.5):
        super().__init__(daemon=True)
        self.filename = filename
        self.interval = interval
        self.running = True
        self.start_time = time.time()

    def run(self):
        # Ordner erstellen falls nicht vorhanden
        os.makedirs("messdaten", exist_ok=True)
        filepath = os.path.join("messdaten", self.filename)

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
                now = time.time() - self.start_time
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
class AxisThread(threading.Thread):
    def __init__(self, port, cmd_queue, log_callback):
        super().__init__(daemon=True)
        self.port, self.cmd_queue, self.log = port, cmd_queue, log_callback

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.05)
            time.sleep(2)
            ser.reset_input_buffer()
            self.log(f"Achsen-Arduino verbunden ({self.port}).")

            while True:
                # Watchdog
                with state.lock:
                    if not state.axis_ready and (time.time() - state.last_cmd_time > 15.0):
                        state.axis_ready = True
                        self.log("!! Watchdog: Axis Ready Reset (Timeout) !!")

                # 1. Lesen
                if ser.in_waiting >= 1:
                    try:
                        hdr = read_i8(ser)
                        if hdr == AxisOrder.LOG_DATA:
                            if ser.in_waiting >= 13:
                                _ = read_i32(ser)
                                rh = read_i32(ser);
                                rv = read_i32(ser);
                                rr = read_i32(ser)
                                _stat = read_i8(ser)
                                with state.lock:
                                    state.pos['h'], state.pos['v'], state.pos['r'] = \
                                        rh / STEPS_PER_MM, rv / STEPS_PER_MM, rr / STEPS_PER_DEG
                        elif hdr == AxisOrder.COMMAND_DONE:
                            with state.lock:
                                state.axis_ready = True
                            self.log(">> Achse: Bewegung abgeschlossen.")
                    except Exception as e:
                        print(f"Serial Read Error: {e}")

                # 2. Senden
                can_send = False
                with state.lock:
                    can_send = state.axis_ready

                if can_send and not self.cmd_queue.empty():
                    cmd, args = self.cmd_queue.get()
                    try:
                        write_i8(ser, cmd)
                        for a in args:
                            if cmd == AxisOrder.MOVE_AXIS and args.index(a) == 0:
                                write_i8(ser, a)  # Axis ID ist Byte
                            else:
                                write_i32(ser, a)

                        if cmd in [AxisOrder.MOVE_AXIS, AxisOrder.HOME_AXIS]:
                            with state.lock:
                                state.axis_ready = False
                                state.last_cmd_time = time.time()
                    except Exception as e:
                        self.log(f"Axis Error: {e}")

                time.sleep(0.01)
        except Exception as e:
            self.log(f"AXIS CRITICAL: {e} (Port prüfen!)")


# ================= WORKER: HEIZUNG =================
class HeatThread(threading.Thread):
    def __init__(self, port, cmd_queue, log_callback):
        super().__init__(daemon=True)
        self.port, self.cmd_queue, self.log = port, cmd_queue, log_callback

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.05)
            time.sleep(2)
            ser.reset_input_buffer()
            self.log(f"Heizung verbunden ({self.port}).")

            while True:
                # Lesen
                if ser.in_waiting >= 1:
                    try:
                        hdr = read_i8(ser)
                        if hdr == HeatOrder.LOG_DATA:
                            if ser.in_waiting >= 12:
                                _ = read_i32(ser);
                                ra = read_i32(ser);
                                rb = read_i32(ser)
                                with state.lock:
                                    state.temp['a'], state.temp['b'] = ra / 100.0, rb / 100.0
                                    state.temp_history_a.append(state.temp['a'])
                                    state.temp_history_b.append(state.temp['b'])

                                    # Stability Check
                                    for p in ['a', 'b']:
                                        hist = state.temp_history_a if p == 'a' else state.temp_history_b
                                        if len(hist) == 20:
                                            diff = [abs(x - state.setpoint[p]) for x in hist]
                                            is_stable = max(diff) <= 0.2
                                            state.stable[p] = is_stable
                                        else:
                                            state.stable[p] = False
                    except Exception as e:
                        print(f"Heat Read Error: {e}")

                # Senden
                while not self.cmd_queue.empty():
                    p_idx, val = self.cmd_queue.get()
                    try:
                        write_i8(ser, p_idx)
                        write_i32(ser, int(val * 100))
                        with state.lock:
                            state.setpoint['a' if p_idx == 1 else 'b'] = val
                            state.stable_reported['a' if p_idx == 1 else 'b'] = False  # Reset Meldung
                    except Exception as e:
                        self.log(f"Heat Send Error: {e}")

                time.sleep(0.05)
        except Exception as e:
            self.log(f"HEAT CRITICAL: {e} (Port prüfen!)")


# ================= GUI =================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ETD QA Terminal V3 - Full Integration")
        self.resize(1200, 800)

        self.axis_q = queue.Queue()
        self.heat_q = queue.Queue()
        self.logger_thread = None

        self.t_data, self.ta_data, self.tb_data = [], [], []
        self.start_t = time.time()

        self.setup_ui()

        # Threads starten
        AxisThread(AXIS_PORT, self.axis_q, self.log).start()
        HeatThread(HEAT_PORT, self.heat_q, self.log).start()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(100)

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
        heat_layout.addWidget(QLabel("<b>HEIZUNG SOLLWERTE</b>"))

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
            fname = f"messung_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with state.lock:
                state.is_logging = True
            self.logger_thread = LoggerThread(fname)
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

            # Screenshot speichern
            try:
                os.makedirs("messdaten", exist_ok=True)
                plot_name = os.path.join("messdaten", f"plot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
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

            # === LOGGING (CMD LINE) ===
            elif text == "start measurement":
                self.handle_logging("start")
            elif text == "stop measurement":
                self.handle_logging("stop")

            else:
                self.log("!! SYNTAX: m [h/v/r] [pos] [spd] | m zp | t [a/b] [temp] | start/stop measurement")
        except Exception as e:
            self.log(f"Fehler: {e}")

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
        self.t_data.append(cur_t);
        self.ta_data.append(ta);
        self.tb_data.append(tb)

        # Puffer begrenzen für Performance (letzte 1000 Punkte)
        if len(self.t_data) > 1000:
            self.t_data.pop(0);
            self.ta_data.pop(0);
            self.tb_data.pop(0)

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())