"""
Simulation types.

Each module in this package is a complete, standalone simulation: its own
settings, meshing sequence, solver setup, report definitions and exports.
Nothing is shared or inherited, so reading one file tells you everything that
will run.

Every module exposes the same four things:

    NAME                display name, e.g. "Half Car"
    KEY                 identifier, e.g. "half_car"
    NAMED_SELECTIONS    {label: (boundary type, description)}
    REPORT_DEFINITIONS  {name:  (kind, description)}
    Settings            dataclass of everything the GUI can edit
    run(settings, log, progress)  -> results dict

To add a simulation type: copy the closest existing module, edit it, and add
it to the import list below.
"""
from simtypes import half_car

# Ordered as they appear in the GUI.
MODULES = [
    half_car,
]

SIM_TYPES = {module.KEY: module for module in MODULES}


def get(key: str):
    """Return the module for a simulation type key."""
    if key not in SIM_TYPES:
        available = ", ".join(SIM_TYPES)
        raise KeyError(f"Unknown simulation type {key!r}. Available: {available}")
    return SIM_TYPES[key]


def names() -> list:
    """[(key, display name), ...] in GUI order."""
    return [(module.KEY, module.NAME) for module in MODULES]
