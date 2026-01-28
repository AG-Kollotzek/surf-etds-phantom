import sys
import time
import queue
import threading
import csv
from datetime import datetime
import numpy as np
import pandas as pd
import serial
import serial.tools.list_ports as list_ports

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGridLayout, QFrame, QTextEdit, QMessageBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ================= CONFIGURATION =================
BAUD_RATE = 115200
LOG_RATE_HZ = 10  # 10Hz Logging
UI_REFRESH_MS = int(1000 / LOG_RATE_HZ)


class Order:
    HELLO = 0
    MOVE_AXIS = 1
    HOME_AXIS = 2
    SET_SETPOINT = 5
    HEATER_STOP = 6
    COMMAND_DONE = 4
    LOG_DATA = 10


class Axis:
    H = 0;
    V = 1;
    R = 2


# Mechanische Faktoren
STEPS_PER_MM = 800.0
STEPS_PER_DEG = 16.156


# ================= BINARY HELPERS =================
def write_i8(ser, v): ser.write(int(v).to_bytes(1, 'little', signed=True))


def write_i32(ser, v): ser.write(int(v).to_bytes(4, 'little', signed=True))


def read_i8(ser): return int.from_bytes(ser.read(1), 'little', signed=True)


def read_i32(ser): return int.from_bytes(ser.read(4), 'little', signed=True)


# ================= SYSTEM STATE =================
class SystemState:
    def __init__(self):
        self.pos_h = 0.0
        self.pos_v = 0.0
        self.pos_r = 0.0
        self.temp_a = 0.0
        self.temp_b = 0.0
        self.setpoint = 0.0
        self.heating_status = 0
        self.lock = threading.Lock()


state = SystemState()


# ================= WORKER THREADS =================
class AxisWorker(QObject):
    log_signal = Signal(str)

    def __init__(self, port, cmd_queue):
        super().__init__()
        self.port = port
        self.queue = cmd_queue
        self.running = True

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.1)
            time.sleep(2)
            self.log_signal.emit(f"Axis-Arduino an {self.port} bereit.")

            while self.running:
                if not self.queue.empty():
                    order_id, params = self.queue.get()
                    write_i8(ser, order_id)
                    for p in params:
                        # Unterscheidung i8/i32 für die Protokollstruktur
                        if abs(p) > 127:
                            write_i32(ser, p)
                        else:
                            write_i8(ser, p)

                    # Warten auf COMMAND_DONE
                    while True:
                        if ser.in_waiting > 0:
                            if read_i8(ser) == Order.COMMAND_DONE: break
                    self.queue.task_done()
                time.sleep(0.01)
        except Exception as e:
            self.log_signal.emit(f"Fehler Axis: {e}")


class HeatingWorker(QObject):
    def __init__(self, port, cmd_queue):  # Queue hinzugefügt
        super().__init__()
        self.port = port
        self.queue = cmd_queue
        self.running = True

    def run(self):
        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=0.1)
            time.sleep(2)
            while self.running:
                # 1. Befehle SENDEN (falls vorhanden)
                if not self.queue.empty():
                    order_id, val_int = self.queue.get()
                    write_i8(ser, order_id)
                    write_i32(ser, val_int)
                    self.queue.task_done()

                # 2. Daten EMPFANGEN
                if ser.in_waiting >= 1:
                    header = read_i8(ser)
                    if header == Order.LOG_DATA:
                        _ = read_i32(ser)  # millis ignorieren, wir nutzen Systemzeit
                        tA = read_i32(ser) / 100.0
                        tB = read_i32(ser) / 100.0
                        sp = read_i32(ser) / 100.0
                        stat = read_i8(ser)

                        with state.lock:
                            state.temp_a = tA
                            state.temp_b = tB
                            state.setpoint = sp
                            state.heating_status = stat
                time.sleep(0.01)
        except Exception as e:
            print(f"Fehler Heating: {e}")


