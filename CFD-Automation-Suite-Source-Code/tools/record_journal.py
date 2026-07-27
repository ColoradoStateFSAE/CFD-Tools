"""
Record a Fluent journal by working through the GUI.

Launches Fluent with journal recording already armed. Do the work by hand
following the Fluent Procedure doc, close Fluent, and the journal is written
to journals/<sim_type>/<stage>.py.

    python tools/record_journal.py --sim-type half_car --stage mesh
    python tools/record_journal.py --sim-type half_car --stage solve \\
        --mesh-file C:/runs/mesh.msh.h5

The recording is raw -- it contains the exact paths and numbers you clicked.
Replace those with {{TOKEN}} placeholders afterwards; journals/PLACEHOLDERS.md
lists every token and journals/README.md shows a worked before/after.

Journaling records commands but omits queries, so anything that only reads a
value will not appear. That is expected: the journal builds the case, the
suite reads the numbers back out.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STAGES = ("mesh", "solve")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch Fluent with journal recording armed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--sim-type", required=True,
                        help="journal folder, e.g. half_car")
    parser.add_argument("--stage", required=True, choices=STAGES,
                        help="mesh or solve")
    parser.add_argument("--geometry", default="",
                        help="geometry to load before recording starts "
                             "(mesh stage)")
    parser.add_argument("--mesh-file", default="",
                        help="mesh to read before recording starts "
                             "(solve stage)")
    parser.add_argument("--processes", type=int, default=4,
                        help="Fluent processes, default 4 — a low count is "
                             "fine for recording")
    parser.add_argument("--output", default="",
                        help="write here instead of journals/<type>/<stage>.py")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing journal without asking")
    return parser


def resolve_output(args) -> str:
    if args.output:
        return os.path.abspath(args.output)
    from utils.resource_path import journals_dir
    return os.path.join(journals_dir(), args.sim_type, f"{args.stage}.py")


def confirm_overwrite(path: str, force: bool) -> None:
    if not os.path.exists(path) or force:
        return
    print(f"\n{path}\nalready exists.")
    backup = f"{path}.{datetime.now():%Y%m%d_%H%M%S}.bak"
    answer = input("Overwrite? A backup will be kept. [y/N] ").strip().lower()
    if answer != "y":
        raise SystemExit("Cancelled.")
    os.replace(path, backup)
    print(f"Backed up to {backup}")


def print_guidance(args, output: str) -> None:
    print("=" * 70)
    print(f"  Recording {args.stage} journal for {args.sim_type}")
    print("=" * 70)
    print(f"\nOutput: {output}\n")

    if args.stage == "mesh":
        steps = [
            "Import Geometry",
            "Create Local Refinement Regions  (near, mid, far, wheels)",
            "Add Local Sizing  (curvature_stuff, curvature_aero, curvature_wheels)",
            "Generate the Surface Mesh",
            "Improve Surface Mesh",
            "Describe Geometry",
            "Update Boundaries",
            "Update Regions",
            "Add Boundary Layers",
            "Generate the Volume Mesh",
            "Improve Volume Mesh",
        ]
        tail = ("Stop after Improve Volume Mesh. The suite writes the mesh "
                "file itself, because it chooses the path.")
    else:
        steps = [
            "Read the mesh",
            "Reference Values  (compute from inlet, velocity, length, zone)",
            "Results > Projected Area  ->  paste into Reference Values > Area",
            "Viscous Model  (k-omega GEKO, production limiter on, CC off)",
            "Boundary Conditions  (inlet, ground, wheels)",
            "Report Definitions  (fz, fx, cl, cd, per element, my_total, mx_total)",
            "Initialize  (hybrid)",
            "Ramp 0  first order",
            "Ramp 1  second order + PRESTO",
            "Ramp 2  full second order",
            "Ramp 3  full send, curvature correction on",
        ]
        tail = ("Report names must match ELEMENT_REPORTS in core/runner.py. "
                "A renamed report reads as zero.")

    print("Work through these in Fluent:\n")
    for i, step in enumerate(steps, 1):
        print(f"  {i:2d}. {step}")
    print(f"\n{tail}")
    print("\nClose Fluent when finished — the journal is written on exit.")
    print("=" * 70 + "\n")


def main() -> None:
    args = build_arg_parser().parse_args()

    try:
        import ansys.fluent.core as pyfluent
    except ImportError:
        raise SystemExit(
            "ansys-fluent-core is not installed.\n"
            "  pip install ansys-fluent-core"
        )

    if not os.environ.get("AWP_ROOT261"):
        for candidate in (r"C:\Program Files\ANSYS Inc\v261",
                          os.path.expanduser("~/ansys_inc/v261"),
                          "/ansys_inc/v261"):
            if os.path.isdir(candidate):
                os.environ["AWP_ROOT261"] = candidate
                break
        else:
            raise SystemExit(
                "Ansys Fluent 2026 R1 not found.\n"
                "Set AWP_ROOT261 to the installation directory."
            )

    output = resolve_output(args)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    confirm_overwrite(output, args.force)
    print_guidance(args, output)

    mode = "meshing" if args.stage == "mesh" else "solver"
    print(f"Launching Fluent ({mode}, {args.processes} processes)...")

    session = pyfluent.launch_fluent(
        mode=mode,
        processor_count=args.processes,
        product_version="26.1",
        ui_mode="gui",            # the GUI is the point — this is interactive
        cleanup_on_exit=True,
    )

    try:
        # Preload so the recording starts at the first real step rather than
        # capturing a file path that will be replaced by a token anyway.
        if args.stage == "mesh" and args.geometry:
            print(f"Pre-loading geometry: {args.geometry}")
            watertight = session.watertight()
            watertight.import_geometry.file_name.set_state(args.geometry)
            watertight.import_geometry.length_unit.set_state("m")
            watertight.import_geometry()
        elif args.stage == "solve" and args.mesh_file:
            print(f"Pre-loading mesh: {args.mesh_file}")
            session.file.read_mesh(file_name=args.mesh_file)

        print(f"\nRecording -> {output}")
        session.journal.start(file_name=output)

        print("\nFluent is recording. Work through the steps above.")
        input("Press Enter here when you have finished in Fluent... ")

        session.journal.stop()
        print("Recording stopped.")

    finally:
        try:
            session.exit()
        except Exception:
            pass

    if os.path.isfile(output):
        lines = sum(1 for _ in open(output, encoding="utf-8", errors="replace"))
        print(f"\nWrote {output}  ({lines} lines)")
        print("\nNext:")
        print("  1. Replace hard-coded values with {{TOKEN}} placeholders")
        print("     (see journals/PLACEHOLDERS.md)")
        print("  2. Add progress markers:  #@ 38 | Adding refinement boxes")
        print(f"  3. Validate:  python -m core.journal_runner --check {output}")
    else:
        print(f"\nWARNING: nothing was written to {output}")
        print("Fluent may have recorded no journalable commands — GUI actions "
              "in solution mode are not journalled. See journals/README.md.")


if __name__ == "__main__":
    main()