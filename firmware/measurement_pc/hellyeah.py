import sys, time, queue, threading, os
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGridLayout, QFrame
)
import serial
import serial.tools.list_ports as list_ports

# ================= CONFIG =================
SERIAL_BAUD = 115200
UI_REFRESH_MS = 200
PLOT_HISTORY_SEC = 300
MAX_SAFE_TEMP = 60.0 
MIN_SAFE_TEMP = 10.0

class SerialSensorReader:
    def __init__(self):
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.ser = None
        self.t0 = time.perf_counter()

    def start(self):
        try:
            ports = list(list_ports.comports())
            if not ports: return False
            port = next((p.device for p in ports if "USB" in p.description or "Arduino" in p.description), ports[0].device)
            self.ser = serial.Serial(port, SERIAL_BAUD, timeout=0.5)
            time.sleep(2) 
            self.ser.reset_input_buffer()
            self.stop_evt.clear()
            self.t0 = time.perf_counter()
            threading.Thread(target=self._loop, daemon=True).start()
            return True
        except: return False

    def stop(self):
        self.stop_evt.set()
        if self.ser: self.ser.close()

    def send_setpoint(self, val):
        """Sendet den neuen Sollwert live an den Arduino"""
        if self.ser and self.ser.is_open:
            try:
                cmd = f"SP {val:.2f}\n"
                self.ser.write(cmd.encode())
                print(f"Sende an Arduino: {cmd.strip()}")
            except Exception as e:
                print(f"Fehler beim Senden: {e}")

    def _loop(self):
        while not self.stop_evt.is_set():
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line or line.startswith("#"): continue
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            temp = float(parts[1]) 
                            if MIN_SAFE_TEMP <= temp <= MAX_SAFE_TEMP:
                                self.q.put((time.perf_counter() - self.t0, temp))
                        except ValueError: continue
            except: pass
            time.sleep(0.01)

