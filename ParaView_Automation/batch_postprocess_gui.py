"""
batch_postprocess_gui.py
VERSION: 2026-11-09_1050

A small launcher window for batch_postprocess.py. Pick a case file, tick the
outputs you want, choose a resolution, hit Run. It builds the command line and
runs pvpython as a subprocess, streaming the output into the log pane.

This does NOT change how batch_postprocess.py works. It just drives the CLI
that is already there, so everything still works from the terminal as before.

Run with your NORMAL python (not pvpython - this needs tkinter, and pvpython
is launched as a subprocess anyway):

    python batch_postprocess_gui.py

Edit the two defaults just below if your paths differ.
"""

import os
import sys
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ============================================================
# DEFAULTS - edit these once
# ============================================================
DEFAULT_PVPYTHON = r"C:\ParaView\bin\pvpython.exe"
DEFAULT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "batch_postprocess.py")

# label -> --stage value
STAGES = [
    ("Pressure contours (car surface)", "contours"),
    ("Streamlines", "streamlines"),
    ("Line graphs (CSV)", "graphs"),
    ("Surface LIC (flow-vis comparison)", "lic"),
    ("Q-criterion isosurfaces", "iso"),
    ("Slice decks (slow)", "slices"),
    ("Sweep movies (slowest)", "movies"),
]
DEFAULT_ON = {"contours", "streamlines", "graphs", "lic", "iso"}

RESOLUTIONS = [
    ("1280 x 720  (fast test)", (1280, 720)),
    ("1920 x 1080 (HD)", (1920, 1080)),
    ("2560 x 1440 (QHD)", (2560, 1440)),
    ("3840 x 2160 (4K)", (3840, 2160)),
]
DEFAULT_RESOLUTION = "3840 x 2160 (4K)"

VIEWS = ["top", "side", "front"]
FIELDS = [("Velocity", "velocity"),
          ("Static pressure", "static_pressure"),
          ("Total pressure", "total_pressure")]


