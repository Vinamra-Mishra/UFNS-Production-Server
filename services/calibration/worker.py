"""Isolated worker process for EPA-SWMM forward coupled simulation (Phase B).

EPA-SWMM C-runtime contains global static state that prevents running multiple
Simulation() instances sequentially in the same process. This worker executes
each forward hydraulic run in an isolated subprocess.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Tuple

import numpy as np

from services.calibration.parameters import CalibrationParameterSet
from services.hydraulics.coupling import CoupledSpike, build_spike_surface
from services.hydraulics.fixture import (
    C1_DIAMETER,
    C1_LENGTH,
    C1_MANNING,
    C1_SLOPE,
    exact_fixture_inp,
)


def run_isolated_forward_simulation(
    params_dict: dict[str, float],
    duration_minutes: float = 30.0,
    rain_mmh: float = 45.0,
    dt_c: int = 5,
) -> tuple[list[float], list[float]]:
    """Execute a single coupled forward simulation inside this process."""
    from pyswmm import Nodes, Simulation

    params = CalibrationParameterSet(**params_dict).validate_and_clip()
    surface = build_spike_surface(n=7, cell_m=30.0)
    d_eff = params.get_effective_conduit_diameter(C1_DIAMETER)
    n_pipe = max(0.009, min(0.040, float(params.pipe_manning_n)))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as f:
        temp_inp = Path(f.name)
        inp_content = exact_fixture_inp(
            blocked=True,
            datum_offset_m=0.0,
            blocked_diameter_m=d_eff,
        )
        if abs(n_pipe - C1_MANNING) > 1e-4:
            lines = inp_content.splitlines(keepends=True)
            replaced = False
            for idx, line in enumerate(lines):
                parts = line.split()
                if parts and parts[0] == "C1" and len(parts) >= 5:
                    parts[4] = f"{n_pipe:.4f}"
                    lines[idx] = " ".join(parts) + "\n"
                    replaced = True
                    break
            if not replaced:
                raise RuntimeError("Could not apply candidate Manning roughness to conduit C1")
            inp_content = "".join(lines)
        temp_inp.write_text(inp_content)

    try:
        spike = CoupledSpike(
            surface=surface,
            inp_path=temp_inp,
            inlet_cell=(3, 3),
            vent_cell=(3, 4),
            dt_c=dt_c,
            cd=params.cd_orifice,
        )

        n_steps = int(round(duration_minutes * 60 / dt_c))
        q_outfall_series: list[float] = []
        time_series: list[float] = []

        with Simulation(str(temp_inp)) as sim:
            sim.step_advance(dt_c)
            st1 = Nodes(sim)["ST1"]
            o1 = Nodes(sim)["O1"]

            rain_ms = rain_mmh / 3600000.0

            for i, _ in enumerate(sim):
                if i >= n_steps:
                    break
                t_sec = (i + 1) * dt_c
                t_min = t_sec / 60.0
                time_series.append(t_min)

                q_out_i = float(o1.total_inflow)
                q_outfall_series.append(q_out_i)
                H_d = float(st1.head)

                spike.surface.apply_rainfall(rain_ms, dt_c)
                spike.surface.step(dt_c)

                eta_s = float(spike.surface.dem[spike.inlet] + spike.surface.depth[spike.inlet])
                q_ex = spike.cd * 0.1 * math.sqrt(2.0 * 9.80665 * max(0.0, eta_s - H_d)) if eta_s > H_d else 0.0

                avail = float(spike.surface.depth[spike.inlet]) * spike.surface.cell_area_m2
                q_ex = min(q_ex, avail / dt_c)
                s2d = q_ex * dt_c
                spike._remove_depth(spike.inlet, s2d / spike.surface.cell_area_m2)

                st1.generated_inflow(q_ex)

        return time_series, q_outfall_series
    finally:
        if temp_inp.exists():
            temp_inp.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", type=str, required=True)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--rain", type=float, default=45.0)
    parser.add_argument("--dt", type=int, default=5)
    parser.add_argument("--output", type=str, required=True)

    args = parser.parse_args()
    pdict = json.loads(args.params)
    t_res, q_res = run_isolated_forward_simulation(
        pdict,
        duration_minutes=args.duration,
        rain_mmh=args.rain,
        dt_c=args.dt,
    )
    Path(args.output).write_text(json.dumps({"time": t_res, "q": q_res}))
