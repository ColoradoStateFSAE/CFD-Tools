"""
Results exporter for Ram Racing CFD simulations.

CoP is derived entirely from simulation data (forces + pitching moments
reported by Fluent) — no hand-measured geometry constants required.

Moment convention:
  Fluent reports pitching moment about the front axle origin (0,0,0),
  Z axis, in lbf·m. We convert to lbf·in to stay consistent with the
  MATLAB script convention.

  Moment arm (effective CoP distance from front axle):
      arm = moment / downforce        [in]

  This is equivalent to the Lf, Lr, Lu geometry constants in the MATLAB
  script — derived from what Fluent actually computed, not hand-measured.

CoP equations (ported from Ram Racing MATLAB script):
    Fy   = Ff + Fr + Fu
    Fx   = Fdr   (rear wing drag is the dominant horizontal aero force)
    Mz   = moment_fw + moment_rw + moment_ut
    x_cp = Mz / Fy                          [in from front axle]
    % Rear  = x_cp / L
    % Front = 1 - % Rear
"""
import os
import math
from datetime import datetime
from typing import Optional


def _compute_scz_scx(downforce_lbf, drag_lbf, speed_mph, frontal_area_m2):
    rho   = 1.225
    v_ms  = speed_mph * 0.44704
    q     = 0.5 * rho * v_ms ** 2
    df_N  = downforce_lbf * 4.44822
    dr_N  = drag_lbf      * 4.44822
    denom = q * frontal_area_m2
    if denom == 0:
        return 0.0, 0.0
    return df_N / denom, dr_N / denom


def _derive_cop(raw, wheelbase_in):
    """
    Derive CoP metrics purely from Fluent simulation output.

    raw must contain (all already scaled for half-car):
        downforce_fw_lbf, downforce_rw_lbf, downforce_ut_lbf
        drag_rw_lbf
        moment_fw_lbf_in, moment_rw_lbf_in, moment_ut_lbf_in

    wheelbase_in: L in inches.
    """
    Ff  = raw.get("downforce_fw_lbf", 0.0)
    Fr  = raw.get("downforce_rw_lbf", 0.0)
    Fu  = raw.get("downforce_ut_lbf", 0.0)
    Fdr = raw.get("drag_rw_lbf",      0.0)

    Mf  = raw.get("moment_fw_lbf_in",  0.0)
    Mr  = raw.get("moment_rw_lbf_in",  0.0)
    Mu  = raw.get("moment_ut_lbf_in",  0.0)

    Fy = Ff + Fr + Fu
    Fx = Fdr
    L  = wheelbase_in

    Mz_total = Mf + Mr + Mu
    x_cp     = Mz_total / Fy if Fy != 0 else 0.0
    pct_rear  = x_cp / L if L != 0 else 0.0
    pct_front = 1.0 - pct_rear

    lf_derived = abs(Mf / Ff) if Ff != 0 else 0.0
    lr_derived = abs(Mr / Fr) if Fr != 0 else 0.0
    lu_derived = abs(Mu / Fu) if Fu != 0 else 0.0

    f_res = math.sqrt(Fx ** 2 + Fy ** 2)
    theta = 180 - (math.degrees(math.atan2(Fy, Fx)) + 90)

    return {
        "x_cp":        x_cp,
        "pct_rear":    pct_rear,
        "pct_front":   pct_front,
        "Mz_total":    Mz_total,
        "Fy":          Fy,
        "Fx":          Fx,
        "f_resultant": f_res,
        "theta_deg":   theta,
        "lf_derived":  lf_derived,
        "lr_derived":  lr_derived,
        "lu_derived":  lu_derived,
    }


