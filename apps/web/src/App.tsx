import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiUrl } from './config';
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
  RoadTier,
  RouteTier,
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
  // Active City State (Defaults to MUMBAI on startup)
  const [activeCity, setActiveCity] = useState<CityId>('MUMBAI');
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
    origin_x: 262955.57,
    origin_y: 2088778.45,
    width: 825,
    height: 1486,
    cell_size_m: 30.0,
    crs: 'EPSG:32643',
  });
  const [depthGrid, setDepthGrid] = useState<Float32Array | null>(null);
  const [rainfallGrid, setRainfallGrid] = useState<Float32Array | null>(null);
  const [roads, setRoads] = useState<RoadSegment[]>([]);
  const [roadTier, setRoadTier] = useState<RoadTier>('main');
  const [roadImpacts, setRoadImpacts] = useState<Record<string, RoadImpact>>({});
  const [drainage, setDrainage] = useState<any>(null);
  const [criticalAssets, setCriticalAssets] = useState<CriticalAssetItem[]>([]);
  const [activeRoute, setActiveRoute] = useState<RouteResponse | null>(null);
  const [telemetry, setTelemetry] = useState<LiveTelemetry | null>(null);

  // Dynamic Map Waypoint Selection State
  const [routingOrigin, setRoutingOrigin] = useState<[number, number] | null>([300615.0, 2503405.0]);
  const [routingDestination, setRoutingDestination] = useState<[number, number] | null>([303405.0, 2500615.0]);
  const [pickingWaypointMode, setPickingWaypointMode] = useState<'origin' | 'destination' | null>(null);

  const handlePickWaypoint = useCallback((coords: [number, number]) => {
    if (pickingWaypointMode === 'origin') {
      setRoutingOrigin(coords);
    } else if (pickingWaypointMode === 'destination') {
      setRoutingDestination(coords);
    }
    setPickingWaypointMode(null);
  }, [pickingWaypointMode]);

  const handleCancelPickingWaypoint = useCallback(() => {
    setPickingWaypointMode(null);
  }, []);

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

    // Calculate live raster metrics from 2D depth array
    let computedPeakDepth = 0.0;
    let computedFloodedArea = 0;
    if (parsedDepth && parsedDepth.length > 0) {
      for (let i = 0; i < parsedDepth.length; i++) {
        const d = parsedDepth[i];
        if (d > computedPeakDepth) computedPeakDepth = d;
        if (d >= 0.05) computedFloodedArea += 1;
      }
    }
    const cs = gridMeta.cell_size_m || 30.0;
    computedFloodedArea = Math.round(computedFloodedArea * cs * cs);

    // Calculate live road counts from impacts dictionary
    const impactValues = Object.values(impacts);
    let dryCount = 0;
    let passableCount = 0;
    let impassableCount = 0;
    impactValues.forEach((imp) => {
      if (imp.classification === 'DRY') dryCount++;
      if (imp.passability === 'PASSABLE') passableCount++;
      else if (imp.passability === 'IMPASSABLE') impassableCount++;
    });

    const m = data.metrics || data.road_metrics || {};
    const parsedMetrics: MetricsSummary = {
      lead_minutes: lead,
      rainfall_rate_mmh: m.rainfall_rate_mmh ?? (scenarioId === 'S4' ? Math.max(0, 85 - lead * 0.4) : (scenarioId === 'REALTIME' ? (telemetry?.precip_rate_mmh ?? 18.5) : 35.0)),
      peak_depth_m: m.peak_depth_m ?? computedPeakDepth,
      flooded_area_m2: m.flooded_area_m2 ?? computedFloodedArea,
      dry_roads_count: m.dry_roads_count ?? m.dry ?? dryCount,
      passable_roads_count: m.passable_roads_count ?? m.passable ?? (passableCount || impactValues.length),
      impassable_roads_count: m.impassable_roads_count ?? m.impassable ?? impassableCount,
      surcharged_nodes_count: m.surcharged_nodes_count ?? (data.drainage?.surcharged ? 1 : 0),
      storage_volume_m3: m.storage_volume_m3 ?? (data.drainage?.surface_storage_m3 || Math.round(computedPeakDepth * computedFloodedArea * 0.4)),
      outfall_q_m3s: m.outfall_q_m3s ?? (data.drainage?.outfall_cum_m3 ? Math.round(data.drainage.outfall_cum_m3 / Math.max(1, lead * 60) * 100) / 100 : (scenarioId === 'S4' ? 3.45 : 1.20)),
      active_model: m.active_model || 'Coupled 1D/2D Hydrodynamics (SWE + SWMM)',
      dataset_source: m.dataset_source || (cityMeta?.city_id !== 'demo' ? 'REAL_OBSERVED' : 'SYNTHETIC_DEMO'),
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
        ? apiUrl(`/api/v1/nowcast/realtime/horizon?max_lead=${horizonMinutes}&step=${stepMinutes}`)
        : apiUrl(`/api/v1/scenarios/${activeScenarioId}/horizon?max_lead=${horizonMinutes}&step=${stepMinutes}`);
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
        ? apiUrl(`/api/v1/nowcast/realtime/frame?lead=${queryLead}`)
        : apiUrl(`/api/v1/scenarios/${scenarioId}/frame?lead=${queryLead}`);
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

      try {
        await fetch(apiUrl('/api/v1/city/switch'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ city_id: city }),
        });
      } catch (e) {
        console.warn('City switch notification notice:', e);
      }

      // Fetch core GIS and active city specification
      const [metaRes, scenRes, roadsRes, drainRes, assetsRes, telemRes] = await Promise.allSettled([
        fetch(apiUrl('/api/v1/city/active')).then((r) => (r.ok ? r.json() : null)),
        fetch(apiUrl('/api/v1/scenarios')).then((r) => (r.ok ? r.json() : null)),
        fetch(apiUrl(`/api/v1/roads?tier=${roadTier === 'none' ? 'main' : roadTier}`)).then((r) => (r.ok ? r.json() : null)),
        fetch(apiUrl('/api/v1/drainage/points')).then((r) => (r.ok ? r.json() : null)),
        fetch(apiUrl(`/api/v1/vulnerability/assets?city=${city}`)).then((r) => (r.ok ? r.json() : null)),
        fetch(apiUrl('/api/v1/telemetry/live')).then((r) => (r.ok ? r.json() : null)),
      ]);

      if (metaRes.status === 'fulfilled' && metaRes.value) {
        const data = metaRes.value;
        const m = data.metadata || data;
        setCityMeta(m);
        const gs = data.grid_spec;
        if (gs && gs.bounds) {
          const ox = gs.bounds[0];
          const oy = gs.bounds[1];
          const w_m = gs.width * gs.cell_size_m;
          const h_m = gs.height * gs.cell_size_m;
          setGridMeta({
            origin_x: ox,
            origin_y: oy,
            width: gs.width,
            height: gs.height,
            cell_size_m: gs.cell_size_m,
            crs: gs.crs_wkt_or_epsg,
          });
          setRoutingOrigin([Math.round(ox + w_m * 0.35), Math.round(oy + h_m * 0.65)]);
          setRoutingDestination([Math.round(ox + w_m * 0.65), Math.round(oy + h_m * 0.35)]);
        }
      }

      if (scenRes.status === 'fulfilled' && scenRes.value) {
        setScenarios(scenRes.value.scenarios || []);
      }

      if (roadsRes.status === 'fulfilled' && roadsRes.value) {
        const r = roadsRes.value;
        setRoads(r.roads || r.features || r.segments || []);
      }

      if (drainRes.status === 'fulfilled' && drainRes.value) {
        setDrainage(drainRes.value);
      }

      if (assetsRes.status === 'fulfilled' && assetsRes.value) {
        setCriticalAssets(assetsRes.value.assets || []);
      }

      if (telemRes.status === 'fulfilled' && telemRes.value) {
        setTelemetry(telemRes.value);
      }

      // Initial Frame (t=0)
      try {
        const frameRes = await fetch(apiUrl(`/api/v1/scenarios/${activeScenarioId}/frame?lead=0`));
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
      } catch (fe) {
        console.warn('Initial frame fetch warning:', fe);
      }

      preloadHorizon(180, 5);
    } catch (e) {
      console.error('Error loading city data:', e);
    } finally {
      setIsLoading(false);
    }
  }, [activeScenarioId, parseFramePayload, preloadHorizon, roadTier]);

  // Handle dynamic road tier partition switching
  const handleRoadTierChange = useCallback(async (tier: RoadTier) => {
    setRoadTier(tier);
    if (tier === 'none') {
      setRoads([]);
      setLayers((prev) => ({ ...prev, roads: false }));
      return;
    }
    setLayers((prev) => ({ ...prev, roads: true }));
    try {
      const res = await fetch(apiUrl(`/api/v1/roads?tier=${tier}`));
      if (res.ok) {
        const data = await res.json();
        const segs: RoadSegment[] = data.roads || data.segments || [];
        setRoads(segs);
      }
    } catch (e) {
      console.error('Error fetching road tier:', e);
    }
  }, []);

  // Handle Route Calculation
  const handleCalculateRoute = async (origin: [number, number], destination: [number, number], mode: string) => {
    try {
      const res = await fetch(apiUrl('/api/v1/routes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: activeScenarioId,
          lead: currentLead,
          origin,
          destination,
          mode: mode || 'safest',
        }),
      });
      if (res.ok) {
        const routeData = await res.json();

        const parseTier = (t: any, defaultId: 'safest' | 'caution' | 'hazardous', defaultLabel: string, defaultColor: string): RouteTier | undefined => {
          if (!t) return undefined;
          const wps = t.waypoints || t.coordinates || t.geometry || [];
          if (!wps || wps.length === 0) return undefined;
          const d_m = t.total_distance_m ?? t.length_m ?? t.distance_m ?? 0;
          const t_min = t.estimated_travel_time_min ?? (t.travel_time_s ? t.travel_time_s / 60 : (t.estimated_time_s ? t.estimated_time_s / 60 : 0));
          const depth = t.max_encountered_depth_m ?? t.max_flood_depth_m ?? 0;
          return {
            tier_id: defaultId,
            label: t.label || defaultLabel,
            color: t.color || defaultColor,
            waypoints: wps,
            total_distance_m: Math.round(d_m),
            estimated_travel_time_min: Math.round(t_min * 10) / 10,
            max_encountered_depth_m: Math.round(depth * 1000) / 1000,
            safety_status: t.safety_status || (depth < 0.15 ? 'SAFE' : (depth < 0.28 ? 'CAUTION' : 'HAZARDOUS')),
            is_passable: t.is_passable ?? (depth <= 0.25),
          };
        };

        const safestTier = parseTier(routeData.safest || routeData.flood_aware, 'safest', 'Safest Route (Recommended)', '#10b981');
        const cautionTier = parseTier(routeData.caution, 'caution', 'Moderate / Not Suggested', '#f59e0b');
        const hazardousTier = parseTier(routeData.hazardous || routeData.baseline, 'hazardous', 'Hazardous / Flooded Shortcut', '#ef4444');

        const initialSelectedTier: 'safest' | 'caution' | 'hazardous' = (mode === 'baseline' || mode === 'hazardous') ? 'hazardous' : (mode === 'caution' ? 'caution' : 'safest');
        const activeTier = (initialSelectedTier === 'hazardous' ? hazardousTier : (initialSelectedTier === 'caution' ? cautionTier : safestTier)) || safestTier || cautionTier || hazardousTier;

        const totalDist = activeTier?.total_distance_m ?? 0;
        const travelTimeMin = activeTier?.estimated_travel_time_min ?? 0;
        const maxDepth = activeTier?.max_encountered_depth_m ?? 0;
        const waypoints = activeTier?.waypoints || [origin, destination];

        const formattedRoute: RouteResponse = {
          route_found: true,
          status: activeTier?.safety_status || 'PASSABLE',
          mode: mode || 'safest',
          total_distance_m: totalDist,
          estimated_travel_time_min: travelTimeMin,
          max_encountered_depth_m: maxDepth,
          safety_status: activeTier?.safety_status || 'SAFE',
          waypoints: waypoints,
          baseline_waypoints: hazardousTier?.waypoints || [],
          flood_aware_waypoints: safestTier?.waypoints || [],
          safest: safestTier,
          caution: cautionTier,
          hazardous: hazardousTier,
          selected_tier: initialSelectedTier,
          segments: [],
          itinerary: [],
          provenance_label: 'Coupled Flood-Aware Dynamic Dijkstra',
        };
        setActiveRoute(formattedRoute);
        setRoutingOrigin(origin);
        setRoutingDestination(destination);
      } else {
        const err = await res.json().catch(() => ({}));
        console.warn('Route calculation warning response:', err);
      }
    } catch (e) {
      console.error('Route calculation error:', e);
    }
  };

  const handleSelectRouteTier = (tierId: 'safest' | 'caution' | 'hazardous') => {
    setActiveRoute((prev) => {
      if (!prev) return null;
      const target = tierId === 'safest' ? prev.safest : (tierId === 'caution' ? prev.caution : prev.hazardous);
      if (!target) return prev;
      return {
        ...prev,
        selected_tier: tierId,
        waypoints: target.waypoints,
        total_distance_m: target.total_distance_m,
        estimated_travel_time_min: target.estimated_travel_time_min,
        max_encountered_depth_m: target.max_encountered_depth_m,
        safety_status: target.safety_status,
      };
    });
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
          onSelectRouteTier={handleSelectRouteTier}
          criticalAssets={criticalAssets}
          activeCity={activeCity}
          routingOrigin={routingOrigin}
          routingDestination={routingDestination}
          pickingWaypointMode={pickingWaypointMode}
          onStartPickingWaypoint={setPickingWaypointMode}
          onOriginChange={setRoutingOrigin}
          onDestinationChange={setRoutingDestination}
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
            roadTier={roadTier}
            onRoadTierChange={handleRoadTierChange}
            routingOrigin={routingOrigin}
            routingDestination={routingDestination}
            pickingWaypointMode={pickingWaypointMode}
            onPickWaypoint={handlePickWaypoint}
            onCancelPickingWaypoint={handleCancelPickingWaypoint}
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