class App:
    def __init__(self, root):
        self.root = root
        root.title("CFD Batch Post-Processing")
        root.minsize(760, 640)

        self.proc = None
        self.log_q = queue.Queue()

        pad = {"padx": 10, "pady": 4}
        row = 0

        # ---------- paths ----------
        box = ttk.LabelFrame(root, text="Case")
        box.grid(row=row, column=0, sticky="ew", **pad)
        box.columnconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)

        ttk.Label(box, text="Case file (.encas)").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.case_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.case_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(box, text="Browse...", command=self.pick_case).grid(row=0, column=2, padx=6)

        ttk.Label(box, text="Output folder").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.out_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(box, text="Browse...", command=self.pick_out).grid(row=1, column=2, padx=6)
        ttk.Label(box, text="(blank = an 'output' folder beside the case file)",
                  foreground="#666").grid(row=2, column=1, sticky="w", padx=6)
        row += 1

        # ---------- outputs ----------
        box = ttk.LabelFrame(root, text="Outputs to generate")
        box.grid(row=row, column=0, sticky="ew", **pad)
        self.stage_vars = {}
        for i, (label, key) in enumerate(STAGES):
            v = tk.BooleanVar(value=(key in DEFAULT_ON))
            self.stage_vars[key] = v
            ttk.Checkbutton(box, text=label, variable=v,
                            command=self.sync_enabled).grid(
                row=i // 2, column=i % 2, sticky="w", padx=8, pady=2)
        btns = ttk.Frame(box)
        btns.grid(row=99, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Button(btns, text="All", width=6,
                   command=lambda: self.set_all(True)).pack(side="left", padx=2)
        ttk.Button(btns, text="None", width=6,
                   command=lambda: self.set_all(False)).pack(side="left", padx=2)
        row += 1

        # ---------- settings ----------
        box = ttk.LabelFrame(root, text="Settings")
        box.grid(row=row, column=0, sticky="ew", **pad)

        ttk.Label(box, text="Resolution").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.res_var = tk.StringVar(value=DEFAULT_RESOLUTION)
        ttk.Combobox(box, textvariable=self.res_var, state="readonly", width=24,
                     values=[r[0] for r in RESOLUTIONS]).grid(row=0, column=1, sticky="w", padx=6)

        # movie/slice scope, only relevant for those two stages
        self.scope = ttk.Frame(box)
        self.scope.grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=(8, 2))

        ttk.Label(self.scope, text="Views (movies and slice decks)").grid(
            row=0, column=0, sticky="w")
        self.view_vars = {}
        for i, v in enumerate(VIEWS):
            bv = tk.BooleanVar(value=True)
            self.view_vars[v] = bv
            ttk.Checkbutton(self.scope, text=v, variable=bv).grid(
                row=0, column=1 + i, sticky="w", padx=6)

        ttk.Label(self.scope, text="Fields (movies and slice decks)").grid(
            row=1, column=0, sticky="w", pady=4)
        self.field_vars = {}
        for i, (label, key) in enumerate(FIELDS):
            bv = tk.BooleanVar(value=True)
            self.field_vars[key] = bv
            ttk.Checkbutton(self.scope, text=label, variable=bv).grid(
                row=1, column=1 + i, sticky="w", padx=6)

        mv = ttk.Frame(box)
        mv.grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=(8, 4))
        ttk.Label(mv, text="Movie length (s)").grid(row=0, column=0, sticky="w")
        self.secs_var = tk.StringVar(value="5")
        ttk.Spinbox(mv, from_=1, to=60, width=5, textvariable=self.secs_var).grid(
            row=0, column=1, padx=6)
        ttk.Label(mv, text="fps").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.fps_var = tk.StringVar(value="60")
        ttk.Spinbox(mv, from_=1, to=120, width=5, textvariable=self.fps_var).grid(
            row=0, column=3, padx=6)
        ttk.Label(mv, text="Slice step (m)").grid(row=0, column=4, sticky="w", padx=(12, 0))
        self.step_var = tk.StringVar(value="0.05")
        ttk.Entry(mv, textvariable=self.step_var, width=7).grid(row=0, column=5, padx=6)
        row += 1

        # ---------- run ----------
        bar = ttk.Frame(root)
        bar.grid(row=row, column=0, sticky="ew", **pad)
        self.run_btn = ttk.Button(bar, text="Run", command=self.run)
        self.run_btn.pack(side="left")
        self.probe_btn = ttk.Button(bar, text="Probe only (fast check)",
                                    command=lambda: self.run(probe=True))
        self.probe_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(bar, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.status = ttk.Label(bar, text="Idle")
        self.status.pack(side="right")
        row += 1

        # ---------- log ----------
        box = ttk.LabelFrame(root, text="Output")
        box.grid(row=row, column=0, sticky="nsew", **pad)
        root.rowconfigure(row, weight=1)
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self.log = tk.Text(box, height=14, wrap="none", bg="#111", fg="#ddd",
                           insertbackground="#ddd")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.config(yscrollcommand=sb.set)

        self.sync_enabled()
        self.root.after(100, self.drain_log)

    # ---------- helpers ----------
    def pick_case(self):
        path = filedialog.askopenfilename(
            title="Select the case file",
            filetypes=[("EnSight case", "*.encas *.case"), ("All files", "*.*")])
        if path:
            self.case_var.set(path)

    def pick_out(self):
        path = filedialog.askdirectory(title="Select the output folder")
        if path:
            self.out_var.set(path)

    def set_all(self, state):
        for v in self.stage_vars.values():
            v.set(state)
        self.sync_enabled()

    def sync_enabled(self):
        """Grey out the view/field pickers unless movies or slices are selected."""
        active = self.stage_vars["movies"].get() or self.stage_vars["slices"].get()
        for child in self.scope.winfo_children():
            try:
                child.configure(state="normal" if active else "disabled")
            except tk.TclError:
                pass

    def selected_stages(self):
        return [k for _, k in STAGES if self.stage_vars[k].get()]

    def build_cmd(self, probe=False):
        case = self.case_var.get().strip()
        if not case:
            raise ValueError("Pick a case file first.")
        if not os.path.exists(case):
            raise ValueError(f"Case file not found:\n{case}")
        if not os.path.exists(DEFAULT_PVPYTHON):
            raise ValueError(f"pvpython not found at:\n{DEFAULT_PVPYTHON}\n\n"
                             f"Edit DEFAULT_PVPYTHON at the top of this file.")
        if not os.path.exists(DEFAULT_SCRIPT):
            raise ValueError(f"batch_postprocess.py not found at:\n{DEFAULT_SCRIPT}")

        cmd = [DEFAULT_PVPYTHON, DEFAULT_SCRIPT, "--file", case]

        out = self.out_var.get().strip()
        if out:
            cmd += ["--out", out]

        if probe:
            cmd += ["--probe-only"]
            return cmd

        stages = self.selected_stages()
        if not stages:
            raise ValueError("Tick at least one output.")
        cmd += ["--stage"] + stages

        w, h = dict(RESOLUTIONS)[self.res_var.get()]
        cmd += ["--resolution", str(w), str(h)]

        if "movies" in stages or "slices" in stages:
            views = [v for v in VIEWS if self.view_vars[v].get()]
            fields = [k for _, k in FIELDS if self.field_vars[k].get()]
            if not views:
                raise ValueError("Tick at least one view.")
            if not fields:
                raise ValueError("Tick at least one field.")
            cmd += ["--views"] + views
            cmd += ["--fields"] + fields

        if "movies" in stages:
            cmd += ["--seconds", self.secs_var.get(), "--fps", self.fps_var.get()]
        if "slices" in stages:
            cmd += ["--slice-step", self.step_var.get()]

        return cmd

    # ---------- run ----------
    def run(self, probe=False):
        if self.proc is not None:
            messagebox.showinfo("Busy", "A run is already in progress.")
            return
        try:
            cmd = self.build_cmd(probe=probe)
        except ValueError as e:
            messagebox.showerror("Check the settings", str(e))
            return

        self.log.delete("1.0", "end")
        printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        self.log_q.put(printable + "\n\n")

        self.run_btn.config(state="disabled")
        self.probe_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status.config(text="Running...")

        threading.Thread(target=self.worker, args=(cmd,), daemon=True).start()

    def worker(self, cmd):
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, creationflags=creationflags)
            for line in self.proc.stdout:
                self.log_q.put(line)
            code = self.proc.wait()
            self.log_q.put(f"\n--- finished, exit code {code} ---\n")
        except Exception as e:
            self.log_q.put(f"\n!! launcher error: {e}\n")
        finally:
            self.proc = None
            self.log_q.put(None)   # sentinel: re-enable the buttons

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            self.log_q.put("\n--- stopped by user ---\n")

    def drain_log(self):
        try:
            while True:
                item = self.log_q.get_nowait()
                if item is None:
                    self.run_btn.config(state="normal")
                    self.probe_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    self.status.config(text="Idle")
                else:
                    self.log.insert("end", item)
                    self.log.see("end")
        except queue.Empty:
            pass
        self.root.after(100, self.drain_log)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()