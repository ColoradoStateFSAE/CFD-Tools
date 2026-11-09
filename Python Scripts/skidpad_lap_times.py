"""
Compute skidpad lap times from a VI-CarRealTime MaxPerformance results CSV,
using driving_machine_monitor.path_y as the lap sensor.

Usage:
    python skidpad_lap_times.py skidpad.csv

How it works:
- path_y swings out to the circle radius and back to (near) zero once per
  lap. It does NOT reliably cross zero with a sign flip every time (it can
  approach zero from the same side and turn back without crossing), so this
  script instead watches for each time |path_y| dips below THRESHOLD and
  comes back out, and records the timestamp of the closest approach to zero
  within that dip as the lap-sensor trigger.
- MIN_GAP_S rejects a second trigger too soon after the last one, in case
  the signal wobbles in and out of the threshold band near the same pass.
- The event time is taken as the sample with minimum |path_y| in each dip
  (not interpolated) since these are near-misses rather than true
  crossings.

Tune THRESHOLD if you get too many or too few events: too small and a lap
that swings less wide (or a noisy signal) may never dip under it; too large
and two separate passes can merge into one event, or extra events appear
mid-lap.
"""

import sys
import csv

TIME_COL = "time.TIME"
Y_COL = "driving_machine_monitor.path_y"
THRESHOLD = 1.0   # meters -- how close to y = 0 counts as "at the sensor"
MIN_GAP_S = 1.0   # minimum seconds between accepted events


def load_column(path, col_name):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if TIME_COL not in reader.fieldnames or col_name not in reader.fieldnames:
            raise SystemExit(
                f"Expected columns '{TIME_COL}' and '{col_name}' not found in {path}"
            )
        times = []
        values = []
        for row in reader:
            times.append(float(row[TIME_COL]))
            values.append(float(row[col_name]))
    return times, values


def find_events(times, values, threshold, min_gap):
    events = []
    in_region = False
    region_start_i = None
    last_event_t = -float("inf")

    def close_region(end_i):
        nonlocal last_event_t
        seg = range(region_start_i, end_i)
        min_i = min(seg, key=lambda k: abs(values[k]))
        t_event = times[min_i]
        if t_event - last_event_t >= min_gap:
            events.append(t_event)
            last_event_t = t_event

    for i in range(len(times)):
        below = abs(values[i]) < threshold
        if below and not in_region:
            in_region = True
            region_start_i = i
        if not below and in_region:
            close_region(i)
            in_region = False

    if in_region:
        close_region(len(times))

    return events


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <skidpad.csv>")
        sys.exit(1)

    path = sys.argv[1]
    times, values = load_column(path, Y_COL)
    events = find_events(times, values, THRESHOLD, MIN_GAP_S)

    if len(events) < 2:
        print(f"Found only {len(events)} sensor event(s) -- not enough to "
              f"compute a lap time. Try adjusting THRESHOLD or MIN_GAP_S "
              f"at the top of the script.")
        return

    print(f"Found {len(events)} sensor events (|{Y_COL}| < {THRESHOLD}):\n")
    for i, t in enumerate(events):
        print(f"  event {i}: t = {t:.4f} s")

    print("\nLap times (time between consecutive events):")
    for i in range(1, len(events)):
        lap_time = events[i] - events[i - 1]
        print(f"  lap {i}: {lap_time:.4f} s")


if __name__ == "__main__":
    main()