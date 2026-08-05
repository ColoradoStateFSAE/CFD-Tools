"""
Results file writer.

Takes the results dictionary a simulation type returns and writes a plain
text report. Works for every simulation type: it prints whichever of the
known keys are present and skips the rest.

All values are SI. Forces already carry any half or quarter model scaling,
applied once inside the simulation type.
"""
import os
from datetime import datetime

SEP = "-" * 68


def _row(label: str, value, unit: str = "", width: int = 40) -> str:
    if isinstance(value, float):
        return f"  {label:<{width}} {value:>14.4f} {unit}"
    return f"  {label:<{width}} {value:>14} {unit}"


def _section(title: str) -> list:
    return [SEP, f"  {title}", SEP]


def write_results(settings, sim_type_name: str, results: dict, log) -> str:
    """
    Write the results file and return its path.

    `settings` is the simulation type's Settings dataclass.
    """
    results_dir = (getattr(settings, "results_dir", "")
                   or getattr(settings, "output_dir", "")
                   or ".")
    os.makedirs(results_dir, exist_ok=True)

    safe = "".join(c if c.isalnum() or c in "._- " else "_"
                   for c in settings.name).strip()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"{safe}_{stamp}_results.txt")

    lines = [
        "=" * 70,
        "   Ram Racing Aerodynamics -- CFD Results",
        "=" * 70,
        "",
        _row("Point ID", settings.name),
        _row("Project", getattr(settings, "project", "")),
        _row("Run", getattr(settings, "run", "")),
        _row("MAP #", getattr(settings, "map_number", "")),
        _row("Type", sim_type_name),
        _row("Speed", settings.speed_ms, "m/s"),
        _row("Speed", settings.speed_mph, "mph"),
        _row("Exported", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    ]
    if getattr(settings, "description", ""):
        lines.append(_row("Description", settings.description))
    if getattr(settings, "geometry_path", ""):
        lines.append(_row("Geometry", os.path.basename(settings.geometry_path)))
    if results.get("runtime_s"):
        lines.append(_row("Runtime", results["runtime_s"] / 60.0, "min"))
    lines.append("")

    # ── Totals ───────────────────────────────────────────────────────────
    lines += _section("TOTAL FORCES")
    lines += [
        _row("Downforce  Fz", results.get("fz", 0.0), "N"),
        _row("Drag       Fx", results.get("fx", 0.0), "N"),
        _row("L/D ratio", results.get("ld_ratio", 0.0)),
        "",
    ]

    # ── Per element ──────────────────────────────────────────────────────
    elements = [
        ("Front wing",       "fz_frontwing", "fx_frontwing"),
        ("Rear wing",        "fz_rearwing",  "fx_rearwing"),
        ("Undertray",        "fz_undertray", "fx_undertray"),
        ("Chassis and body", "fz_body",      "fx_body"),
        ("Front wheel",      "fz_fw",        "fx_fw"),
        ("Rear wheel",       "fz_rw",        "fx_rw"),
        ("Front suspension", "fz_frontsus",  "fx_frontsus"),
        ("Rear suspension",  "fz_rearsus",   "fx_rearsus"),
    ]
    present = [(label, dn, dr) for label, dn, dr in elements
               if dn in results or dr in results]
    if present:
        lines += _section("PER ELEMENT")
        lines.append(f"  {'':<40} {'Downforce [N]':>16} {'Drag [N]':>16}")
        for label, down_key, drag_key in present:
            lines.append(f"  {label:<40} "
                         f"{results.get(down_key, 0.0):>16.3f} "
                         f"{results.get(drag_key, 0.0):>16.3f}")
        lines.append("")

    # ── Coefficients ─────────────────────────────────────────────────────
    lines += _section("COEFFICIENTS AND AREAS")
    lines += [
        _row("Cl", results.get("cl", 0.0)),
        _row("Cd", results.get("cd", 0.0)),
        _row("SCz   (Fz / q)", results.get("SCz", 0.0), "m^2"),
        _row("SCx   (Fx / q)", results.get("SCx", 0.0), "m^2"),
        _row("Reference area", results.get("reference_area", 0.0), "m^2"),
        _row("Dynamic pressure q", results.get("dynamic_pressure", 0.0), "Pa"),
        "",
    ]

    # ── Centre of pressure ───────────────────────────────────────────────
    lines += _section("CENTRE OF PRESSURE")
    lines += [
        _row("CoP x, from origin", results.get("copx", 0.0), "m"),
        _row("CoP z, lateral", results.get("copz", 0.0), "m"),
        _row("Aero balance, forward", results.get("cop_pct", 0.0), "%"),
        _row("Pitch moment  My", results.get("my_total", 0.0), "N*m"),
        _row("Lateral moment Mx", results.get("mx_total", 0.0), "N*m"),
        "",
    ]

    # ── Cornering, when present ──────────────────────────────────────────
    if "yaw_moment" in results:
        lines += _section("CORNERING")
        lines += [
            _row("Yaw angle", results.get("yaw_angle_deg", 0.0), "deg"),
            _row("Turn radius", results.get("turn_radius", 0.0), "m"),
            _row("Yaw moment", results.get("yaw_moment", 0.0), "N*m"),
            _row("Lateral force", results.get("lateral_force", 0.0), "N"),
            "",
        ]

    # ── Setup summary ────────────────────────────────────────────────────
    lines += _section("SETUP")
    lines += [
        _row("Car L x W x H",
             f"{settings.car_length} x {settings.car_width} x "
             f"{settings.car_height}", "m"),
        _row("Wheelbase", getattr(settings, "wheelbase", 0.0), "m"),
        _row("Surface mesh min / max",
             f"{settings.surface_min} / {settings.surface_max}", "m"),
        _row("Volume mesh min / max",
             f"{settings.volume_min} / {settings.volume_max}", "m"),
        _row("Boundary layers", settings.bl_layers),
        _row("First layer height", settings.bl_first_height, "m"),
        _row("Iterations, ramp 1 / 2 / 3",
             f"{settings.ramp1_iters} / {settings.ramp2_iters} / "
             f"{settings.ramp3_iters}"),
        _row("Processes", settings.processes),
        "",
        SEP,
        "  All values SI: N, N*m, m, m/s, Pa, m^2",
        SEP,
        "",
    ]

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    log.info(f"  Results -> {path}")
    return path
