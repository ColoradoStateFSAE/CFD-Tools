"""
Results exporter for Ram Racing CFD simulations.

Exports a clean .txt report containing:
  - Total downforce (FW + RW + undertray)
  - Total drag (whole car)
  - Aerodynamic system drag (FW + RW + undertray only)
  - CoP % (front/rear) via Ram Racing MATLAB-ported equations
  - SCz (downforce coefficient)
  - SCx (drag coefficient)
  - Any extra user-defined result zones

CoP equations ported from Ram Racing MATLAB script.
"""
import os
import math
from datetime import datetime
from typing import Optional


def compute_scz_scx(downforce_lbf: float, drag_lbf: float,
                    speed_mph: float,
                    frontal_area_m2: float) -> tuple:
    """
    Compute SCz (downforce coeff) and SCx (drag coeff).
    Uses standard aero coefficient definition:
        C = F / (0.5 * rho * v^2 * A)
    where rho = 1.225 kg/m^3, F converted to N, A in m^2.

    Returns (SCz, SCx)
    """
    rho = 1.225               # kg/m^3 sea level
    v_ms = speed_mph * 0.44704
    q = 0.5 * rho * v_ms**2  # dynamic pressure [Pa]

    # Convert lbf → N (1 lbf = 4.44822 N)
    df_N   = downforce_lbf * 4.44822
    drag_N = drag_lbf      * 4.44822

    if q * frontal_area_m2 == 0:
        return 0.0, 0.0

    scz = df_N   / (q * frontal_area_m2)
    scx = drag_N / (q * frontal_area_m2)
    return scz, scx


