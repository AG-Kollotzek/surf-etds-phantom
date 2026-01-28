try:
    import PySide6
    import serial
    import numpy
    import pandas
    import matplotlib
    print("✅ Alle Pakete sind korrekt installiert. Ready to go!")
except ImportError as e:
    print(f"❌ Fehler: Das Paket '{e.name}' fehlt oder ist fehlerhaft installiert.")
    print(f"Installiere es mit: pip install {e.name}")