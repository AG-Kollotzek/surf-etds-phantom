addpath(genpath('matlab_app'));

% Beispiel: App starten
% Portnamen unter macOS anpassen: /dev/tty.usbmodemXXXX
app = TestUnitApp("/dev/tty.usbmodem1101", 115200);

% Test: Arduino-Status abfragen
app.send("STAT?");