def export_results(config,
                   raw_results: dict,
                   frontal_area_m2: Optional[float] = None) -> str:
    """
    Compute all derived metrics and write the results .txt file.

    raw_results keys expected from solver (at minimum):
        downforce_fw_lbf     - front wing downforce
        downforce_rw_lbf     - rear wing downforce
        downforce_ut_lbf     - undertray downforce
        drag_total_lbf       - total car drag
        drag_aero_lbf        - aero system drag (FW+RW+UT only)
        drag_rw_lbf          - rear wing drag (for CoP moment arm)
        [+ any extra keys from extra_result_zones]

    Returns the path to the written file.
    """
    # ── Force values ──────────────────────────────────────────────────────────
    ff  = raw_results.get("downforce_fw_lbf", 0.0)
    fr  = raw_results.get("downforce_rw_lbf", 0.0)
    fu  = raw_results.get("downforce_ut_lbf", 0.0)
    fdr = raw_results.get("drag_rw_lbf",      0.0)

    total_df   = ff + fr + fu
    total_drag = raw_results.get("drag_total_lbf", 0.0)
    aero_drag  = raw_results.get("drag_aero_lbf",  fdr)  # fallback to RW drag

    # ── CoP calculation ───────────────────────────────────────────────────────
    cop = config.cop_geometry.compute(ff, fr, fu, fdr)

    # ── Aero coefficients ─────────────────────────────────────────────────────
    area = frontal_area_m2 or 0.6  # use a sensible fallback if not provided
    scz, scx = compute_scz_scx(total_df, total_drag,
                                config.vehicle_speed_mph, area)

    # ── Multiplier for half-car ───────────────────────────────────────────────
    mult = 2.0 if config.is_half_symmetry else 1.0
    half_note = "  (half-car sim: all forces doubled)" if mult == 2.0 else ""

    # ── Extra user-defined zones ──────────────────────────────────────────────
    extra_lines = []
    for zone_def in config.extra_result_zones:
        label  = zone_def.get("label", "Unknown")
        key    = zone_def.get("result_key", label.lower().replace(" ", "_"))
        value  = raw_results.get(key, "N/A")
        unit   = zone_def.get("unit", "lbf")
        if isinstance(value, float):
            extra_lines.append(f"  {label:<30} {value * mult:>10.3f} {unit}")
        else:
            extra_lines.append(f"  {label:<30} {'N/A':>10}")

    # ── Build report ──────────────────────────────────────────────────────────
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "─" * 62

    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║         Ram Racing Aerodynamics — CFD Results Export         ║",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        f"  Simulation  : {config.name}",
        f"  Type        : {config.sim_type.value}",
        f"  Speed       : {config.vehicle_speed_mph:.1f} mph",
        f"  Exported    : {now}",
        f"  Geometry    : {os.path.basename(config.geometry_path)}",
        "",
        sep,
        "  DOWNFORCE (lbf)" + half_note,
        sep,
        f"  {'Front Wing':<30} {ff * mult:>10.3f} lbf",
        f"  {'Rear Wing':<30} {fr * mult:>10.3f} lbf",
        f"  {'Undertray':<30} {fu * mult:>10.3f} lbf",
        f"  {'TOTAL Downforce':<30} {total_df * mult:>10.3f} lbf",
        "",
        sep,
        "  DRAG (lbf)" + half_note,
        sep,
        f"  {'Total Car Drag':<30} {total_drag * mult:>10.3f} lbf",
        f"  {'Aero System Drag (FW+RW+UT)':<30} {aero_drag * mult:>10.3f} lbf",
        f"  {'Rear Wing Drag (for CoP)':<30} {fdr * mult:>10.3f} lbf",
        "",
        sep,
        "  CENTER OF PRESSURE",
        sep,
        f"  {'CoP from front axle':<30} {cop['x_cp']:>10.3f} in",
        f"  {'Aero Balance — Rear':<30} {cop['percent_rear'] * 100:>10.2f} %",
        f"  {'Aero Balance — Front':<30} {cop['percent_front'] * 100:>10.2f} %",
        f"  {'Resultant Force':<30} {cop['f_resultant'] * mult:>10.3f} lbf",
        f"  {'Resultant Angle from Vertical':<30} {cop['theta_deg']:>10.2f} deg",
        "",
        sep,
        "  AERODYNAMIC COEFFICIENTS",
        sep,
        f"  {'SCz (Downforce Coeff)':<30} {scz:>10.4f}",
        f"  {'SCx (Drag Coeff)':<30} {scx:>10.4f}",
        f"  {'L/D Ratio':<30} {(total_df / total_drag if total_drag else 0):>10.3f}",
        f"  {'Reference Area':<30} {area:>10.4f} m^2",
        "",
    ]

    if extra_lines:
        lines += [
            sep,
            "  ADDITIONAL ZONES",
            sep,
        ] + extra_lines + [""]

    lines += [
        sep,
        "  CoP EQUATION REFERENCE",
        sep,
        "  Mz  = (Fr*(L+Lr)) + (Fu*Lu) + (Fdr*H) - (Ff*Lf)",
        "  x_cp = Mz / Fy",
        "  W_RD = ((Fu*Lu) + (Fr*(L+Lr)) + (Fdr*H) - (Ff*Lf)) / L",
        "  W_FD = ((Ff*(L+Lf)) + (Fu*(L-Lu)) - (Fr*Lr) - (Fdr*H)) / L",
        "  % Rear = W_RD / (W_FD + W_RD)",
        "",
        f"  Wheelbase L = {config.cop_geometry.wheelbase:.2f} in",
        f"  Lf (FW CoP to front axle)    = {config.cop_geometry.lf:.3f} in",
        f"  Lr (RW CoP to rear axle)     = {config.cop_geometry.lr:.3f} in",
        f"  Lu (UT CoP to front axle)    = {config.cop_geometry.lu:.3f} in",
        f"  H  (RW drag CoP from ground) = {config.cop_geometry.rw_drag_height:.2f} in",
        "",
        sep,
        "  END OF REPORT",
        sep,
        "",
    ]

    report_text = "\n".join(lines)

    # ── Write file ────────────────────────────────────────────────────────────
    os.makedirs(config.results_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_"
                        for c in config.name).strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}_results.txt"
    filepath = os.path.join(config.results_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)

    return filepath
