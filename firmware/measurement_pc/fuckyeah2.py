import sys, time, queue, threading, os
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGridLayout, QFrame, QMessageBox
)
import serial
import serial.tools.list_ports as list_ports

# ================= CONFIG =================
SERIAL_BAUD = 115200
UI_REFRESH_MS = 200
PLOT_HISTORY_SEC = 600
MAX_SAFE_TEMP = 50.0 
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

    def send_setpoint(self, pad_id, val):
        if self.ser and self.ser.is_open:
            try:
                cmd = f"SP{pad_id} {val:.2f}\n"
                self.ser.write(cmd.encode())
            except Exception as e:
                print(f"Fehler beim Senden: {e}")

    def _loop(self):
        while not self.stop_evt.is_set():
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line or line.startswith("#"): continue
                    parts = line.split(',')
                    if len(parts) >= 3:
                        try:
                            t_rel = time.perf_counter() - self.t0
                            temp_a = float(parts[1])
                            temp_b = float(parts[2])
                            self.q.put((t_rel, temp_a, temp_b))
                        except ValueError: continue
            except: pass
            time.sleep(0.01)

class LivePlot(QWidget):
    def __init__(self):
        super().__init__()
        self.fig = Figure(figsize=(8, 4), facecolor='#121212')
        self.canvas = FigureCanvas(self.fig)
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e1e')
        self.ax.tick_params(colors='white')
        self.ax.xaxis.label.set_color('white')
        self.ax.yaxis.label.set_color('white')
        self.ax.grid(True, alpha=0.1, color='gray')
        
        self.line_a, = self.ax.plot([], [], color="#3498db", lw=2, label="Ist A")
        self.line_b, = self.ax.plot([], [], color="#e74c3c", lw=2, label="Ist B")
        self.sp_a_line, = self.ax.plot([], [], color="#3498db", ls=":", alpha=0.5, label="Soll A")
        self.sp_b_line, = self.ax.plot([], [], color="#e74c3c", ls=":", alpha=0.5, label="Soll B")
        
        self.ax.legend(loc="upper left", fontsize='small')

    def update_plot(self, times, temps_a, temps_b, sp_a, sp_b):
        if not times: return
        self.line_a.set_data(times, temps_a)
        self.line_b.set_data(times, temps_b)
        t_now = times[-1]
        t_start = max(0, t_now - PLOT_HISTORY_SEC)
        self.sp_a_line.set_data([t_start, t_now], [sp_a, sp_a])
        self.sp_b_line.set_data([t_start, t_now], [sp_b, sp_b])
        self.ax.set_xlim(t_start, t_now + 2)
        all_v = [v for v in (temps_a + temps_b) if not np.isnan(v)]
        if all_v:
            self.ax.set_ylim(min(all_v + [sp_a, sp_b]) - 2, max(all_v + [sp_a, sp_b]) + 2)
        self.canvas.draw_idle()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LabControl Dual-Pad Professional")
        self.resize(1100, 850)
        self.times, self.temps_a, self.temps_b = [], [], []
        self.sp_a, self.sp_b = 25.0, 25.0
        self.reader = SerialSensorReader()

        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QVBoxLayout(container)

        # --- Steuerung ---
        top = QHBoxLayout()
        top.addWidget(QLabel("Soll A [°C]:"))
        self.input_a = QLineEdit("25.0")
        self.input_a.setFixedWidth(60)
        top.addWidget(self.input_a)
        top.addSpacing(10)
        top.addWidget(QLabel("Soll B [°C]:"))
        self.input_b = QLineEdit("25.0")
        self.input_b.setFixedWidth(60)
        top.addWidget(self.input_b)
        
        self.btn_apply = QPushButton("Übernehmen")
        self.btn_apply.clicked.connect(self.apply_setpoints)
        top.addWidget(self.btn_apply)
        
        top.addStretch()
        self.btn_start = QPushButton("START Messung")
        self.btn_stop = QPushButton("STOP & DATEN SPEICHERN") # Wichtiger Hinweis im Label
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("background: #c0392b; font-weight: bold;")
        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        main_layout.addLayout(top)

        main_layout.addWidget(QFrame(frameShape=QFrame.HLine))

        # --- Statistik Grid ---
        stats_layout = QGridLayout()
        headers = ["Pad", "Messwert", "Sollwert", "Abweichung", "Min", "Max"]
        for i, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
            stats_layout.addWidget(lbl, 0, i)

        self.labels = {"A": {}, "B": {}}
        for i, pad in enumerate(["A", "B"]):
            row = i + 1
            color = "#3498db" if pad == "A" else "#e74c3c"
            p_lbl = QLabel(f"PAD {pad}")
            p_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 16px;")
            stats_layout.addWidget(p_lbl, row, 0, Qt.AlignCenter)
            for col, key in enumerate(["val", "sp", "err", "min", "max"], 1):
                lbl = QLabel("–")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
                stats_layout.addWidget(lbl, row, col)
                self.labels[pad][key] = lbl
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
            QPushButton { background: #333; border: 1px solid #555; padding: 8px; border-radius: 4px; min-width: 120px; }
            QPushButton:hover { background: #444; }
            QPushButton[text="Übernehmen"] { background: #2c3e50; color: #3498db; font-weight: bold; }
            QLineEdit { background: #222; border: 1px solid #444; color: #3498db; font-weight: bold; padding: 4px; }
        """)

    def apply_setpoints(self):
        try:
            self.sp_a = float(self.input_a.text().replace(",", "."))
            self.sp_b = float(self.input_b.text().replace(",", "."))
            self.reader.send_setpoint("A", self.sp_a)
            self.reader.send_setpoint("B", self.sp_b)
        except: pass

    def start_logging(self):
        self.times.clear(); self.temps_a.clear(); self.temps_b.clear()
        if self.reader.start():
            self.apply_setpoints()
            self.timer.start(UI_REFRESH_MS)
            self.btn_start.setEnabled(False); self.btn_stop.setEnabled(True)

    def stop_logging(self):
        self.timer.stop()
        self.reader.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        
        if self.temps_a:
            # --- DATEI SPEICHERUNG ---
            ts = time.strftime("%Y%m%d-%H%M%S")
            csv_name = f"Log_{ts}.csv"
            plot_name = f"Plot_{ts}.png"
            
            # 1. CSV Speichern
            df = pd.DataFrame({"t_sec": self.times, "Temp_A": self.temps_a, "Temp_B": self.temps_b})
            df.to_csv(csv_name, sep=";", index=False)
            
            # 2. Bild Speichern
            self.plot.fig.savefig(plot_name, dpi=150)
            
            QMessageBox.information(self, "Speicherung erfolgreich", 
                                    f"Messdaten gespeichert als:\n1. {csv_name}\n2. {plot_name}")

    def process_data(self):
        while not self.reader.q.empty():
            t, ta, tb = self.reader.q.get()
            self.times.append(t); self.temps_a.append(ta); self.temps_b.append(tb)
        
        if self.temps_a:
            for pad, temps, sp in [("A", self.temps_a, self.sp_a), ("B", self.temps_b, self.sp_b)]:
                curr = temps[-1]
                self.labels[pad]["val"].setText(f"{curr:.2f} °C")
                self.labels[pad]["err"].setText(f"{(curr-sp):+.2f}")
                self.labels[pad]["min"].setText(f"{np.min(temps):.1f}")
                self.labels[pad]["max"].setText(f"{np.max(temps):.1f}")
                self.labels[pad]["sp"].setText(f"{sp:.1f}")
            self.plot.update_plot(self.times, self.temps_a, self.temps_b, self.sp_a, self.sp_b)

if __name__ == "__main__":
    app = QApplication(sys.argv); window = MainWindow(); window.show(); sys.exit(app.exec())