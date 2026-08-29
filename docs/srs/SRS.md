# Software Requirements Specification (SRS)
## Urban Flood Nowcasting System (UFNS) with Rainfall and Drainage Coupling
**Document Version:** 4.2.0  
**Project ID:** SIH26085  
**Standard:** IEEE Std 830-1998 Format  
**Author:** Vynex Labs Engineering Team  
**Status:** Approved & Verified (Release Candidate)

---

## 1. Introduction

### 1.1 Purpose
This Software Requirements Specification (SRS) document details the complete functional, non-functional, mathematical, interface, and performance requirements for the **Urban Flood Nowcasting System (UFNS)**. The system is designed to provide municipal decision-makers, emergency disaster response authorities (NDRF/SDRF), and city planners with hyper-local (30m spatial resolution), real-time, zero-lag flood hazard projections (0–180 minutes) combining 1D underground storm-drainage networks and 2D overland shallow-water hydrodynamic simulations.

### 1.2 Scope of the System
UFNS integrates multi-source hydro-meteorological observations (IMD Doppler Weather Radar, ISRO-MOSDAC INSAT-3DS satellites, NASA GPM IMERG, AWS telemetry) with physics-based coupled hydrodynamic engines (EPA-SWMM 1D + Saint-Venant 2D Finite Volume Solver) and emergency routing algorithms.

Target geographical pilot areas:
1. **Mumbai Metropolitan Region (MMR)**: Coastal, estuarine, and extreme tidal surge boundary domain (EPSG:32643).
2. **Vijayawada Municipal Corporation**: Riverine Krishna basin and flood embankment domain (EPSG:32644).
3. **Synthetic Pilot / Validation Basin**: Controlled hydrodynamic calibration benchmark domain (EPSG:32645).

### 1.3 Definitions, Acronyms, and Abbreviations
* **1D SWE / 2D SWE**: One-Dimensional / Two-Dimensional Shallow Water Equations.
* **SWMM**: EPA Storm Water Management Model (1D conduit & junction engine).
* **DWR**: Doppler Weather Radar (S-Band / C-Band reflectivity in dBZ).
* **MOSDAC**: Meteorological and Oceanographic Satellite Data Archival Centre (ISRO).
* **IMD**: India Meteorological Department.
* **CAP**: Common Alerting Protocol (OASIS Standard v1.2 / ITU-T X.1303).
* **CFL**: Courant-Friedrichs-Lewy numerical stability condition ($C = \frac{u \Delta t}{\Delta x} \le 1.0$).
* **TTFT**: Time-to-First-Telemetry-Frame.
* **D x V Metric**: Municipal Flood Hazard Index ($h \times v$, $\text{m}^2/\text{s}$).

---

## 2. Overall Description

### 2.1 Product Perspective & Polyglot Architecture
UFNS v4.2.0 utilizes a multi-tier polyglot architecture:
1. **C++20 High-Performance Physics Core (`cpp_core`)**:
   - 2D Saint-Venant Shallow Water Equations with Audusse well-balanced hydrostatic reconstruction.
   - Multi-scale Pyramidal Farnebäck Optical Flow motion field estimation.
   - Sub-millisecond $A^*$ time-dependent emergency evacuation routing.
   - Exported as C-ABI native dynamic shared library (`libufns_physics.dll` / `.so`).
2. **Rust Multi-Threaded Core & Streaming Microservice (`rust_core`, `rust_api`)**:
   - Rayon-parallelized Semi-Lagrangian backward trajectory advection with exponential convective decay.
   - SIMD-accelerated cryptographic SHA-256 data lineage hashing.
   - High-throughput Actix-web / Tokio streaming microservice.
3. **Go Real-Time Ingestion Hub (`services/go_stream`)**:
   - Zero-allocation high-concurrency WebSocket client broadcasting (>50,000 concurrent subscribers).
   - Autonomous background radar and NWP ingestion daemons.
4. **Python FastAPI Backend & Orchestration (`apps/api`, `services/`)**:
   - Zero-copy pointer bridge to C++ and Rust engines.
   - Nelder-Mead inverse calibration optimizer for Manning's $n$ and conduit blockage coefficients.
   - Sponge City Nature-based Solutions (NbS) mitigation and Pareto multi-objective optimizer.
   - CAP v1.2 XML alerting dispatcher and PDF/GeoJSON reporting dossiers.
5. **React 18 / TypeScript Web Dashboard (`apps/web`)**:
   - Minimalist Apple Design System UI with AMOLED dark theme.
   - Continuous 1-minute scrubber with client-side linear sub-frame interpolation across 5-minute backend snapshots.
   - Dynamic nearest shelter proximity calculator and real-time hazard HUD overlays.

---

## 3. Functional Requirements (FR)

### FR-01: Hydro-Meteorological Ingestion & Calibration
* **FR-01.1**: The system shall continuously poll and ingest live Doppler Weather Radar (DWR) reflectivity grids from IMD Colaba, Machilipatnam, and Mumbai stations at 10–15 minute cadences.
* **FR-01.2**: The system shall ingest ISRO-MOSDAC INSAT-3DS Hydro-Estimator precipitation grids (HPI/HEM) and convert them to calibrated rain-rate fields (mm/h).
* **FR-01.3**: The system shall ingest NASA GPM IMERG 0.1° half-hourly satellite precipitation and SMAP L4 soil moisture root-zone metrics.
* **FR-01.4**: All ingested data assets shall be fingerprinted with SHA-256 digests and tagged with provenance metadata adhering to W3C PROV-DM standards.

