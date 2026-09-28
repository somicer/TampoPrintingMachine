#!/usr/bin/env python3
"""Axis sizing check for the large-format closed-cup pad printer.

Run:  python3 tools/axis_sizing.py
All inputs are at the top; edit them to match the real machine.
"""
import math

G = 9.81

# ---------- common drive train ----------
PULLEY_TEETH = 24
BELT_PITCH_MM = 5.0              # HTD 5M
PULSES_PER_REV = 4000            # CL57 microstep setting (recommended)
ROTOR_INERTIA = 0.9e-4           # kg.m^2, typical NEMA24 4 N.m (check 60HSE4N datasheet)
PULLEY_INERTIA = 0.6e-5          # kg.m^2, aluminium 24T x 15 mm, approx.

# ---------- axes ----------
GEAR = {"X (pad carriage)": 3.0, "Y (closed cup)": 1.0}   # planetary ratio

# Field data (docs/08): X 14 kg, 500 mm pick->print in ~0.9 s;
# Y cup drag up to ~90 N (rated force of the existing DC drive).
AXES = {
    "X (pad carriage)": dict(stroke=500.0, t_move=0.9, mass=14.0, mu=0.08, f_ext=0.0),
    "Y (closed cup)":   dict(stroke=370.0, t_move=1.0, mass=4.0,  mu=0.02, f_ext=90.0),
}

# ---------- Z pneumatic ----------
P_BAR = 5.1   # measured on the existing machine
BORES = {"MGPM25": (25, 10), "SC40": (40, 16), "MGPM50": (50, 18), "SC63": (63, 20)}


def trapezoid(stroke, t, frac=1 / 3):
    """Peak speed and accel for a trapezoidal profile with given accel fraction."""
    t_acc = t * frac
    v = stroke / (t - t_acc)          # mm/s
    a = v / t_acc                      # mm/s^2
    return v, a, t_acc


def main():
    circ = PULLEY_TEETH * BELT_PITCH_MM            # mm/rev
    r = circ / (2 * math.pi) / 1000.0              # m
    ppmm = PULSES_PER_REV / circ
    print(f"Pulley: {PULLEY_TEETH}T HTD5M -> {circ:.1f} mm/rev, pitch radius {r*1000:.2f} mm")
    print(f"Resolution: {PULSES_PER_REV} p/rev -> {ppmm:.3f} p/mm ({1/ppmm:.4f} mm/pulse)")
    print(f"Scale param 'pulses per 1000 mm' = {round(ppmm*1000)}\n")

    for name, ax in AXES.items():
        v, a, t_acc = trapezoid(ax["stroke"], ax["t_move"])
        g = GEAR[name]
        rps = v / circ * g
        f_hz = v * ppmm * g
        j_load = ax["mass"] * r ** 2 / g ** 2
        ratio = j_load / ROTOR_INERTIA
        f_lin = ax["mass"] * a / 1000 + ax["mu"] * ax["mass"] * G + ax["f_ext"]
        t_load = f_lin * r / g
        t_rot = (ROTOR_INERTIA + PULLEY_INERTIA / g ** 2) * (a / 1000) / r * g
        t_total = t_load + t_rot
        print(f"== {name} ==")
        print(f"  avg speed {ax['stroke']/ax['t_move']:.0f} mm/s, PEAK speed {v:.0f} mm/s,"
              f" accel {a/1000:.2f} m/s^2 (t_acc {t_acc:.2f} s)")
        print(f"  motor {rps*60:.0f} rpm, pulse freq {f_hz/1000:.1f} kHz")
        print(f"  belt force {f_lin:.1f} N, torque {t_total:.2f} N.m (x2 safety -> {2*t_total:.2f})")
        print(f"  gearbox 1:{g:g}, inertia ratio load/rotor = {ratio:.1f}:1\n")

    print("== Z cylinder force at %.1f bar ==" % P_BAR)
    for n, (d, rod) in BORES.items():
        a_ext = math.pi * (d / 2) ** 2
        a_ret = a_ext - math.pi * (rod / 2) ** 2
        print(f"  {n}: push {a_ext*P_BAR/10:.0f} N, pull {a_ret*P_BAR/10:.0f} N")


if __name__ == "__main__":
    main()