def export_results(config, raw_results, frontal_area_m2=None,
                   mesh_quality: Optional[dict] = None):
    """
    Compute all derived metrics and write the results .txt file.
    Returns the path to the written file.

    mesh_quality: dict returned by _extract_mesh_quality() in runner.py.
                  When provided, a MESH QUALITY section is written before
                  the aerodynamic results.
    """
    mult = 2.0 if config.is_half_symmetry else 1.0

    # Forces (scaled for half-car)
    ff  = raw_results.get("downforce_fw_lbf", 0.0) * mult
    fr  = raw_results.get("downforce_rw_lbf", 0.0) * mult
    fu  = raw_results.get("downforce_ut_lbf", 0.0) * mult
    fdr = raw_results.get("drag_rw_lbf",      0.0) * mult

    total_df   = ff + fr + fu
    total_drag = raw_results.get("drag_total_lbf", 0.0) * mult
    aero_drag  = raw_results.get("drag_aero_lbf",  0.0) * mult

    # Scale moments too for half-car
    scaled = dict(raw_results)
    for k in ("downforce_fw_lbf", "downforce_rw_lbf", "downforce_ut_lbf",
              "drag_rw_lbf", "moment_fw_lbf_in", "moment_rw_lbf_in",
              "moment_ut_lbf_in", "moment_tot_lbf_in"):
        if k in scaled:
            scaled[k] = scaled[k] * mult

    wheelbase_in = getattr(config, "wheelbase_in", 62.0)
    cop = _derive_cop(scaled, wheelbase_in)

    area = frontal_area_m2 or 0.6
    scz, scx = _compute_scz_scx(total_df, total_drag,
                                 config.vehicle_speed_mph, area)

    # Extra user-defined zones
    extra_lines = []
    for zone_def in config.extra_result_zones:
        label = zone_def.get("label", "Unknown")
        key   = zone_def.get("result_key", label.lower().replace(" ", "_"))
        value = raw_results.get(key, "N/A")
        unit  = zone_def.get("unit", "lbf")
        if isinstance(value, float):
            extra_lines.append(f"  {label:<32} {value * mult:>10.3f} {unit}")
        else:
            extra_lines.append(f"  {label:<32} {'N/A':>10}")

    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep  = "-" * 64
    half = "  x2 (half-car)" if mult == 2.0 else ""

    lines = [
        "=" * 66,
        "   Ram Racing Aerodynamics -- CFD Results Export",
        "=" * 66,
        "",
        f"  Simulation  : {config.name}",
        f"  Type        : {config.sim_type.value}",
        f"  Speed       : {config.vehicle_speed_mph:.1f} mph",
        f"  Exported    : {now}",
        f"  Geometry    : {os.path.basename(config.geometry_path)}",
        "",
    ]

    # ── Mesh quality section ─────────────────────────────────────────────
    mq = mesh_quality or {}
    oq_min   = mq.get("oq_min",  0.0)
    oq_max   = mq.get("oq_max",  0.0)
    oq_mean  = mq.get("oq_mean", 0.0)
    oq_note  = mq.get("oq_note", "Not available")
    oq_cells = mq.get("oq_total_cells", 0)
    oq_bands = mq.get("oq_bands", [])
    oq_p01   = mq.get("oq_pct_below_01", 0.0) * 100
    oq_p02   = mq.get("oq_pct_below_02", 0.0) * 100

    lines += [
        sep,
        "  MESH QUALITY  (orthogonal quality, post-improvement)",
        sep,
        f"  {'Verdict':<32} {oq_note}",
        f"  {'Min Orthogonal Quality':<32} {oq_min:>10.4f}",
        f"  {'Mean Orthogonal Quality':<32} {oq_mean:>10.4f}",
        f"  {'Max Orthogonal Quality':<32} {oq_max:>10.4f}",
        f"  {'Total Cell Count':<32} {oq_cells:>10,}",
        f"  {'Cells below OQ 0.10 (approx)':<32} {oq_p01:>9.2f} %",
        f"  {'Cells below OQ 0.20 (approx)':<32} {oq_p02:>9.2f} %",
    ]

    if oq_bands:
        lines += ["", "  Orthogonal quality distribution (approx):"]
        for band in oq_bands:
            bar_width = 20
            filled    = int(round(band["pct"] / 100 * bar_width))
            bar       = "█" * filled + "░" * (bar_width - filled)
            lines.append(
                f"  {band['label']:<28} [{bar}] {band['pct']:5.1f}%"
                + (f"  (~{band['count']:,} cells)" if band["count"] > 0 else "")
            )

    lines += [
        "",
        "  Target: min orthogonal quality > 0.10 (ideally > 0.20).",
        "  Band percentages are approximate (derived from min/mean statistics).",
        "",
    ]

    lines += [
        sep,
        f"  DOWNFORCE (lbf){half}",
        sep,
        f"  {'Front Wing':<32} {ff:>10.3f} lbf",
        f"  {'Rear Wing':<32} {fr:>10.3f} lbf",
        f"  {'Undertray':<32} {fu:>10.3f} lbf",
        f"  {'TOTAL Downforce':<32} {total_df:>10.3f} lbf",
        "",
        sep,
        f"  DRAG (lbf){half}",
        sep,
        f"  {'Total Car Drag':<32} {total_drag:>10.3f} lbf",
        f"  {'Aero System Drag (FW+RW+UT)':<32} {aero_drag:>10.3f} lbf",
        f"  {'Rear Wing Drag':<32} {fdr:>10.3f} lbf",
        "",
        sep,
        "  CENTER OF PRESSURE  (derived from simulation moments)",
        sep,
        f"  {'CoP from front axle':<32} {cop['x_cp']:>10.3f} in",
        f"  {'Aero Balance -- Rear':<32} {cop['pct_rear'] * 100:>10.2f} %",
        f"  {'Aero Balance -- Front':<32} {cop['pct_front'] * 100:>10.2f} %",
        f"  {'Total Pitching Moment (Mz)':<32} {cop['Mz_total']:>10.1f} lbf.in",
        f"  {'Resultant Aero Force':<32} {cop['f_resultant']:>10.3f} lbf",
        f"  {'Resultant Angle from Vertical':<32} {cop['theta_deg']:>10.2f} deg",
        "",
        "  Derived moment arm lengths (from simulation data):",
        f"  {'  Lf (FW CoP to front axle)':<32} {cop['lf_derived']:>10.3f} in",
        f"  {'  Lr (RW CoP to rear axle)':<32} {cop['lr_derived']:>10.3f} in",
        f"  {'  Lu (UT CoP to front axle)':<32} {cop['lu_derived']:>10.3f} in",
        "",
        sep,
        "  AERODYNAMIC COEFFICIENTS",
        sep,
        f"  {'SCz (Downforce Coeff)':<32} {scz:>10.4f}",
        f"  {'SCx (Drag Coeff)':<32} {scx:>10.4f}",
        f"  {'L/D Ratio':<32} {(total_df / total_drag if total_drag else 0):>10.3f}",
        f"  {'Reference Area':<32} {area:>10.4f} m^2",
        "",
    ]

    if extra_lines:
        lines += [sep, "  ADDITIONAL ZONES", sep] + extra_lines + [""]

    # ── Cornering section (Turning sim only) ─────────────────────────────
    from simtypes.configs import SimType
    if config.sim_type == SimType.TURNING:
        yaw_moment   = raw_results.get("yaw_moment_lbf_ft",  0.0)
        lateral      = raw_results.get("lateral_force_lbf",  0.0)
        yaw_used     = raw_results.get("yaw_angle_deg_used",  0.0)
        turn_r       = raw_results.get("turn_radius_m",       0.0)
        # Yaw moment sign convention: positive = oversteer tendency (nose rotates
        # in direction of turn), negative = understeer tendency.
        tendency = "oversteer tendency" if yaw_moment > 0 else "understeer tendency"
        lines += [
            sep,
            "  CORNERING",
            sep,
            f"  {'Turn Radius':<32} {turn_r:>10.2f} m",
            f"  {'Applied Yaw Angle':<32} {yaw_used:>10.2f} deg",
            f"  {'Yaw Moment (about centroid)':<32} {yaw_moment:>10.2f} lbf.ft",
            f"  {'Lateral Force (Z)':<32} {lateral:>10.2f} lbf",
            f"  {'Tendency':<32} {'':>10}  {tendency}",
            "",
            "  Yaw moment sign convention:",
            "  +ve = moment rotates nose into the turn  (oversteer tendency)",
            "  -ve = moment rotates nose away from turn (understeer tendency)",
            "",
        ]

    lines += [
        sep,
        "  CoP METHOD",
        sep,
        "  Derived directly from Fluent pitching moment reports.",
        "  No hand-measured geometry constants used.",
        "",
        "  Mz   = moment_fw + moment_rw + moment_ut",
        "         (Z-axis moments about front axle origin, lbf.in)",
        "  x_cp = Mz / Fy          [in from front axle]",
        "  %Rear  = x_cp / L",
        "  %Front = 1 - %Rear",
        f"  Wheelbase L = {wheelbase_in:.2f} in",
        "",
        sep,
        "  END OF REPORT",
        sep,
        "",
    ]

    os.makedirs(config.results_dir, exist_ok=True)
    safe_name = "".join(
        c if c.isalnum() or c in "._- " else "_" for c in config.name
    ).strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath  = os.path.join(config.results_dir,
                             f"{safe_name}_{timestamp}_results.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