### FR-02: 1D/2D Coupled Hydrodynamic Simulation
* **FR-02.1**: The 2D surface inundation engine shall solve the depth-averaged Saint-Venant shallow water equations with Manning surface friction and microtopographic depression storage:
  $$\frac{\partial h}{\partial t} + \frac{\partial (hu)}{\partial x} + \frac{\partial (hv)}{\partial y} = R - I - Q_{drain}$$
* **FR-02.2**: The 1D drainage engine shall interface with EPA-SWMM, simulating pipe flow, backwater surcharging, and manhole surface overflow.
* **FR-02.3**: Bidirectional fluid exchange between 1D manhole junctions and 2D surface cells shall conserve mass with a global closure error $< 0.05\%$.
* **FR-02.4**: The solver shall preserve the *Lake-at-Rest* C-property, maintaining exact zero spurious velocity ($|u| < 10^{-6}\,\text{m/s}$) over arbitrary dry and wet bathymetry.

### FR-03: Radar Advection & Optical Flow Nowcasting
* **FR-03.1**: The advection engine shall compute dense motion vectors $(u, v)$ across successive radar frames using Farnebäck optical flow.
* **FR-03.2**: The system shall extrapolate precipitation fields up to a 180-minute horizon ($T+0$ to $T+180\,\text{min}$) at 5-minute intervals using Semi-Lagrangian backward trajectory tracking.
* **FR-03.3**: The engine shall apply exponential convective cell decay based on lifespan half-life parameter $\tau \approx 180\,\text{minutes}$.

### FR-04: Road Network Impact & Emergency Evacuation Routing
* **FR-04.1**: The system shall evaluate water depth $h$ and flow velocity $v$ for every road segment in the OpenStreetMap road graph.
* **FR-04.2**: Passability shall be categorized according to municipal standard B13 criteria:
  - **PASSABLE**: $h \le 0.15\,\text{m}$ and $h \times v \le 0.35\,\text{m}^2/\text{s}$.
  - **CAUTION**: $0.15\,\text{m} < h \le 0.30\,\text{m}$.
  - **IMPASSABLE**: $h > 0.30\,\text{m}$ or $h \times v > 0.35\,\text{m}^2/\text{s}$.
* **FR-04.3**: Emergency routing shall compute optimal multi-profile evacuation paths (Ambulance, Fire Engine, Rescue 4x4, High-Clearance Truck) bypassing impassable road links with sub-millisecond latency.
* **FR-04.4**: The system shall dynamically resolve the nearest available relief shelter from active critical infrastructure assets using Euclidean distance and graph reachability.

### FR-05: Alerting & Multi-Channel Broadcast
* **FR-05.1**: The alerting module shall generate standardized OASIS Common Alerting Protocol (CAP v1.2) XML payloads for all severe inundation events.
* **FR-05.2**: The system shall classify alert severity into standard tiers: `Advisory` (Yellow), `Watch` (Orange), and `Warning` (Red).

### FR-06: Sponge City Nature-based Solutions (NbS) & Mitigation
* **FR-06.1**: The mitigation engine shall simulate permeable pavements, bioswales, rain gardens, and detention basins.
* **FR-06.2**: The optimization solver shall compute Pareto-optimal investment trade-offs between capital expenditure (INR) and flood risk reduction.

---

## 4. Non-Functional Requirements (NFR)

### NFR-01: Latency & Response Time
* **NFR-01.1**: Static and pre-computed scenario API endpoints shall respond in $< 20\,\text{ms}$ at P90.
* **NFR-01.2**: 2D Hydrodynamic inundation simulation for a 15-minute horizon across 65,536 cells shall execute in $< 15\,\text{ms}$ in native C++20.
* **NFR-01.3**: 180-minute radar advection nowcast across 262,144 pixels shall complete in $< 1.0\,\text{ms}$ in Rust SIMD.
* **NFR-01.4**: Emergency vehicle route evaluation across 1,000 waypoints shall complete in $< 500\,\mu\text{s}$.

### NFR-02: Scalability & Concurrency
* **NFR-02.1**: The Go telemetry streaming hub shall support $\ge 50,000$ concurrent WebSocket subscribers.
* **NFR-02.2**: The system shall scale horizontally across CPU cores utilizing OpenMP and Rayon multi-threading.

### NFR-03: Numerical Precision & Stability
* **NFR-03.1**: Mass conservation closure error shall not exceed $0.05\%$ across all simulated scenarios.
* **NFR-03.2**: Water depths shall remain strictly non-negative ($h \ge 0.0\,\text{m}$) with zero spurious oscillations.

### NFR-04: Availability & Fault Tolerance
* **NFR-04.1**: The system shall provide automated synthetic fallback generators when upstream live radar/satellite feeds are offline, maintaining 99.95% API uptime.
* **NFR-04.2**: Ingested payload parsing failures shall degrade gracefully with safe type coercion without crashing background daemons.

### NFR-05: User Experience & Design Compliance
* **NFR-05.1**: The web dashboard shall maintain 60 FPS smooth rendering during timeline scrubbing.
* **NFR-05.2**: The interface shall adhere to the minimalist Apple Design System guidelines (SF Pro typography, translucent blur surfaces, calibrated dark palette).
