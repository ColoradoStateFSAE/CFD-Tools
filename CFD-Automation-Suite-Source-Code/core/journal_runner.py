"""
Journal rendering and execution.

A journal is a recorded Fluent Python script under journals/<sim_type>/ with
{{TOKEN}} placeholders. This module substitutes the tokens, splits the result
on progress markers, and executes each chunk against a live Fluent session.

Why journals: PyFluent's journal.start()/stop() records whatever you click in
Fluent as the exact API calls that version accepts. Re-recording after an Ansys
upgrade replaces guessing at argument names with a repeatable procedure.

Check a journal without launching Fluent:

    python -m core.journal_runner --check journals/half_car/mesh.py
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("journal_runner")

# {{TOKEN}} with optional surrounding whitespace
_TOKEN_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")

# #@ 38 | Adding refinement boxes
_MARKER_RE = re.compile(r"^\s*#@\s*(\d+)\s*\|\s*(.*)$")


class JournalError(RuntimeError):
    """Raised when a journal is missing, malformed, or fails to execute."""


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def find_tokens(source: str) -> set:
    """Every {{TOKEN}} name appearing in a journal."""
    return set(_TOKEN_RE.findall(source))


def render(source: str, tokens: Dict[str, Any],
           journal_name: str = "journal") -> str:
    """
    Substitute {{TOKEN}} placeholders using repr(), so strings arrive quoted
    and lists arrive as Python literals. Journals must NOT quote tokens
    themselves.

    An unknown token raises rather than executing a half-substituted journal
    against a live Fluent session.
    """
    used    = find_tokens(source)
    unknown = sorted(used - set(tokens))
    if unknown:
        raise JournalError(
            f"{journal_name}: unknown placeholder(s) {unknown}.\n"
            f"Add them to core/journal_params.build() or fix the spelling. "
            f"See journals/PLACEHOLDERS.md."
        )

    def replace(match: "re.Match") -> str:
        return repr(tokens[match.group(1)])

    rendered = _TOKEN_RE.sub(replace, source)

    unused = sorted(set(tokens) - used)
    if unused:
        log.debug(f"  {journal_name}: {len(unused)} tokens unused by this journal")
    return rendered


# ---------------------------------------------------------------------------
# Progress markers
# ---------------------------------------------------------------------------

def split_sections(source: str) -> list:
    """
    Split a rendered journal into (percent, message, code) sections on
    progress markers.

    A journal with no markers returns one section covering the whole file.
    """
    lines = source.splitlines()
    sections, current, pct, msg = [], [], None, ""

    for line in lines:
        marker = _MARKER_RE.match(line)
        if marker:
            if current:
                sections.append((pct, msg, "\n".join(current)))
                current = []
            pct = int(marker.group(1))
            msg = marker.group(2).strip()
        else:
            current.append(line)

    if current:
        sections.append((pct, msg, "\n".join(current)))
    return sections


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def load(journal_file: str) -> str:
    """Read a journal, with a clear error if it has not been recorded yet."""
    if not os.path.isfile(journal_file):
        raise JournalError(
            f"Journal not found: {journal_file}\n"
            f"Record it with:  python tools/record_journal.py "
            f"--sim-type {os.path.basename(os.path.dirname(journal_file))} "
            f"--stage {os.path.splitext(os.path.basename(journal_file))[0]}"
        )
    with open(journal_file, encoding="utf-8") as handle:
        return handle.read()


def execute(journal_file: str,
            tokens: Dict[str, Any],
            namespace: Dict[str, Any],
            progress_cb: Optional[Callable] = None,
            pct_offset: float = 0.0,
            pct_scale: float = 1.0) -> Dict[str, Any]:
    """
    Render and execute a journal.

    `namespace` supplies the objects the journal expects to be bound already
    (meshing, watertight, solver, config, log). It is used as the exec globals,
    so anything the journal defines is visible to the caller afterwards.

    `pct_offset` and `pct_scale` map the journal's 0-100 markers into a slice
    of the overall job progress, so meshing and solving can share one bar.

    Returns the namespace after execution.
    """
    name     = os.path.basename(journal_file)
    source   = load(journal_file)
    rendered = render(source, tokens, name)
    sections = split_sections(rendered)

    log.info(f"  Journal: {journal_file}")
    log.info(f"  {len(sections)} section(s), {len(rendered.splitlines())} lines")

    namespace.setdefault("__name__", "__journal__")
    namespace.setdefault("log", log)

    started = time.time()
    for index, (pct, msg, code) in enumerate(sections, start=1):
        if not code.strip():
            continue
        if pct is not None:
            overall = pct_offset + pct * pct_scale
            log.info(f"[{overall:3.0f}%] {msg}")
            if progress_cb:
                progress_cb(msg, int(overall))
        try:
            exec(compile(code, f"{name}:section{index}", "exec"), namespace)
        except Exception as exc:
            raise JournalError(
                f"{name} failed in section {index}"
                + (f" ({msg})" if msg else "")
                + f": {exc}"
            ) from exc

    log.info(f"  Journal complete in {time.time() - started:.1f}s")
    return namespace


def run_mesh_journal(config, meshing, watertight, tokens,
                     progress_cb=None) -> Dict[str, Any]:
    """
    Execute the meshing journal for this simulation type.

    Bound names: meshing, watertight, config, log.
    Progress markers map onto 0-95% of the job.
    """
    from core.journal_params import sim_type_key
    from utils.resource_path import journal_path

    journal_file = journal_path(sim_type_key(config.sim_type), "mesh",
                                getattr(config, "journal_dir", ""))
    # `workflow` is what recorded journals use -- PyFluent writes meshing
    # workflow calls in the classic TaskObject form, not the enhanced one.
    namespace = {
        "meshing":    meshing,
        "workflow":   meshing.workflow,
        "watertight": watertight,
        "config":     config,
        "log":        log,
    }
    return execute(journal_file, tokens, namespace,
                   progress_cb=progress_cb, pct_offset=0.0, pct_scale=0.95)


def run_solve_journal(config, solver, tokens,
                      progress_cb=None) -> Dict[str, Any]:
    """
    Execute the solver journal for this simulation type.

    Bound names: solver, config, log.
    Progress markers map onto 0-95% of the job; the remainder is result
    extraction, which stays in Python because journaling omits queries.
    """
    from core.journal_params import sim_type_key
    from utils.resource_path import journal_path

    journal_file = journal_path(sim_type_key(config.sim_type), "solve",
                                getattr(config, "journal_dir", ""))
    namespace = {
        "solver": solver,
        "config": config,
        "log":    log,
    }
    return execute(journal_file, tokens, namespace,
                   progress_cb=progress_cb, pct_offset=0.0, pct_scale=0.95)


# ---------------------------------------------------------------------------
# CLI -- validate a journal without Fluent
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    from simtypes.configs import SimType, SIM_TYPE_REGISTRY
    from core import journal_params

    parser = argparse.ArgumentParser(
        description="Render a journal and report token problems without "
                    "executing it."
    )
    parser.add_argument("--check", required=True, metavar="JOURNAL",
                        help="path to a journal file")
    parser.add_argument("--sim-type", default=None,
                        help="sim type for token values "
                             "(default: inferred from the journal's folder)")
    parser.add_argument("--show", action="store_true",
                        help="print the rendered journal")
    args = parser.parse_args()

    key = args.sim_type or os.path.basename(os.path.dirname(args.check))
    match = next(
        (t for t in SimType if journal_params.sim_type_key(t) == key), None
    )
    if match is None:
        valid = ", ".join(journal_params.all_sim_type_keys())
        raise SystemExit(f"Unknown sim type {key!r}. Valid: {valid}")

    config = SIM_TYPE_REGISTRY[match]()
    config.name          = "check"
    config.geometry_path = "C:/example/car.pmdb"
    config.output_dir    = "C:/example/out"
    tokens = journal_params.build(config)

    source = load(args.check)
    used   = find_tokens(source)

    print(f"Journal:   {args.check}")
    print(f"Sim type:  {match.value}")
    print(f"Lines:     {len(source.splitlines())}")
    print(f"Tokens:    {len(used)} used of {len(tokens)} available")

    unknown = sorted(used - set(tokens))
    if unknown:
        print(f"\nUNKNOWN TOKENS ({len(unknown)}):")
        for token in unknown:
            print(f"  {{{{{token}}}}}")
        raise SystemExit(1)

    sections = split_sections(render(source, tokens, os.path.basename(args.check)))
    print(f"Sections:  {len(sections)}")
    for pct, msg, _ in sections:
        if pct is not None:
            print(f"  {pct:3d}%  {msg}")

    if args.show:
        print("\n" + "-" * 70)
        print(render(source, tokens, os.path.basename(args.check)))

    print("\nOK — journal renders cleanly.")


if __name__ == "__main__":
    _main()