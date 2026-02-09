import sys
import time
import queue
import threading
from collections import deque
from datetime import datetime
import serial
import numpy as np

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QTextEdit
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ================= KONFIGURATION & LIMITS =================
AXIS_PORT = "/dev/cu.usbserial-120"
HEAT_PORT = "/dev/cu.usbserial-140"
BAUD_RATE = 115200

# Physikalische Grenzen (Anpassen an deine Mechanik!)
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

        # Stability Buffers (20 Sek bei ~1Hz Log-Rate)
        self.temp_history_a = deque(maxlen=20)
        self.temp_history_b = deque(maxlen=20)


state = SystemState()


# ================= BINARY HELPERS =================
def write_i8(ser, v): ser.write(int(v).to_bytes(1, 'little', signed=True))


def write_i32(ser, v): ser.write(int(v).to_bytes(4, 'little', signed=True))


def read_i8(ser): return int.from_bytes(ser.read(1), 'little', signed=True)


def read_i32(ser): return int.from_bytes(ser.read(4), 'little', signed=True)


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
            self.log(f"Achsen-Arduino verbunden.")

            while True:
                # Watchdog: Falls CMD_DONE verloren ging, nach 10s resetten
                with state.lock:
                    if not state.axis_ready and (time.time() - state.last_cmd_time > 10.0):
                        state.axis_ready = True
                        self.log("!! Watchdog: Axis Ready Reset !!")

                # 1. Lesen
                if ser.in_waiting >= 1:
                    hdr = read_i8(ser)
                    if hdr == AxisOrder.LOG_DATA:
                        if ser.in_waiting >= 13:  # Time(4) + 3*Pos(4) + Stat(1)
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
                        self.log(">> Achse: Bewegung abgeschlossen.")

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
                                write_i8(ser, a)
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
            self.log(f"AXIS CRITICAL: {e}")


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
            self.log("Heizung verbunden.")

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

                                # Stability Check: 20 Samples, Abweichung < 0.2
                                for p in ['a', 'b']:
                                    hist = state.temp_history_a if p == 'a' else state.temp_history_b
                                    if len(hist) == 20:
                                        diff = [abs(x - state.setpoint[p]) for x in hist]
                                        state.stable[p] = max(diff) <= 0.2
                                    else:
                                        state.stable[p] = False

                while not self.cmd_queue.empty():
                    p_idx, val = self.cmd_queue.get()
                    write_i8(ser, p_idx);
                    write_i32(ser, int(val * 100))
                    with state.lock: state.setpoint['a' if p_idx == 1 else 'b'] = val

                time.sleep(0.05)
        except Exception as e:
            self.log(f"HEAT CRITICAL: {e}")


# ================= GUI =================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ETD QA Terminal V2 - ESTRO/SGRT")
        self.resize(1100, 700)
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

        # Left Panel (Controls)
        left = QVBoxLayout()
        self.status_lbl = QLabel("Initialisiere...");
        self.status_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.status_lbl.setFrameStyle(QFrame.StyledPanel)
        left.addWidget(self.status_lbl)

        self.console = QTextEdit();
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background: #111; color: #0f0; font-family: 'Courier New';")
        left.addWidget(self.console)

        self.cmd_line = QLineEdit();
        self.cmd_line.setPlaceholderText("Befehl hier (z.B. m h 50 10)")
        self.cmd_line.returnPressed.connect(self.parse_input)
        left.addWidget(self.cmd_line)

        layout.addLayout(left, 1)

        # Right Panel (Plot)
        self.fig = Figure(facecolor='#222');
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111);
        self.ax.set_facecolor('#111')
        self.ax.tick_params(colors='white');
        self.ax.grid(alpha=0.2)
        layout.addWidget(self.canvas, 2)

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console.append(f"[{ts}] {msg}")

    def parse_input(self):
        text = self.cmd_line.text().strip().lower();
        self.cmd_line.clear()
        p = text.split()
        if not p: return

        try:
            # MOVEMENT: m [h/v/r] [pos] [speed]
            if p[0] == 'm' and len(p) == 4:
                ax_char = p[1]
                if ax_char not in LIMITS: raise ValueError(f"Achse '{ax_char}' unbekannt.")

                target = float(p[2]);
                speed = float(p[3])
                min_v, max_v = LIMITS[ax_char]

                if not (min_v <= target <= max_v):
                    self.log(f"!! LIMIT ERROR: {ax_char} Bereich ist {min_v} bis {max_v}")
                    return

                ax_id = {'h': 0, 'v': 1, 'r': 2}[ax_char]
                factor = STEPS_PER_DEG if ax_id == 2 else STEPS_PER_MM
                self.axis_q.put((AxisOrder.MOVE_AXIS, [ax_id, int(target * factor), int(speed * factor)]))
                self.log(f"Sende Move: {ax_char} auf {target}")

            # HOMING: h [h/v/r]
            elif p[0] == 'h' and len(p) == 2:
                ax_id = {'h': 0, 'v': 1, 'r': 2}.get(p[1])
                if ax_id is not None: self.axis_q.put((AxisOrder.HOME_AXIS, [ax_id]))

            # HEATING: t [a/b] [temp]
            elif p[0] == 't' and len(p) == 3:
                pad = 1 if p[1] == 'a' else 2
                val = float(p[2])
                if 10 <= val <= 50:
                    self.heat_q.put((pad, val))
                else:
                    self.log("!! TEMP LIMIT: Bereich 10-50°C")

            else:
                self.log("!! SYNTAX: m [h/v/r] [pos] [spd] | h [h/v/r] | t [a/b] [temp]")
        except Exception as e:
            self.log(f"Fehler: {e}")

    def update_ui(self):
        with state.lock:
            ph, pv, pr = state.pos['h'], state.pos['v'], state.pos['r']
            ta, tb = state.temp['a'], state.temp['b']
            sa, sb = state.stable['a'], state.stable['b']
            rdy = state.axis_ready

        # Status Label
        ready_col = "lime" if rdy else "orange"
        stab_a = "DONE" if sa else "..."
        stab_b = "DONE" if sb else "..."

        self.status_lbl.setText(
            f"ACHSEN: H:{ph:5.1f} V:{pv:5.1f} R:{pr:5.1f} | <font color='{ready_col}'>{'BEREIT' if rdy else 'BEWEGT'}</font><br>"
            f"TEMP A: {ta:5.2f}°C ({stab_a}) | TEMP B: {tb:5.2f}°C ({stab_b})"
        )

        # Plot Update (Cumulative)
        cur_t = time.time() - self.start_t
        self.t_data.append(cur_t);
        self.ta_data.append(ta);
        self.tb_data.append(tb)

        if len(self.t_data) % 10 == 0:
            self.ax.clear();
            self.ax.grid(alpha=0.3)
            self.ax.plot(self.t_data, self.ta_data, 'r-', label='Pad A', linewidth=1)
            self.ax.plot(self.t_data, self.tb_data, 'b-', label='Pad B', linewidth=1)
            self.ax.set_xlabel("Zeit [s]", color='white');
            self.ax.set_ylabel("Temp [°C]", color='white')
            self.ax.set_xlim(0, max(60, cur_t + 5))  # X-Achse startet immer bei 0
            self.ax.set_ylim(20, 55)
            self.canvas.draw()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow();
    window.show()
    sys.exit(app.exec())