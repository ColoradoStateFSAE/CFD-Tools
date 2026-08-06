# CFD Batch Post-Processing (ParaView)

Automated ParaView post-processing for FSAE aero CFD runs. Takes Fluent EnSight Gold
exports (`.encas`) and produces contours, streamlines, sweep movies, slice decks,
line-graph CSVs, surface LIC, and Q-criterion isosurfaces.

**Current script:** `batch_postprocess_2026-08-05_0247.py`

Every version is stamped with a date and time in both the filename and the
`SCRIPT_VERSION` constant, which prints at startup. Always check the banner to
confirm which version you are actually running.

---

## Requirements

- ParaView 6.2.0-RC1 (the script is written against a confirmed trace from this
  version; see Version Sensitivity below)
- Run with `pvpython`, not a system Python. `paraview.simple` is not a pip package,
  it ships inside the ParaView install.

The script is run through `pvpython.exe` from the ParaView `bin` folder:

```powershell
C:\ParaView\bin\pvpython.exe batch_postprocess.py [flags]
```

For headless runs on the HPC, use `pvbatch --mesa` instead of `pvpython`.

---

## Quick start

Always start with a probe. It resolves the block selectors and exits before
rendering anything, so it finishes in seconds:

```powershell
C:\ParaView\bin\pvpython.exe batch_postprocess.py --probe-only
```

Then a fast smoke test of the most fragile stage:

```powershell
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --fields static_pressure --views side --frames 10 --resolution 1280 720
```

Then scale up once that works.

---

## Configuration

Edit these at the top of the script before the first run.

### Cases

```python
CASES = [
    {"name": "case_001",
     "file": r"C:\path\to\FLTG-Setup-Output.encas",
     "out":  r"C:\path\to\output"},
]
```

Add one dict per Fluent run. `name` is used as a filename prefix, `out` is the
output root for that case.

### Other settings worth knowing

| Constant | Default | Meaning |
|---|---|---|
| `IMG_SIZE` | `[3840, 2160]` | Output resolution (true 4K) |
| `N_SWEEP_FRAMES` | `120` | Frames per sweep movie (120 at 24fps = 5 seconds) |
| `MOVIE_FRAMERATE` | `24` | Movie framerate |
| `MOVIE_BITRATE` | `10000000` | MP4 bitrate |
| `SLICE_STEP` | `0.05` | Slice deck spacing in metres (50mm) |
| `FIELD_RANGES` | see script | Fixed color scale per field, so cases stay comparable |
| `COLOR_PRESET` | `Rainbow Uniform` | Applied to every color-mapped output |
| `WASH_BOUNDS` | x -1.0 to 2.5, y 0 to 1.8, z 0 to 1.8 | Sweep and slice extent |
| `ISOSURFACE_VALUE` | `1.0` | Q-criterion threshold; data-dependent, tune if empty or solid |

The four command-line overrides (`--frames`, `--fps`, `--slice-step`,
`--resolution`) change these at runtime without editing the file.

---

## Flags

### `--stage {contours,streamlines,graphs,movies,slices,lic,iso,all} [...]`
Which stage(s) to run. Accepts multiple values. Default: `all`.

```powershell
--stage contours
--stage contours streamlines graphs
--stage all
```

### `--views {top,side,front} [...]`
Limit sweep movies and slice decks to specific views. Default: all three.
Has no effect on contours, streamlines, LIC, or isosurfaces, which use their own
fixed isometric and underside-isometric cameras.

```powershell
--views side
--views top front
```

### `--fields {velocity,static_pressure,total_pressure} [...]`
Limit sweep movies and slice decks to specific fields. Default: all three.

```powershell
--fields static_pressure
--fields velocity total_pressure
```

### `--case NAME [...]`
Run only the named cases from `CASES`. Default: all of them.

```powershell
--case case_001
--case case_001 case_003
```

### `--frames N`
Override sweep movie frame count. Default: `N_SWEEP_FRAMES` (120).
Movie duration in seconds is `frames / fps`.

```powershell
--frames 24     # 1 second at 24fps
--frames 120    # 5 seconds at 24fps
```

### `--fps N`
Override movie framerate. Default: `MOVIE_FRAMERATE` (24).

### `--slice-step METRES`
Override slice deck spacing. Default: `SLICE_STEP` (0.05, i.e. 50mm).
Larger values mean far fewer images and much shorter runtimes.

```powershell
--slice-step 0.1    # 100mm spacing, roughly half as many slices
```

### `--resolution W H`
Override output resolution for both stills and movies. Default: 3840 2160.

```powershell
--resolution 1280 720     # fast test
--resolution 1920 1080
--resolution 3840 2160    # 4K
```

### `--encoder {auto,paraview,ffmpeg}`
Which backend encodes the movies. Default: `auto`.

