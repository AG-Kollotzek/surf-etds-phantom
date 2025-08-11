addpath(genpath('matlab_app'));

% App starten (Port anpassen für macOS)
app = TestUnitApp("/dev/tty.usbmodem1101", 115200);

% Test: Arduino-Status abfragen
app.send("STAT?");
