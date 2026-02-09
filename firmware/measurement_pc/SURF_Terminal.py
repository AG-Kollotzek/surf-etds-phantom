import sys
import time
import queue
import threading
from collections import deque
from datetime import datetime
import serial

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QTextEdit, QMessageBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ================= KONFIGURATION =================
AXIS_PORT = "/dev/cu.usbserial-120"
HEAT_PORT = "/dev/cu.usbserial-140"
BAUD_RATE = 115200

LIMITS = {'h': (0, 150), 'v': (0, 100), 'r': (-180, 180)}
STEPS_PER_MM = 800.0
STEPS_PER_DEG = 16.156


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


class SystemState:
    def __init__(self):
        self.lock = threading.Lock()
        self.pos = {'h': 0.0, 'v': 0.0, 'r': 0.0}
        self.axis_ready = True
        self.homing_active = False  # Sperre für andere Befehle
        self.last_cmd_time = 0
        self.temp = {'a': 0.0, 'b': 0.0}
        self.setpoint = {'a': 25.0, 'b': 25.0}
        self.stable = {'a': False, 'b': False}
        self.temp_history_a = deque(maxlen=20)
        self.temp_history_b = deque(maxlen=20)


state = SystemState()


# Helper zum Senden
def write_i8(ser, v): ser.write(int(v).to_bytes(1, 'little', signed=True))


def write_i32(ser, v): ser.write(int(v).to_bytes(4, 'little', signed=True))


def read_i8(ser): return int.from_bytes(ser.read(1), 'little', signed=True)


def read_i32(ser): return int.from_bytes(ser.read(4), 'little', signed=True)


class AxisThread(threading.Thread):
    def __init__(self, port, cmd_queue, log_callback):
        super().__init__(daemon=True)
        self.port, self.cmd_queue, self.log = port, cmd_queue, log_callback

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.05)
            time.sleep(2)
            ser.reset_input_buffer()
            self.log("INFO: Achsen-Arduino bereit.")

            while True:
                # Watchdog für Deadlocks (15s für langes Homing)
                with state.lock:
                    if not state.axis_ready and (time.time() - state.last_cmd_time > 15.0):
                        state.axis_ready = True
                        state.homing_active = False
                        self.log("WARNUNG: Timeout - Achse wieder freigegeben.")

                # 1. Empfangen
                if ser.in_waiting >= 1:
                    hdr = read_i8(ser)
                    if hdr == AxisOrder.LOG_DATA:
                        if ser.in_waiting >= 13:
                            _ = read_i32(ser)
                            rh = read_i32(ser);
                            rv = read_i32(ser);
                            rr = read_i32(ser)
                            _stat = read_i8(ser)
                            with state.lock:
                                state.pos['h'], state.pos['v'], state.pos[
                                    'r'] = rh / STEPS_PER_MM, rv / STEPS_PER_MM, rr / STEPS_PER_DEG
                    elif hdr == AxisOrder.COMMAND_DONE:
                        with state.lock:
                            state.axis_ready = True
                            state.homing_active = False
                        self.log("STATUS: Arduino meldet 'Befehl ausgeführt'.")

                # 2. Senden
                can_send = False
                with state.lock:
                    can_send = state.axis_ready

                if can_send and not self.cmd_queue.empty():
                    cmd, args, txt = self.cmd_queue.get()
                    try:
                        write_i8(ser, cmd)
                        for a in args:
                            if cmd in [AxisOrder.MOVE_AXIS, AxisOrder.HOME_AXIS] and args.index(a) == 0:
                                write_i8(ser, a)  # Axis ID
                            else:
                                write_i32(ser, a)  # Payload

                        with state.lock:
                            state.axis_ready = False
                            state.last_cmd_time = time.time()
                        self.log(f"CMD -> {txt}")
                    except Exception as e:
                        self.log(f"FEHLER beim Senden: {e}")

                time.sleep(0.01)
        except Exception as e:
            self.log(f"KRITISCH: AxisThread Error: {e}")


