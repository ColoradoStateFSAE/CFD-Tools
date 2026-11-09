#!/usr/bin/env python3
"""
DEGraph.py

Reads a simulation sweep CSV (like the one exported from your aero/lap-time
sweep tool) and produces a filled-contour plot of lap time as a function of
Cd (x-axis) and Cl (y-axis) -- the same style as the "Average - All Circuits"
plot you referenced.

USAGE
-----
    python DEGraph.py metrics.csv

    # if your column names differ from the defaults, point at them directly:
    python DEGraph.py metrics.csv \
        --cd-col aero.CDragAverage \
        --cl-col aero.CLiftAverage \
        --time-col summary.tRunTotal \
        --out cd_cl_laptime.png

WHAT IT DOES
------------
1. Loads the CSV.
2. Pulls out the Cd column, Cl column, and lap/run-time column.
3. If the (Cd, Cl) samples fall on a regular grid (as in a Cd x Cl sweep),
   it pivots them straight into a 2-D grid. If they don't (e.g. scattered/
   randomly sampled data), it interpolates onto a regular grid with
   scipy.griddata so contouring still works.
4. Draws filled contours (colormap) + contour lines with inline labels,
   overlays the actual sample points, and marks the best (lowest) lap time.

Adjust DEFAULT_CD_CANDIDATES / DEFAULT_CL_CANDIDATES / DEFAULT_TIME_CANDIDATES
below if you want the auto-detector to look for different substrings.
"""

import argparse
import sys
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from scipy.interpolate import RegularGridInterpolator


