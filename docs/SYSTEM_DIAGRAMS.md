# UFNS Complete System Architecture Diagrams

This document contains architectural diagrams (Mermaid format) representing the complete **Urban Flood Nowcasting System (UFNS v4.2.0)**.

---

## 1. C4 Context Diagram (System Ecosystem)

```mermaid
graph TD
    subgraph External_Data_Providers["External Hydro-Meteorological Providers"]
        IMD["IMD Doppler Radar & AWS APIs"]
        MOSDAC["ISRO MOSDAC INSAT-3DS Satellite"]
        NASA["NASA GPM IMERG & SMAP"]
        OSM["OpenStreetMap Road & Drain Vectors"]
    end

    subgraph UFNS_System["Urban Flood Nowcasting System (UFNS)"]
        INGEST["Ingestion & Quality Engine"]
        HYDRO["Coupled 1D/2D Hydrodynamic Engine"]
        NOWCAST["Radar Advection & Blending Engine"]
        ROUTING["Dynamic Emergency Evacuation Router"]
        GATEWAY["FastAPI & Streaming Gateway"]
    end

    subgraph End_Users["Stakeholders & Consuming Clients"]
        MCGM["Municipal Disaster Control (MCGM / VMC)"]
        FIRST_RESP["First Responders & Emergency Fleets (NDRF)"]
        PUBLIC["Public Web GIS Portal"]
    end

    IMD -->|Radar dBZ & Live AWS| INGEST
    MOSDAC -->|INSAT-3DS Rain Rate| INGEST
    NASA -->|Soil Moisture & Precipitation| INGEST
    OSM -->|Road & Drainage Graph| INGEST

    INGEST --> NOWCAST
    NOWCAST --> HYDRO
    HYDRO --> ROUTING
    ROUTING --> GATEWAY
    HYDRO --> GATEWAY
    NOWCAST --> GATEWAY

    GATEWAY -->|CAP v1.2 Alerts & GeoJSON| MCGM
    GATEWAY -->|Safe Evacuation Waypoints| FIRST_RESP
    GATEWAY -->|60 FPS Interactive GIS Stream| PUBLIC
```

---

## 2. C4 Container Diagram (Polyglot Microservices)

```mermaid
graph TB
    subgraph Client_Tier["Client Presentation Tier"]
        WEB["React 18 / TypeScript Web Dashboard<br/>(TailwindCSS, HTML5 Canvas, 60 FPS Scrubber)"]
    end

    subgraph Gateway_Tier["API Gateway & Orchestration"]
        FASTAPI["Python 3.12 FastAPI REST Gateway<br/>(Port 8000: /api/v1/*, /health)"]
        GO_HUB["Go 1.22 Streaming Hub<br/>(Port 8080: WebSocket Broadcast & Ingestion)"]
        RUST_API["Rust Actix-Web Microservice<br/>(Port 8081: Low-Latency Telemetry Stream)"]
    end

    subgraph Computational_Core["High-Performance Computational Core"]
        CPP_LIB["C++20 OpenMP / SIMD Dynamic Library<br/>(libufns_physics.dll / .so)<br/>- 2D Saint-Venant SWE Solver<br/>- Pyramidal Farneback Optical Flow<br/>- Flood-Aware A* Router"]
        RUST_CORE["Rust High-Performance Core (ufns_rs)<br/>(PyO3 C-ABI Bindings)<br/>- Semi-Lagrangian Advection<br/>- SHA-256 Data Fingerprinting"]
        SWMM_ENGINE["1D EPA-SWMM Engine<br/>(Subsurface Drainage & Surcharge)"]
    end

    subgraph Data_Storage["Data & Ingestion Storage"]
        DEM_STORE["Normalized CartoDEM / SRTM 30m Rasters"]
        LINEAGE_LEDGER["W3C PROV-DM Data Lineage Ledger (JSON/Parquet)"]
    end

    WEB -->|REST HTTP Requests| FASTAPI
    WEB -->|Real-Time WebSocket Stream| GO_HUB
    FASTAPI -->|C-ABI Zero-Copy ctypes| CPP_LIB
    FASTAPI -->|PyO3 Native Extension| RUST_CORE
    FASTAPI -->|Python SWMM Bridge| SWMM_ENGINE
    FASTAPI -->|Read Rasters| DEM_STORE
    FASTAPI -->|Audit Records| LINEAGE_LEDGER
```

---

## 3. Coupled 1D/2D Hydrodynamic Numerical Solver Flow

```mermaid
sequenceDiagram
    autonumber
    participant Rain as Rainfall Forcing (Radar/NWP)
    participant Land as 2D Overland Surface (Saint-Venant)
    participant Inlets as Storm-Drain Inlets (Weir/Orifice)
    participant Pipes as 1D SWMM Drainage Conduits
    participant Nodes as Manhole Junctions

    Rain->>Land: Precipitation Flux R(x,y,t)
    Land->>Land: Compute Hydrostatic Head h + z & Friction S_f
    Land->>Inlets: Surface Inflow Q_in = C_w * L * h^(3/2)
    Inlets->>Pipes: Conduit Inflow
    Pipes->>Nodes: Dynamic Wave Routing (Saint-Venant 1D)
    alt Conduit Capacity Exceeded (Surcharge)
        Nodes->>Land: Manhole Overflow Q_surch = A_manhole * sqrt(2g * delta_H)
        Land->>Land: Inundation Accumulation & Topographic Spreading
    else Normal Drainage
        Nodes->>Nodes: Gravity Outfall Discharge
    end
    Land->>Land: Audusse Well-Balanced Reconstruction & Flux Balance
```

---

## 4. Emergency Evacuation Route Evaluation Flow

```mermaid
flowchart TD
    A[Start: Vehicle Route Request] --> B[Retrieve Active Scenario / Nowcast Frame]
    B --> C[Extract 2D Depth Grid h and Flow Velocity v]
    C --> D[Evaluate Road Segments in OpenStreetMap Graph]
    D --> E{Check Hazard Metric:<br/>h <= 0.15m AND h*v <= 0.35 m²/s?}
    E -- Yes --> F[Status: PASSABLE<br/>Base Travel Speed]
    E -- No --> G{Check Caution Limit:<br/>0.15m < h <= 0.30m?}
    G -- Yes --> H[Status: CAUTION<br/>Reduced Speed 50%]
    G -- No --> I[Status: IMPASSABLE<br/>Block Edge in Routing Graph]
    F --> J[C++20 Spatial A* Search Algorithm]
    H --> J
    I --> K[Dynamic Rerouting via Alternate Nodes]
    K --> J
    J --> L[Generate Safe Evacuation Waypoints]
    L --> M[Dispatch Route & Turn-by-Turn to Emergency Fleet]
```
