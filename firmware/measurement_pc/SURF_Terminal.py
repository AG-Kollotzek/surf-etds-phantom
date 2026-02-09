import sys
import time
import queue
import threading
from datetime import datetime
import serial
import serial.tools.list_ports as list_ports

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QTextEdit
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ================= KONFIGURATION =================
AXIS_PORT = "/dev/cu.usbserial-120"
HEAT_PORT = "/dev/cu.usbserial-140"
BAUD_RATE = 115200

# Mechanik
STEPS_PER_MM = 800.0
STEPS_PER_DEG = 16.156


# ================= PROTOKOLL (BINÄR) =================
# Achsen (Bestehend)
class AxisOrder:
    LOG_DATA = 10
    MOVE_AXIS = 1
    HOME_AXIS = 2
    STOP_ALL = 3
    COMMAND_DONE = 4


# Heizung (NEU - Passend zur neuen Firmware)
class HeatOrder:
    LOG_DATA = 10  # [Header, Time(i32), TempA(i32), TempB(i32)]
    SET_A = 1  # [Header, Val(i32)]
    SET_B = 2  # [Header, Val(i32)]


class AxisID:
    H = 0;
    V = 1;
    R = 2


# ================= BINARY HELPERS =================
def write_i8(ser, v): ser.write(int(v).to_bytes(1, 'little', signed=True))


def write_i32(ser, v): ser.write(int(v).to_bytes(4, 'little', signed=True))


def read_i8(ser): return int.from_bytes(ser.read(1), 'little', signed=True)


def read_i32(ser): return int.from_bytes(ser.read(4), 'little', signed=True)


# ================= SHARED STATE =================
class SystemState:
    def __init__(self):
        self.lock = threading.Lock()
        # Achsen
        self.pos_h = 0.0;
        self.pos_v = 0.0;
        self.pos_r = 0.0
        self.axis_ready = True
        # Heizung
        self.temp_a = 0.0;
        self.temp_b = 0.0
        self.setpoint_a = 25.0;
        self.setpoint_b = 25.0


state = SystemState()


# ================= WORKER: ACHSEN =================
class AxisThread(threading.Thread):
    def __init__(self, port, cmd_queue, log_callback):
        super().__init__(daemon=True)
        self.port = port
        self.cmd_queue = cmd_queue
        self.log = log_callback

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.1)
            time.sleep(2);
            ser.reset_input_buffer()
            self.log(f"Achsen-Arduino verbunden: {self.port}")

            while True:
                # 1. Lesen
                if ser.in_waiting:
                    try:
                        hdr = read_i8(ser)
                        if hdr == AxisOrder.LOG_DATA:
                            _ = read_i32(ser)  # Time
                            rh = read_i32(ser);
                            rv = read_i32(ser);
                            rr = read_i32(ser)
                            stat = read_i8(ser)
                            with state.lock:
                                state.pos_h = rh / STEPS_PER_MM
                                state.pos_v = rv / STEPS_PER_MM
                                state.pos_r = rr / STEPS_PER_DEG
                        elif hdr == AxisOrder.COMMAND_DONE:
                            with state.lock:
                                state.axis_ready = True
                            self.log(">> Achse: DONE")
                    except:
                        pass

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
                                write_i8(ser, a)  # AxisID
                            else:
                                write_i32(ser, a)  # Steps/Speed

                        if cmd in [AxisOrder.MOVE_AXIS, AxisOrder.HOME_AXIS]:
                            with state.lock: state.axis_ready = False
                            self.log(f">> Sende Achsbefehl {cmd}")
                    except Exception as e:
                        self.log(f"Fehler Axis-Write: {e}")

                time.sleep(0.005)
        except Exception as e:
            self.log(f"AXIS ERROR: {e}")


# ================= WORKER: HEIZUNG (JETZT BINÄR) =================
class HeatThread(threading.Thread):
    def __init__(self, port, cmd_queue, log_callback):
        super().__init__(daemon=True)
        self.port = port
        self.cmd_queue = cmd_queue
        self.log = log_callback

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.1)
            time.sleep(2);
            ser.reset_input_buffer()
            self.log(f"Heizungs-Arduino verbunden (Binär): {self.port}")

            while True:
                # 1. Lesen
                if ser.in_waiting:
                    try:
                        hdr = read_i8(ser)
                        if hdr == HeatOrder.LOG_DATA:
                            _ = read_i32(ser)  # Time
                            raw_a = read_i32(ser)
                            raw_b = read_i32(ser)
                            with state.lock:
                                state.temp_a = raw_a / 100.0
                                state.temp_b = raw_b / 100.0
                    except:
                        pass

                # 2. Senden
                while not self.cmd_queue.empty():
                    pad_idx, val_float = self.cmd_queue.get()  # pad_idx: 1=A, 2=B
                    val_int = int(val_float * 100)  # Float -> Int (Centi-Degree)

                    try:
                        write_i8(ser, pad_idx)  # Header (1 oder 2)
                        write_i32(ser, val_int)  # Payload
                        self.log(f">> Heizung {('A' if pad_idx == 1 else 'B')} -> {val_float:.2f}°C")

                        with state.lock:
                            if pad_idx == 1:
                                state.setpoint_a = val_float
                            else:
                                state.setpoint_b = val_float
                    except Exception as e:
                        self.log(f"Fehler Heat-Write: {e}")

                time.sleep(0.01)
        except Exception as e:
            self.log(f"HEAT ERROR: {e}")


