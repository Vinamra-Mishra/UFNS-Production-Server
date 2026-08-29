import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Navbar } from './components/Navbar';
import { SidebarTabs } from './components/SidebarTabs';
import { MapView } from './components/MapView';
import { TimelineController } from './components/TimelineController';
import { MetricsBar } from './components/MetricsBar';
import {
  CityId,
  CityMetadata,
  ScenarioMeta,
  RoadSegment,
  RoadImpact,
  RouteResponse,
  LiveTelemetry,
  CriticalAssetItem,
  LayerState,
  MetricsSummary,
} from './types';
import { GridMeta } from './gl/coords';

interface CachedFrame {
  depth: Float32Array;
  rainfallGrid?: Float32Array;
  roadImpacts: Record<string, RoadImpact>;
  metrics: MetricsSummary;
  grid?: any;
}

export const App: React.FC = () => {
  // Active City State (Defaults to DEMO on startup)
  const [activeCity, setActiveCity] = useState<CityId>('DEMO');
  const [cityMeta, setCityMeta] = useState<CityMetadata | null>(null);

  // Core Simulation & Scenario State
  const [scenarios, setScenarios] = useState<ScenarioMeta[]>([]);
  const [activeScenarioId, setActiveScenarioId] = useState<string>('S4');
  const [currentLead, setCurrentLead] = useState<number>(0);
  const [currentTimeStep, setCurrentTimeStep] = useState<number>(1);

  // Basemap & Asset Filter State
  const [basemapStyle, setBasemapStyle] = useState<'vector' | 'dark' | 'voyager' | 'satellite' | 'cad'>('vector');
  const [selectedAssetCategory, setSelectedAssetCategory] = useState<string>('ALL');

  // GIS Data Stores (Default: DEMO 134x134 Synthetic Catchment)
  const [gridMeta, setGridMeta] = useState<GridMeta>({
    origin_x: 300000.0,
    origin_y: 2500000.0,
    width: 134,
    height: 134,
    cell_size_m: 30.0,
    crs: 'EPSG:32645',
  });
  const [depthGrid, setDepthGrid] = useState<Float32Array | null>(null);
  const [rainfallGrid, setRainfallGrid] = useState<Float32Array | null>(null);
  const [roads, setRoads] = useState<RoadSegment[]>([]);
  const [roadImpacts, setRoadImpacts] = useState<Record<string, RoadImpact>>({});
  const [drainage, setDrainage] = useState<any>(null);
  const [criticalAssets, setCriticalAssets] = useState<CriticalAssetItem[]>([]);
  const [activeRoute, setActiveRoute] = useState<RouteResponse | null>(null);
  const [telemetry, setTelemetry] = useState<LiveTelemetry | null>(null);

  // In-Memory Fast Frame Cache & Pre-Buffering State
  const frameCacheRef = useRef<Map<string, CachedFrame>>(new Map());
  const [bufferedLeads, setBufferedLeads] = useState<number[]>([]);
  const [isBuffering, setIsBuffering] = useState<boolean>(false);

  // 14 Layer Toggles State
  const [layers, setLayers] = useState<LayerState>({
    flood_2d: true,
    flood_1d: true,
    roads: true,
    passability: true,
    policyFilter: false,
    drainage: true,
    assets: true,
    tiles: true,
    elevation: false,
    rainfall: false, // Default off so flood inundation raster and road network are crystal clear
    radar: true,
    vuln: false,
    sponge: false,
    risk: false,
  });

  // Loading indicator state
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadingMessage, setLoadingMessage] = useState<string>('Initializing High-Resolution Flood Engine...');

  // Real-Time Metrics State
  const [metrics, setMetrics] = useState<MetricsSummary>({
    lead_minutes: 0,
    rainfall_rate_mmh: 0.0,
    peak_depth_m: 0.0,
    flooded_area_m2: 0,
    dry_roads_count: 0,
    passable_roads_count: 0,
    impassable_roads_count: 0,
    surcharged_nodes_count: 0,
    storage_volume_m3: 0,
    outfall_q_m3s: 0.0,
    active_model: 'Hydrodynamic (2D)',
    dataset_source: 'REAL_OBSERVED',
  });

  // Helper to parse raw API frame payload
  const parseFramePayload = useCallback((data: any, scenarioId: string, lead: number): CachedFrame => {
    const rawDepth = data.depth || data.depth_grid || data.grid_depth;
    let parsedDepth: Float32Array;
    if (rawDepth) {
      if (Array.isArray(rawDepth) && Array.isArray(rawDepth[0])) {
        const rows = rawDepth.length;
        const cols = rawDepth[0].length;
        parsedDepth = new Float32Array(rows * cols);
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            parsedDepth[r * cols + c] = rawDepth[r][c];
          }
        }
      } else if (rawDepth instanceof Float32Array) {
        parsedDepth = rawDepth;
      } else {
        parsedDepth = new Float32Array(rawDepth);
      }
    } else {
      parsedDepth = new Float32Array(gridMeta.width * gridMeta.height);
    }

    const rawRain = data.rainfall_grid || data.rainfall?.values || data.rain_grid;
    let parsedRain: Float32Array | undefined = undefined;
    if (rawRain) {
      if (Array.isArray(rawRain) && Array.isArray(rawRain[0])) {
        const rows = rawRain.length;
        const cols = rawRain[0].length;
        parsedRain = new Float32Array(rows * cols);
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            parsedRain[r * cols + c] = rawRain[r][c];
          }
        }
      } else if (rawRain instanceof Float32Array) {
        parsedRain = rawRain;
      } else if (Array.isArray(rawRain)) {
        parsedRain = new Float32Array(rawRain);
      }
    }

    const impacts: Record<string, RoadImpact> = {};
    if (Array.isArray(data.road_impacts)) {
      data.road_impacts.forEach((v: any) => {
        const rId = v.road_id || v.id;
        if (rId) {
          impacts[rId] = {
            road_id: rId,
            classification: v.classification || (v.status === 'IMPASSABLE' ? 'IMPASSABLE' : (v.max_depth_m > 0.15 ? 'CAUTION' : 'DRY')),
            max_depth_m: v.max_depth_m ?? v.peak_depth_m ?? v.depth_m ?? 0.0,
            passability: v.passability || (v.status === 'IMPASSABLE' ? 'IMPASSABLE' : 'PASSABLE'),
            is_passable: v.is_passable ?? (v.status !== 'IMPASSABLE'),
            effective_speed_kmh: v.effective_speed_kmh ?? v.velocity_ms ?? 30.0,
          };
        }
      });
    } else if (data.road_impacts && typeof data.road_impacts === 'object') {
      Object.entries(data.road_impacts).forEach(([k, v]: [string, any]) => {
        impacts[k] = {
          road_id: k,
          classification: v.classification || (v.status === 'IMPASSABLE' ? 'IMPASSABLE' : 'DRY'),
          max_depth_m: v.max_depth_m ?? v.depth_m ?? 0.0,
          passability: v.passability || (v.status === 'IMPASSABLE' ? 'IMPASSABLE' : 'PASSABLE'),
          is_passable: v.is_passable ?? (v.status !== 'IMPASSABLE'),
          effective_speed_kmh: v.effective_speed_kmh ?? v.velocity_ms ?? 0.0,
        };
      });
    }

    const m = data.metrics || data.road_metrics || {};
    const parsedMetrics: MetricsSummary = {
      lead_minutes: lead,
      rainfall_rate_mmh: m.rainfall_rate_mmh ?? (scenarioId === 'S4' ? Math.max(0, 85 - lead * 0.4) : (scenarioId === 'REALTIME' ? (telemetry?.precip_rate_mmh ?? 18.5) : 35.0)),
      peak_depth_m: m.peak_depth_m ?? 0.0,
      flooded_area_m2: m.flooded_area_m2 ?? 0,
      dry_roads_count: m.dry_roads_count ?? m.dry ?? 0,
      passable_roads_count: m.passable_roads_count ?? m.passable ?? 0,
      impassable_roads_count: m.impassable_roads_count ?? m.impassable ?? 0,
      surcharged_nodes_count: m.surcharged_nodes_count ?? 0,
      storage_volume_m3: m.storage_volume_m3 ?? 0,
      outfall_q_m3s: m.outfall_q_m3s ?? 0.0,
      active_model: m.active_model || 'Hydrodynamic (2D)',
      dataset_source: m.dataset_source || 'REAL_OBSERVED',
    };

    let gridObj: any = undefined;
    if (data.grid) {
      gridObj = {
        width: data.grid.width || data.grid.cols || (data.grid.shape ? data.grid.shape[1] : undefined),
        height: data.grid.height || data.grid.rows || (data.grid.shape ? data.grid.shape[0] : undefined),
        origin_x: data.grid.origin_x ?? (data.grid.origin ? data.grid.origin[0] : undefined),
        origin_y: data.grid.origin_y ?? (data.grid.origin ? data.grid.origin[1] : undefined),
        cell_size_m: data.grid.cell_size_m,
        crs: data.grid.crs,
      };
    }

    return {
      depth: parsedDepth,
      rainfallGrid: parsedRain,
      roadImpacts: impacts,
      metrics: parsedMetrics,
      grid: gridObj,
    };
  }, [gridMeta.width, gridMeta.height, telemetry?.precip_rate_mmh]);

  // Sub-frame linear interpolation
  const getInterpolatedFrame = useCallback((scenarioId: string, exactLead: number): CachedFrame | null => {
    const keyExact = `${scenarioId}_${exactLead}`;
    if (frameCacheRef.current.has(keyExact)) {
      return frameCacheRef.current.get(keyExact)!;
    }

    const lowerKeyframe = Math.floor(exactLead / 5) * 5;
    const upperKeyframe = lowerKeyframe + 5;
    const keyLower = `${scenarioId}_${lowerKeyframe}`;
    const keyUpper = `${scenarioId}_${upperKeyframe}`;

    const lowerFrame = frameCacheRef.current.get(keyLower);
    const upperFrame = frameCacheRef.current.get(keyUpper);

    if (lowerFrame && upperFrame) {
      const alpha = (exactLead - lowerKeyframe) / 5.0;
      const len = lowerFrame.depth.length;
      const interpDepth = new Float32Array(len);
      for (let i = 0; i < len; i++) {
        interpDepth[i] = lowerFrame.depth[i] * (1 - alpha) + upperFrame.depth[i] * alpha;
      }

      const interpMetrics: MetricsSummary = {
        ...lowerFrame.metrics,
        lead_minutes: exactLead,
        peak_depth_m: lowerFrame.metrics.peak_depth_m * (1 - alpha) + upperFrame.metrics.peak_depth_m * alpha,
        flooded_area_m2: Math.round(lowerFrame.metrics.flooded_area_m2 * (1 - alpha) + upperFrame.metrics.flooded_area_m2 * alpha),
        rainfall_rate_mmh: lowerFrame.metrics.rainfall_rate_mmh * (1 - alpha) + upperFrame.metrics.rainfall_rate_mmh * alpha,
        outfall_q_m3s: lowerFrame.metrics.outfall_q_m3s * (1 - alpha) + upperFrame.metrics.outfall_q_m3s * alpha,
        storage_volume_m3: lowerFrame.metrics.storage_volume_m3 * (1 - alpha) + upperFrame.metrics.storage_volume_m3 * alpha,
      };

      let interpRain: Float32Array | undefined = undefined;
      if (lowerFrame.rainfallGrid && upperFrame.rainfallGrid && lowerFrame.rainfallGrid.length === upperFrame.rainfallGrid.length) {
        const rLen = lowerFrame.rainfallGrid.length;
        interpRain = new Float32Array(rLen);
        for (let i = 0; i < rLen; i++) {
          interpRain[i] = lowerFrame.rainfallGrid[i] * (1 - alpha) + upperFrame.rainfallGrid[i] * alpha;
        }
      }

      const blendedFrame: CachedFrame = {
        depth: interpDepth,
        rainfallGrid: interpRain || lowerFrame.rainfallGrid || upperFrame.rainfallGrid,
        roadImpacts: alpha < 0.5 ? lowerFrame.roadImpacts : upperFrame.roadImpacts,
        metrics: interpMetrics,
        grid: lowerFrame.grid,
      };
      return blendedFrame;
    }

    return lowerFrame || upperFrame || null;
  }, []);

  // Pre-load horizon frames in background (Full 3-hour 180min nowcast horizon)
  const preloadHorizon = useCallback(async (horizonMinutes = 180, stepMinutes = 5) => {
    setIsBuffering(true);
    try {
      const url = activeScenarioId === 'REALTIME'
        ? `/api/v1/nowcast/realtime/horizon?max_lead=${horizonMinutes}&step=${stepMinutes}`
        : `/api/v1/scenarios/${activeScenarioId}/horizon?max_lead=${horizonMinutes}&step=${stepMinutes}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.frames)) {
          const loadedLeads: number[] = [];
          data.frames.forEach((f: any) => {
            const lead = f.lead_minutes ?? 0;
            const parsed = parseFramePayload(f, activeScenarioId, lead);
            frameCacheRef.current.set(`${activeScenarioId}_${lead}`, parsed);
            loadedLeads.push(lead);
          });
          setBufferedLeads((prev) =>
            Array.from(new Set([...prev, ...loadedLeads])).sort((a, b) => a - b)
          );
        }

      }
    } catch (e) {
      console.warn('Batch horizon preload failed:', e);
    } finally {
      setIsBuffering(false);
    }
  }, [activeScenarioId, parseFramePayload]);

  // Load single or interpolated frame
  const loadFrame = useCallback(async (scenarioId: string, lead: number, showBlockingLoader = false) => {
    const cached = getInterpolatedFrame(scenarioId, lead);
    if (cached) {
      setDepthGrid(cached.depth);
      setRainfallGrid(cached.rainfallGrid || null);
      setRoadImpacts(cached.roadImpacts);
      setMetrics(cached.metrics);
      if (cached.grid) {
        setGridMeta((prev) => ({ ...prev, ...cached.grid }));
      }
      return;
    }

    if (scenarioId !== 'REALTIME' && lead % 5 !== 0) {
      const lower = Math.floor(lead / 5) * 5;
      const upper = Math.min(180, lower + 5);
      await Promise.all([
        loadFrame(scenarioId, lower, showBlockingLoader),
        loadFrame(scenarioId, upper, false),
      ]);
      const interpolated = getInterpolatedFrame(scenarioId, lead);
      if (interpolated) {
        setDepthGrid(interpolated.depth);
        setRainfallGrid(interpolated.rainfallGrid || null);
        setRoadImpacts(interpolated.roadImpacts);
        setMetrics(interpolated.metrics);
        if (interpolated.grid) {
          setGridMeta((prev) => ({ ...prev, ...interpolated.grid }));
        }
      }
      return;
    }

    if (showBlockingLoader) {
      setIsLoading(true);
      setLoadingMessage(`Solving Coupled Hydrodynamic Equations (T+${lead}m)...`);
    }

    try {
      const queryLead = scenarioId === 'REALTIME' ? lead : Math.round(lead / 5) * 5;
      const url = scenarioId === 'REALTIME'
        ? `/api/v1/nowcast/realtime/frame?lead=${queryLead}`
        : `/api/v1/scenarios/${scenarioId}/frame?lead=${queryLead}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const parsed = parseFramePayload(data, scenarioId, queryLead);
        frameCacheRef.current.set(`${scenarioId}_${queryLead}`, parsed);
        setDepthGrid(parsed.depth);
        setRainfallGrid(parsed.rainfallGrid || null);
        setRoadImpacts(parsed.roadImpacts);
        setMetrics(parsed.metrics);
        if (parsed.grid) {
          setGridMeta((prev) => ({ ...prev, ...parsed.grid }));
        }

        setBufferedLeads((prev) => Array.from(new Set([...prev, queryLead])).sort((a, b) => a - b));
      }
    } catch (e) {
      console.error('Error fetching frame:', e);
    } finally {
      if (showBlockingLoader) setIsLoading(false);
    }
  }, [getInterpolatedFrame, parseFramePayload]);


  // Load City Data
  const loadCityData = useCallback(async (city: CityId) => {
    setIsLoading(true);
    setLoadingMessage(`Loading High-Precision GIS Topography & Infrastructure for ${city}...`);
    try {
      frameCacheRef.current.clear();
      setBufferedLeads([]);

      await fetch('/api/v1/city/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ city_id: city }),
      });

      const [metaRes, scenRes, roadsRes, drainRes, assetsRes, telemRes] = await Promise.all([
        fetch('/api/v1/city/active'),
        fetch('/api/v1/scenarios'),
        fetch('/api/v1/roads'),
        fetch('/api/v1/drainage/points'),
        fetch(`/api/v1/vulnerability/assets?city=${city}`),
        fetch('/api/v1/telemetry/live'),
      ]);

      if (metaRes.ok) {
        const data = await metaRes.json();
        const m = data.metadata || data;
        setCityMeta(m);
        const gs = data.grid_spec;
        if (gs && gs.bounds) {
          setGridMeta({
            origin_x: gs.bounds[0],
            origin_y: gs.bounds[1],
            width: gs.width,
            height: gs.height,
            cell_size_m: gs.cell_size_m,
            crs: gs.crs_wkt_or_epsg,
          });
        }
      }

      if (scenRes.ok) {
        const sc = await scenRes.json();
        setScenarios(sc.scenarios || []);
      }

      if (roadsRes.ok) {
        const r = await roadsRes.json();
        setRoads(r.roads || r.features || r.segments || []);
      }

      if (drainRes.ok) {
        const d = await drainRes.json();
        setDrainage(d);
      }

      if (assetsRes.ok) {
        const a = await assetsRes.json();
        setCriticalAssets(a.assets || []);
      }

      if (telemRes.ok) {
        const t = await telemRes.json();
        setTelemetry(t);
      }

      // Now fetch lead 0 frame for this switched city
      const frameRes = await fetch(`/api/v1/scenarios/${activeScenarioId}/frame?lead=0`);
      if (frameRes.ok) {
        const fData = await frameRes.json();
        const parsed = parseFramePayload(fData, activeScenarioId, 0);
        frameCacheRef.current.set(`${activeScenarioId}_0`, parsed);
        setDepthGrid(parsed.depth);
        setRainfallGrid(parsed.rainfallGrid || null);
        setRoadImpacts(parsed.roadImpacts);
        setMetrics(parsed.metrics);
        if (parsed.grid) {
          setGridMeta((prev) => ({ ...prev, ...parsed.grid }));
        }
        setBufferedLeads([0]);
      }

      preloadHorizon(180, 5);
    } catch (e) {
      console.error('Error loading city data:', e);
    } finally {
      setIsLoading(false);
    }
  }, [activeScenarioId, parseFramePayload, preloadHorizon]);

  // Handle Route Calculation
  const handleCalculateRoute = async (origin: [number, number], destination: [number, number], mode: string) => {
    try {
      const res = await fetch('/api/v1/routes/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: activeScenarioId,
          lead_minutes: currentLead,
          origin,
          destination,
          mode,
        }),
      });
      if (res.ok) {
        const routeData = await res.json();
        setActiveRoute(routeData);
      }
    } catch (e) {
      console.error('Route calculation error:', e);
    }
  };

  // When activeCity changes (initial load or city switch)
  useEffect(() => {
    loadCityData(activeCity);
  }, [activeCity, loadCityData]);

  // When scenario changes
  useEffect(() => {
    frameCacheRef.current.clear();
    setBufferedLeads([]);
    loadFrame(activeScenarioId, currentLead, false);
    preloadHorizon(180, 5);
  }, [activeScenarioId]);

  // When lead changes (Smooth playback - purely in-memory from cache)
  useEffect(() => {
    loadFrame(activeScenarioId, currentLead, false);
  }, [currentLead]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh', background: '#000000', overflow: 'hidden' }}>
      {/* 1. Sleek Top Navigation Bar */}
      <Navbar
        activeCity={activeCity}
        onCityChange={(city) => {
          setActiveCity(city);
          setActiveRoute(null);
          frameCacheRef.current.clear();
          setBufferedLeads([]);
        }}
        cityMeta={cityMeta}
        telemetry={telemetry}
      />

      {/* 2. Main Middle Viewport (Sidebar + Map) */}
      <div style={{ display: 'flex', flex: 1, height: 'calc(100vh - 48px - 58px - 44px)', overflow: 'hidden', position: 'relative' }}>
        {/* Left Sidebar Tabs (Simulation, Routing, Assets, Mitigation, Calibration & CAP) */}
        <SidebarTabs
          scenarios={scenarios}
          activeScenarioId={activeScenarioId}
          onScenarioChange={(scId) => {
            setActiveScenarioId(scId);
            setCurrentLead(0);
          }}
          currentLead={currentLead}
          telemetry={telemetry}
          activeRoute={activeRoute}
          onCalculateRoute={handleCalculateRoute}
          criticalAssets={criticalAssets}
          activeCity={activeCity}
        />

        {/* Center / Right Dynamic Canvas Map View */}
        <div style={{ flex: 1, position: 'relative', height: '100%', overflow: 'hidden' }}>
          <MapView
            cityMeta={cityMeta}
            gridMeta={gridMeta}
            depthGrid={depthGrid}
            rainfallGrid={rainfallGrid}
            roads={roads}
            roadImpacts={roadImpacts}
            drainage={drainage}
            criticalAssets={criticalAssets}
            activeRoute={activeRoute}
            currentLead={currentLead}
            minDepthThreshold={0.01}
            layers={layers}
            onLayersChange={setLayers}
            isLoading={isLoading}
            loadingMessage={loadingMessage}
            telemetry={telemetry}
            basemapStyle={basemapStyle}
            onBasemapChange={setBasemapStyle}
            selectedAssetCategory={selectedAssetCategory}
          />
        </div>
      </div>

      {/* 3. Bottom Smooth 1-Minute Video-Like Timeline Controller */}
      <TimelineController
        currentLead={currentLead}
        onLeadChange={setCurrentLead}
        maxLead={180}
        step={currentTimeStep}
        onStepChange={setCurrentTimeStep}
        bufferedLeads={bufferedLeads}
        isBuffering={isBuffering}
        onPreloadHorizon={preloadHorizon}
      />

      {/* 4. Bottom Real-Time Telemetry Metrics Strip */}
      <MetricsBar metrics={metrics} />
    </div>
  );
};