class LivePlot(QWidget):
    def __init__(self):
        super().__init__()
        self.fig = Figure(figsize=(6, 4), facecolor='#121212')
        self.canvas = FigureCanvas(self.fig)
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e1e')
        self.ax.tick_params(colors='white')
        self.ax.xaxis.label.set_color('white')
        self.ax.yaxis.label.set_color('white')
        self.ax.grid(True, alpha=0.2, color='gray')
        
        self.temp_line, = self.ax.plot([], [], color="#3498db", lw=2, label="Messwert")
        self.sp_line, = self.ax.plot([], [], color="#e67e22", ls="--", label="Sollwert")
        self.ax.legend(loc="upper right")

    def update_plot(self, times, temps, sp):
        if not times: return
        self.temp_line.set_data(times, temps)
        t_now = times[-1]
        t_start = max(0, t_now - PLOT_HISTORY_SEC)
        
        # Sollwert-Linie zeichnen
        self.sp_line.set_data([t_start, t_now], [sp, sp])
        
        self.ax.set_xlim(t_start, t_now + 2)
        # Y-Achse dynamisch um den aktuellen Sollwert halten
        self.ax.set_ylim(sp - 5, sp + 5)
        self.canvas.draw_idle()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LabControl - Live Setpoint Adjustment")
        self.resize(1100, 800)
        self.times, self.temps = [], []
        self.current_setpoint = 27.0
        self.reader = SerialSensorReader()

        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QVBoxLayout(container)

        # --- Steuerung ---
        top = QHBoxLayout()
        top.addWidget(QLabel("Sollwert [°C]:"))
        self.sp_input = QLineEdit("27.0")
        self.sp_input.setFixedWidth(60)
        # Live-Änderung bei Enter
        self.sp_input.returnPressed.connect(self.update_live_setpoint)
        top.addWidget(self.sp_input)
        
        self.btn_apply = QPushButton("Übernehmen")
        self.btn_apply.clicked.connect(self.update_live_setpoint)
        top.addWidget(self.btn_apply)
        
        top.addSpacing(20)
        self.btn_start = QPushButton("START Messung")
        self.btn_stop = QPushButton("STOP & Speichern")
        self.btn_stop.setEnabled(False)
        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        top.addStretch()
        main_layout.addLayout(top)

        main_layout.addWidget(QFrame(frameShape=QFrame.HLine))

        # --- Statistiken ---
        stats_layout = QGridLayout()
        labels = ["Messwert", "Mittelwert (Gesamt)", "Abweichung (Fehler)", "Min", "Max"]
        self.val_labels = {}

        for i, name in enumerate(labels):
            header = QLabel(name)
            header.setAlignment(Qt.AlignCenter)
            header.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
            stats_layout.addWidget(header, 0, i)

            val = QLabel("–")
            val.setAlignment(Qt.AlignCenter)
            val.setStyleSheet("color: #3498db; font-size: 20px; font-weight: bold;")
            stats_layout.addWidget(val, 1, i)
            self.val_labels[name] = val

        main_layout.addLayout(stats_layout)
        main_layout.addWidget(QFrame(frameShape=QFrame.HLine))

        self.plot = LivePlot()
        main_layout.addWidget(self.plot)

        self.timer = QTimer()
        self.timer.timeout.connect(self.process_data)
        self.btn_start.clicked.connect(self.start_logging)
        self.btn_stop.clicked.connect(self.stop_logging)
        
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #121212; color: white; }
            QPushButton { background: #333; border: 1px solid #555; padding: 8px; border-radius: 4px; }
            QPushButton[text="Übernehmen"] { background: #2c3e50; color: #3498db; }
            QPushButton:hover { background: #444; }
            QLineEdit { background: #222; border: 1px solid #444; color: #3498db; font-weight: bold; }
        """)

    def update_live_setpoint(self):
        """Wird aufgerufen, wenn der Sollwert geändert wird (Button oder Enter)"""
        try:
            new_val = float(self.sp_input.text().replace(",", "."))
            if MIN_SAFE_TEMP <= new_val <= MAX_SAFE_TEMP:
                self.current_setpoint = new_val
                # Befehl sofort an Hardware senden
                self.reader.send_setpoint(new_val)
                print(f"Sollwert auf {new_val} °C geändert.")
        except ValueError:
            pass

    def start_logging(self):
        self.times.clear()
        self.temps.clear()
        self.update_live_setpoint() # Initialen Wert übernehmen
        
        if self.reader.start():
            self.reader.send_setpoint(self.current_setpoint)
            self.timer.start(UI_REFRESH_MS)
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)

    def stop_logging(self):
        self.timer.stop()
        self.reader.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if self.temps: self.auto_save()

    def auto_save(self):
        ts = time.strftime("%Y%m%d-%H%M%S")
        df = pd.DataFrame({
            "Zeit_s": self.times, 
            "Messwert_C": self.temps, 
            "Letzter_Sollwert_C": [self.current_setpoint]*len(self.temps)
        })
        df.to_csv(f"Log_{ts}.csv", index=False, sep=";")
        self.plot.fig.savefig(f"Plot_{ts}.png", dpi=150)

    def process_data(self):
        while not self.reader.q.empty():
            t, temp = self.reader.q.get()
            self.times.append(t)
            self.temps.append(temp)
        
        if self.temps:
            curr = self.temps[-1]
            avg = np.mean(self.temps)
            err = curr - self.current_setpoint # Fehler auf aktuellen Ist-Zustand bezogen
            t_min = np.min(self.temps)
            t_max = np.max(self.temps)

            self.val_labels["Messwert"].setText(f"{curr:.2f} °C")
            self.val_labels["Mittelwert (Gesamt)"].setText(f"{avg:.2f} °C")
            self.val_labels["Abweichung (Fehler)"].setText(f"{err:+.3f} °C")
            self.val_labels["Min"].setText(f"{t_min:.2f} °C")
            self.val_labels["Max"].setText(f"{t_max:.2f} °C")

            self.plot.update_plot(self.times, self.temps, self.current_setpoint)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())