class HeatThread(threading.Thread):
    def __init__(self, port, cmd_queue, log_callback):
        super().__init__(daemon=True)
        self.port, self.cmd_queue, self.log = port, cmd_queue, log_callback

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.05)
            time.sleep(2);
            ser.reset_input_buffer()
            self.log("INFO: Heizungs-Arduino bereit.")

            while True:
                if ser.in_waiting >= 1:
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
                                for p in ['a', 'b']:
                                    hist = state.temp_history_a if p == 'a' else state.temp_history_b
                                    if len(hist) == 20:
                                        state.stable[p] = max([abs(x - state.setpoint[p]) for x in hist]) <= 0.2
                                    else:
                                        state.stable[p] = False

                while not self.cmd_queue.empty():
                    p_idx, val, txt = self.cmd_queue.get()
                    write_i8(ser, p_idx);
                    write_i32(ser, int(val * 100))
                    with state.lock: state.setpoint['a' if p_idx == 1 else 'b'] = val
                    self.log(f"CMD -> {txt}")
                time.sleep(0.05)
        except Exception as e:
            self.log(f"KRITISCH: HeatThread Error: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Projekt Assistent ETD QA - Unified Terminal V3")
        self.resize(1200, 750)
        self.axis_q = queue.Queue();
        self.heat_q = queue.Queue()
        self.t_data, self.ta_data, self.tb_data = [], [], []
        self.start_t = time.time()
        self.setup_ui()

        AxisThread(AXIS_PORT, self.axis_q, self.log).start()
        HeatThread(HEAT_PORT, self.heat_q, self.log).start()

        self.timer = QTimer();
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(100)

    def setup_ui(self):
        cw = QWidget();
        self.setCentralWidget(cw);
        layout = QHBoxLayout(cw)
        left = QVBoxLayout()
        self.status_lbl = QLabel("Warte auf Verbindung...");
        self.status_lbl.setStyleSheet("font-size: 14px; font-weight: bold; background: #EEE; padding: 10px;")
        left.addWidget(self.status_lbl)

        self.console = QTextEdit();
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background: #000; color: #0f0; font-family: 'Consolas'; font-size: 11px;")
        left.addWidget(self.console)

        self.cmd_line = QLineEdit();
        self.cmd_line.setPlaceholderText("Befehl eingeben (z.B. 'h all' oder 'm h 50 10')...")
        self.cmd_line.setStyleSheet("height: 30px; font-size: 14px;")
        self.cmd_line.returnPressed.connect(self.parse_input)
        left.addWidget(self.cmd_line)

        layout.addLayout(left, 1)
        self.fig = Figure(facecolor='#111');
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111);
        self.ax.set_facecolor('#000')
        self.ax.tick_params(colors='gray');
        self.ax.grid(alpha=0.2)
        layout.addWidget(self.canvas, 2)

    def log(self, msg):
        self.console.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def parse_input(self):
        text = self.cmd_line.text().strip().lower()
        self.cmd_line.clear()
        p = text.split()
        if not p: return

        # Homing-Sperre prüfen
        with state.lock:
            if state.homing_active:
                self.log("INFO: Bitte warten, Homing läuft noch.")
                return

        try:
            # === HOMING ===
            if p[0] == 'h':
                target = p[1] if len(p) > 1 else 'all'

                # Sicherheitsabfrage R-Achse
                if target in ['r', 'all']:
                    msg = "Homing R: Sind alle Kabel frei und ist eine Rotation sicher?"
                    reply = QMessageBox.question(self, 'Sicherheitscheck', msg, QMessageBox.Yes | QMessageBox.No)
                    if reply == QMessageBox.No:
                        self.log("INFO: Homing abgebrochen.")
                        return

                if target == 'all':
                    self.log("PROZESS: Starte sequentielles Homing (H -> V -> R)...")
                    with state.lock:
                        state.homing_active = True
                    self.axis_q.put((AxisOrder.HOME_AXIS, [0], "Homing H: Suche Endschalter..."))
                    self.axis_q.put((AxisOrder.HOME_AXIS, [1], "Homing V: Suche Endschalter..."))
                    self.axis_q.put((AxisOrder.HOME_AXIS, [2], "Homing R: Nullpunkt setzen."))
                else:
                    ax_id = {'h': 0, 'v': 1, 'r': 2}.get(target)
                    if ax_id is not None:
                        with state.lock: state.homing_active = True
                        self.log(f"BEFEHL: Homing für Achse {target.upper()} gestartet.")
                        self.axis_q.put((AxisOrder.HOME_AXIS, [ax_id], f"Homing {target.upper()} läuft..."))

            # === MOVE ===
            elif p[0] == 'm' and len(p) == 4:
                ax_char = p[1]
                target = float(p[2])
                speed = float(p[3])

                # Validierung
                min_val, max_val = LIMITS.get(ax_char, (0, 0))
                if not (min_val <= target <= max_val):
                    self.log(f"FEHLER: {ax_char.upper()} Ziel {target} außerhalb Bereich ({min_val}-{max_val})")
                    return

                ax_id = {'h': 0, 'v': 1, 'r': 2}[ax_char]
                factor = STEPS_PER_DEG if ax_id == 2 else STEPS_PER_MM

                self.log(f"BEFEHL: {ax_char.upper()} auf {target} mit {speed} mm/s (°) erkannt.")
                self.axis_q.put((AxisOrder.MOVE_AXIS, [ax_id, int(target * factor), int(speed * factor)],
                                 f"Fahre {ax_char.upper()}..."))

            # === STOP ===
            elif p[0] == 's':
                self.log("!!! NOT-STOPP: Alle Motoren werden angehalten !!!")
                self.axis_q.put((AxisOrder.STOP_ALL, [], "Stopp-Signal gesendet."))

        except Exception as e:
            self.log(f"FEHLER: Syntax falsch oder Wert ungültig. (Typ: {e})")

    def update_ui(self):
        with state.lock:
            ph, pv, pr = state.pos['h'], state.pos['v'], state.pos['r']
            ta, tb = state.temp['a'], state.temp['b']
            sa, sb = state.stable['a'], state.stable['b']
            rdy = state.axis_ready
            h_active = state.homing_active

        col = "orange" if h_active else ("lime" if rdy else "yellow")
        status = "HOMING" if h_active else ("BEREIT" if rdy else "IN BEWEGUNG")

        self.status_lbl.setText(
            f"SYSTEM: <font color='{col}'>{status}</font> | "
            f"H: {ph:5.1f} | V: {pv:5.1f} | R: {pr:5.1f}<br>"
            f"HEIZUNG: A: {ta:5.2f}°C ({'OK' if sa else '..'}) | B: {tb:5.2f}°C ({'OK' if sb else '..'})"
        )

        cur_t = time.time() - self.start_t
        self.t_data.append(cur_t);
        self.ta_data.append(ta);
        self.tb_data.append(tb)
        if len(self.t_data) % 20 == 0:
            self.ax.clear();
            self.ax.grid(alpha=0.3)
            self.ax.plot(self.t_data, self.ta_data, 'r-', label='Pad A')
            self.ax.plot(self.t_data, self.tb_data, 'b-', label='Pad B')
            self.ax.set_xlim(0, max(120, cur_t + 10))
            self.ax.set_ylim(20, 55);
            self.canvas.draw()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow();
    window.show();
    sys.exit(app.exec())