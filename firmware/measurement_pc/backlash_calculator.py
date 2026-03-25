import tkinter as tk
from tkinter import messagebox
import math


def calculate():
    r_str = entry_r.get().replace(',', '.')
    theta_str = entry_theta.get().replace(',', '.')
    x_str = entry_x.get().replace(',', '.')

    try:
        # Prüfen, ob der Achsabstand r da ist
        if not r_str:
            messagebox.showerror("Fehler", "Der Achsabstand (r) muss immer angegeben werden!")
            return

        r = float(r_str)
        if r <= 0:
            messagebox.showerror("Fehler", "Der Achsabstand muss größer als 0 sein.")
            return

        # Prüfen, was berechnet werden soll
        if (not theta_str and not x_str) or (theta_str and x_str):
            messagebox.showinfo("Hinweis",
                                "Bitte genau EINEN Wert (Winkel ODER Strecke) freilassen, um ihn zu berechnen.")
            return

        if theta_str:  # Winkel ist gegeben -> Strecke x berechnen
            theta = float(theta_str)
            # Formel: x = r * tan(theta)
            x = r * math.tan(math.radians(theta))
            entry_x.delete(0, tk.END)
            entry_x.insert(0, f"{x:.4f}")

        elif x_str:  # Strecke ist gegeben -> Winkel theta berechnen
            x = float(x_str)
            # Formel: theta = arctan(x / r)
            theta = math.degrees(math.atan(x / r))
            entry_theta.delete(0, tk.END)
            entry_theta.insert(0, f"{theta:.4f}")

    except ValueError:
        messagebox.showerror("Fehler", "Bitte nur gültige Zahlen eingeben.")


def clear():
    entry_r.delete(0, tk.END)
    entry_theta.delete(0, tk.END)
    entry_x.delete(0, tk.END)
    # Setze Standard-Achsabstand wieder ein
    entry_r.insert(0, "15.0")


# --- GUI Setup ---
root = tk.Tk()
root.title("SGRT QA - Messuhr Rechner")
root.geometry("380x200")
root.resizable(False, False)

# Labels und Eingabefelder
tk.Label(root, text="Achsabstand r (mm):").grid(row=0, column=0, padx=15, pady=10, sticky="e")
entry_r = tk.Entry(root, width=15)
entry_r.grid(row=0, column=1, padx=10, pady=10)
entry_r.insert(0, "15.0")  # Euer aktueller Hebelarm

tk.Label(root, text="Winkel θ (Grad):").grid(row=1, column=0, padx=15, pady=10, sticky="e")
entry_theta = tk.Entry(root, width=15)
entry_theta.grid(row=1, column=1, padx=10, pady=10)

tk.Label(root, text="Lineare Strecke Δx (mm):").grid(row=2, column=0, padx=15, pady=10, sticky="e")
entry_x = tk.Entry(root, width=15)
entry_x.grid(row=2, column=1, padx=10, pady=10)

# Buttons
btn_clear = tk.Button(root, text="Leeren", command=clear, width=10)
btn_clear.grid(row=3, column=0, pady=15, sticky="e", padx=10)

btn_calc = tk.Button(root, text="Berechnen", command=calculate, width=12, bg="lightblue")
btn_calc.grid(row=3, column=1, pady=15, sticky="w")

# Fokus direkt auf das Winkel-Feld setzen
entry_theta.focus_set()

# Hauptschleife starten
root.mainloop()