# ================= GUI & PLOTTING =================
class MplCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(figsize=(5, 3), dpi=100, facecolor='#2b2b2b')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e1e')
        self.ax.tick_params(colors='white')
        self.ax.set_xlabel("Zeit [s]", color='white')
        self.ax.set_ylabel("Temp [°C]", color='white')
        super().__init__(self.fig)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ETD QA Unified Platform - 10Hz Log")
        self.cmd_queue = queue.Queue()

        # Plot-Daten Puffer
        self.plot_times = []
        self.plot_temp_a = []
        self.plot_temp_b = []
        self.start_time = time.time()

        self.init_ui()
        self.csv_filename = f"QA_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.init_csv()

        self.start_threads()

        # Zentraler Timer für UI-Refresh und 10Hz-Logging
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(UI_REFRESH_MS)

    def init_csv(self):
        with open(self.csv_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(
                ["Timestamp", "Elapsed_s", "TempA", "TempB", "Setpoint", "PosH", "PosV", "PosR", "HeaterStatus"])

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        self.canvas = MplCanvas()
        layout.addWidget(self.canvas)

        status_frame = QFrame()
        status_grid = QGridLayout(status_frame)
        self.lbl_temp = QLabel("Temp A: -- | Temp B: -- | Soll: --")
        self.lbl_pos = QLabel("Positionen: H: 0.0 | V: 0.0 | R: 0.0")
        status_grid.addWidget(self.lbl_temp, 0, 0)
        status_grid.addWidget(self.lbl_pos, 1, 0)
        layout.addWidget(status_frame)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #111; color: #0f0; font-family: monospace;")
        layout.addWidget(self.console)

        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Befehl (m h 20 10 / t 37 / h v)...")
        self.cmd_input.returnPressed.connect(self.handle_command)
        layout.addWidget(self.cmd_input)

    def start_threads(self):
        ports = [p.device for p in list_ports.comports()]
        if len(ports) >= 2:
            # HINWEIS: Portzuordnung muss ggf. getauscht werden
            self.axis_worker = AxisWorker(ports[0], self.cmd_queue)
            self.axis_thread = threading.Thread(target=self.axis_worker.run, daemon=True)
            self.axis_thread.start()

            self.heat_worker = HeatingWorker(ports[1])
            self.heat_thread = threading.Thread(target=self.heat_worker.run, daemon=True)
            self.heat_thread.start()
            self.log(f"System gestartet. Logging: 10Hz -> {self.csv_filename}")
        else:
            self.log("WARNUNG: Zu wenige Arduinos gefunden!")

    def tick(self):
        """ Zentraler 10Hz Herzschlag für Logging und UI """
        elapsed = time.time() - self.start_time

        with state.lock:
            tA, tB, sp = state.temp_a, state.temp_b, state.setpoint
            pH, pV, pR = state.pos_h, state.pos_v, state.pos_r
            stat = state.heating_status

        # 1. CSV Logging (10Hz)
        with open(self.csv_filename, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), round(elapsed, 2), tA, tB, sp, pH, pV, pR, stat])

        # 2. UI Updates
        self.lbl_temp.setText(f"Temp A: {tA:.2f}°C | Temp B: {tB:.2f}°C | Soll: {sp:.1f}°C")
        self.lbl_pos.setText(f"Positionen: H: {pH:.1f} | V: {pV:.1f} | R: {pR:.1f}")

        # 3. Plot Update (Wir plotten nur neue Punkte)
        if not self.plot_times or abs(elapsed - self.plot_times[-1]) > 0.5:
            self.plot_times.append(elapsed)
            self.plot_temp_a.append(tA)
            self.plot_temp_b.append(tB)

            if len(self.plot_times) > 100:  # Rolling window
                self.plot_times.pop(0);
                self.plot_temp_a.pop(0);
                self.plot_temp_b.pop(0)

            self.canvas.ax.clear()
            self.canvas.ax.plot(self.plot_times, self.plot_temp_a, 'r-', label='Pad A')
            self.canvas.ax.plot(self.plot_times, self.plot_temp_b, 'b-', label='Pad B')
            self.canvas.ax.legend()
            self.canvas.draw()

    def handle_command(self):
        text = self.cmd_input.text().strip().lower()
        self.cmd_input.clear()
        parts = text.split()
        if not parts: return

        try:
            if parts[0] == 'm' and len(parts) == 4:  # Move: m h 10 5
                ax_char = parts[1]
                target = float(parts[2])
                speed = float(parts[3])
                ax_id = Axis.H if ax_char == 'h' else (Axis.V if ax_char == 'v' else Axis.R)
                conv = STEPS_PER_DEG if ax_char == 'r' else STEPS_PER_MM

                self.cmd_queue.put((Order.MOVE_AXIS, [ax_id, int(target * conv), int(speed * conv)]))

                # Update State (Wichtig für das 10Hz Log)
                with state.lock:
                    if ax_id == Axis.H:
                        state.pos_h = target
                    elif ax_id == Axis.V:
                        state.pos_v = target
                    else:
                        state.pos_r = target
                self.log(f"Fahre {ax_char} auf {target}...")

            elif parts[0] == 't' and len(parts) == 2:  # Temp: t 37.5
                # Hier brauchen wir direkten Zugriff auf den Heizungs-Serial
                # Im Prototyp schicken wir es über eine globale Variable oder direkt
                # Für diese Demo setzen wir den State und der Worker müsste es senden
                # (Zukunft: Heiz-Queue hinzufügen)
                sp_val = int(float(parts[1]) * 100)
                self.heat_queue.put((Order.SET_SETPOINT, sp_val))  # Jetzt aktiv!
                self.log(f"Sollwert {parts[1]}°C an Heizung gesendet.")

        except Exception as e:
            self.log(f"Fehler: {e}")

    def log(self, msg):
        self.console.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())