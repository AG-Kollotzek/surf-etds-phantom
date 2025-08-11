classdef TestUnitApp < handle
    properties
        s % serialport object
    end
    
    methods
        function obj = TestUnitApp(port, baud)
            if nargin < 1, port = "COM3"; end
            if nargin < 2, baud = 115200; end
            obj.s = serialport(port, baud, "Timeout", 1);
            configureTerminator(obj.s, "LF");
            flush(obj.s);
            fprintf("Verbunden mit %s @ %d Baud\n", port, baud);
        end
        
        function delete(obj)
            if ~isempty(obj.s) && isvalid(obj.s)
                clear obj.s;
                fprintf("Serielle Verbindung geschlossen.\n");
            end
        end
        
        function send(obj, cmd)
            writeline(obj.s, cmd);
            pause(0.05);
            if obj.s.NumBytesAvailable > 0
                resp = readline(obj.s);
                fprintf("Antwort: %s\n", resp);
            end
        end
    end
end
