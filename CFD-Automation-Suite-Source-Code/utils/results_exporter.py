"""
Results exporter for Ram Racing CFD simulations.

All units are standard Ansys SI:
  Forces:   Newtons [N]
  Moments:  Newton-metres [N*m]
  Length:   metres [m]
  Speed:    m/s
  Pressure: Pascals [Pa]
  Area:     m^2

CoP is derived entirely from simulation data (forces + pitching moments
reported by Fluent) -- no hand-measured geometry constants required.

Moment convention:
  Fluent reports pitching moment about the front axle origin (0,0,0),
  Z axis, in N*m.

CoP equations:
    Fz   = total downforce             [N]
    Fx   = total drag                  [N]
    My   = pitch moment about Z-axis   [N*m]
    copx = My / Fz                     [m from front axle]
    % Rear  = copx / wheelbase
    % Front = 1 - % Rear
"""
import os
import math
from datetime import datetime
from typing import Optional


def export_results(config, raw_results, frontal_area_m2=None,
                   mesh_quality: Optional[dict] = None):
    """
    Write the results .txt file. All inputs and outputs are SI.
    Returns the path to the written file.
    """
    mult = 2.0 if config.is_half_symmetry else 1.0

    # Forces [N] (already scaled in _extract_results)
    fz          = raw_results.get("fz", 0.0)
    fx          = raw_results.get("fx", 0.0)
    fz_fw_wing  = raw_results.get("fz_frontwing", 0.0)
    fz_rw_wing  = raw_results.get("fz_rearwing", 0.0)
    fz_ut       = raw_results.get("fz_undertray", 0.0)
    fx_fw_wing  = raw_results.get("fx_frontwing", 0.0)
    fx_rw_wing  = raw_results.get("fx_rearwing", 0.0)
    fx_ut       = raw_results.get("fx_undertray", 0.0)
    fz_fwheel   = raw_results.get("fz_fw", 0.0)
    fz_rwheel   = raw_results.get("fz_rw", 0.0)
    fx_fwheel   = raw_results.get("fx_fw", 0.0)
    fx_rwheel   = raw_results.get("fx_rw", 0.0)
    fz_fsus     = raw_results.get("fz_frontsus", 0.0)
    fz_rsus     = raw_results.get("fz_rearsus", 0.0)
    fx_fsus     = raw_results.get("fx_frontsus", 0.0)
    fx_rsus     = raw_results.get("fx_rearsus", 0.0)
    fz_body     = raw_results.get("fz_body", 0.0)
    fx_body     = raw_results.get("fx_body", 0.0)

    # Coefficients
    cl       = raw_results.get("cl", 0.0)
    cd       = raw_results.get("cd", 0.0)
    SCz      = raw_results.get("SCz", 0.0)
    SCx      = raw_results.get("SCx", 0.0)
    ld_ratio = raw_results.get("ld_ratio", 0.0)

    # CoP [m]
    copx          = raw_results.get("copx", 0.0)
    copz          = raw_results.get("copz", 0.0)
    cop_pct_front = raw_results.get("cop_pct_front", 0.0)
    cop_pct_rear  = raw_results.get("cop_pct_rear", 0.0)
    my_total      = raw_results.get("my_total", 0.0)
    mx_total      = raw_results.get("mx_total", 0.0)

    # Resultant
    f_res = math.sqrt(fx ** 2 + fz ** 2)
    theta = math.degrees(math.atan2(abs(fx), abs(fz))) if f_res > 0 else 0.0

    # Reference values
    area = frontal_area_m2 or 0.6
    speed_ms = config.vehicle_speed_mph * 0.44704
    wheelbase_m = getattr(config, "wheelbase_m", 1.575)

    # Build report
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
        f"  Speed       : {speed_ms:.2f} m/s  ({config.vehicle_speed_mph:.1f} mph)",
        f"  Exported    : {now}",
        f"  Geometry    : {os.path.basename(config.geometry_path)}",
        "",
    ]

    # Mesh quality
    mq = mesh_quality or {}
    lines += [
        sep,
        "  MESH QUALITY  (orthogonal quality)",
        sep,
        f"  {'Verdict':<40} {mq.get('oq_note', 'N/A')}",
        f"  {'Min Orthogonal Quality':<40} {mq.get('oq_min', 0):.4f}",
        f"  {'Mean Orthogonal Quality':<40} {mq.get('oq_mean', 0):.4f}",
        f"  {'Total Cell Count':<40} {mq.get('oq_total_cells', 0):,}",
        "",
    ]

    # Downforce [N]
    lines += [
        sep,
        f"  DOWNFORCE [N]{half}",
        sep,
        f"  {'Front Wing':<40} {fz_fw_wing:>12.3f} N",
        f"  {'Rear Wing':<40} {fz_rw_wing:>12.3f} N",
        f"  {'Undertray':<40} {fz_ut:>12.3f} N",
        f"  {'Front Wheel':<40} {fz_fwheel:>12.3f} N",
        f"  {'Rear Wheel':<40} {fz_rwheel:>12.3f} N",
        f"  {'Front Suspension':<40} {fz_fsus:>12.3f} N",
        f"  {'Rear Suspension':<40} {fz_rsus:>12.3f} N",
        f"  {'Body/Chassis':<40} {fz_body:>12.3f} N",
        f"  {'TOTAL Fz':<40} {fz:>12.3f} N",
        "",
    ]

    # Drag [N]
    lines += [
        sep,
        f"  DRAG [N]{half}",
        sep,
        f"  {'Front Wing':<40} {fx_fw_wing:>12.3f} N",
        f"  {'Rear Wing':<40} {fx_rw_wing:>12.3f} N",
        f"  {'Undertray':<40} {fx_ut:>12.3f} N",
        f"  {'Front Wheel':<40} {fx_fwheel:>12.3f} N",
        f"  {'Rear Wheel':<40} {fx_rwheel:>12.3f} N",
        f"  {'Front Suspension':<40} {fx_fsus:>12.3f} N",
        f"  {'Rear Suspension':<40} {fx_rsus:>12.3f} N",
        f"  {'Body/Chassis':<40} {fx_body:>12.3f} N",
        f"  {'TOTAL Fx':<40} {fx:>12.3f} N",
        "",
    ]

    # Center of Pressure
    lines += [
        sep,
        "  CENTER OF PRESSURE",
        sep,
        f"  {'CoP x (from front axle)':<40} {copx:>12.4f} m",
        f"  {'CoP z (lateral)':<40} {copz:>12.4f} m",
        f"  {'Aero Balance -- Front':<40} {cop_pct_front:>12.2f} %",
        f"  {'Aero Balance -- Rear':<40} {cop_pct_rear:>12.2f} %",
        f"  {'Pitch Moment My':<40} {my_total:>12.3f} N*m",
        f"  {'Resultant Force':<40} {f_res:>12.3f} N",
        f"  {'Resultant Angle from Vertical':<40} {theta:>12.2f} deg",
        "",
    ]

    # Coefficients
    q = 0.5 * 1.225 * speed_ms ** 2
    lines += [
        sep,
        "  AERODYNAMIC COEFFICIENTS",
        sep,
        f"  {'Cl':<40} {cl:>12.4f}",
        f"  {'Cd':<40} {cd:>12.4f}",
        f"  {'SCz  (= Fz / q)':<40} {SCz:>12.4f} m^2",
        f"  {'SCx  (= Fx / q)':<40} {SCx:>12.4f} m^2",
        f"  {'L/D Ratio':<40} {ld_ratio:>12.3f}",
        f"  {'Reference Area':<40} {area:>12.4f} m^2",
        f"  {'Dynamic Pressure q':<40} {q:>12.2f} Pa",
        "",
    ]

    # Turning section
    from simtypes.configs import SimType
    if config.sim_type == SimType.TURNING:
        yaw_moment = raw_results.get("yaw_moment", 0.0)
        lateral    = raw_results.get("lateral_force", 0.0)
        yaw_used   = raw_results.get("yaw_angle_deg", 0.0)
        turn_r     = raw_results.get("turn_radius", 0.0)
        tendency   = "oversteer" if yaw_moment > 0 else "understeer"
        lines += [
            sep,
            "  CORNERING",
            sep,
            f"  {'Turn Radius':<40} {turn_r:>12.2f} m",
            f"  {'Applied Yaw Angle':<40} {yaw_used:>12.2f} deg",
            f"  {'Yaw Moment':<40} {yaw_moment:>12.2f} N*m",
            f"  {'Lateral Force':<40} {lateral:>12.2f} N",
            f"  {'Tendency':<40} {tendency:>12}",
            "",
        ]

    # Method notes
    lines += [
        sep,
        "  METHOD",
        sep,
        "  CoP derived from Fluent pitching moment reports.",
        f"  Wheelbase = {wheelbase_m:.3f} m",
        "  All units: SI (N, m, m/s, Pa, m^2)",
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
