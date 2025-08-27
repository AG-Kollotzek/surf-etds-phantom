import numpy as np
import matplotlib.pyplot as plt
import pyserial                       # needed for connection with hardware aka oscilloscope


# CONFIGURATION SETTING
# unique identifier for oscilloscope (e.g., via USB or LAN)
SCOPE_RESOURCE_ID = 'USB::XXX::YYY::ZZZ::INSTR' # replace when device is known

# Channel assignments for the signals
ACQ_CHANNEL_BEAM = 'CH1'    # Channel receiving the LINAC beam signal, ACQ = acquisition (Erfassung/Messung)
ACQ_CHANNEL_SYSTEM = 'CH2'  # Channel receiving the LINAC system-off signal

# Number of data points to acquire from the oscilloscope
DATA_POINTS = 2500    # random number atm  

# Voltage level that define the "off" state of the signal 
THRESHOLD_VOLTAGE = 2.5     # random number atm


# FUNCTION TO DETECT SIGNAL DROPOFF
def detect_falling_edge(signal, time, threshold=1.0):

    """
    Detect the first falling in the signal, i.e., where the voltage drops from above
    the threshold to below it. This marks the "off" time.

    Parameters:
    - signal: numpy array with voltage values
    - time: numpy array with correspomding time values
    - threshold: voltage threshold to detect drop

    Returns:
    - timestamp of the falling edge or none if not found 
    """

    for i in range(1, len(signal)):
        if signal[i-1] > threshold and signal[i] <= threshold:
            return time[i]
    return None  # no falling edge detected

 
# START OF THE MAIN PROGRAM


rm = pyvisa.ResourceManager()
scope = rm.open_resource(SCOPE_RESOURCE_ID)

# Set source to beam signal (channel 1)
scope.write("DATA:SOURCE" + ACQ_CHANNEL_BEAM)
scope.write("DATA:START 1")
scope.write("DATA:STOP" + str(DATA_POINTS))
raw_data_ch1 = scope.query.binary_values("CURVE?", datatype='B', container=np.array)

# Set source to system signal (channel 2)
scope.write("DATA:SOURCE" + ACQ_CHANNEL_SYSTEM)
raw_data_ch2 = scope.query.binary_values("CURVE?", datatype='B', container=np.array)


# DETECT SIGNAL DROP-OFF TIMES (falling edges)
beam_off_time = detect_falling_edge(raw_data_ch1, time, threshold=THRESHOLD_VOLTAGE)
system_off_time = detect_falling_edge(raw_data_ch2, time, THRESHOLD_VOLTAGE)

# PRINT RESULTS
# convert seconds to microseconds (1e6) for easier reading, this was a wild guess, I don't actually know the correct scientific notation
print(f"Beam off at: {beam_off_time*1e6:.2f}µs")
print(f"System off at: {system_off_time*1e6:.2f}µs")
print(f"Δt = {(system_off_time - beam_off_time)*1e6:.2f}µs")


# PLOT THE SIGNALS FOR VISUAL VERIFICATION 
plt.plot(time*1e6, raw_data_ch1, label='Beam (CH1)')        # Beam signal (blue)
plt.plot(time*1e6, raw_data_ch2, label='System (CH2)')      # System signal (orange)

# Draw vertical lines where the signals fall below threshold 
plt.axvline(beam_off_time*1e6, color='blue', linestyle='--', alpha=0.5)
plt.axvline(system_off_time*1e6, color='orange', linestyle='--', alpha=0.5)

# Label the plot
plt.xlabel("Time[µs]")              # x-axis label: time in microseconds
plt.ylabel("Voltage [V]")           # y-axis label: voltage in volts
plt.title("LINAC Signal Analysis")  # plot title
plt.legend()                        # show legend to distinguish signals
plt.grid(True)                      # add background grid
plt.tight_layout()                  # ensure labels and layout are clean
plt.show()                          # display the plot window
