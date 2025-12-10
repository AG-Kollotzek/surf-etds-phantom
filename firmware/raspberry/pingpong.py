import serial
import time
import serial.tools.list_ports

# Alle USB-Ports finden
ports = serial.tools.list_ports.comports()
arduino_ports = [p.device for p in ports if 'USB' in p.device]

if not arduino_ports:
    print("Keine Arduinos gefunden!")
    exit()

print("Gefundene Arduinos:", arduino_ports)

for port in arduino_ports:
    try:
        ser = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)  # kurze Pause, bis Arduino Serial stabil ist
        ser.write(b"ping\n")
        reply = ser.readline().decode().strip()
        print(f"{port} antwortet: {reply}")
        ser.close()
    except Exception as e:
        print(f"Fehler mit {port}: {e}")
