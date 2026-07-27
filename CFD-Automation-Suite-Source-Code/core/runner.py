"""
Fluent session management and result extraction.

The Fluent *workflow* lives in recorded journals under journals/<sim_type>/;
this module owns everything around them:

    * launching and tearing down Fluent sessions
    * running the mesh and solve journals via core.journal_runner
    * reading report values back out
    * deriving CoP / SCz / SCx and writing the results file
    * exporting EnSight Gold for ParaView

Journaling records commands but omits queries, so reading a report value never
appears in a journal. That split is the reason this module still exists: the
journal builds the case, Python reads the numbers back out.

Target: Ansys Fluent 2026 R1 (v261) / PyFluent 0.39
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

log = logging.getLogger("fluent_runner")

MPH_TO_MS = 0.44704


def mph_to_ms(mph: float) -> float:
    """Miles per hour to metres per second."""
    return mph * MPH_TO_MS


def ms_to_mph(ms: float) -> float:
    """Metres per second to miles per hour."""
    return ms / MPH_TO_MS


# ---------------------------------------------------------------------------
# Fluent install detection and launch
# ---------------------------------------------------------------------------

_AWP_KEY = "AWP_ROOT261"
_PV      = "26.1"          # product_version string for launch_fluent()

FLUENT_LAUNCH_TIMEOUT = 300  # seconds -- increase for slow HPC startup


def _get_pyfluent_version() -> tuple:
    """Returns (major, minor) e.g. (0, 38)."""
    try:
        import ansys.fluent.core as pf
        ver = getattr(pf, "__version__", None)
        if ver is None:
            from importlib.metadata import version
            ver = version("ansys-fluent-core")
        parts = str(ver).split(".")
        maj, minor = int(parts[0]), int(parts[1])
        log.info(f"  PyFluent {ver}")
        return maj, minor
    except Exception as e:
        log.warning(f"  PyFluent version unknown ({e}), assuming 0.38")
        return 0, 38


def _ensure_awp_root():
    """Set AWP_ROOT261 if not already in env. Searches common install paths."""
    if os.environ.get(_AWP_KEY):
        log.info(f"  {_AWP_KEY}={os.environ[_AWP_KEY]}")
        return
    # Check for any AWP_ROOT already set
    existing = {k: v for k, v in os.environ.items() if k.startswith("AWP_ROOT")}
    if existing:
        log.info(f"  Found AWP_ROOT: {existing}")
        return

    is_win = sys.platform == "win32"
    home   = os.path.expanduser("~")

    candidates = [
        # User home (common on HPC)
        os.path.join(home, "ansys_inc", "v252", "fluent"),
        os.path.join(home, "ansys_inc", "v251", "fluent"),
        # System paths
        "/ansys_inc/v261/fluent",
        "/usr/ansys_inc/v261/fluent",
        "/opt/ansys_inc/v261/fluent",
        "/apps/ansys/v261/fluent",
        "/apps/ansys_inc/v261/fluent",
        # Windows
        "C:/Program Files/ANSYS Inc/v261/fluent",
    ]

    for candidate in candidates:
        fluent_bin = os.path.join(candidate, "bin",
                                  "fluent" + (".exe" if is_win else ""))
        if os.path.exists(fluent_bin):
            awp_root = os.path.dirname(candidate)
            os.environ[_AWP_KEY] = awp_root
            log.info(f"  Auto-set {_AWP_KEY}={awp_root}")
            return

    log.warning(
        f"  Fluent not found. Set {_AWP_KEY} manually:\n"
        f"  export {_AWP_KEY}=/path/to/ansys_inc/v261"
    )


def _launch_fluent(pyfluent, config, mode: str):
    """Launch Fluent in the given mode targeting Ansys 2026 R1."""
    _ensure_awp_root()
    timeout = getattr(config, "launch_timeout", FLUENT_LAUNCH_TIMEOUT)
    # PyFluent 0.39: FluentMode/Precision enums preferred, strings still work
    try:
        mode_enum = getattr(pyfluent.FluentMode, mode.upper(), mode)
    except Exception:
        mode_enum = mode
    try:
        prec_enum = pyfluent.Precision.DOUBLE if config.double_precision else pyfluent.Precision.SINGLE
    except Exception:
        prec_enum = "double" if config.double_precision else "single"
    kwargs = dict(
        mode            = mode_enum,
        precision       = prec_enum,
        processor_count = config.num_processes,
        product_version = _PV,
        start_timeout   = timeout,
    )
    log.info(f"  launch_fluent({mode}, procs={config.num_processes}, "
             f"timeout={timeout}s, version={_PV})")
    return pyfluent.launch_fluent(**kwargs)


def _launch_fluent_meshing(pyfluent, config):
    return _launch_fluent(pyfluent, config, "meshing")


def _launch_fluent_solver(pyfluent, config):
    return _launch_fluent(pyfluent, config, "solver")


# ---------------------------------------------------------------------------
# Report values -- queries, so they are never journalled
# ---------------------------------------------------------------------------

def _get_report_value(solver, report_type: str, name: str) -> float:
    """
    Read a force/moment report value using Fluent built-in scheme functions.

    Uses (report-forces ...) and (report-moments ...) which are always
    available in Fluent 252 and do not depend on monitor history.
    Zone list and force vector are read from the report definition object
    so this works for any report created by _add_report_lift/drag/moment.
    """
    import re as _re

    def _parse(s: str) -> float:
        nums = _re.findall(r'[-+]?[0-9]*[.]?[0-9]+(?:[eE][-+]?[0-9]+)?', str(s))
        return float(nums[0]) if nums else 0.0

    try:
        rd  = solver.solution.report_definitions
        obj = getattr(rd, report_type)[name]

        zones = list(obj.zones.get_state())
        if not zones:
            log.warning(f"  Report {name!r}: no zones defined")
            return 0.0

        # Build a Scheme list of zone name strings
        zone_list = "(list " + " ".join(f'"{z}"' for z in zones) + ")"

        if report_type in ("lift", "drag"):
            vec = list(obj.force_vector.get_state())
            vx, vy, vz = float(vec[0]), float(vec[1]), float(vec[2])
            # report-forces returns a list of (zone pressure viscous) + net entry.
            # Net is (car (reverse result)); total = pressure + viscous = cadr + caddr.
            expr = (
                f"(let* ((f (report-forces {zone_list}"
                f" (list {vx} {vy} {vz}) #f))"
                f" (net (car (reverse f))))"
                f" (+ (cadr net) (caddr net)))"
            )
        else:
            # Moment: center and axis are set separately; use (0 0 0) / (0 0 1)
            # as the universal default — matches _add_report_moment convention.
            expr = (
                f"(let* ((m (report-moments {zone_list}"
                f" (list 0.0 0.0 0.0) (list 0.0 0.0 1.0) #f))"
                f" (net (car (reverse m))))"
                f" (+ (cadr net) (caddr net)))"
            )

        result = solver.scheme_eval.string_eval(expr)
        return _parse(result)

    except Exception as e:
        log.warning(f"  Report {name!r}: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# Mesh quality -- a query, read after the meshing journal finishes
# ---------------------------------------------------------------------------

def _extract_mesh_quality(meshing) -> dict:
    """
    Extract orthogonal quality statistics from the meshing session.

    Tries the PyFluent 0.38 meshing API first, then falls back to
    Scheme/TUI evaluation.  Always returns a dict — never raises.

    Returned keys:
        oq_min       float   minimum orthogonal quality across all cells
        oq_max       float   maximum (should be ≤ 1.0)
        oq_mean      float   volume-weighted mean orthogonal quality
        oq_pct_below_01  float  fraction of cells with OQ < 0.10  (0–1)
        oq_pct_below_02  float  fraction of cells with OQ < 0.20  (0–1)
        oq_total_cells   int    total cell count
        oq_bands     list[dict] histogram: [{label, lo, hi, count, pct}]
        oq_pass      bool    True when min OQ ≥ _OQ_MIN_WARN
        oq_note      str     human-readable quality verdict
        oq_raw_text  str     raw Fluent output (for debugging)
    """
    result = {
        "oq_min": 0.0, "oq_max": 0.0, "oq_mean": 0.0,
        "oq_pct_below_01": 0.0, "oq_pct_below_02": 0.0,
        "oq_total_cells": 0, "oq_bands": [],
        "oq_pass": False, "oq_note": "Quality data unavailable",
        "oq_raw_text": "",
    }

    # ── Attempt 1: PyFluent 0.38 mesh quality object ─────────────────────
    try:
        mq = meshing.meshing.MeshQuality
        oq_min  = float(mq.MinOrthogonalQuality.get_state())
        oq_max  = float(mq.MaxOrthogonalQuality.get_state())
        oq_mean = float(mq.MeanOrthogonalQuality.get_state())
        result.update({"oq_min": oq_min, "oq_max": oq_max, "oq_mean": oq_mean})
        log.info(f"  Mesh quality (API): min={oq_min:.4f}  mean={oq_mean:.4f}  max={oq_max:.4f}")
    except Exception as e1:
        log.debug(f"  MeshQuality API failed: {e1}")

        # ── Attempt 2: Scheme eval ────────────────────────────────────────
        try:
            raw = meshing.scheme_eval.string_eval(
                '(cx-gui-do cx-set-list-selections "Mesh Quality" '
                '(list "Orthogonal Quality")) '
                '(cx-gui-do cx-activate-item "Mesh Quality") '
                '(cx-gui-do cx-get-list-selections "Mesh Quality")'
            )
            result["oq_raw_text"] = str(raw)
            log.debug(f"  Mesh quality scheme raw: {raw}")
        except Exception as e2:
            log.debug(f"  Scheme eval mesh quality failed: {e2}")

        # ── Attempt 3: TUI report ─────────────────────────────────────────
        try:
            raw = meshing.tui.report.mesh_quality("orthogonal-quality")
            result["oq_raw_text"] = str(raw)
            # Parse "Minimum Orthogonal Quality = X" style output
            import re
            for label, key in [
                (r"[Mm]inimum.*?=\s*([\d.eE+\-]+)", "oq_min"),
                (r"[Mm]aximum.*?=\s*([\d.eE+\-]+)", "oq_max"),
                (r"[Aa]verage.*?=\s*([\d.eE+\-]+)",  "oq_mean"),
            ]:
                m = re.search(label, str(raw))
                if m:
                    result[key] = float(m.group(1))
            log.info(
                f"  Mesh quality (TUI): min={result['oq_min']:.4f}  "
                f"mean={result['oq_mean']:.4f}  max={result['oq_max']:.4f}"
            )
        except Exception as e3:
            log.debug(f"  TUI mesh quality failed: {e3}")

    # ── Cell count ────────────────────────────────────────────────────────
    try:
        # PyFluent 0.38: cell count via GlobalSettings or mesh info
        total_cells = int(
            meshing.meshing.GlobalSettings.FTMRegionData
            .TotalCellCount.get_state()
        )
        result["oq_total_cells"] = total_cells
    except Exception:
        try:
            raw = meshing.tui.report.mesh_statistics()
            import re
            m = re.search(r"(\d[\d,]+)\s+cells", str(raw))
            if m:
                result["oq_total_cells"] = int(m.group(1).replace(",", ""))
        except Exception:
            pass

    # ── Per-band histogram (best-effort via Fluent distribution query) ────
    try:
        # Ask Fluent for the orthogonal quality histogram as a distribution.
        # This is supported in Fluent 252 via scheme.
        raw_hist = meshing.scheme_eval.string_eval(
            "(let ((q (mesh/quality-info))) "
            "(list (assq 'orthogonal-quality q)))"
        )
        result["oq_raw_text"] = (result["oq_raw_text"] + "\n" + str(raw_hist)).strip()
        log.debug(f"  Quality histogram raw: {raw_hist}")
    except Exception as e:
        log.debug(f"  Quality histogram scheme eval skipped: {e}")

    # ── Build band histogram from min/mean/max heuristic ─────────────────
    # If we have at least min + mean, synthesise approximate band counts.
    # This is not exact — it's a triangular distribution approximation used
    # only when Fluent doesn't expose per-band counts directly.
    oq_min  = result["oq_min"]
    oq_mean = result["oq_mean"]
    total   = result["oq_total_cells"]
    bands   = []
    below_01 = 0
    below_02 = 0

    for label, lo, hi in _OQ_BANDS:
        # Rough fraction estimate: linear ramp from min to mean,
        # then flat above mean. Not exact, clearly labelled as approximate.
        hi_eff = min(hi, 1.0)
        if hi_eff <= oq_min:
            frac = 0.0
        elif lo >= oq_mean:
            # Above the mean — uniform distribution assumption
            span_total = max(1.0 - oq_mean, 1e-9)
            frac = max(0.0, (hi_eff - lo)) / span_total * 0.5
        else:
            # Straddles or is below mean
            span_total = max(oq_mean - oq_min, 1e-9)
            effective_lo = max(lo, oq_min)
            frac = max(0.0, min(hi_eff, oq_mean) - effective_lo) / span_total * 0.5

        frac  = min(frac, 1.0)
        count = int(round(frac * total)) if total > 0 else 0
        pct   = frac * 100.0
        bands.append({"label": label, "lo": lo, "hi": hi_eff,
                      "count": count, "pct": pct})
        if hi_eff <= 0.10:
            below_01 += frac
        if hi_eff <= 0.20:
            below_02 += frac

    result["oq_bands"]         = bands
    result["oq_pct_below_01"]  = min(below_01, 1.0)
    result["oq_pct_below_02"]  = min(below_02, 1.0)

    # ── Verdict ───────────────────────────────────────────────────────────
    oq_min = result["oq_min"]
    if oq_min <= 0.0:
        note = "Quality data unavailable — check logs"
        passed = False
    elif oq_min < _OQ_MIN_ERROR:
        note = f"POOR  — min OQ {oq_min:.4f} below {_OQ_MIN_ERROR:.2f}. Remesh recommended."
        passed = False
    elif oq_min < _OQ_MIN_WARN:
        note = f"MARGINAL  — min OQ {oq_min:.4f} below {_OQ_MIN_WARN:.2f}. Review before solving."
        passed = False
    else:
        note = f"PASS  — min OQ {oq_min:.4f} ≥ {_OQ_MIN_WARN:.2f}"
        passed = True

    result["oq_pass"] = passed
    result["oq_note"] = note
    log.info(f"  Mesh quality verdict: {note}")
    return result


# ---------------------------------------------------------------------------
# Main Meshing Workflow
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Post-processing export
# ---------------------------------------------------------------------------

def _export_ensight_gold(solver, config):
    """
    Export the solution in EnSight Gold format for ParaView visualization.
    Creates a .encas file + associated .geo and variable files.
    """
    import os
    out_dir = config.output_dir.rstrip("/\\")
    ensight_dir = os.path.join(out_dir, f"{config.name}_ensight")
    os.makedirs(ensight_dir, exist_ok=True)
    ensight_base = os.path.join(ensight_dir, config.name)

    try:
        # Method 1: PyFluent file.export API
        solver.file.export.ensight_gold(
            file_name=ensight_base,
        )
        log.info(f"  EnSight Gold exported: {ensight_dir}/")
        return ensight_dir
    except Exception as e1:
        log.debug(f"  EnSight export API: {e1}")

    try:
        # Method 2: TUI export command
        solver.tui.file.export.ensight_gold(
            ensight_base,   # filename base
            "yes",          # append project ID
            "yes",          # export all variables
        )
        log.info(f"  EnSight Gold exported (TUI): {ensight_dir}/")
        return ensight_dir
    except Exception as e2:
        log.debug(f"  EnSight TUI: {e2}")

    try:
        # Method 3: Scheme eval
        solver.scheme_eval.string_eval(
            f'(ti-menu-load-string "file export ensight-gold '
            f'{ensight_base} () () yes")'
        )
        log.info(f"  EnSight Gold exported (scheme): {ensight_dir}/")
        return ensight_dir
    except Exception as e3:
        log.warning(f"  EnSight Gold export failed: {e3}")
        return None

# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------

# Report definitions created by the solve journal. Renaming one here without
# renaming it in the journal makes it read as zero.
ELEMENT_REPORTS = [
    "fz_frontwing", "fx_frontwing",
    "fz_rearwing",  "fx_rearwing",
    "fz_undertray", "fx_undertray",
    "fz_fw",        "fx_fw",
    "fz_rw",        "fx_rw",
    "fz_frontsus",  "fx_frontsus",
    "fz_rearsus",   "fx_rearsus",
    "fz_body",      "fx_body",
]


def extract_results(solver, config, mesh_quality: Optional[dict] = None) -> dict:
    """
    Read every report the solve journal created and derive the aero metrics.

    All values are SI: forces in N, moments in N*m, lengths in m, areas in m^2.
    Half-car results are doubled here, once, and nowhere else.
    """
    from simtypes.configs import SimType

    results = {}
    if mesh_quality:
        results["mesh_quality"] = mesh_quality

    def fval(report_type: str, name: str) -> float:
        return _get_report_value(solver, report_type, name)

    mult = 2.0 if config.is_half_symmetry else 1.0

    # ── Totals [N] ───────────────────────────────────────────────────────
    results["fz"] = fval("lift", "fz") * mult
    results["fx"] = fval("drag", "fx") * mult

    # ── Coefficients ─────────────────────────────────────────────────────
    results["cl"] = fval("lift", "cl")
    results["cd"] = fval("drag", "cd")

    # ── Per element [N] ──────────────────────────────────────────────────
    for name in ELEMENT_REPORTS:
        rtype = "lift" if name.startswith("fz") else "drag"
        results[name] = fval(rtype, name) * mult

    # ── SCz / SCx [m^2] ──────────────────────────────────────────────────
    speed_ms = mph_to_ms(config.vehicle_speed_mph)
    q = 0.5 * 1.225 * speed_ms ** 2          # dynamic pressure [Pa]
    results["q"]   = q
    results["SCz"] = abs(results["fz"]) / q if q > 0 else 0.0
    results["SCx"] = abs(results["fx"]) / q if q > 0 else 0.0

    # ── Reference area [m^2] ─────────────────────────────────────────────
    # Set by the solve journal from Fluent's projected-area computation.
    frontal_area = None
    try:
        area = solver.setup.reference_values.area
        frontal_area = float(area() if callable(area) else area)
        results["frontal_area"] = frontal_area
    except Exception as exc:
        log.debug(f"  reference area: {exc}")

    # ── Centre of pressure [m] ───────────────────────────────────────────
    my_total = fval("moment", "my_total") * mult   # pitch, about front axle
    mx_total = fval("moment", "mx_total") * mult   # lateral
    results["my_total"] = my_total
    results["mx_total"] = mx_total

    fz_total = results["fz"]
    if abs(fz_total) > 1e-6:
        copx = my_total / fz_total
        results["copx"] = copx
        results["copz"] = mx_total / fz_total

        wheelbase = float(getattr(config, "wheelbase_m", 1.575))
        if wheelbase > 0:
            pct_front = max(0.0, min(100.0, (copx / wheelbase) * 100.0))
            results["cop_pct_front"] = pct_front
            results["cop_pct_rear"]  = 100.0 - pct_front
        else:
            results["cop_pct_front"] = 0.0
            results["cop_pct_rear"]  = 0.0
    else:
        log.warning("  Total Fz is ~0 — CoP cannot be derived. Check that the "
                    "solve journal created the fz and my_total reports.")
        results.update({"copx": 0.0, "copz": 0.0,
                        "cop_pct_front": 0.0, "cop_pct_rear": 0.0})

    # ── L/D ──────────────────────────────────────────────────────────────
    results["ld_ratio"] = (abs(results["fz"]) / abs(results["fx"])
                           if abs(results["fx"]) > 1e-6 else 0.0)

    if config.is_half_symmetry:
        results["note"] = "Half-car sim — all forces doubled automatically."

    # ── Cornering ────────────────────────────────────────────────────────
    if config.sim_type == SimType.TURNING:
        results["yaw_moment"]    = fval("moment", "yaw_moment") * mult
        results["lateral_force"] = fval("lift", "lateral_force") * mult
        results["yaw_angle_deg"] = config.effective_yaw_deg()
        results["turn_radius"]   = config.turn_radius_m

    # ── Summary ──────────────────────────────────────────────────────────
    log.info(f"  Fz={results['fz']:.1f} N   Fx={results['fx']:.1f} N   "
             f"L/D={results['ld_ratio']:.2f}")
    log.info(f"  FW={results.get('fz_frontwing', 0):.1f} N   "
             f"RW={results.get('fz_rearwing', 0):.1f} N   "
             f"UT={results.get('fz_undertray', 0):.1f} N")
    log.info(f"  SCz={results['SCz']:.4f} m^2   SCx={results['SCx']:.4f} m^2")
    log.info(f"  CoP x={results['copx']:.3f} m   "
             f"front={results['cop_pct_front']:.1f}%   "
             f"rear={results['cop_pct_rear']:.1f}%")

    # ── Results file ─────────────────────────────────────────────────────
    try:
        from utils.results_exporter import export_results
        results["result_file"] = export_results(
            config, results,
            frontal_area_m2=frontal_area,
            mesh_quality=results.get("mesh_quality"),
        )
        log.info(f"  Results exported: {results['result_file']}")
    except Exception as exc:
        log.warning(f"  Results export failed: {exc}")

    return results


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def run_meshing(config, progress_cb: Optional[Callable] = None):
    """
    Launch Fluent Meshing, run the mesh journal, write the mesh.

    The journal owns every workflow task. This function owns the session, the
    mesh file write, and the quality query -- none of which belong in a
    journal, since two of them are queries and the third must use the path the
    suite chose.

    Returns (mesh_file, mesh_quality).
    """
    from core import journal_params, journal_runner

    try:
        import ansys.fluent.core as pyfluent
    except ImportError as exc:
        raise RuntimeError(
            "ansys-fluent-core is not installed. "
            "Run: pip install ansys-fluent-core"
        ) from exc

    def prog(msg: str, pct: int) -> None:
        log.info(f"[MESH {pct:3d}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    os.makedirs(config.output_dir, exist_ok=True)
    mesh_file = os.path.join(config.output_dir.rstrip("/\\"), "mesh.msh.h5")
    tokens    = journal_params.build(config, mesh_file=mesh_file)

    prog("Launching Fluent Meshing...", 0)
    meshing = _launch_fluent_meshing(pyfluent, config)

    try:
        watertight = meshing.watertight()

        journal_runner.run_mesh_journal(
            config, meshing, watertight, tokens, progress_cb=progress_cb
        )

        prog("Extracting mesh quality...", 95)
        mesh_quality = _extract_mesh_quality(meshing)
        if mesh_quality.get("oq_pass"):
            log.info(f"  Mesh quality: {mesh_quality['oq_note']}")
        else:
            log.warning(f"  Mesh quality: {mesh_quality.get('oq_note')} "
                        f"(min {mesh_quality.get('oq_min', 0):.4f})")

        prog("Writing mesh...", 98)
        try:
            meshing.meshing.File.WriteMesh(FileName=mesh_file)
        except Exception as exc:
            log.debug(f"  WriteMesh: {exc} — falling back to scheme")
            meshing.scheme_eval.string_eval(f'(write-mesh "{mesh_file}")')

        prog(f"Mesh saved: {mesh_file}", 100)
        return mesh_file, mesh_quality

    except Exception:
        log.error("Meshing failed")
        raise
    finally:
        try:
            meshing.exit()
        except Exception:
            pass


def run_solver(config, mesh_file: str,
               progress_cb: Optional[Callable] = None,
               mesh_quality: Optional[dict] = None) -> dict:
    """
    Launch the Fluent solver, run the solve journal, extract results.

    The journal reads the mesh, sets physics and boundary conditions, creates
    the report definitions and runs the ramp sequence. This function then reads
    the reports back, exports EnSight, and writes the results file.
    """
    from core import journal_params, journal_runner

    try:
        import ansys.fluent.core as pyfluent
        import warnings
        try:
            from ansys.fluent.core.solver.flobject import DeprecatedSettingWarning
            warnings.filterwarnings("ignore", category=DeprecatedSettingWarning)
        except ImportError:
            pass
    except ImportError as exc:
        raise RuntimeError(
            "ansys-fluent-core is not installed. "
            "Run: pip install ansys-fluent-core"
        ) from exc

    def prog(msg: str, pct: int) -> None:
        log.info(f"[SOLVE {pct:3d}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    tokens = journal_params.build(config, mesh_file=mesh_file)

    prog("Launching Fluent solver...", 0)
    solver = _launch_fluent_solver(pyfluent, config)

    try:
        journal_runner.run_solve_journal(
            config, solver, tokens, progress_cb=progress_cb
        )

        prog("Exporting EnSight Gold for ParaView...", 96)
        _export_ensight_gold(solver, config)

        prog("Extracting results...", 97)
        results = extract_results(solver, config, mesh_quality)

        prog("Simulation complete.", 100)
        return results

    except Exception:
        log.error("Solver failed")
        raise
    finally:
        try:
            solver.exit()
        except Exception:
            pass