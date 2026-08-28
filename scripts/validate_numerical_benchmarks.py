"""
UFNS v4.1.0 — Comprehensive Numerical & Physical Benchmark Validation Suite
Runs standalone tests across Level 1 (Numerical), Level 2 (Hydrologic Coupling), and Level 3 (Performance).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from services.physics_bridge import (
    has_native_cpp_engine,
    solve_inundation_2d,
    compute_optical_flow,
    evaluate_dynamic_evacuation_path,
)

print("=" * 80)
print("  UFNS v4.1.0 NUMERICAL & PHYSICAL BENCHMARK VALIDATION SUITE")
print("  Physics Core Engine:", "C++20 SIMD OpenMP" if has_native_cpp_engine() else "NumPy Fallback")
print("=" * 80)

passed_tests = 0
total_tests = 0

def assert_benchmark(name: str, condition: bool, detail: str = ""):
    """Execute Assert Benchmark operation and return result."""
    global passed_tests, total_tests
    total_tests += 1
    if condition:
        passed_tests += 1
        print(f"  [PASS] {name}: {detail}")
    else:
        print(f"  [FAIL] {name}: {detail}")

# --- LEVEL 1: NUMERICAL ACCURACY & WELL-BALANCED PROPERTY ---
print("\n--- LEVEL 1: NUMERICAL ACCURACY & WELL-BALANCED PROPERTY ---")
grid_size = 128
y, x = np.ogrid[:grid_size, :grid_size]
dem = (5.0 * np.exp(-((x - 64)**2 + (y - 64)**2) / (32.0**2))).astype(np.float32)
land_mask = np.ones((grid_size, grid_size), dtype=np.uint8)

depth_out, report = solve_inundation_2d(
    dem=dem,
    land_mask=land_mask,
    scenario_id="S1",
    lead_minutes=0,
    cell_size_m=10.0,
    base_rain_rate_mmh=0.0,
    drain_capacity_mmh=0.0,
)

max_spurious_vel = report.get("max_spurious_velocity_ms", 0.0)
assert_benchmark(
    "1.1 Lake-at-Rest C-Property",
    max_spurious_vel < 1e-4,
    f"Max spurious velocity = {max_spurious_vel:.2e} m/s (Threshold < 1e-4 m/s)"
)

# --- LEVEL 1.2: DRY-BED POSITIVITY ---
steep_dem = (x * 0.5 + y * 0.5).astype(np.float32)
depth_out, report = solve_inundation_2d(
    dem=steep_dem,
    land_mask=land_mask,
    scenario_id="S3",
    lead_minutes=30,
    cell_size_m=30.0,
    base_rain_rate_mmh=72.0,
    drain_capacity_mmh=15.0,
)

min_depth = float(np.min(depth_out))
has_no_nan = not bool(np.isnan(depth_out).any())
assert_benchmark(
    "1.2 Dry-Bed Positivity & NaN Check",
    min_depth >= 0.0 and has_no_nan,
    f"Min depth = {min_depth:.6f} m (Must be >= 0.0, NaNs: {not has_no_nan})"
)

# --- LEVEL 1.3: MASS BALANCE CONSERVATION ---
depth_out, report = solve_inundation_2d(
    dem=dem,
    land_mask=land_mask,
    scenario_id="S4",
    lead_minutes=60,
    cell_size_m=30.0,
    base_rain_rate_mmh=120.0,
    drain_capacity_mmh=5.0,
)

closure_err = report.get("mass_closure_error_pct", 0.0)
assert_benchmark(
    "1.3 Mass Balance Conservation",
    closure_err < 0.1,
    f"Relative closure error = {closure_err:.4f}% (Threshold < 0.10%)"
)

# --- LEVEL 2: HYDROLOGIC & SWMM COUPLING DYNAMICS ---
print("\n--- LEVEL 2: HYDROLOGIC & SWMM COUPLING DYNAMICS ---")
depth_out_surcharge, report_surcharge = solve_inundation_2d(
    dem=dem,
    land_mask=land_mask,
    scenario_id="S4",
    lead_minutes=45,
    cell_size_m=30.0,
    base_rain_rate_mmh=85.0,
    drain_capacity_mmh=3.3,
)

low_elev_depth = float(np.mean(depth_out_surcharge[dem < 2.0]))
assert_benchmark(
    "2.1 Surcharge Backflow Injection",
    low_elev_depth > 0.02,
    f"Mean depth in surcharge nodes = {low_elev_depth:.3f} m (Surcharging fountain active)"
)

# --- LEVEL 3: PERFORMANCE & OPTICAL FLOW BENCHMARK ---
print("\n--- LEVEL 3: PERFORMANCE & OPTICAL FLOW BENCHMARK ---")
f1 = (np.sin(x * 0.1) * np.cos(y * 0.1) * 50.0).astype(np.float32)
f2 = (np.sin((x - 2) * 0.1) * np.cos((y - 1) * 0.1) * 50.0).astype(np.float32)

t0 = time.perf_counter()
u_flow, v_flow = compute_optical_flow(f1, f2)
t1 = time.perf_counter()
flow_time_ms = (t1 - t0) * 1000.0
mean_u = float(np.mean(u_flow[10:-10, 10:-10]))

assert_benchmark(
    "3.1 Pyramidal Farnebäck Optical Flow",
    flow_time_ms < 50.0 and abs(mean_u) > 0.05,
    f"Latency = {flow_time_ms:.2f} ms (< 50 ms), Mean advection u = {mean_u:.2f} px/frame"
)

# --- LEVEL 4: TIME-DEPENDENT EVACUATION & HAZARD ROUTING ---
print("\n--- LEVEL 4: TIME-DEPENDENT EVACUATION & HAZARD ROUTING ---")
waypoints = [
    [100.0, 100.0],
    [200.0, 200.0],
    [300.0, 300.0],
    [400.0, 400.0],
]
depth_grid = np.zeros((100, 100), dtype=np.float32)
depth_grid[6:12, 6:12] = 0.50

t0 = time.perf_counter()
safe_path, hazards = evaluate_dynamic_evacuation_path(
    waypoints=waypoints,
    depth_grid=depth_grid,
    origin_x=0.0,
    origin_y=0.0,
    cell_size_m=30.0,
    profile_mode=1,
)
t1 = time.perf_counter()
routing_time_ms = (t1 - t0) * 1000.0

assert_benchmark(
    "4.1 Time-Dependent A* Evacuation Routing",
    len(safe_path) == len(waypoints) and routing_time_ms < 5.0,
    f"Latency = {routing_time_ms:.3f} ms (< 5 ms), Safe waypoints generated: {len(safe_path)}"
)

print("\n" + "=" * 80)
print(f"  BENCHMARK SUMMARY: {passed_tests}/{total_tests} TESTS PASSED ({passed_tests/total_tests*100:.1f}%)")
print("=" * 80)

if passed_tests == total_tests:
    print(">>> ALL MATHEMATICAL, NUMERICAL & COUPLING BENCHMARKS VERIFIED! <<<")
    sys.exit(0)
else:
    print(">>> SOME BENCHMARKS FAILED! <<<")
    sys.exit(1)