# ================= GUI =================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ETD QA Unified Terminal (Full Binary)")
        self.resize(900, 600)
        self.axis_q = queue.Queue()
        self.heat_q = queue.Queue()

        # Plot Data
        self.times = [];
        self.ta_hist = [];
        self.tb_hist = []
        self.start_t = time.time()

        self.setup_ui()

        # Threads starten
        AxisThread(AXIS_PORT, self.axis_q, self.log).start()
        HeatThread(HEAT_PORT, self.heat_q, self.log).start()

        self.timer = QTimer();
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(100)

    def setup_ui(self):
        w = QWidget();
        self.setCentralWidget(w);
        l = QHBoxLayout(w)
        left = QVBoxLayout()

        self.status = QLabel("Init...")
        self.status.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        left.addWidget(self.status)

        self.inp = QLineEdit();
        self.inp.setPlaceholderText("Befehl (h v, m h 10 5, t a 40)")
        self.inp.returnPressed.connect(self.parse_cmd)
        left.addWidget(self.inp)

        self.console = QTextEdit();
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background:#000; color:#0f0; font-family:monospace")
        left.addWidget(self.console)
        l.addLayout(left, 1)

        self.cv = FigureCanvas(Figure(figsize=(5, 4), facecolor='#2b2b2b'))
        self.ax = self.cv.figure.add_subplot(111);
        self.ax.set_facecolor('#1e1e1e')
        self.ax.tick_params(colors='white')
        l.addWidget(self.cv, 2)

    def log(self, t):
        print(t)  # Debug
        # In GUI Thread über Timer/Signal wäre sauberer, aber hier quick:
        self.console.append(t)

    def parse_cmd(self):
        txt = self.inp.text().strip().lower();
        self.inp.clear()
        parts = txt.split()
        if not parts: return

        cmd = parts[0]
        try:
            if cmd == 'm' and len(parts) >= 4:  # m h 10 5
                ax = {'h': 0, 'v': 1, 'r': 2}.get(parts[1])
                steps = int(float(parts[2]) * (STEPS_PER_DEG if ax == 2 else STEPS_PER_MM))
                spd = int(float(parts[3]) * (STEPS_PER_DEG if ax == 2 else STEPS_PER_MM))
                self.axis_q.put((AxisOrder.MOVE_AXIS, [ax, steps, spd]))
            elif cmd == 'h' and len(parts) >= 2:  # h v
                ax = {'h': 0, 'v': 1, 'r': 2}.get(parts[1])
                self.axis_q.put((AxisOrder.HOME_AXIS, [ax]))
            elif cmd == 't' and len(parts) >= 3:  # t a 40
                pad = 1 if parts[1] == 'a' else 2
                self.heat_q.put((pad, float(parts[2])))
            elif cmd == 's':
                self.axis_q.put((AxisOrder.STOP_ALL, []))
        except Exception as e:
            self.log(f"Cmd Err: {e}")

    def update_ui(self):
        with state.lock:
            ph, pv, pr = state.pos_h, state.pos_v, state.pos_r
            ta, tb = state.temp_a, state.temp_b
            rdy = state.axis_ready

        self.status.setText(
            f"AXIS: H{ph:.1f} V{pv:.1f} R{pr:.1f} [{'RDY' if rdy else 'MOV'}] | TEMP: A{ta:.2f} B{tb:.2f}")

        # Plot
        t = time.time() - self.start_t
        self.times.append(t);
        self.ta_hist.append(ta);
        self.tb_hist.append(tb)
        if len(self.times) > 100:
            self.times.pop(0);
            self.ta_hist.pop(0);
            self.tb_hist.pop(0)

        if len(self.times) % 5 == 0:
            self.ax.clear();
            self.ax.grid(alpha=0.2)
            self.ax.plot(self.times, self.ta_hist, 'r');
            self.ax.plot(self.times, self.tb_hist, 'b')
            self.cv.draw()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    MainWindow().show();
    sys.exit(app.exec())