- `paraview` uses vtkMP4Writer (Windows Media Foundation). Two hard limits: both
  dimensions must be divisible by 16, and it will not initialize above roughly
  1920x1088 in an offscreen pvpython process.
- `ffmpeg` renders PNG frames at full resolution and encodes externally. No
  dimension limits, so this is the only way to get 4K movies.
- `auto` uses ffmpeg when it is installed and the requested size exceeds what
  vtkMP4Writer can handle, otherwise stays on the ParaView path.

Dimensions are snapped up to the nearest multiple of 16 automatically on the
ParaView path, so `--resolution 1920 1080` silently becomes 1920x1088 rather
than failing. The startup banner reports which encoder was chosen and whether
any snapping occurred.

### `--ffmpeg-path PATH`
Full path to `ffmpeg.exe` if it is not on PATH.

```powershell
--ffmpeg-path "C:\ffmpeg\bin\ffmpeg.exe"
```

### `--crf N`
ffmpeg quality. 0 is lossless, 18 is visually lossless, 23 is the ffmpeg default,
51 is worst. Default: 18. Lower values mean bigger files.

### `--keep-frames`
Keep the intermediate PNG frames after ffmpeg encoding. They are deleted by
default. Useful if you want the individual frames as stills.

### `--probe-only`
Resolve the block selectors, print cell counts, and exit without rendering.
The fastest way to confirm the pipeline is healthy, and the first thing to run
after any ParaView upgrade.

### `--list-stages`
Print available stage names and exit.

### `--help`
Full usage text with examples.

---

## Installing ffmpeg (needed for 4K movies)

ffmpeg is only required for movies above 1920x1088. Everything else, including all
still images at true 4K, works without it.

### Option A: winget (easiest)

```powershell
winget install Gyan.FFmpeg
```

Close and reopen PowerShell, then verify:

```powershell
ffmpeg -version
```

winget handles PATH automatically. If the verify step fails, reboot and try again.

### Option B: manual install

1. Go to https://www.gyan.dev/ffmpeg/builds/ and download **ffmpeg-release-essentials.zip**
   under "release builds".
2. Extract it. You will get a folder like `ffmpeg-7.1-essentials_build` containing a
   `bin` subfolder with `ffmpeg.exe` inside.
3. Move that folder to a simple path with no spaces, for example `C:\ffmpeg`, so the
   executable ends up at `C:\ffmpeg\bin\ffmpeg.exe`.
4. Add `C:\ffmpeg\bin` to PATH:
   - Press the Windows key, type "environment variables", open **Edit the system
     environment variables**
   - Click **Environment Variables**
   - Under **User variables**, select **Path**, click **Edit**
   - Click **New**, paste `C:\ffmpeg\bin`
   - Click OK on all three dialogs
5. Close and reopen PowerShell, then verify:

```powershell
ffmpeg -version
```

You should see version and build information. If you get "not recognized", the PATH
entry did not take; confirm `C:\ffmpeg\bin\ffmpeg.exe` exists at that exact path and
that you opened a new terminal window.

### Skipping PATH entirely

If you would rather not touch PATH, point the script straight at the executable:

```powershell
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --encoder ffmpeg --ffmpeg-path "C:\ffmpeg\bin\ffmpeg.exe" --resolution 3840 2160
```

Or set `FFMPEG_PATH` near the top of the script to that full path once.

---

## Movie resolution reference

| Requested | H.264 valid | Encoder used (auto) | Notes |
|---|---|---|---|
| 1280x720 | yes | paraview | Both dimensions divide by 16 |
| 1920x1080 | no | paraview | Snapped to 1920x1088; 1080/16 = 67.5 |
| 1920x1088 | yes | paraview | Maximum for the ParaView writer |
| 2560x1440 | yes | ffmpeg | Above the writer limit |
| 3840x2160 | yes | ffmpeg | True 4K, ffmpeg required |

Without ffmpeg installed, anything above 1920x1088 falls back to the ParaView writer
and fails with "Could not initialize writer".

Still images (contours, streamlines, slice decks, LIC, isosurfaces) are PNG and have
none of these constraints, so they render at true 4K regardless.

---

## Stages

| Stage | Output folder | What it makes |
|---|---|---|
| `contours` | `contours/` | Static and total pressure on the car surface, isometric and underside-isometric. Velocity is deliberately excluded: no-slip makes surface velocity ~0, so it carries no information. |
| `streamlines` | `streamlines/` | Streamlines seeded in the fluid domain from two clouds (a general upstream cloud plus a dedicated low seed for underfloor coverage), colored by pressure and velocity, with the car shown in plain grey for context. |
| `graphs` | `graphs/centerline/`, `graphs/spanwise/` | CSV line extractions. Centerline front-to-rear, plus a spanwise family every 50mm across the half-width. |
| `movies` | `movies/` | Sweep movies as `.mp4`, driven by ParaView's native animation engine. The slice plane sweeps the domain while the camera translates with it. |
| `slices` | `slices/<view>/<field>/` | Static slice deck at `SLICE_STEP` spacing, filenames tagged by position (e.g. `zp0500mm.png`). |
| `lic` | `surface_lic/` | Surface LIC on the car body colored by total pressure. The CFD analogue of flow-vis paint. |
| `iso` | `isosurfaces/` | Q-criterion isosurfaces colored by velocity magnitude, for locating vortex structures and induced-drag sources. |

