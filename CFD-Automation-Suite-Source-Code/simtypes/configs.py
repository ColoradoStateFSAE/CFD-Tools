"""
Simulation type definitions.
Add new sim types by subclassing BaseSimConfig and registering in SIM_TYPES.
"""
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class SimType(Enum):
    HALF_CAR = "Half Car"
    FULL_CAR = "Full Car"
    FRONT_WING_ONLY = "Front Wing Only"
    REAR_WING_ONLY = "Rear Wing Only"
    QUARTER_MODEL = "Quarter Model"


@dataclass
class WheelMRFConfig:
    """Configuration for a single wheel Moving Reference Frame zone."""
    name: str                    # e.g. "FLW", "FRW", "RLW", "RRW"
    zone_name: str               # Fluent zone name for the MRF cell zone
    center_x: float = 0.0        # wheel center coords [m]
    center_y: float = 0.0
    center_z: float = 0.0
    axis_x: float = 0.0          # rotation axis direction (usually 0,0,1 or 0,0,-1)
    axis_y: float = 0.0
    axis_z: float = 1.0
    rpm: float = 0.0             # auto-calculated from vehicle speed if 0
    wheel_radius: float = 0.203  # [m] default ~8 inch radius


@dataclass
class BaseSimConfig:
    """Base configuration shared by all simulation types."""
    name: str = "Untitled Sim"
    geometry_path: str = ""
    output_dir: str = ""            # where .cas.h5 mesh/case files are saved
    results_dir: str = ""           # where exported results .txt is saved
    vehicle_speed_mph: float = 40.0
    turbulence_model: str = "GEKO"           # k-omega GEKO
    use_curvature_correction: bool = False    # off until final ramp-up
    use_production_limiter: bool = True
    double_precision: bool = True
    num_processes: int = 70
    mpi_type: str = "intel"                # openmpi, intel, default

    # Mesh sizing
    surface_mesh_min: float = 0.002          # [m]
    surface_mesh_max: float = 0.256          # [m]
    volume_mesh_min: float = 0.0005          # [m]
    volume_mesh_max: float = 0.256           # [m]

    # Boundary layer
    bl_num_layers: int = 8
    bl_first_height: float = 0.0005          # [m]
    bl_transition_ratio: float = 0.272

    # Ramp-up iterations
    ramp0_iters: int = 500    # Initial first-order run
    ramp1_iters: int = 1000    # Second order + Presto pressure
    ramp2_iters: int = 1000    # Full second order no curvature correction
    ramp3_iters: int = 1000    # Full send (with curvature correction)

    # Car geometry reference (for refinement box sizing)
    car_length_m: float = 3.1    # L - x axis
    car_width_m: float = 1.4     # W - z axis
    car_height_m: float = 1.2    # H - y axis

    # Wheel MRF zones
    wheel_mrf_zones: List[WheelMRFConfig] = field(default_factory=list)
    use_wheel_mrf: bool = True

    # Wheelbase for CoP % calculation [in] — RR26 default 62.0 in
    # CoP arm lengths (Lf, Lr, Lu) are derived from simulation moment data
    wheelbase_in: float = 62.0

    # Extra custom result fields user can define (expandable)
    # Each entry: {"label": str, "zone": str, "type": "lift"|"drag"}
    extra_result_zones: List[dict] = field(default_factory=list)

    @property
    def sim_type(self) -> SimType:
        raise NotImplementedError

    @property
    def is_half_symmetry(self) -> bool:
        return False

    def validate(self) -> List[str]:
        """Return list of validation errors, empty if valid."""
        import os
        errors = []
        if not self.geometry_path:
            errors.append("Geometry path is required.")
        else:
            ext = os.path.splitext(self.geometry_path)[1].lower()
            if ext not in (".pmdb", ".dsco"):
                errors.append(
                    f"Geometry must be a .pmdb or .dsco file (got '{ext}'). "
                    "Export from Ansys Discovery as PMDB before importing."
                )
        if not self.output_dir:
            errors.append("Simulation output directory is required.")
        if not self.results_dir:
            errors.append("Results export directory is required.")
        if self.vehicle_speed_mph <= 0:
            errors.append("Vehicle speed must be > 0.")
        if self.num_processes <= 0:
            errors.append("Number of processes must be > 0.")
        return errors


