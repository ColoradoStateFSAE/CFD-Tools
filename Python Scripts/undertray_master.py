#!/usr/bin/env python3
"""
undertray_master.py  -  Undertray / diffuser screening tool with a GUI.

Change any input on the left and every result and plot on the right updates.

INSTALL:   pip install PySide6 matplotlib numpy
RUN:       python undertray_master.py

INPUTS (all optional beyond the basics, sensible defaults provided)
  Diffuser   : stage-1 length and end height, optional stage-2 "kick"
               (length + exit height), throat height, entry radius,
               floor leading-edge height
  Widths     : floor width, diffuser inlet width, diffuser exit width
               (planform flare), number of channels, divider thickness
  Attitude   : rake (nose-down positive), side-edge treatment
  Air        : altitude + temperature -> density and viscosity, speed
  Vehicle    : wheelbase, diffuser inlet position, car + driver mass,
               clearance rule
  Strakes    : same-direction (two-channel) or counter-rotating layout
  Model knobs: exit Cp, realism factor, flat-floor Cp fraction, stall slope

WHAT IT GIVES YOU
  * effective diffuser angle(s) incl. rake, 3-D area ratio, steepness verdict
  * critical (stall) ride height and your margin to it
  * estimated downforce, CLA, % of car weight, front/rear load split
  * ride-height sweep (the stall cliff), floor pressure plot, side view,
    and a plan view of the strakes
  * strake count / height / length / angle / gap
  * a list of design flags

!! HOW MUCH TO TRUST IT !!
This is a hand-calc SCREENING tool. Treat downforce as +/-30 %. (Jensen's FSAE
CFD was 31 % off track data.) Use it to compare options and catch bad geometry
before spending Fluent time. Numbers tagged [HEURISTIC] are engineering
assumptions of mine, not values from a paper. Calibrate the "Model knobs"
against your own CFD.

SOURCES
  Ruhrmann & Zhang 2003, Senior & Zhang 2001 (diffuser angle, stall height,
    side-plate vortices, separation at the inlet centre)
  Katz 2006 review incl. Cooper 1998 and George & Donis 1983 (stall angles,
    sharp-entry separation, sealed skirts)
  KTH undertray thesis 2021 (pressure-based force, Cp recovery, inlet height)
  Jensen 2010 (FSAE undertray: roll, yaw, CFD error, "false seal")
  Harjula 2024 (FSAE CFD, multi-angle diffusers)
  Logdberg 2006, James 2024, Katz & Morey 2008, Dudek 2011 (strakes)
"""

import math
import sys
from dataclasses import dataclass

import numpy as np

# ============================================================================
#  PART 1 - ENGINEERING MODEL (no GUI code here, so it can be tested alone)
# ============================================================================

# [HEURISTIC] diffuser efficiency vs angle: fraction of the ideal pressure
# recovery (1 - 1/AR^2) actually achieved. Falls with angle because of
# separation. Consistent with Harjula's FSAE CFD (no gain from 7 to 20.5 deg).
THETA_TAB = [0, 3, 5, 7, 10, 14, 20, 30]
ETA_TAB = [0.85, 0.85, 0.85, 0.80, 0.65, 0.50, 0.40, 0.30]

SIDE_EDGE_OPTIONS = ["open", "endplates", "skirts (near-sealed)"]


@dataclass
class Inputs:
    # ---- diffuser profile = spline (quadratic Bezier), measured at zero rake ----
    #   P0 = throat point
    #   P1 = end of the HORIZONTAL control line (length a_mm from P0)
    #   P2 = exit point, reached from P1 by the ANGLED control line
    #        (length b_mm at theta_deg above horizontal)
    # The spline leaves the throat horizontally and arrives at the exit at
    # theta_deg. a_mm = 0 gives a straight ramp at theta_deg.
    H_t_mm: float = 40.0        # throat height = floor clearance at diffuser inlet
    a_mm: float = 150.0         # horizontal control line length
    theta_deg: float = 9.0      # angled control line angle (= exit tangent angle)
    b_mm: float = 460.0         # angled control line length
    H_le_mm: float = 40.0       # floor leading-edge (inlet) height above ground
    # ---- widths (mm) ----
    W_floor_mm: float = 600.0   # flat floor width
    W_in_mm: float = 600.0      # diffuser width at the inlet (throat)
    W_out_mm: float = 600.0     # diffuser width at the exit (planform flare)
    n_channels: int = 2
    t_div_mm: float = 3.0       # thickness of each channel divider / fence
    L_flat_mm: float = 1000.0   # flat floor length ahead of diffuser inlet
    # ---- attitude and edges ----
    rake_deg: float = 0.0       # + = nose down (rear up); adds to diffuser angle
    side_edge: str = "open"     # open / endplates / skirts (near-sealed)
    # ---- air and speed ----
    V_kph: float = 90.0
    altitude_m: float = 1525.0  # Fort Collins ~1525 m; FSAE Michigan ~300 m
    temp_C: float = 20.0
    # ---- vehicle and rules ----
    wheelbase_mm: float = 1550.0
    x_inlet_mm: float = 1300.0  # diffuser inlet distance behind the front axle
    mass_kg: float = 300.0      # car + driver
    h_min_rule_mm: float = 25.4  # FSAE has been 1 in historically. CHECK RULEBOOK.
    # ---- strakes ----
    vg_layout: str = "same"      # "same" (Katz & Morey, two-channel) or "counter"
    vg_n_per_channel: int = 2
    vg_width_fraction: float = 1.0   # "counter" layout only
    # ---- model knobs ----
    Cp_exit: float = 0.0         # base pressure coefficient at the diffuser exit
    k_cal: float = 0.80          # [HEURISTIC] realism factor on pressure recovery
    f_flat: float = 0.50         # [HEURISTIC] mean floor Cp / throat Cp
    collapse_slope: float = 1.4  # [FIT] downforce loss slope below critical height


def air_properties(altitude_m, temp_C):
    """ISA pressure at altitude, density from the actual temperature,
    viscosity from Sutherland's law (textbook)."""
    p = 101325.0 * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588
    T = temp_C + 273.15
    rho = p / (287.05 * T)
    mu = 1.716e-5 * (T / 273.15) ** 1.5 * (273.15 + 110.4) / (T + 110.4)
    return rho, mu, p