---

## Common commands

```powershell
# health check, no rendering
C:\ParaView\bin\pvpython.exe batch_postprocess.py --probe-only

# fast smoke test of the movie pipeline
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --fields static_pressure --views side --frames 10 --resolution 1280 720

# 5 second 1080p movies, one view at a time (auto-snaps to 1920x1088)
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --views top --frames 120 --fps 24 --resolution 1920 1080
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --views side --frames 120 --fps 24 --resolution 1920 1080
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --views front --frames 120 --fps 24 --resolution 1920 1080

# all three views in one run
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --views top side front --frames 120 --fps 24 --resolution 1920 1080

# 1 second 4K movie, single field and view (needs ffmpeg)
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --fields static_pressure --views side --frames 24 --fps 24 --resolution 3840 2160

# full quality single 4K movie, 5 seconds
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --fields static_pressure --views side --frames 120 --fps 24 --resolution 3840 2160

# ffmpeg installed but not on PATH
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage movies --encoder ffmpeg --ffmpeg-path "C:\ffmpeg\bin\ffmpeg.exe" --resolution 3840 2160

# individual stage tests at low res
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage contours --resolution 1280 720
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage streamlines --resolution 1280 720
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage graphs
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage lic --resolution 1280 720
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage iso --resolution 1280 720

# everything except movies, at 4K
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage contours streamlines graphs lic iso slices --resolution 3840 2160

# coarse slice deck to keep image counts manageable
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage slices --slice-step 0.2 --resolution 3840 2160

# everything
C:\ParaView\bin\pvpython.exe batch_postprocess.py --stage all
```

---

## Runtime expectations

The fluid domain is roughly 20 million cells, so slicing it repeatedly is the
dominant cost. Every stage prints its own elapsed time and the total prints at
the end. Use a short run to extrapolate before committing to a full batch.

Rough scaling: one movie at N frames costs about N renders. A full `--stage movies`
run is 3 fields times 3 views, so nine movies, or roughly nine times a single-movie
timing. Slice decks scale as `(range / slice_step) + 1` images per field-view pair.

---

## Version sensitivity

ParaView's Python API changes between releases, and several of these changes fail
silently rather than raising. Known examples encountered while building this script:

- **Block selector names changed between 6.1.1 and 6.2.0-RC1**: the fluid block went
  from `/Root/enclosureenclosure11` to `/Root/enclosure-enclosure11`. `ExtractBlock`
  does not error on an unmatched selector, it returns zero cells, so every downstream
  output renders blank with no warning. The script now probes candidate spellings at
  runtime and reports which one matched.
- `AxisAlignedReflect` uses `ReflectionPlane.Set(Origin=..., Normal=...)`, not a
  `Plane` enum.
- Scalar bar placement uses `WindowLocation='Any Location'` (with a space) and
  `ScalarBarLength`, not the removed `Position2`.
- The camera animation track must be set to `Mode='Interpolate Camera'`. The default
  is `'Follow-data'`, which silently ignores keyframe positions.

**After any ParaView upgrade, run `--probe-only` first.** If a selector stops
matching, add the new spelling to `FLUID_BLOCK_CANDIDATES` or `CAR_BLOCK_NAMES` at
the top of the script.

To recover an unknown selector name: open the case in the ParaView GUI, add an
ExtractBlock filter with the blocks you want, and record it with
`Tools > Start Trace`. The trace shows the exact selector strings for that build.

---

## Troubleshooting

**Blank or empty images**
Run `--probe-only`. A zero cell count on either block is the cause. See Version
Sensitivity above.

**`[movie] FAILED` in the output**
The animation ran but the MP4 writer produced nothing. Retry at a lower
`--resolution` to determine whether it is an encoder limit rather than a pipeline
problem.

**Isosurface warning about being empty**
`ISOSURFACE_VALUE` is data-dependent. If the warning appears, lower it (try 0.5).
If the result is a solid blob obscuring everything, raise it (try 2.0).

**Legends stacked on top of each other**
Should not occur; `hide_all_scalar_bars()` force-clears every known legend before
each new one. If it reappears, a new field was added to the script without being
listed in `ALL_COLOR_FIELDS`.

**Slice deck producing an overwhelming number of images**
Raise `--slice-step`. At the default 50mm across the configured bounds you get
roughly 70 slices in X, 36 in Y, and 36 in Z, for each field and view combination.