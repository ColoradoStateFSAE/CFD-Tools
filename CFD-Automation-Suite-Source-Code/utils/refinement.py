"""
Local refinement region calculator.

Computes the Near / Mid / Far bounding boxes from the car's overall
dimensions, per Tables 1-3 of the Ram Racing Fluent Procedure document.
Same formulas as MATLAB-Scripts/localrefinementregion.m.

    L = length (x axis)      W = width (z axis)      H = height (y axis)

    Near   0.032 m    X  -L        to 3L     Y 0 to H + L/3     Z  +/-(W + H/2)
    Mid    0.064 m    X  -1.25L    to 5L     Y 0 to H + 2L/3    Z  +/-(W + H)
    Far    0.128 m    X  -1.5L     to 7L     Y 0 to 2L          Z  +/-(W + 3H/2)

Half and quarter models sit at z >= 0, so their z_min is clamped to 0.

Check the numbers without launching Fluent:

    python -m utils.refinement 2.9 1.4 1.2 --half
"""
from dataclasses import dataclass


@dataclass
class Box:
    """One refinement box. All values in metres."""
    name:  str
    size:  float
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    def __str__(self) -> str:
        return (f"{self.name:28s} {self.size:6.3f} m   "
                f"X[{self.x_min:8.3f}, {self.x_max:8.3f}]  "
                f"Y[{self.y_min:8.3f}, {self.y_max:8.3f}]  "
                f"Z[{self.z_min:8.3f}, {self.z_max:8.3f}]")


def refinement_boxes(length: float, width: float, height: float,
                     half_model: bool = False) -> list:
    """
    Return [near, mid, far] boxes for a car of the given dimensions.

    `half_model` clamps z_min to 0 for half and quarter geometries.
    """
    L, W, H = float(length), float(width), float(height)

    def z_lo(extent: float) -> float:
        return 0.0 if half_model else -extent

    near = Box("local-refinement-nearfield", 0.032,
               -L,        3.0 * L,
               0.0,       H + L / 3.0,
               z_lo(W + H / 2.0),  W + H / 2.0)

    mid = Box("local-refinement-midfield", 0.064,
              -1.25 * L,  5.0 * L,
              0.0,        H + 2.0 * L / 3.0,
              z_lo(W + H),        W + H)

    far = Box("local-refinement-farfield", 0.128,
              -1.5 * L,   7.0 * L,
              0.0,        2.0 * L,
              z_lo(W + 1.5 * H),  W + 1.5 * H)

    return [near, mid, far]


# Wheel refinement box -- Table 4. Bounds are ratios of the wheel body, not
# absolute coordinates, so they do not depend on car dimensions.
WHEEL_BOX_SIZE = 0.032
WHEEL_BOX_RATIOS = {
    "XminRatio": 0.1, "XmaxRatio": 1.0,
    "YminRatio": 0.0, "YmaxRatio": 0.1,
    "ZminRatio": 0.1, "ZmaxRatio": 0.1,
}


def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Print refinement box bounds for a car."
    )
    parser.add_argument("length", type=float, help="car length [m], x axis")
    parser.add_argument("width",  type=float, help="car width [m], z axis")
    parser.add_argument("height", type=float, help="car height [m], y axis")
    parser.add_argument("--half", action="store_true",
                        help="half or quarter model, clamps z_min to 0")
    args = parser.parse_args()

    print(f"\nL = {args.length} m   W = {args.width} m   H = {args.height} m"
          f"   {'(half model)' if args.half else '(full model)'}\n")
    for box in refinement_boxes(args.length, args.width, args.height,
                                args.half):
        print(f"  {box}")
    print()


if __name__ == "__main__":
    _main()