def undertray_model(h, G, q, inp, h_crit):
    """Pressure-based downforce estimate for a rigid undertray with throat
    (ride) height h. Diffuser angles are held fixed, so exit height moves
    with h. Pumping model (Sovran via Senior & Zhang / KTH):
        AR  = (H_exit * W_out) / (H_throat * W_in)         3-D area ratio
        Cpd = k_cal * eta(theta_max) * (1 - 1/AR^2)
        Cp1 = (Cp_exit - Cpd) / (1 - Cpd)                   Bernoulli at inlet
        F   = -integral(p dA) over the plan area            KTH Eq. 6
    G holds geometry in SI (from compute()). Returns (downforce_N, dict).
    Efficiency eta is taken at the spline CHORD angle [HEURISTIC]: the
    straight-ramp data in the papers maps best to the overall rise/length."""
    He = h + G["rise"]
    AR = (He * G["W_out"]) / (h * G["W_in"])
    th = min(max(G["th_eta_deg"], THETA_TAB[0]), THETA_TAB[-1])
    eta = float(np.interp(th, THETA_TAB, ETA_TAB))
    Cpd = inp.k_cal * eta * (1.0 - 1.0 / AR ** 2) if AR > 1 else 0.0
    Cp1 = (inp.Cp_exit - Cpd) / (1.0 - Cpd)
    Cp_flat = inp.f_flat * Cp1

    L_d = G["L_d"]
    DF_flat = -Cp_flat * q * G["W_floor"] * G["L_flat"]
    DF_diff = -0.5 * (Cp1 + inp.Cp_exit) * q * G["W_diff_avg"] * L_d

    fac = max(0.0, 1.0 - inp.collapse_slope * (1.0 - h / h_crit)) if h < h_crit else 1.0
    total = DF_flat + DF_diff
    DF = total * fac

    a, b = Cp1, inp.Cp_exit
    xc_d = L_d / 2.0 if abs(a + b) < 1e-9 else L_d * (a + 2 * b) / (3 * (a + b))
    xcp = ((DF_flat * G["L_flat"] / 2.0 + DF_diff * (G["L_flat"] + xc_d)) / total
           if total != 0 else G["L_flat"])
    return DF, dict(eta=eta, Cpd=Cpd, Cp1=Cp1, Cp_flat=Cp_flat, xcp=xcp,
                    AR=AR, collapse=fac, He=He)


def steepness_verdict(theta_deg):
    """Returns (text, severity, flag_or_None). severity: 0 blue (shallow),
    1 green, 2 yellow, 3 orange, 4 red."""
    if theta_deg < 3:
        return ("TOO SHALLOW: little pumping, downforce left on the table", 0,
                "Diffuser angle under 3 deg: little downforce gain.")
    if theta_deg <= 7:
        return ("OK: attached flow expected (2-D rules, Jensen / Harjula)", 1, None)
    if theta_deg <= 10:
        return ("CAUTION: separation risk rising, strakes / side vortices needed", 2,
                "Steepest diffuser stage 7-10 deg: marginal. Strakes recommended.")
    if theta_deg <= 14:
        return ("RISKY: ramp centre likely separated, works only via edge vortices", 3,
                "Steepest diffuser stage 10-14 deg: likely centre separation "
                "(Ruhrmann, Cooper).")
    if theta_deg <= 20:
        return ("TOO STEEP: past the 14 deg stall of Katz; hysteresis at 15-20 deg "
                "(Ruhrmann)", 4,
                "Steepest diffuser stage over 14 deg: stall and hysteresis risk. "
                "Reduce the angle or lengthen the diffuser.")
    return ("WAY TOO STEEP: outside all the test data (max 20 deg)", 4,
            "Steepest diffuser stage over 20 deg: outside all the papers.")