@dataclass
class HalfCarConfig(BaseSimConfig):
    """
    Half-car simulation (symmetry plane at z=0).
    Downforce outputs are doubled automatically.
    """
    name: str = "Half Car Sim"
    # Half car defaults - 2 wheels (driver side)
    wheel_mrf_zones: List[WheelMRFConfig] = field(default_factory=lambda: [
        WheelMRFConfig(
            name="FRW",
            zone_name="mrf_frw",
            center_x=0.0, center_y=0.152, center_z=0.0,
            axis_x=0.0, axis_y=0.0, axis_z=1.0,
            wheel_radius=0.203,
        ),
        WheelMRFConfig(
            name="RRW",
            zone_name="mrf_rrw",
            center_x=0.0, center_y=0.152, center_z=0.0,
            axis_x=0.0, axis_y=0.0, axis_z=1.0,
            wheel_radius=0.203,
        ),
    ])

    @property
    def sim_type(self) -> SimType:
        return SimType.HALF_CAR

    @property
    def is_half_symmetry(self) -> bool:
        return True

    def validate(self) -> List[str]:
        errors = super().validate()
        return errors


@dataclass
class FullCarConfig(BaseSimConfig):
    """Full car simulation - all 4 wheels."""
    name: str = "Full Car Sim"
    wheel_mrf_zones: List[WheelMRFConfig] = field(default_factory=lambda: [
        WheelMRFConfig(name="FLW", zone_name="mrf_flw", wheel_radius=0.203,
                       axis_z=1.0),
        WheelMRFConfig(name="FRW", zone_name="mrf_frw", wheel_radius=0.203,
                       axis_z=-1.0),
        WheelMRFConfig(name="RLW", zone_name="mrf_rlw", wheel_radius=0.203,
                       axis_z=1.0),
        WheelMRFConfig(name="RRW", zone_name="mrf_rrw", wheel_radius=0.203,
                       axis_z=-1.0),
    ])

    @property
    def sim_type(self) -> SimType:
        return SimType.FULL_CAR


@dataclass
class FrontWingConfig(BaseSimConfig):
    """Front wing only simulation - isolated element testing."""
    name: str = "Front Wing Sim"
    wheel_mrf_zones: List[WheelMRFConfig] = field(default_factory=list)
    use_wheel_mrf: bool = False

    @property
    def sim_type(self) -> SimType:
        return SimType.FRONT_WING_ONLY


@dataclass
class RearWingConfig(BaseSimConfig):
    """Rear wing only simulation - isolated element testing."""
    name: str = "Rear Wing Sim"
    wheel_mrf_zones: List[WheelMRFConfig] = field(default_factory=list)
    use_wheel_mrf: bool = False

    @property
    def sim_type(self) -> SimType:
        return SimType.REAR_WING_ONLY


@dataclass
class QuarterModelConfig(BaseSimConfig):
    """
    Quarter model - symmetry in both z and... not y.
    Typically used for isolated wing endplate sensitivity studies.
    """
    name: str = "Quarter Model Sim"
    wheel_mrf_zones: List[WheelMRFConfig] = field(default_factory=list)
    use_wheel_mrf: bool = False

    @property
    def sim_type(self) -> SimType:
        return SimType.QUARTER_MODEL

    @property
    def is_half_symmetry(self) -> bool:
        return True


# Registry: maps SimType enum → config class
SIM_TYPE_REGISTRY = {
    SimType.HALF_CAR: HalfCarConfig,
    SimType.FULL_CAR: FullCarConfig,
    SimType.FRONT_WING_ONLY: FrontWingConfig,
    SimType.REAR_WING_ONLY: RearWingConfig,
    SimType.QUARTER_MODEL: QuarterModelConfig,
}