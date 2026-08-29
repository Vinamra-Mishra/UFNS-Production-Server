# UFNS System Architecture & Technical Specification

**Document Version:** 4.2.0  
**Project ID:** SIH26085  
**Classification:** Operational Hydrological Decision Support Platform  

---

## 1. System Philosophy & Multi-Tier Polyglot Design

The Urban Flood Nowcasting System (UFNS) addresses the twin computational challenges of urban hydrology:
1. **High-Resolution Physics Simulation**: Simulating nonlinear partial differential equations (2D Saint-Venant shallow water equations) over millions of spatial cells within tight real-time constraints.
2. **Sub-Second Real-Time Telemetry Processing**: Ingesting high-velocity multi-source satellite, radar, and in-situ sensor telemetry and broadcasting updates to thousands of concurrent users.

To achieve this, UFNS uses a **polyglot micro-architecture**:
* **C++20 Core**: Number crunching, hydrodynamic numerical flux calculation, optical flow, and graph algorithms.
* **Rust Core**: Memory-safe parallel advection and cryptographic hashing.
* **Go Microservice**: High-concurrency WebSocket telemetry distribution.
* **Python FastAPI**: REST API gateway, calibration, alerting, and high-level workflow orchestration.
* **React 18 / TypeScript**: Hardware-accelerated Apple-style GIS dashboard.

---

## 2. Component Directory Architecture

```
SIH 2026/
├── apps/
│   ├── api/                 # FastAPI REST Gateway & Endpoint Controllers
│   │   ├── app.py           # Application Entrypoint, Middleware, Lifespan
│   │   ├── city_api.py      # Multi-City Geographic Domain Routing
│   │   ├── imd_api.py       # IMD 20-API Endpoints & Observation Proxy
│   │   ├── impacts.py       # Road Impact Classification & Nowcast Frames
│   │   └── mosdac_api.py    # ISRO MOSDAC Satellite Ingestion Endpoints
│   └── web/                 # React 18 / TypeScript GIS Dashboard
│       ├── src/
│       │   ├── App.tsx      # Core State Container & Keyframe Interpolator
│       │   ├── components/  # Modular Apple-Style UI Components
│       │   │   ├── MapView.tsx            # HTML5 Canvas 2D Vector Basemap
│       │   │   ├── Navbar.tsx             # System Header & Telemetry Pills
│       │   │   ├── SidebarTabs.tsx        # Ingestion, Scenarios, Routing
│       │   │   ├── TimelineController.tsx # 1-Min Continuous Timeline Scrubber
│       │   │   ├── IMDWeatherPanel.tsx    # Meteorological Dossier & Radar
│       │   │   ├── MetricsBar.tsx         # KPI Gauge Cards
│       │   │   └── WeatherWidget.tsx      # Real-Time Telemetry HUD
│       │   └── index.css    # Apple Design System Design Tokens & Glassmorphism
│       └── package.json
├── cpp_core/                # C++20 OpenMP / SIMD Native Physics Engine
│   ├── solver_2d.cpp        # 2D Shallow Water Finite Volume Hydrodynamic Solver
│   ├── optical_flow.cpp     # Multi-scale Pyramidal Farneback Optical Flow
│   ├── routing.cpp          # Flood-Aware A* Shortest Path Routing
│   ├── physics_engine.cpp   # Unified C-ABI Export Interface
│   ├── test_physics.cpp     # Native C++ Verification Test Suite
│   └── libufns_physics.dll  # Compiled Native Shared Library (MSVC /O2)
├── rust_core/               # Rust High-Performance SIMD Core (PyO3)
│   ├── src/
│   │   ├── lib.rs           # Python PyO3 Module Interface (ufns_rs)
│   │   ├── advection.rs     # Rayon-Parallelized Semi-Lagrangian Advection
│   │   └── fingerprint.rs   # Hardware-Accelerated SHA-256 Checksummer
│   └── Cargo.toml
├── rust_api/                # Rust Actix-Web Streaming Microservice
│   ├── src/main.rs          # Low-Latency HTTP & SSE Telemetry Endpoint
│   └── Cargo.toml
├── services/                # Backend Hydrological & Algorithmic Services
│   ├── alerting/            # OASIS CAP v1.2 XML Alert Dispatcher
│   ├── calibration/         # Nelder-Mead Inverse Parameter Optimizer
│   ├── go_stream/           # Go High-Concurrency WebSocket Streaming Hub
│   ├── hydraulics/          # 1D/2D Exchange & SWMM Coupler
│   ├── ingestion/           # IMD, MOSDAC, NASA Ingestion & Provenance
│   ├── mitigation/          # Sponge City NbS Simulator & Pareto Optimizer
│   ├── nowcast/             # Multi-Model NWP Blending & Radar Extrapolator
│   ├── physics_bridge.py    # Zero-Copy C-ABI ctypes Interface to cpp_core
│   ├── pilot/               # Mumbai & Vijayawada Real Pilot Adapters
│   ├── probabilistic/       # Monte-Carlo Ensemble Flood Risk Engine
│   ├── reporting/           # Incident Dossier & Technical Report Generator
│   ├── routing/             # Road Graph Construction & Passability Evaluator
│   └── scenarios/           # S1-S4 Scenario Runner & Baseline Registry
├── data/                    # Geographical Rasters, Inundation Basins & DEMs
├── docs/                    # Complete Architecture, SRS, and Technical Docs
│   └── srs/                 # Software Requirements Spec & Empirical Benchmarks
└── tests/                   # 731-Test Automated Pytest Verification Suite
```