def seconds_to_mmss(x, pos=None):
    """Format a value in seconds as M:SS.ss (e.g. 254.4 -> '4:14.40')."""
    if x < 0 or not np.isfinite(x):
        return ""
    minutes = int(x // 60)
    secs = x - minutes * 60
    return f"{minutes}:{secs:05.2f}"

# Substrings used to auto-detect the right columns if the user doesn't
# pass --cd-col / --cl-col / --time-col explicitly.
DEFAULT_CD_CANDIDATES = ["CDragAverage", "CDrag", "Cd"]
DEFAULT_CL_CANDIDATES = ["CLiftAverage", "CLift", "Cl"]
DEFAULT_TIME_CANDIDATES = ["tRunTotal", "tLapTotal", "LapTime", "tLap"]


def autodetect_column(df, candidates, label):
    for cand in candidates:
        matches = [c for c in df.columns if cand.lower() in c.lower()]
        if matches:
            return matches[0]
    raise SystemExit(
        f"Could not auto-detect a column for {label}. "
        f"Please pass it explicitly (e.g. --{label}-col your.column.name).\n"
        f"Available columns:\n" + "\n".join(df.columns)
    )


def build_grid(cd, cl, t):
    """Return (Cd_grid, Cl_grid, T_grid) as 2D arrays for contour plotting."""
    cd_u = np.unique(cd)
    cl_u = np.unique(cl)

    # Regular-grid case: every (cd_u[i], cl_u[j]) combo present exactly once.
    if len(cd_u) * len(cl_u) == len(cd):
        T = np.full((len(cl_u), len(cd_u)), np.nan)
        cd_idx = {v: i for i, v in enumerate(cd_u)}
        cl_idx = {v: i for i, v in enumerate(cl_u)}
        for cdi, cli, ti in zip(cd, cl, t):
            T[cl_idx[cli], cd_idx[cdi]] = ti
        if not np.isnan(T).any():
            CD, CL = np.meshgrid(cd_u, cl_u)
            return CD, CL, T

    # Fallback: irregular / scattered samples -> interpolate onto a grid.
    from scipy.interpolate import griddata
    grid_n = 200
    cd_lin = np.linspace(cd.min(), cd.max(), grid_n)
    cl_lin = np.linspace(cl.min(), cl.max(), grid_n)
    CD, CL = np.meshgrid(cd_lin, cl_lin)
    T = griddata((cd, cl), t, (CD, CL), method="cubic")
    # patch any NaNs (usually at the convex-hull edges) with nearest-neighbor
    nan_mask = np.isnan(T)
    if nan_mask.any():
        T_nn = griddata((cd, cl), t, (CD, CL), method="nearest")
        T[nan_mask] = T_nn[nan_mask]
    return CD, CL, T


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv_path", help="Path to the sweep-results CSV file")
    p.add_argument("--cd-col", default=None, help="Column name to use for Cd (x-axis)")
    p.add_argument("--cl-col", default=None, help="Column name to use for Cl (y-axis)")
    p.add_argument("--time-col", default=None, help="Column name to use for lap/run time")
    p.add_argument("--out", default="cd_cl_laptime.png", help="Output image filename")
    p.add_argument("--levels", type=int, default=25, help="Number of contour levels")
    p.add_argument("--cmap", default="turbo", help="Matplotlib colormap name")
    p.add_argument("--title", default="Average Lap Time - Cd vs Cl", help="Plot title")
    args = p.parse_args()

    df = pd.read_csv(args.csv_path)

    cd_col = args.cd_col or autodetect_column(df, DEFAULT_CD_CANDIDATES, "cd")
    cl_col = args.cl_col or autodetect_column(df, DEFAULT_CL_CANDIDATES, "cl")
    time_col = args.time_col or autodetect_column(df, DEFAULT_TIME_CANDIDATES, "time")

    print(f"Using columns -> Cd: '{cd_col}', Cl: '{cl_col}', time: '{time_col}'")

    sub = df[[cd_col, cl_col, time_col]].dropna()
    cd = sub[cd_col].to_numpy(dtype=float)
    cl = sub[cl_col].to_numpy(dtype=float)
    t = sub[time_col].to_numpy(dtype=float)

    if len(cd) < 4:
        raise SystemExit("Not enough valid data points to build a contour plot.")

    CD, CL, T = build_grid(cd, cl, t)

    fig, ax = plt.subplots(figsize=(9, 7.5))

    # Filled contours (the color background) -- lowest z-order, sits at the back
    cf = ax.contourf(CD, CL, T, levels=args.levels, cmap=args.cmap, zorder=1)
    cbar = fig.colorbar(cf, ax=ax, format=FuncFormatter(seconds_to_mmss))
    cbar.set_label(f"{time_col} (MM:SS)")

    # Thin contour lines with inline labels, like the reference plot
    cl_lines = ax.contour(CD, CL, T, levels=args.levels, colors="k",
                           linewidths=0.5, alpha=0.6, zorder=2)
    cl_label_texts = ax.clabel(cl_lines, inline=True, fontsize=7, fmt=seconds_to_mmss)
    # Push the contour-label text itself to the very top z-order so the
    # sample-point markers below can never be drawn over the numbers.
    for txt in cl_label_texts:
        txt.set_zorder(10)

    # Overlay the actual simulated sample points -- drawn UNDER the contour
    # line labels (zorder=3, below the labels' zorder=10) so the "+" marks
    # never obscure the lap-time text.
    pts = ax.scatter(cd, cl, c="black", s=15, marker="+", linewidths=1.2,
                      label="Simulated points", zorder=3)

    # Mark the best (lowest lap time) sample
    best_idx = np.argmin(t)
    best_pt = ax.scatter(cd[best_idx], cl[best_idx], facecolors="none",
                          edgecolors="white", s=140, linewidths=2,
                          label=f"Best: {seconds_to_mmss(t[best_idx])}", zorder=4)

    ax.set_xlabel(cd_col if cd_col != "aero.CDragAverage" else "Cd (Drag Coefficient)")
    ax.set_ylabel(cl_col if cl_col != "aero.CLiftAverage" else "Cl (Lift Coefficient)")
    ax.set_title(args.title)

    # Put the "simulated points" / "best" legend BELOW the graph instead of
    # overlapping the plot area.
    ax.legend(handles=[pts, best_pt], loc="upper center",
              bbox_to_anchor=(0.5, -0.12), ncol=2, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(args.out, dpi=200)
    print(f"Saved plot to {args.out}")

    # --- Interactive hover: show the (interpolated) lap time under the cursor ---
    # Build an interpolator over the (Cl, Cd) grid so we can look up a lap
    # time for ANY cursor position inside the plot, not just the sample points.
    cd_axis = CD[0, :]
    cl_axis = CL[:, 0]
    interpolator = RegularGridInterpolator(
        (cl_axis, cd_axis), T, bounds_error=False, fill_value=None
    )

    annot = ax.annotate(
        "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
        bbox=dict(boxstyle="round", fc="white", ec="black", alpha=0.9),
        zorder=20,
    )
    annot.set_visible(False)

    def on_move(event):
        if event.inaxes != ax:
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()
            return
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return
        try:
            val = float(interpolator([[y, x]])[0])
        except Exception:
            return
        if not np.isfinite(val):
            annot.set_visible(False)
        else:
            annot.xy = (x, y)
            annot.set_text(f"Cd={x:.3f}  Cl={y:.3f}\nLap time: {seconds_to_mmss(val)}")
            annot.set_visible(True)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)

    # Open an interactive window (in addition to saving the file above).
    # On a headless machine (no display) this call is a harmless no-op, and
    # hovering only works in a real interactive window (TkAgg/Qt5Agg/etc).
    plt.show()


if __name__ == "__main__":
    main()