def compute(inp: Inputs) -> dict:
    """Run the whole analysis. Returns a dict with results, flags and arrays."""
    mm = 1e-3
    H_t = inp.H_t_mm * mm
    a, b, th_c = inp.a_mm * mm, inp.b_mm * mm, math.radians(inp.theta_deg)
    W_floor, W_in, W_out = inp.W_floor_mm * mm, inp.W_in_mm * mm, inp.W_out_mm * mm
    L_flat = inp.L_flat_mm * mm
    wheelbase, x_inlet = inp.wheelbase_mm * mm, inp.x_inlet_mm * mm
    h_min, t_div = inp.h_min_rule_mm * mm, inp.t_div_mm * mm
    n_ch = max(int(inp.n_channels), 1)
    flags = []
    R = {"flags": flags}

    # ---------------- input sanity ----------------
    if min(b, H_t, W_in, W_out, W_floor, inp.V_kph) <= 0 or L_flat < 0 or a < 0:
        R["error"] = ("Angled control line, heights, widths and speed must be "
                      "positive (horizontal control line may be 0).")
        return R
    if inp.theta_deg <= 0:
        R["error"] = "Control line angle must be above 0 deg (that is a flat floor)."
        return R
    W_div_total = (n_ch - 1) * t_div
    if W_div_total >= W_in:
        R["error"] = "Channel dividers are wider than the diffuser."
        return R

    # ---------------- air ----------------
    rho, mu, p_amb = air_properties(inp.altitude_m, inp.temp_C)
    V = inp.V_kph / 3.6
    q = 0.5 * rho * V ** 2
    rho_sl = air_properties(0.0, 15.0)[0]
    R.update(rho=rho, mu=mu, V=V, q=q, rho_ratio=rho / rho_sl)
    if rho / rho_sl < 0.9:
        flags.append(f"Air density is {100*rho/rho_sl:.0f} % of sea level: home "
                     "testing at altitude shows less downforce than at competition.")

    # ---------------- spline profile (quadratic Bezier) + rake ----------------
    # Control points relative to the throat P0 = (0, 0), then rotated by rake
    # about the throat (nose-down rake lifts the rear).
    rake = math.radians(inp.rake_deg)
    cr, sr = math.cos(rake), math.sin(rake)
    def rot(x, y):
        return (x * cr - y * sr, x * sr + y * cr)
    P0 = (0.0, 0.0)
    P1 = rot(a, 0.0)
    P2 = rot(a + b * math.cos(th_c), b * math.sin(th_c))
    t = np.linspace(0.0, 1.0, 201)
    bx = (1 - t) ** 2 * P0[0] + 2 * (1 - t) * t * P1[0] + t ** 2 * P2[0]
    by = (1 - t) ** 2 * P0[1] + 2 * (1 - t) * t * P1[1] + t ** 2 * P2[1]
    dx = 2 * (1 - t) * (P1[0] - P0[0]) + 2 * t * (P2[0] - P1[0])
    dy = 2 * (1 - t) * (P1[1] - P0[1]) + 2 * t * (P2[1] - P1[1])
    slope_deg = np.degrees(np.arctan2(dy, dx))      # local ramp angle along spline
    L_d, rise = P2[0], P2[1]
    if L_d <= 0 or rise <= 0:
        R["error"] = "Rake makes the diffuser fold back or point down."
        return R
    He_eff = H_t + rise
    th_chord_deg = math.degrees(math.atan(rise / L_d))
    th_exit_deg = inp.theta_deg + inp.rake_deg       # exit tangent incl. rake
    th_entry_deg = inp.rake_deg                      # entry tangent incl. rake
    # radius of curvature at the throat: R0 = 2 a^2 / (b sin(theta))
    R0 = 2 * a ** 2 / (b * math.sin(th_c)) if a > 0 else 0.0
    # local angle at 25/50/75/100 % of the diffuser length
    ang_at = {f: float(np.interp(f * L_d, bx, slope_deg)) for f in (0.25, 0.5, 0.75, 1.0)}

    G = dict(L_d=L_d, rise=rise, th_eta_deg=th_chord_deg,
             W_floor=W_floor, W_in=W_in, W_out=W_out, L_flat=L_flat,
             W_diff_avg=0.5 * (W_in + W_out) - W_div_total)
    flare_deg = math.degrees(math.atan(0.5 * (W_out - W_in) / L_d))
    AR3 = (He_eff * W_out) / (H_t * W_in)
    th_max_deg = max(th_chord_deg, th_exit_deg)
    R.update(th_chord_deg=th_chord_deg, th_exit_deg=th_exit_deg,
             th_entry_deg=th_entry_deg, th_eq_deg=th_chord_deg,
             th_max_deg=th_max_deg, R0_mm=R0 * 1e3, ang_at=ang_at,
             rise_mm=rise * 1e3, He_eff_mm=He_eff * 1e3, AR_h=He_eff / H_t,
             AR3=AR3, flare_deg=flare_deg, L_d_mm=L_d * 1e3,
             spline_x=bx * 1e3, spline_y=(by + H_t) * 1e3,
             ctrl=[(P0[0] * 1e3, (P0[1] + H_t) * 1e3),
                   (P1[0] * 1e3, (P1[1] + H_t) * 1e3),
                   (P2[0] * 1e3, (P2[1] + H_t) * 1e3)])

    # verdict on the CHORD angle (the equivalent straight ramp in the papers)
    verdict, sev, vflag = steepness_verdict(th_chord_deg)
    if vflag:
        flags.append(vflag.replace("Steepest diffuser stage", "Diffuser chord angle"))
    R.update(verdict=verdict, severity=sev,
             L_for_7_mm=rise / math.tan(math.radians(7)) * 1e3)

    # the spline gets steeper toward the exit: check the exit tangent too
    if th_exit_deg > 20:
        flags.append(f"Spline exit tangent {th_exit_deg:.1f} deg is outside all the "
                     "test data (max 20 deg). The last part of the ramp will very "
                     "likely separate.")
        sev = max(sev, 3)
    elif th_exit_deg > 14:
        flags.append(f"Spline exit tangent {th_exit_deg:.1f} deg is past the 14 deg "
                     "stall seen by Katz. The rear of the ramp may separate. Less "
                     "pressure recovery is left there, so it costs less than a "
                     "steep entry would, but check the exit in CFD.")
        sev = max(sev, 2)
    elif th_exit_deg > 10 and th_chord_deg <= 7:
        flags.append(f"Spline exit tangent {th_exit_deg:.1f} deg is over 10 deg even "
                     "though the chord is mild: watch the rear third in CFD.")
    R["severity"] = sev
    if a > 0 and a > 0.6 * L_d:
        flags.append("Horizontal control line is over 60 % of the diffuser length: "
                     "the expansion is bunched at the rear, so the spline behaves "
                     "like a short, steep diffuser.")

    # rake
    if abs(inp.rake_deg) > 0:
        flags.append(f"Rake {inp.rake_deg:+.1f} deg changes every diffuser angle by "
                     "the same amount. Check the verdict at max pitch under braking "
                     "and acceleration too.")
    # planform flare
    if flare_deg > 7:
        flags.append(f"Planform flare {flare_deg:.1f} deg per side: the sidewalls can "
                     "separate as well as the ramp [HEURISTIC 7 deg limit].")
    if W_out < W_in:
        flags.append("Diffuser narrows toward the exit: it loses area ratio.")

    # ---------------- entry and inlet ----------------
    if R0 < H_t and th_max_deg > 7:
        flags.append(f"Tight diffuser entry (radius {R0*1e3:.0f} mm) with a "
                     f"{th_max_deg:.0f} deg ramp: flow separates at a sharp entrance "
                     "and relies on side vortices to reattach (Katz/Cooper). KTH "
                     "found a gradual transition gives a smoother pressure. "
                     "Lengthen the horizontal control line. [HEURISTIC] aim for "
                     "r >= 1-2x throat height.")
    if inp.H_le_mm > 1.25 * inp.H_t_mm:
        flags.append("Floor leading edge is well above the throat: Barnard (via KTH) "
                     "finds no downforce gain from inlet compression and a local "
                     "lift spot at the inlet.")
    front_floor_mm = inp.H_le_mm + L_flat * math.tan(rake) * 1e3
    lowest_mm = min(inp.H_t_mm, front_floor_mm)
    R.update(front_floor_mm=front_floor_mm, lowest_mm=lowest_mm)
    if lowest_mm < inp.h_min_rule_mm:
        flags.append(f"Lowest floor point {lowest_mm:.1f} mm is below the "
                     f"{inp.h_min_rule_mm:.1f} mm clearance rule.")

    # ---------------- side edges ----------------
    if inp.side_edge == "skirts (near-sealed)":
        flags.append("Near-sealed skirts kill the edge vortices. George & Donis saw "
                     "downforce loss and asymmetric diffuser flow with sealed "
                     "skirts. Treat the estimate as optimistic.")
    elif inp.side_edge == "open":
        flags.append("Open sides: the edge vortices form a 'false seal' (Katz via "
                     "Jensen) but leak in air. Side plates/endplates were on "
                     "all of the Ruhrmann/Senior test models.")

    # ---------------- critical (stall) ride height ----------------
    # Ruhrmann: max downforce near h/(d*theta) = 0.7, d = half-width
    h_crit = 0.7 * (W_in / 2.0) * math.radians(th_chord_deg)
    margin = H_t / h_crit if h_crit > 0 else float("inf")
    R.update(h_crit_mm=h_crit * 1e3, margin=margin,
             rules_set_floor=h_crit < h_min)
    if margin < 1.0:
        flags.append("Throat height is BELOW the critical ride height: downforce "
                     "collapse zone.")
    elif margin < 1.3:
        flags.append("Margin to critical ride height under 30 %: bumps / heave / "
                     "pitch may stall the diffuser.")

    # ---------------- downforce ----------------
    DF, out = undertray_model(H_t, G, q, inp, h_crit)
    x_cp_car = x_inlet - L_flat + out["xcp"]
    front_pct = 100.0 * (1.0 - x_cp_car / wheelbase)
    weight = inp.mass_kg * 9.81
    R.update(DF=DF, DF_lo=0.7 * DF, DF_hi=1.3 * DF, CLA=DF / q, out=out,
             xcp_pct=100.0 * out["xcp"] / (L_flat + L_d), front_pct=front_pct,
             pct_weight=100.0 * DF / weight if weight > 0 else 0.0,
             speeds={v: DF * (v / inp.V_kph) ** 2 for v in (40, 60, 80, 100)})
    if x_cp_car > wheelbase:
        flags.append("Undertray centre of pressure is behind the rear axle: it "
                     "unloads the front axle.")
    elif x_cp_car < 0:
        flags.append("Undertray centre of pressure is ahead of the front axle.")

    # ---------------- ride-height sweep ----------------
    h_vec = np.linspace(0.5 * H_t, 2.0 * H_t, 80)
    DF_vec = np.array([undertray_model(h, G, q, inp, h_crit)[0] for h in h_vec])
    ip = int(np.argmax(DF_vec))
    dfp = undertray_model(H_t + 0.005, G, q, inp, h_crit)[0]
    dfm = undertray_model(max(H_t - 0.005, 1e-3), G, q, inp, h_crit)[0]
    R.update(h_vec=h_vec * 1e3, DF_vec=DF_vec, DF_peak=float(DF_vec[ip]),
             h_peak_mm=float(h_vec[ip] * 1e3),
             pct_of_peak=100.0 * DF / float(DF_vec[ip]) if DF_vec[ip] else 0.0,
             d_plus=100.0 * (dfp / DF - 1.0) if DF else 0.0,
             d_minus=100.0 * (dfm / DF - 1.0) if DF else 0.0)
    if DF and dfm < 0.85 * DF:
        flags.append("Losing over 15 % downforce for -5 mm ride height: you are "
                     "sitting on the stall cliff.")

    # floor pressure distribution for the plot
    R["cp_x"] = [0.0, L_flat, L_flat, L_flat + L_d]
    R["cp_y"] = [0.0, out["Cp_flat"], out["Cp1"], inp.Cp_exit]

    # ---------------- boundary layer ----------------
    if L_flat > 0:
        Re_x = rho * V * L_flat / mu
        delta = 0.37 * L_flat * Re_x ** (-0.2)
    else:
        delta = 1e-3
    R.update(delta_mm=delta * 1e3, delta_pct=100.0 * delta / H_t)
    if delta / H_t > 0.5:
        flags.append("Underbody boundary layer fills over half the throat: expect "
                     "weaker pumping than the model.")

    # ---------------- strakes ----------------
    H_half = H_t / 2.0
    th_eq_deg = th_chord_deg
    f_ang = min(max((th_max_deg - 3.0) / (10.0 - 3.0), 0.0), 1.0)
    x_TE = -2.0 * H_half
    S = {"layout": inp.vg_layout, "x_TE_mm": x_TE * 1e3,
         "optional": th_max_deg < 5}
    W_ch = (W_in - W_div_total) / n_ch
    if inp.vg_layout == "same":
        h_vg = 0.4 * H_half                 # [HEURISTIC] James Vd4 end of range
        l_vg = 4.0 * h_vg
        d_gap = 2.0 * h_vg                  # Katz d/h = 2 (Logdberg: <3h may interfere)
        n_per = max(int(inp.vg_n_per_channel), 2)   # Rossow: at least 2
        W_cluster = (n_per - 1) * d_gap
        S.update(n_strakes=n_ch * n_per, n_per=n_per, n_ch=n_ch,
                 h_mm=h_vg * 1e3, l_mm=l_vg * 1e3, alpha=20.0, alpha_outer=30.0,
                 d_mm=d_gap * 1e3, W_cluster_mm=W_cluster * 1e3,
                 W_ch_mm=W_ch * 1e3)
        if W_cluster > 0.5 * W_ch:
            flags.append("Same-direction strake cluster takes over half the "
                         "channel width: reduce the count.")
        flags.append("Same-direction strakes are a downforce / edge-vortex device: "
                     "weaker for separation control than counter-rotating pairs.")
    else:
        h_vg = 0.2 * H_half                 # James Vd3
        l_vg = 4.0 * h_vg
        alpha = 15.0 + 7.0 * f_ang          # [HEURISTIC]
        D_pair = 8.33 * h_vg                # Pearcy D ~ 8-10 h
        d_gap = D_pair / 4.0                # D/d ~ 4
        W_vg = inp.vg_width_fraction * (W_in - W_div_total)
        n_pairs = max(int(W_vg // D_pair), 1)
        S.update(n_strakes=2 * n_pairs, n_pairs=n_pairs, n_ch=1,
                 h_mm=h_vg * 1e3, l_mm=l_vg * 1e3, alpha=alpha,
                 d_mm=d_gap * 1e3, D_mm=D_pair * 1e3, W_vg_mm=W_vg * 1e3)
        if 2 * n_pairs > 12:
            flags.append(f"{2*n_pairs} strakes is a lot of tiny parts: use fewer, "
                         "larger vanes (0.4 x half-throat) in the centre, "
                         "width fraction 0.5.")
    S["h_over_delta"] = h_vg / delta
    if h_vg / delta < 0.3:
        flags.append("Strakes are small vs the boundary layer (h/delta < 0.3): "
                     "try 0.4 x half-throat height (James Vd4).")
    R["strakes"] = S
    R["geom"] = dict(L_d=L_d, H_t=H_t, He=He_eff, W_in=W_in,
                     W_out=W_out, W_floor=W_floor, L_flat=L_flat, x_TE=x_TE,
                     n_ch=n_ch, t_div=t_div,
                     H_le=inp.H_le_mm * mm, rake=rake,
                     front_floor=front_floor_mm * mm, th_eq_deg=th_eq_deg)
    return R


def format_report(inp: Inputs, R: dict) -> str:
    """Plain-text report (shown in the GUI and exportable)."""
    if "error" in R:
        return "INPUT ERROR: " + R["error"]
    o, S = R["out"], R["strakes"]
    L = []
    a = L.append
    a("UNDERTRAY MASTER - screening report")
    a("=" * 64)
    a("AIR AND SPEED")
    a(f"  Density             : {R['rho']:.3f} kg/m^3 ({100*R['rho_ratio']:.0f} % of "
      f"sea level) at {inp.altitude_m:.0f} m, {inp.temp_C:.0f} C")
    a(f"  Speed / q           : {inp.V_kph:.0f} km/h / {R['q']:.0f} Pa")
    a("")
    a("DIFFUSER GEOMETRY (angles include rake)")
    a(f"  Spline input        : horizontal line {inp.a_mm:.0f} mm, angled line "
      f"{inp.b_mm:.0f} mm at {inp.theta_deg:.1f} deg")
    a(f"  Diffuser length     : {R['L_d_mm']:.0f} mm, rise {R['rise_mm']:.1f} mm")
    a(f"  Chord angle         : {R['th_chord_deg']:.1f} deg  (equivalent straight ramp)")
    a(f"  Entry / exit tangent: {R['th_entry_deg']:.1f} / {R['th_exit_deg']:.1f} deg")
    aa = R["ang_at"]
    a(f"  Local angle 25/50/75/100 % : {aa[0.25]:.1f} / {aa[0.5]:.1f} / "
      f"{aa[0.75]:.1f} / {aa[1.0]:.1f} deg")
    a(f"  Entry radius        : {R['R0_mm']:.0f} mm  (curvature at the throat)")
    a(f"  Effective exit ht   : {R['He_eff_mm']:.1f} mm")
    a(f"  Area ratio (height) : {R['AR_h']:.2f}")
    a(f"  Area ratio (3-D)    : {R['AR3']:.2f}  (incl. planform flare "
      f"{R['flare_deg']:.1f} deg per side)")
    a(f"  Length for 7 deg    : {R['L_for_7_mm']:.0f} mm for the same rise")
    a(f"  Front floor height  : {R['front_floor_mm']:.1f} mm  (lowest point "
      f"{R['lowest_mm']:.1f} mm)")
    a(f"  Side edges          : {inp.side_edge}")
    a(f"  Verdict (chord)     : {R['verdict']}")
    a("")
    a("CRITICAL RIDE HEIGHT  (Ruhrmann: h/(d*theta) = 0.7, d = half inlet width)")
    a(f"  Critical height     : {R['h_crit_mm']:.1f} mm")
    a(f"  Your throat height  : {inp.H_t_mm:.1f} mm   (margin x{R['margin']:.2f})")
    if R["rules_set_floor"]:
        a("  (critical height is below the rule limit: rules, not stall, set "
          "your floor)")
    a("")
    a("ESTIMATED AERO (undertray only, +/-30 %)")
    a(f"  Diffuser efficiency : {o['eta']:.2f}   [HEURISTIC, from chord angle]")
    a(f"  Pressure recovery   : Cpd = {o['Cpd']:.2f}   (KTH CFD tunnel: 0.53)")
    a(f"  Throat Cp           : {o['Cp1']:.2f}   (KTH CFD ~ -1.7, Katz/Senior ~ -2)")
    a(f"  Downforce           : {R['DF']:.0f} N at {inp.V_kph:.0f} km/h   "
      f"(range {R['DF_lo']:.0f} - {R['DF_hi']:.0f} N)")
    a(f"  CLA (-L/q)          : {R['CLA']:.2f} m^2")
    a(f"  % of car weight     : {R['pct_weight']:.1f} %  ({inp.mass_kg:.0f} kg car + driver)")
    a(f"  Load centre         : {R['xcp_pct']:.0f} % of floor length behind the nose")
    a(f"  Axle split          : {R['front_pct']:.0f} % front / "
      f"{100 - R['front_pct']:.0f} % rear")
    a("  Speed scaling       : " + "   ".join(
        f"{v} km/h = {f:.0f} N" for v, f in R["speeds"].items()))
    a("  Drag                : not predicted, get it from CFD")
    a("  Papers' sensitivities: 1 deg roll ~ -6 % downforce; 5 deg yaw ~ +24 %")
    a("                        on the whole car (Jensen CFD)")
    a("")
    a("RIDE-HEIGHT SENSITIVITY (rigid heave, angles fixed)")
    a(f"  Peak downforce      : {R['DF_peak']:.0f} N at {R['h_peak_mm']:.1f} mm "
      f"(design point is {R['pct_of_peak']:.0f} % of peak)")
    a(f"  +5 mm / -5 mm       : {R['d_plus']:+.0f} % / {R['d_minus']:+.0f} %")
    a("")
    a("BOUNDARY LAYER")
    a(f"  Underbody BL at diffuser inlet ~ {R['delta_mm']:.0f} mm "
      f"({R['delta_pct']:.0f} % of throat height)")
    a("")
    a(f"STRAKES ({S['layout']} layout)")
    if S["optional"]:
        a(f"  Strakes are OPTIONAL: steepest stage {R['th_max_deg']:.1f} deg is "
          "mild; they mostly add drag.")
    a(f"  Number of strakes   : {S['n_strakes']}")
    if S["layout"] == "same":
        a(f"    ({S['n_per']} per channel x {S['n_ch']} channels, all the same "
          "direction, mirrored left/right)")
    else:
        a(f"    ({S['n_pairs']} counter-rotating pairs over {S['W_vg_mm']:.0f} mm)")
    a(f"  Height              : {S['h_mm']:.1f} mm   (h/delta = {S['h_over_delta']:.2f})")
    a(f"  Length              : {S['l_mm']:.1f} mm")
    if S["layout"] == "same":
        a(f"  Angle               : {S['alpha']:.0f} deg inner, "
          f"{S['alpha_outer']:.0f} deg outer vane")
        a("                        Point the trailing ends toward the channel edge")
        a("                        (my reading of Katz: feeds the edge vortices).")
        a(f"  Gap between strakes : {S['d_mm']:.1f} mm  (d = 2h)")
        a(f"  Cluster width       : {S['W_cluster_mm']:.1f} mm of a "
          f"{S['W_ch_mm']:.0f} mm channel")
    else:
        a(f"  Angle               : {S['alpha']:.1f} deg (alternate sign in each pair)")
        a(f"  Gap within pair     : {S['d_mm']:.1f} mm")
        a(f"  Pair spacing        : {S['D_mm']:.1f} mm")
    a(f"  Trailing edge at    : {S['x_TE_mm']:.0f} mm from the throat (upstream)")
    a("")
    a("FLAGS")
    if R["flags"]:
        for i, f in enumerate(R["flags"], 1):
            a(f"  {i}) {f}")
    else:
        a("  No flags raised.")
    a("")
    a("Validate in CFD: near-ground diffuser flow is 3-D and unsteady near stall "
      "(hysteresis,")
    a("asymmetric vortices), which a screening model cannot capture.")
    return "\n".join(L)


# ============================================================================
#  PART 2 - GUI (PySide6 + matplotlib)
# ============================================================================

def run_gui():
    # Import matplotlib (and dateutil/six, which it pulls in) BEFORE PySide6.
    # PySide6's import hook crashes on old versions of 'six' when they are
    # imported after Qt ("_SixMetaPathImporter object has no attribute _path").
    # Also fixed by:  pip install -U six python-dateutil
    import matplotlib
    matplotlib.use("QtAgg")
    import matplotlib.dates  # noqa: F401  (loads dateutil + six early)
    from matplotlib.figure import Figure
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
        QFormLayout, QGroupBox, QDoubleSpinBox, QSpinBox, QComboBox, QLabel,
        QPushButton, QTabWidget, QPlainTextEdit, QScrollArea, QFileDialog,
        QMessageBox)
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    SEV_COLORS = {0: "#3b82f6", 1: "#16a34a", 2: "#ca8a04", 3: "#ea580c",
                  4: "#dc2626"}

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Undertray Master")
            self.resize(1400, 900)
            self.defaults = Inputs()
            self.widgets = {}
            self.combos = {}
            self.last = None

            central = QWidget()
            self.setCentralWidget(central)
            root = QHBoxLayout(central)

            # ---------------- left: inputs ----------------
            left = QWidget()
            lv = QVBoxLayout(left)
            self._group(lv, "Diffuser profile (heights at zero rake)", [
                ("H_t_mm", "Throat height (mm)", 5, 300, 0.5, 1, "Floor clearance at the diffuser inlet"),
                ("a_mm", "Horizontal control line (mm)", 0, 3000, 1, 1, "Spline handle leaving the throat horizontally. 0 = straight ramp"),
                ("theta_deg", "Control line angle (deg)", 0.1, 40, 0.1, 2, "Angle of the angled control line = exit tangent angle"),
                ("b_mm", "Angled control line (mm)", 1, 3000, 1, 1, "Length from the end of the horizontal line to the exit point"),
            ])
            self._group(lv, "Floor and widths", [
                ("L_flat_mm", "Flat floor length (mm)", 0, 4000, 1, 0, "Flat floor ahead of the diffuser inlet"),
                ("H_le_mm", "Floor leading-edge height (mm)", 5, 400, 0.5, 1, "Inlet height at the front of the floor"),
                ("W_floor_mm", "Floor width (mm)", 100, 2000, 1, 0, ""),
                ("W_in_mm", "Diffuser inlet width (mm)", 100, 2000, 1, 0, "Total across all channels"),
                ("W_out_mm", "Diffuser exit width (mm)", 100, 2500, 1, 0, "Larger than inlet = planform flare"),
                ("t_div_mm", "Divider / fence thickness (mm)", 0, 50, 0.5, 1, "Each channel divider"),
            ])
            ag = QGroupBox("Attitude and edges")
            af = QFormLayout(ag)
            self.widgets["rake_deg"] = self._spin(af, "Rake (deg, + nose down)", -3.0, 3.0, 0.1, 2, self.defaults.rake_deg,
                                                  "Pitch adds to every diffuser angle")
            self.widgets["n_channels"] = self._spin_int(af, "Diffuser channels", 1, 6, self.defaults.n_channels)
            self.combos["side_edge"] = self._combo(af, "Side edges", SIDE_EDGE_OPTIONS, self.defaults.side_edge,
                                                   "open / endplates / near-sealed skirts")
            lv.addWidget(ag)
            self._group(lv, "Air and speed", [
                ("V_kph", "Speed (km/h)", 10, 300, 1, 0, "Design speed"),
                ("altitude_m", "Altitude (m)", -100, 4000, 10, 0, "Fort Collins ~1525 m, FSAE Michigan ~300 m"),
                ("temp_C", "Air temperature (C)", -20, 50, 1, 0, ""),
            ])
            self._group(lv, "Vehicle and rules", [
                ("wheelbase_mm", "Wheelbase (mm)", 1000, 4000, 1, 0, ""),
                ("x_inlet_mm", "Diffuser inlet behind front axle (mm)", 0, 4000, 1, 0, "Used only for the axle load split"),
                ("mass_kg", "Car + driver mass (kg)", 100, 1500, 1, 0, ""),
                ("h_min_rule_mm", "Min ground clearance rule (mm)", 0, 100, 0.1, 1, "FSAE 1 in = 25.4 mm. Check the current rulebook."),
            ])
            sg = QGroupBox("Strakes")
            sf = QFormLayout(sg)
            self.combos["vg_layout"] = self._combo(
                sf, "Layout", ["same", "counter"], self.defaults.vg_layout,
                "same = all strakes in a channel angled the same way (two-channel "
                "diffuser, Katz & Morey)\ncounter = counter-rotating pairs "
                "(separation control)")
            self.widgets["vg_n_per_channel"] = self._spin_int(sf, "Strakes per channel ('same')", 2, 12,
                                                              self.defaults.vg_n_per_channel)
            self.widgets["vg_width_fraction"] = self._spin(sf, "Width fraction ('counter')", 0.1, 1.0, 0.05, 2,
                                                           self.defaults.vg_width_fraction,
                                                           "Fraction of the width that gets strake pairs")
            lv.addWidget(sg)
            self._group(lv, "Model knobs (calibrate to your CFD)", [
                ("Cp_exit", "Exit Cp (base pressure)", -1.0, 0.5, 0.05, 2, "Senior & Zhang saw it slightly negative. A rear wing above the exit lowers it."),
                ("k_cal", "Realism factor k_cal", 0.2, 1.2, 0.01, 2, "[HEURISTIC] multiplier on pressure recovery. Set it so the throat Cp matches your CFD."),
                ("f_flat", "Flat-floor Cp fraction", 0.0, 1.0, 0.05, 2, "[HEURISTIC] mean floor Cp as a fraction of the throat Cp"),
                ("collapse_slope", "Stall collapse slope", 0.0, 5.0, 0.1, 1, "Fit to Senior & Zhang 17 deg: -33 % for a 24 % fall in h/d"),
            ])
            btns = QHBoxLayout()
            b_reset = QPushButton("Reset defaults")
            b_reset.clicked.connect(self.reset)
            b_save = QPushButton("Export report...")
            b_save.clicked.connect(self.export)
            btns.addWidget(b_reset)
            btns.addWidget(b_save)
            lv.addLayout(btns)
            lv.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(left)
            scroll.setMinimumWidth(420)
            scroll.setMaximumWidth(480)
            root.addWidget(scroll)

            # ---------------- right: verdict + tabs ----------------
            right = QWidget()
            rv = QVBoxLayout(right)
            self.banner = QLabel("")
            self.banner.setWordWrap(True)
            rv.addWidget(self.banner)
            self.kpis = QLabel("")
            self.kpis.setTextFormat(Qt.RichText)
            rv.addWidget(self.kpis)

            tabs = QTabWidget()
            self.report = QPlainTextEdit()
            self.report.setReadOnly(True)
            mono = QFont("Consolas" if sys.platform.startswith("win") else "Menlo")
            mono.setStyleHint(QFont.Monospace)
            mono.setPointSize(10)
            self.report.setFont(mono)
            tabs.addTab(self.report, "Report")

            self.fig = Figure(figsize=(8, 7.5), tight_layout=True)
            self.canvas = FigureCanvasQTAgg(self.fig)
            gs = self.fig.add_gridspec(2, 2)
            self.ax_sweep = self.fig.add_subplot(gs[0, 0])
            self.ax_cp = self.fig.add_subplot(gs[0, 1])
            self.ax_side = self.fig.add_subplot(gs[1, 0])
            self.ax_plan = self.fig.add_subplot(gs[1, 1])
            tabs.addTab(self.canvas, "Plots")
            rv.addWidget(tabs, 1)
            root.addWidget(right, 1)

            self.update_all()

        # ---------- widget builders ----------
        def _spin(self, form, label, lo, hi, step, dec, val, tip=""):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setSingleStep(step)
            s.setDecimals(dec)
            s.setValue(val)
            s.setKeyboardTracking(False)
            if tip:
                s.setToolTip(tip)
            s.valueChanged.connect(self.update_all)
            form.addRow(label, s)
            return s

        def _spin_int(self, form, label, lo, hi, val):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setKeyboardTracking(False)
            s.valueChanged.connect(self.update_all)
            form.addRow(label, s)
            return s

        def _combo(self, form, label, items, val, tip=""):
            c = QComboBox()
            c.addItems(items)
            c.setCurrentText(val)
            if tip:
                c.setToolTip(tip)
            c.currentIndexChanged.connect(self.update_all)
            form.addRow(label, c)
            return c

        def _group(self, layout, title, rows):
            g = QGroupBox(title)
            f = QFormLayout(g)
            for key, label, lo, hi, step, dec, tip in rows:
                self.widgets[key] = self._spin(f, label, lo, hi, step, dec,
                                               getattr(self.defaults, key), tip)
            layout.addWidget(g)

        # ---------- actions ----------
        def read_inputs(self) -> Inputs:
            inp = Inputs()
            for k, w in self.widgets.items():
                setattr(inp, k, w.value())
            for k, c in self.combos.items():
                setattr(inp, k, c.currentText())
            inp.n_channels = int(inp.n_channels)
            inp.vg_n_per_channel = int(inp.vg_n_per_channel)
            return inp

        def reset(self):
            d = Inputs()
            for k, w in self.widgets.items():
                w.blockSignals(True)
                w.setValue(getattr(d, k))
                w.blockSignals(False)
            for k, c in self.combos.items():
                c.blockSignals(True)
                c.setCurrentText(getattr(d, k))
                c.blockSignals(False)
            self.update_all()

        def export(self):
            if not self.last:
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "Export report", "undertray_report.txt", "Text (*.txt)")
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(self.last)
                except OSError as e:
                    QMessageBox.warning(self, "Export failed", str(e))

        def update_all(self, *_):
            inp = self.read_inputs()
            same = inp.vg_layout == "same"
            self.widgets["vg_n_per_channel"].setEnabled(same)
            self.widgets["vg_width_fraction"].setEnabled(not same)
            R = compute(inp)
            txt = format_report(inp, R)
            self.last = txt
            self.report.setPlainText(txt)

            if "error" in R:
                self.banner.setText("INPUT ERROR: " + R["error"])
                self.banner.setStyleSheet("padding:8px; color:white; background:#dc2626; font-weight:bold;")
                self.kpis.setText("")
                for ax in (self.ax_sweep, self.ax_cp, self.ax_side, self.ax_plan):
                    ax.clear()
                self.canvas.draw_idle()
                return

            ang = (f"Spline diffuser: {R['th_chord_deg']:.1f} deg chord, "
                   f"{R['th_exit_deg']:.1f} deg exit tangent")
            self.banner.setText(f"{ang} - {R['verdict']}")
            self.banner.setStyleSheet(
                f"padding:8px; color:white; font-weight:bold; "
                f"background:{SEV_COLORS[R['severity']]};")
            S = R["strakes"]
            margin_col = "#dc2626" if R["margin"] < 1.0 else (
                "#ca8a04" if R["margin"] < 1.3 else "#16a34a")
            self.kpis.setText(
                f"<table cellpadding=4><tr>"
                f"<td><b>Downforce</b><br>{R['DF']:.0f} N "
                f"<small>({R['DF_lo']:.0f}-{R['DF_hi']:.0f})</small></td>"
                f"<td><b>CLA</b><br>{R['CLA']:.2f} m&sup2;</td>"
                f"<td><b>% weight</b><br>{R['pct_weight']:.1f} %</td>"
                f"<td><b>Area ratio</b><br>{R['AR3']:.2f}</td>"
                f"<td><b>Critical height</b><br>{R['h_crit_mm']:.1f} mm "
                f"<span style='color:{margin_col}'>(x{R['margin']:.2f})</span></td>"
                f"<td><b>Axle split</b><br>{R['front_pct']:.0f}/{100-R['front_pct']:.0f} F/R</td>"
                f"<td><b>Strakes</b><br>{S['n_strakes']} x (h {S['h_mm']:.1f}, "
                f"l {S['l_mm']:.0f} mm) @ {S['alpha']:.0f} deg</td>"
                f"<td><b>Flags</b><br>{len(R['flags'])}</td></tr></table>")
            self.draw_plots(inp, R)

        # ---------- plots ----------
        def draw_plots(self, inp, R):
            ax = self.ax_sweep
            ax.clear()
            ax.plot(R["h_vec"], R["DF_vec"], "b-", lw=1.8, label="Est. downforce")
            ax.axvline(inp.H_t_mm, color="k", ls="--", label="Design height")
            ax.axvline(R["h_crit_mm"], color="r", ls="--", label="Critical (stall)")
            ax.axvline(inp.h_min_rule_mm, color="m", ls=":", label="Clearance rule")
            ax.plot([inp.H_t_mm], [R["DF"]], "ko")
            ax.set_xlabel("Throat / ride height (mm)")
            ax.set_ylabel(f"Downforce at {inp.V_kph:.0f} km/h (N)")
            ax.set_title("Ride-height sweep (screening model)")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=7)

            ax = self.ax_cp
            ax.clear()
            ax.plot(R["cp_x"], R["cp_y"], "b-o", lw=1.6)
            ax.invert_yaxis()
            ax.set_xlabel("Distance from undertray nose (m)")
            ax.set_ylabel("Cp (suction up)")
            ax.set_title("Assumed floor pressure distribution")
            ax.grid(True, alpha=0.3)

            self.draw_side(R)
            self.draw_plan(R)
            self.canvas.draw_idle()

        def draw_side(self, R):
            """Side view of the floor profile with rake, in mm (not to scale vertically)."""
            ax = self.ax_side
            ax.clear()
            g = R["geom"]
            Lf = g["L_flat"] * 1e3
            xs = [-Lf] + list(R["spline_x"])
            ys = [g["front_floor"] * 1e3] + list(R["spline_y"])
            ax.fill_between(xs, ys, max(ys) * 1.25, color="#cbd5e1")
            ax.plot(xs, ys, "k-", lw=1.8)
            cx, cy = zip(*R["ctrl"])
            ax.plot(cx, cy, "b-.", lw=1.0, label="control lines")
            ax.plot(cx, cy, "b*", ms=7)
            ax.plot([cx[0], cx[2]], [cy[0], cy[2]], color="gray", ls=":", lw=1.0,
                    label=f"chord {R['th_chord_deg']:.1f} deg")
            ax.legend(fontsize=7, loc="upper left")
            ax.axhline(0, color="k", lw=2)
            ax.text(xs[0], -0.1 * max(ys), "ground", fontsize=8)
            ax.annotate(f"throat {ys[1]:.0f} mm", (0, ys[1]), xytext=(0, ys[1] * 0.35),
                        fontsize=8, arrowprops=dict(arrowstyle="->"))
            ax.annotate(f"exit {ys[-1]:.0f} mm", (xs[-1], ys[-1]),
                        xytext=(xs[-1] - 0.25 * (xs[-1] - xs[0]), ys[-1] * 0.6),
                        fontsize=8, arrowprops=dict(arrowstyle="->"))
            ax.set_xlim(xs[0] - 50, xs[-1] + 50)
            ax.set_ylim(-0.15 * max(ys), max(ys) * 1.25)
            ax.set_xlabel("x from throat (mm)")
            ax.set_ylabel("height (mm, vertical exaggerated)")
            ax.set_title(f"Side view incl. rake {math.degrees(g['rake']):+.1f} deg")
            ax.grid(True, alpha=0.2)

        def draw_plan(self, R):
            """Plan view: channels and strakes (illustrative, mm)."""
            ax = self.ax_plan
            ax.clear()
            g, S = R["geom"], R["strakes"]
            Ld = g["L_d"] * 1e3
            Wi, Wo = g["W_in"] * 1e3, g["W_out"] * 1e3
            x_te = g["x_TE"] * 1e3
            x0 = x_te - max(4.0 * S["l_mm"] + 60.0, 120.0)
            Wmax = max(Wi, Wo)
            yc = Wmax / 2.0
            # diffuser outline with flare, flow left -> right
            ax.plot([x0, 0, Ld, Ld, 0, x0, x0],
                    [yc - Wi / 2, yc - Wi / 2, yc - Wo / 2, yc + Wo / 2,
                     yc + Wi / 2, yc + Wi / 2, yc - Wi / 2], "k-", lw=1.2)
            ax.axvline(0, color="gray", ls="--")
            ax.text(0, yc + Wmax * 0.53, "throat", ha="center", fontsize=8)
            n_ch = g["n_ch"]
            for k in range(1, n_ch):
                fr = k / n_ch
                ax.plot([0, Ld], [yc - Wi / 2 + fr * Wi, yc - Wo / 2 + fr * Wo],
                        color="gray", lw=max(1.0, g["t_div"] * 1e3 / 2))
            ax.annotate("", xy=(x0 + 80, -0.06 * Wmax), xytext=(x0, -0.06 * Wmax),
                        arrowprops=dict(arrowstyle="->"))
            ax.text(x0 + 90, -0.06 * Wmax, "flow", fontsize=8, va="center")

            l = S["l_mm"]
            y_lo0 = yc - Wi / 2
            if S["layout"] == "same":
                W_ch = Wi / n_ch
                for c in range(n_ch):
                    y_lo = y_lo0 + c * W_ch
                    toward_up = (c + 0.5) > n_ch / 2.0 or n_ch == 1
                    edge_y = y_lo + W_ch if toward_up else y_lo
                    for i in range(S["n_per"]):
                        off = i * S["d_mm"]
                        yt = (edge_y - 0.1 * W_ch - off) if toward_up else \
                             (edge_y + 0.1 * W_ch + off)
                        a_deg = S["alpha"] if i == 0 else S["alpha_outer"]
                        sign = 1 if toward_up else -1
                        ax.plot([x_te - l * math.cos(math.radians(a_deg)), x_te],
                                [yt - sign * l * math.sin(math.radians(a_deg)), yt],
                                "r-", lw=2.5)
            else:
                ca, sa = math.cos(math.radians(S["alpha"])), math.sin(math.radians(S["alpha"]))
                npairs = min(S["n_pairs"], 25)
                step = S["D_mm"]
                y_start = yc - 0.5 * (npairs - 1) * step
                for p in range(npairs):
                    ycp = y_start + p * step
                    for sgn, dy in ((1, -S["d_mm"] / 2), (-1, S["d_mm"] / 2)):
                        yt = ycp + dy
                        ax.plot([x_te - l * ca, x_te], [yt - sgn * l * sa, yt],
                                "r-", lw=1.6)
            ax.set_xlim(x0 - 0.04 * (Ld - x0), Ld + 0.04 * (Ld - x0))
            ax.set_ylim(-0.2 * Wmax, 1.12 * Wmax)
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlabel("x from throat (mm)")
            ax.set_ylabel("span (mm)")
            ax.set_title(f"Plan view, strakes ({S['layout']}, illustrative)")
            ax.grid(True, alpha=0.2)

    app = QApplication.instance() or QApplication(sys.argv)
    w = Window()
    w.show()
    return app, w


if __name__ == "__main__":
    app, win = run_gui()
    sys.exit(app.exec())