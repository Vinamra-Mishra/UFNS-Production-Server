# UFNS Complete Codebase Walkthrough

**Document Version:** 4.2.0  
**Repository:** `Vynex-Labs/SIH26085-Urban-Flood-Nowcasting-System`  
**Purpose:** Comprehensive module-by-module and file-by-file technical reference for the entire repository.

---

## 1. Application Layer (`apps/`)

### 1.1 Web Dashboard (`apps/web/`)
* **`src/App.tsx`**: Central application state container. Implements client-side linear sub-frame depth grid interpolation for smooth 1-minute scrubber stepping across 5-minute discrete backend snapshots. Manages active city, scenario selection, routing waypoints, and theme state.
* **`src/components/MapView.tsx`**: High-performance Canvas 2D geospatial renderer. Projects raster flood depth heatmaps, DWR radar mosaics, OSM road networks, drainage conduits, and critical assets in local metric UTM projection. Implements inverted top-down row hit-testing for mouse hover tooltips and simulated dual-pol Doppler HUD overlays.
* **`src/components/Navbar.tsx`**: Top navigation bar with Apple dark glassmorphism styling. Renders dynamic city selectors, live radar status chips (`--` / `UNKNOWN` / `HEALTHY`), and tidal surge indicators.
* **`src/components/SidebarTabs.tsx`**: Multi-tab control sidebar containing Ingestion feeds (IMD 20-APIs, ISRO-MOSDAC), Scenarios (S1–S4 baseline simulations), Emergency Evacuation Routing (with dynamic Euclidean Nearest Relief Shelter selector), Mitigation NbS planner, and Audit logs.
* **`src/components/TimelineController.tsx`**: Smooth video-like timeline scrubber supporting 0–180 minute lead times with playback, pause, 1-minute step, and scenario horizon markers.
* **`src/components/IMDWeatherPanel.tsx`**: Real-time meteorological intelligence panel. Renders live IMD automatic weather station (AWS) observations, INSAT-3DS hydro-estimator rainfall rates, atmospheric pressure, wind vectors, and radar status.
* **`src/components/MetricsBar.tsx`**: Executive KPI cards displaying peak flood depth ($m$), inundated road kilometers, blocked drainage conduits, and active population at risk.
* **`src/components/WeatherWidget.tsx`**: Real-time Doppler telemetry HUD overlay showing live rain rate, convective reflectivity, and storm movement vectors.
* **`src/index.css`**: Apple Design System stylesheet defining SF Pro typography, dark AMOLED tokens, translucent glassmorphism variables (`backdrop-filter: blur(20px)`), and custom animation keyframes.

### 1.2 REST API Gateway (`apps/api/`)
* **`apps/api/app.py`**: Main FastAPI entrypoint. Implements CORS middleware, global error handling, lifecycle management, static asset mounting, and router registration.
* **`apps/api/city_api.py`**: Dynamic multi-city spatial domain router. Returns bounding box centers, grid specifications, and CRS definitions for Mumbai (EPSG:32643), Vijayawada (EPSG:32644), and Demo (EPSG:32645).
* **`apps/api/imd_api.py`**: REST proxy for IMD meteorological observations, district rainfall summaries, radar nowcasts, and AWS sensor feeds.
* **`apps/api/mosdac_api.py`**: ISRO-MOSDAC satellite ingestion gateway providing live and simulated INSAT-3DS Hydro-Estimator precipitation products.
* **`apps/api/impacts.py`**: Road hazard classifier and nowcast frame handler. Implements deterministic road impact hashing (`_deterministic_road_hash` CRC32 % 100), 60-second TTL time-bucketed caching, and dry-weather synthetic demonstration labeling.

---

## 2. High-Performance Native Engines

### 2.1 C++20 Physics Core (`cpp_core/`)
* **`solver_2d.cpp`**: 2D Saint-Venant shallow water equations solver. Employs Audusse well-balanced hydrostatic reconstruction and OpenMP multithreading to guarantee exact C-property preservation on wet/dry irregular bathymetry.
* **`optical_flow.cpp`**: Multi-scale Pyramidal Farnebäck optical flow calculator. Uses coordinate clamping to prevent boundary out-of-bounds access.
* **`routing.cpp`**: Time-dependent flood-aware $A^*$ spatial router. Evaluates road passability using Smith & Xia $D \times V$ criteria and computes optimal multi-profile emergency routes.
* **`physics_engine.cpp`**: Unified C-ABI dynamic library export interface.
* **`test_physics.cpp`**: Native C++ test binary verifying the Lake-at-Rest C-property, optical flow motion magnitude, and evacuation routing.

### 2.2 Rust SIMD Core (`rust_core/`)
* **`src/lib.rs`**: PyO3 native Python extension module (`ufns_rs`). Enforces array dimension validation at the Python boundary.
* **`src/advection.rs`**: Rayon-parallelized Semi-Lagrangian 2D advection backward trajectory extrapolator with bilinear interpolation and exponential convective decay.
* **`src/fingerprint.rs`**: Hardware-accelerated cryptographic SHA-256 data buffer hashing for audit trails and provenance tracking.

### 2.3 Go Telemetry Hub (`services/go_stream/`)
* **`main.go` & `main_test.go`**: High-concurrency streaming microservice written in Go 1.22. Uses lightweight goroutines and non-blocking channels to broadcast live telemetry to over 50,000 concurrent WebSocket clients.

---

## 3. Hydrological & Algorithmic Services (`services/`)

* **`services/physics_bridge.py`**: Zero-copy ctypes C-ABI bridge providing transparent Python access to `libufns_physics.dll`.
* **`services/ingestion/`**: Data ingestion subsystem covering IMD clients, MOSDAC INSAT-3DS parsers, NASA IMERG clients, GRIB2/NetCDF reprojection, and W3C PROV-DM lineage recording (`provenance.py`).
* **`services/nowcast/`**: Multi-model nowcasting engine combining Doppler radar advection, NWP blending, and neural fallback predictors.
* **`services/alerting/`**: Automated Common Alerting Protocol (CAP v1.2) XML generator and multi-channel notification dispatcher.
* **`services/calibration/`**: Nelder-Mead and Differential Evolution inverse calibration optimizer for Manning's $n$ roughness and conduit blockage coefficients.
* **`services/mitigation/`**: Sponge City Nature-based Solutions (NbS) evaluator and Pareto multi-objective investment optimizer.
* **`services/routing/`**: Road network graph constructor and emergency vehicle routing profiles (`evacuation.py`, `roads.py`, `router.py`).
* **`services/scenarios/`**: S1 to S4 scenario simulation runners and baseline benchmark registry.
* **`services/probabilistic/`**: Monte-Carlo ensemble generator and probabilistic flood exceedance risk mapper.

---

## 4. Test Suites (`tests/`)

* **`tests/test_contracts.py`**: Validates schema contracts, data types, and API structures.
* **`tests/test_m4_coupled.py`**: Coupled 1D SWMM + 2D overland simulation verification, mass conservation, and timestep sensitivity.
* **`tests/test_m5_scenarios.py`**: S1–S4 scenario execution, blockage sensitivity, and complete suite reproducibility.
* **`tests/test_m7_api.py` & `tests/test_m11_api.py`**: Comprehensive REST API endpoint tests.
* **`tests/test_phase_a_nowcast.py` to `test_phase_k_probabilistic.py`**: Rigorous unit and integration test suites covering all phases of the UFNS architecture.
* **`tests/test_unified_engines.py`**: Layering hygiene, import integrity, and custom hyetograph simulation tests.
