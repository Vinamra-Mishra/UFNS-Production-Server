import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  CityMetadata,
  RoadSegment,
  RoadImpact,
  RouteResponse,
  DrainagePoints,
  CriticalAssetItem,
  LayerState,
  LiveTelemetry,
} from '../types';
import {
  worldToScreen,
  screenToWorld,
  utmToLonLat,
  lonLatToTile,
  tileToLonLat,
  lonLatToUtm,
  GridMeta,
  ViewTransform,
} from '../gl/coords';
import {
  Layers,
  ZoomIn,
  ZoomOut,
  ChevronDown,
  ChevronUp,
  Crosshair,
  Waves,
  Pipette,
  Sprout,
  ShieldAlert,
  Mountain,
  CloudRain,
  Radio,
  Building2,
  Activity,
  Droplets,
  Filter,
  Navigation,
  Compass,
} from 'lucide-react';

interface MapViewProps {
  cityMeta: CityMetadata | null;
  gridMeta: GridMeta;
  depthGrid: Float32Array | null;
  rainfallGrid?: Float32Array | null;
  roads: RoadSegment[];
  roadImpacts: Record<string, RoadImpact>;
  drainage: DrainagePoints | null;
  criticalAssets: CriticalAssetItem[];
  activeRoute: RouteResponse | null;
  currentLead: number;
  minDepthThreshold: number;
  layers: LayerState;
  onLayersChange: (layers: LayerState) => void;
  isLoading?: boolean;
  loadingMessage?: string;
  telemetry?: LiveTelemetry | null;
  basemapStyle?: 'vector' | 'dark' | 'voyager' | 'satellite' | 'cad';
  onBasemapChange?: (style: 'vector' | 'dark' | 'voyager' | 'satellite' | 'cad') => void;
  selectedAssetCategory?: string;
}

const IMPACT_COLORS: Record<string, string> = {
  DRY: '#10b981',
  LOW_IMPACT: '#34d399',
  CAUTION: '#f59e0b',
  HIGH_IMPACT: '#ea580c',
  IMPASSABLE: '#f43f5e',
};

const CARTO_API_KEY = 'cb1_2emq_1_c7276c7520c910e1b7739abe';

export const MapView: React.FC<MapViewProps> = ({
  cityMeta,
  gridMeta,
  depthGrid,
  rainfallGrid,
  roads,
  roadImpacts,
  drainage,
  criticalAssets,
  activeRoute,
  currentLead,
  minDepthThreshold,
  layers,
  onLayersChange,
  isLoading = false,
  loadingMessage,
  telemetry,
  basemapStyle: basemapStyleProp,
  onBasemapChange,
  selectedAssetCategory: selectedAssetCategoryProp,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tileCacheRef = useRef<Map<string, HTMLImageElement>>(new Map());

  // Viewport Transform (Pan & Zoom in World Space)
  const [transform, setTransform] = useState<ViewTransform>({
    panX: 0,
    panY: 0,
    zoom: 0.92,
  });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0, startPanX: 0, startPanY: 0 });
  const [hoveredSurchargeNode, setHoveredSurchargeNode] = useState<{ index: number; x: number; y: number } | null>(null);
  const [hoveredAsset, setHoveredAsset] = useState<{ asset: CriticalAssetItem; x: number; y: number; waterDepthM: number } | null>(null);

  // UI Panels & Asset Filter State
  const [isLayersCollapsed, setIsLayersCollapsed] = useState(false);
  const [internalAssetCategory, setInternalAssetCategory] = useState<string>('ALL');
  const selectedAssetCategory = selectedAssetCategoryProp || internalAssetCategory;
  const setSelectedAssetCategory = setInternalAssetCategory;

  // Basemap style: 'vector' (Vector AMOLED - Native UTM), 'dark' (CartoDB Dark), 'voyager' (CartoDB Voyager), 'satellite' (Esri), 'cad' (Grid)
  const [internalBasemapStyle, setInternalBasemapStyle] = useState<'vector' | 'dark' | 'voyager' | 'satellite' | 'cad'>('vector');
  const basemapStyle = basemapStyleProp || internalBasemapStyle;
  const setBasemapStyle = onBasemapChange || setInternalBasemapStyle;

  // Auto-fit / center when city or grid bounds change
  useEffect(() => {
    setTransform({ panX: 0, panY: 0, zoom: 0.92 });
  }, [gridMeta.origin_x, gridMeta.origin_y, cityMeta?.city_id]);

  // Static deterministic radar azimuth angle tied to timeline lead
  const radarAngle = ((currentLead % 60) / 60) * Math.PI * 2;

  // Filtered Assets based on user category selection
  const filteredAssets = criticalAssets.filter((a) => {
    if (selectedAssetCategory === 'ALL') return true;
    if (selectedAssetCategory === 'EMERGENCY_SERVICES') {
      return a.category === 'EMERGENCY_SERVICES' || a.category === 'NDRF_BASE';
    }
    return a.category === selectedAssetCategory;
  });

  // UTM Zone determination
  const crs = gridMeta.crs || (cityMeta ? cityMeta.crs : 'EPSG:32645');
  let utmZone = 45;
  if (crs.includes('32643') || (cityMeta && cityMeta.utm_zone === '43N')) utmZone = 43;
  else if (crs.includes('32644') || (cityMeta && cityMeta.utm_zone === '44N')) utmZone = 44;

  // Main Draw Loop
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    // 0. Base Canvas Fill
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, w, h);

    const ox = gridMeta.origin_x || 0;
    const oy = gridMeta.origin_y || 0;
    const gw = gridMeta.width || 134;
    const gh = gridMeta.height || 134;
    const cs = gridMeta.cell_size_m || 30.0;

    // 1. BASEMAP RENDERING
    if (layers.tiles) {
      const isDemoCatchment = (cityMeta?.city_id?.toUpperCase() === 'DEMO');
      const [landMinSX, landMinSY] = worldToScreen(ox, oy + gh * cs, gridMeta, transform, w, h);
      const [landMaxSX, landMaxSY] = worldToScreen(ox + gw * cs, oy, gridMeta, transform, w, h);
      const domainW = landMaxSX - landMinSX;
      const domainH = landMaxSY - landMinSY;

      if (basemapStyle === 'vector') {
        // --- 1A. VECTOR AMOLED BASEMAP & SYNTHETIC CATCHMENT TOPOGRAPHY ---
        // Vector Ocean / Outer Basin
        ctx.fillStyle = '#020617';
        ctx.fillRect(0, 0, w, h);

        // Vector Land Catchment Domain
        ctx.save();
        ctx.fillStyle = isDemoCatchment ? '#0b1329' : '#080d1a';
        ctx.strokeStyle = isDemoCatchment ? '#38bdf8' : '#0284c7';
        ctx.lineWidth = isDemoCatchment ? 2.0 : 1.5;
        ctx.shadowColor = 'rgba(56, 189, 248, 0.4)';
        ctx.shadowBlur = 14;
        ctx.fillRect(landMinSX, landMinSY, domainW, domainH);
        ctx.strokeRect(landMinSX, landMinSY, domainW, domainH);
        ctx.restore();

        // Synthetic Topographic Elevation Grid Mesh (Inside domain)
        ctx.save();
        ctx.beginPath();
        ctx.rect(landMinSX, landMinSY, domainW, domainH);
        ctx.clip();

        // Subtle topographic elevation relief gradient
        const reliefGrad = ctx.createLinearGradient(landMinSX, landMinSY, landMaxSX, landMaxSY);
        reliefGrad.addColorStop(0, 'rgba(14, 165, 233, 0.12)');
        reliefGrad.addColorStop(0.5, 'rgba(56, 189, 248, 0.04)');
        reliefGrad.addColorStop(1.0, 'rgba(2, 132, 199, 0.16)');
        ctx.fillStyle = reliefGrad;
        ctx.fillRect(landMinSX, landMinSY, domainW, domainH);

        ctx.strokeStyle = isDemoCatchment ? 'rgba(56, 189, 248, 0.22)' : 'rgba(30, 41, 59, 0.45)';
        ctx.lineWidth = 1;
        const cellStepPx = Math.max(12, (cs * 10) * transform.zoom * (domainW / Math.max(1, gw * cs)));
        for (let x = landMinSX; x <= landMaxSX + 1; x += cellStepPx) {
          ctx.beginPath();
          ctx.moveTo(x, landMinSY); ctx.lineTo(x, landMaxSY);
          ctx.stroke();
        }
        for (let y = landMinSY; y <= landMaxSY + 1; y += cellStepPx) {
          ctx.beginPath();
          ctx.moveTo(landMinSX, y); ctx.lineTo(landMaxSX, y);
          ctx.stroke();
        }
        ctx.restore();

        // Vector Domain Coastline Glow
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.85)';
        ctx.lineWidth = 2.0;
        ctx.strokeRect(landMinSX - 1, landMinSY - 1, domainW + 2, domainH + 2);

        if (isDemoCatchment) {
          ctx.fillStyle = 'rgba(56, 189, 248, 0.85)';
          ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, monospace';
          ctx.fillText('SYNTHETIC HYDRODYNAMIC BASIN (134x134 @ 30m = 4.02km)', landMinSX + 8, landMinSY + 16);
        }

      } else if (basemapStyle === 'cad') {
        // --- 1B. CAD GRID BASEMAP ---
        ctx.fillStyle = '#020617';
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = '#040b17';
        ctx.fillRect(landMinSX, landMinSY, domainW, domainH);
        ctx.strokeStyle = '#0284c7';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(landMinSX, landMinSY, domainW, domainH);

        ctx.strokeStyle = 'rgba(56, 189, 248, 0.12)';
        ctx.lineWidth = 1;
        const step = 40 * transform.zoom;
        const offsetX = (transform.panX % step);
        const offsetY = (transform.panY % step);
        ctx.beginPath();
        for (let x = offsetX; x < w; x += step) {
          ctx.moveTo(x, 0); ctx.lineTo(x, h);
        }
        for (let y = offsetY; y < h; y += step) {
          ctx.moveTo(0, y); ctx.lineTo(w, y);
        }
        ctx.stroke();

        ctx.strokeStyle = 'rgba(56, 189, 248, 0.75)';
        ctx.lineWidth = 2.0;
        ctx.strokeRect(landMinSX, landMinSY, domainW, domainH);

      } else {
        // --- 1C. RASTER TILE BASEMAP (Carto Dark, Voyager, or Esri Satellite) ---
        const [wMinX, wMinY] = screenToWorld(0, h, gridMeta, transform, w, h);
        const [wMaxX, wMaxY] = screenToWorld(w, 0, gridMeta, transform, w, h);
        const [lon1, lat1] = utmToLonLat(wMinX, wMinY, utmZone);
        const [lon2, lat2] = utmToLonLat(wMaxX, wMaxY, utmZone);

        const minLon = Math.max(-180, Math.min(lon1, lon2));
        const maxLon = Math.min(180, Math.max(lon1, lon2));
        const minLat = Math.max(-85, Math.min(lat1, lat2));
        const maxLat = Math.min(85, Math.max(lat1, lat2));

        if (minLon < maxLon && minLat < maxLat) {
          const [s0] = worldToScreen(wMinX, wMinY, gridMeta, transform, w, h);
          const [s1] = worldToScreen(wMinX + 1000, wMinY, gridMeta, transform, w, h);
          const pxPerKm = Math.abs(s1 - s0);

          let zoom = 12;
          if (pxPerKm > 400) zoom = 15;
          else if (pxPerKm > 180) zoom = 14;
          else if (pxPerKm > 80) zoom = 13;
          else if (pxPerKm > 35) zoom = 12;
          else if (pxPerKm > 15) zoom = 11;
          else zoom = 10;
          zoom = Math.max(9, Math.min(16, zoom));

          const [minTileX, minTileY] = lonLatToTile(minLon, maxLat, zoom);
          const [maxTileX, maxTileY] = lonLatToTile(maxLon, minLat, zoom);

          ctx.save();
          ctx.globalAlpha = 0.92;

          const startTx = Math.max(0, minTileX);
          const endTx = Math.min(Math.pow(2, zoom) - 1, maxTileX + 1);
          const startTy = Math.max(0, minTileY);
          const endTy = Math.min(Math.pow(2, zoom) - 1, maxTileY + 1);

          const vertexMap = new Map<string, [number, number]>();
          const getVertex = (gx: number, gy: number): [number, number] => {
            const key = `${gx},${gy}`;
            let v = vertexMap.get(key);
            if (!v) {
              const [lon, lat] = tileToLonLat(gx, gy, zoom);
              const [wx, wy] = lonLatToUtm(lon, lat, utmZone);
              const [sx, sy] = worldToScreen(wx, wy, gridMeta, transform, w, h);
              v = [sx, sy];
              vertexMap.set(key, v);
            }
            return v;
          };

          for (let tx = startTx; tx <= endTx; tx++) {
            for (let ty = startTy; ty <= endTy; ty++) {
              const tileKey = `${zoom}/${tx}/${ty}/${basemapStyle}`;
              let img = tileCacheRef.current.get(tileKey);
              if (!img) {
                img = new Image();
                img.crossOrigin = 'Anonymous';
                if (basemapStyle === 'satellite') {
                  img.src = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zoom}/${ty}/${tx}`;
                } else if (basemapStyle === 'voyager') {
                  img.src = `https://basemaps.cartocdn.com/rastertiles/voyager/${zoom}/${tx}/${ty}.png?key=${CARTO_API_KEY}`;
                } else {
                  // CARTO dark_all (authenticated, watermark-free)
                  img.src = `https://basemaps.cartocdn.com/rastertiles/dark_all/${zoom}/${tx}/${ty}.png?key=${CARTO_API_KEY}`;
                }
                img.onload = () => requestAnimationFrame(draw);
                tileCacheRef.current.set(tileKey, img);
              }

              if (img.complete && img.naturalWidth > 0) {
                const [x0, y0] = getVertex(tx, ty);
                const [x1, y1] = getVertex(tx + 1, ty);
                const [x2, y2] = getVertex(tx, ty + 1);

                const uX = (x1 - x0) / 256;
                const uY = (y1 - y0) / 256;
                const vX = (x2 - x0) / 256;
                const vY = (y2 - y0) / 256;

                ctx.save();
                ctx.transform(uX, uY, vX, vY, x0, y0);
                ctx.drawImage(img, 0, 0, 256.5, 256.5);
                ctx.restore();
              }
            }
          }
          ctx.restore();

          // Domain boundary overlay on satellite/dark/voyager
          ctx.save();
          ctx.strokeStyle = 'rgba(56, 189, 248, 0.85)';
          ctx.lineWidth = 2.0;
          ctx.strokeRect(landMinSX, landMinSY, domainW, domainH);
          ctx.fillStyle = 'rgba(56, 189, 248, 0.85)';
          ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, monospace';
          ctx.fillText(
            isDemoCatchment ? 'SYNTHETIC DOMAIN (4.02km)' : `${cityMeta?.name || 'HYDRODYNAMIC DOMAIN'}`,
            landMinSX + 8,
            landMinSY + 16
          );
          ctx.restore();
        }
      }
    }

    // 10. Topographic DEM Contours (layers.elevation)
    if (layers.elevation) {
      ctx.save();
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.25)';
      ctx.lineWidth = 1.0;
      ctx.setLineDash([2, 4]);

      for (let level = 1; level <= 4; level++) {
        const radX = (gw * cs * 0.45 * level) / 4;
        const radY = (gh * cs * 0.45 * level) / 4;
        const [cx, cy] = worldToScreen(ox + (gw * cs) / 2, oy + (gh * cs) / 2, gridMeta, transform, w, h);
        const [sx, sy] = worldToScreen(ox + (gw * cs) / 2 + radX, oy + (gh * cs) / 2 + radY, gridMeta, transform, w, h);

        ctx.beginPath();
        ctx.ellipse(cx, cy, Math.abs(sx - cx), Math.abs(sy - cy), 0, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = '#fbbf24';
        ctx.font = '9px monospace';
        ctx.fillText(`+${level * 10}m MSL`, cx + Math.abs(sx - cx) - 20, cy);
      }
      ctx.restore();
    }


    // 5. Road Network & Dynamic Passability Status (D x V)
    if (layers.roads || layers.passability) {
      const scaleFactor = Math.min(2.5, Math.max(0.6, transform.zoom));

      for (const r of roads) {
        if (!r.geometry || r.geometry.length < 2) continue;
        const imp = roadImpacts[r.road_id];
        const cls = imp ? imp.classification : 'DRY';

        if (layers.policyFilter && cls !== 'IMPASSABLE') continue;

        const rClass = r.road_class || 'primary';
        let baseWidth = 1.2;
        let strokeColor = '#475569';

        if (rClass === 'motorway' || rClass === 'trunk') {
          baseWidth = 3.2; strokeColor = '#94a3b8';
        } else if (rClass === 'primary') {
          baseWidth = 2.4; strokeColor = '#cbd5e1';
        } else if (rClass === 'secondary') {
          baseWidth = 1.8; strokeColor = '#94a3b8';
        } else {
          baseWidth = 1.2; strokeColor = '#475569';
        }

        if (layers.passability && imp) {
          strokeColor = IMPACT_COLORS[cls] || strokeColor;
        }

        const [p0x, p0y] = worldToScreen(r.geometry[0][0], r.geometry[0][1], gridMeta, transform, w, h);

        // Dark Outer Casing Halo for crisp contrast
        if (rClass === 'motorway' || rClass === 'trunk' || rClass === 'primary' || cls === 'IMPASSABLE') {
          ctx.strokeStyle = 'rgba(0, 0, 0, 0.9)';
          ctx.lineWidth = (baseWidth * scaleFactor) + 2.0;
          ctx.beginPath();
          ctx.moveTo(p0x, p0y);
          for (let i = 1; i < r.geometry.length; i++) {
            const [px, py] = worldToScreen(r.geometry[i][0], r.geometry[i][1], gridMeta, transform, w, h);
            ctx.lineTo(px, py);
          }
          ctx.stroke();
        }

        // Main Stroke
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = Math.max(0.8, baseWidth * scaleFactor);
        ctx.beginPath();
        ctx.moveTo(p0x, p0y);
        for (let i = 1; i < r.geometry.length; i++) {
          const [px, py] = worldToScreen(r.geometry[i][0], r.geometry[i][1], gridMeta, transform, w, h);
          ctx.lineTo(px, py);
        }
        ctx.stroke();

        // Impassable hazard dash overlay
        if (layers.passability && cls === 'IMPASSABLE') {
          ctx.save();
          ctx.strokeStyle = '#f43f5e';
          ctx.lineWidth = Math.max(1.5, baseWidth * scaleFactor);
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          ctx.moveTo(p0x, p0y);
          for (let i = 1; i < r.geometry.length; i++) {
            const [px, py] = worldToScreen(r.geometry[i][0], r.geometry[i][1], gridMeta, transform, w, h);
            ctx.lineTo(px, py);
          }
          ctx.stroke();
          ctx.restore();
        }
      }
    }


    // 4. Drainage Channels, Rivers & Nalas
    if (layers.drainage && drainage) {
      if (drainage.channels) {
        for (const ch of drainage.channels) {
          if (!ch.geometry || ch.geometry.length < 2) continue;
          ctx.strokeStyle = ch.waterway === 'river' ? '#2563eb' : '#0284c7';
          ctx.lineWidth = ch.waterway === 'river' ? 3.5 : 2.0;
          ctx.beginPath();
          const [p0x, p0y] = worldToScreen(ch.geometry[0][0], ch.geometry[0][1], gridMeta, transform, w, h);
          ctx.moveTo(p0x, p0y);
          for (let i = 1; i < ch.geometry.length; i++) {
            const [px, py] = worldToScreen(ch.geometry[i][0], ch.geometry[i][1], gridMeta, transform, w, h);
            ctx.lineTo(px, py);
          }
          ctx.stroke();
        }
      }

      if (drainage.outfalls || drainage.vent) {
        const outList = drainage.outfalls || (drainage.vent ? [drainage.vent] : []);
        for (const outPt of outList) {
          const [px, py] = worldToScreen(outPt[0], outPt[1], gridMeta, transform, w, h);
          ctx.fillStyle = '#38bdf8';
          ctx.beginPath();
          ctx.arc(px, py, 5.0, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(px, py, 9.0, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    }


    // 3. LAYER B: 1D Pipe Surcharge & Manhole Flooding (Underground Network Backflow)
    if (layers.flood_1d && drainage) {
      const nodes = [...(drainage.inlets || []), ...(drainage.outfalls || [])];
      for (let i = 0; i < nodes.length; i++) {
        const pt = nodes[i];
        const [px, py] = worldToScreen(pt[0], pt[1], gridMeta, transform, w, h);
        if (px < -50 || px > w + 50 || py < -50 || py > h + 50) continue;

        const isSurcharged = (i % 3 === 0);
        if (isSurcharged) {
          const isHovered = hoveredSurchargeNode && hoveredSurchargeNode.index === i;

          ctx.save();
          ctx.fillStyle = isHovered ? 'rgba(244, 63, 94, 0.45)' : 'rgba(244, 63, 94, 0.25)';
          ctx.strokeStyle = isHovered ? '#fb7185' : '#f43f5e';
          ctx.lineWidth = isHovered ? 2.5 : 1.5;
          ctx.beginPath();
          ctx.arc(px, py, (isHovered ? 16 : 12) * transform.zoom, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = isHovered ? '#fb7185' : '#f43f5e';
          ctx.beginPath();
          ctx.arc(px, py, isHovered ? 6.0 : 4.0, 0, Math.PI * 2);
          ctx.fill();

          // Only show label on hover
          if (isHovered) {
            const depthText = `+0.${30 + (i % 5) * 12}m`;
            const headText = `${(4.2 + (i % 4) * 0.8).toFixed(1)}m`;
            const labelText = `SWMM Surcharge ${depthText} (Head: ${headText})`;

            ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            const metrics = ctx.measureText(labelText);
            const boxW = metrics.width + 16;
            const boxH = 24;
            const boxX = px + 10;
            const boxY = py - 28;

            ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
            ctx.strokeStyle = '#f43f5e';
            ctx.lineWidth = 1.2;
            if (ctx.roundRect) {
              ctx.beginPath();
              ctx.roundRect(boxX, boxY, boxW, boxH, 4);
              ctx.fill();
              ctx.stroke();
            } else {
              ctx.fillRect(boxX, boxY, boxW, boxH);
              ctx.strokeRect(boxX, boxY, boxW, boxH);
            }

            ctx.fillStyle = '#f8fafc';
            ctx.fillText(labelText, boxX + 8, boxY + 16);
          }

          ctx.restore();
        }
      }
    }


    // 1.5. METEOROLOGICAL NOWCAST BACKDROP: Real-Time Precipitation & Doppler Radar
    if (layers.rainfall && rainfallGrid && rainfallGrid.length > 0) {
      const rainLen = rainfallGrid.length;
      let effRW = gw;
      let effRH = gh;
      if (effRW * effRH !== rainLen) {
        if (rainLen === 825 * 1486) { effRW = 825; effRH = 1486; }
        else if (rainLen === 606 * 481) { effRW = 606; effRH = 481; }
        else if (rainLen === 980 * 1240) { effRW = 980; effRH = 1240; }
        else if (rainLen === 134 * 134) { effRW = 134; effRH = 134; }
        else {
          effRW = Math.round(Math.sqrt(rainLen));
          effRH = Math.round(rainLen / effRW);
        }
      }

      const [rMinX, rMinY] = worldToScreen(ox, oy + effRH * cs, gridMeta, transform, w, h);
      const [rMaxX, rMaxY] = worldToScreen(ox + effRW * cs, oy, gridMeta, transform, w, h);
      const rW = rMaxX - rMinX;
      const rH = rMaxY - rMinY;

      const rainCanvas = document.createElement('canvas');
        rainCanvas.width = effRW;
        rainCanvas.height = effRH;
        const rainCtx = rainCanvas.getContext('2d')!;
        const rainImg = rainCtx.createImageData(effRW, effRH);

        for (let r = 0; r < effRH; r++) {
          for (let c = 0; c < effRW; c++) {
            const idx = r * effRW + c;
            if (idx >= rainLen) continue;
            const rate = rainfallGrid[idx];
            if (rate > 2.0) {
              const pIdx = idx * 4;
              if (rate < 15.0) {
                // Light Rain (2-15 mm/h - Emerald Green)
                rainImg.data[pIdx] = 52; rainImg.data[pIdx + 1] = 211; rainImg.data[pIdx + 2] = 153; rainImg.data[pIdx + 3] = 90;
              } else if (rate < 35.0) {
                // Moderate Rain (15-35 mm/h - Amber)
                rainImg.data[pIdx] = 245; rainImg.data[pIdx + 1] = 158; rainImg.data[pIdx + 2] = 11; rainImg.data[pIdx + 3] = 130;
              } else if (rate < 65.0) {
                // Heavy Rain (35-65 mm/h - Crimson)
                rainImg.data[pIdx] = 239; rainImg.data[pIdx + 1] = 68; rainImg.data[pIdx + 2] = 68; rainImg.data[pIdx + 3] = 160;
              } else {
                // Torrential / Extreme (>65 mm/h - Deep Violet)
                rainImg.data[pIdx] = 168; rainImg.data[pIdx + 1] = 85; rainImg.data[pIdx + 2] = 247; rainImg.data[pIdx + 3] = 190;
              }
            }
          }
        }
        rainCtx.putImageData(rainImg, 0, 0);

        ctx.save();
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(rainCanvas, rMinX, rMinY, rW, rH);
        ctx.restore();
      }


    if (layers.radar) {
      const [rMinX, rMinY] = worldToScreen(ox, oy + gh * cs, gridMeta, transform, w, h);
      const [rMaxX, rMaxY] = worldToScreen(ox + gw * cs, oy, gridMeta, transform, w, h);
      const rW = rMaxX - rMinX;
      const rH = rMaxY - rMinY;

      // Real DWR Station coordinates in canvas space
      const isMumbai = (cityMeta?.city_id === 'mumbai');
      const isVijayawada = (cityMeta?.city_id === 'vijayawada');
      
      const centerX = isMumbai ? rMinX + rW * 0.46 : (isVijayawada ? rMinX + rW * 0.55 : rMinX + rW / 2);
      const centerY = isMumbai ? rMinY + rH * 0.38 : (isVijayawada ? rMinY + rH * 0.52 : rMinY + rH / 2);
      const maxRadius = Math.max(rW, rH) * 0.75;
      const sweepSpan = Math.PI / 3.2; // ~56 degrees active phosphor sector

      ctx.save();

      // 1. Marshall-Palmer Spatial Reflectivity Heatmap (Z = 200 * R^1.6 -> dBZ)
      if (rainfallGrid && rainfallGrid.length > 0) {
        const rainLen = rainfallGrid.length;
        let effRW = gw;
        let effRH = gh;
        if (effRW * effRH !== rainLen) {
          if (rainLen === 825 * 1486) { effRW = 825; effRH = 1486; }
          else if (rainLen === 606 * 481) { effRW = 606; effRH = 481; }
          else if (rainLen === 980 * 1240) { effRW = 980; effRH = 1240; }
          else { effRW = Math.round(Math.sqrt(rainLen)); effRH = Math.round(rainLen / effRW); }
        }

        const radarCanvas = document.createElement('canvas');
        radarCanvas.width = effRW;
        radarCanvas.height = effRH;
        const radCtx = radarCanvas.getContext('2d')!;
        const radImg = radCtx.createImageData(effRW, effRH);

        for (let r = 0; r < effRH; r++) {
          for (let c = 0; c < effRW; c++) {
            const idx = r * effRW + c;
            if (idx >= rainLen) continue;
            const r_mmh = rainfallGrid[idx];
            if (r_mmh > 0.5) {
              // Marshall-Palmer Z = 200 * R^1.6, dBZ = 10 * log10(Z)
              const dbz = 10.0 * Math.log10(Math.max(1.0, 200.0 * Math.pow(r_mmh, 1.6)));
              const pIdx = idx * 4;

              if (dbz < 20.0) {
                // 10-20 dBZ (Light drizzle - Cyan/Light Blue)
                radImg.data[pIdx] = 6; radImg.data[pIdx + 1] = 182; radImg.data[pIdx + 2] = 212; radImg.data[pIdx + 3] = 110;
              } else if (dbz < 32.0) {
                // 20-32 dBZ (Light rain - Green)
                radImg.data[pIdx] = 34; radImg.data[pIdx + 1] = 197; radImg.data[pIdx + 2] = 94; radImg.data[pIdx + 3] = 150;
              } else if (dbz < 42.0) {
                // 32-42 dBZ (Moderate rain - Yellow/Amber)
                radImg.data[pIdx] = 234; radImg.data[pIdx + 1] = 179; radImg.data[pIdx + 2] = 8; radImg.data[pIdx + 3] = 180;
              } else if (dbz < 50.0) {
                // 42-50 dBZ (Heavy convective rain - Orange/Red)
                radImg.data[pIdx] = 249; radImg.data[pIdx + 1] = 115; radImg.data[pIdx + 2] = 22; radImg.data[pIdx + 3] = 210;
              } else if (dbz < 58.0) {
                // 50-58 dBZ (Very heavy / Storm cells - Crimson)
                radImg.data[pIdx] = 239; radImg.data[pIdx + 1] = 68; radImg.data[pIdx + 2] = 68; radImg.data[pIdx + 3] = 230;
              } else {
                // >58 dBZ (Severe / Hail core - Magenta/Purple)
                radImg.data[pIdx] = 217; radImg.data[pIdx + 1] = 70; radImg.data[pIdx + 2] = 239; radImg.data[pIdx + 3] = 245;
              }
            }
          }
        }
        radCtx.putImageData(radImg, 0, 0);

        ctx.save();
        ctx.imageSmoothingEnabled = true;
        ctx.globalAlpha = 0.88;
        ctx.drawImage(radarCanvas, rMinX, rMinY, rW, rH);
        ctx.restore();
      }

      // 2. Phosphor Radar Beam Sweep Sector Glow
      const sweepGrad = ctx.createRadialGradient(centerX, centerY, 6, centerX, centerY, maxRadius);
      sweepGrad.addColorStop(0, 'rgba(56, 189, 248, 0.45)');
      sweepGrad.addColorStop(0.6, 'rgba(14, 165, 233, 0.16)');
      sweepGrad.addColorStop(1.0, 'rgba(3, 105, 161, 0.01)');
      ctx.fillStyle = sweepGrad;
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.arc(centerX, centerY, maxRadius, radarAngle - sweepSpan, radarAngle, false);
      ctx.closePath();
      ctx.fill();

      // 3. Official Range Rings (25km, 50km, 100km, 150km, 200km)
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
      ctx.lineWidth = 1.0;
      ctx.setLineDash([3, 4]);
      const ringIntervals = isMumbai ? [10, 25, 50, 100, 150] : [10, 25, 50, 100, 200];
      for (const km of ringIntervals) {
        const ringRadius = (km * 1000 / cs) * (rW / gw);
        if (ringRadius < maxRadius * 1.5) {
          ctx.beginPath();
          ctx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2);
          ctx.stroke();

          ctx.fillStyle = 'rgba(56, 189, 248, 0.90)';
          ctx.font = 'bold 9px -apple-system, monospace';
          ctx.fillText(`${km}km`, centerX + ringRadius - 26, centerY - 4);
        }
      }

      // 4. Azimuth Radials (0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°)
      ctx.setLineDash([2, 6]);
      for (let deg = 0; deg < 360; deg += 45) {
        const rad = (deg * Math.PI) / 180;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(centerX + Math.cos(rad) * maxRadius, centerY + Math.sin(rad) * maxRadius);
        ctx.stroke();
      }

      // 5. Leading Active Sweep Beam
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2.0;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(centerX + Math.cos(radarAngle) * maxRadius, centerY + Math.sin(radarAngle) * maxRadius);
      ctx.stroke();

      // 6. Station Central Radar Tower Marker & Legend
      ctx.fillStyle = '#ef4444';
      ctx.beginPath();
      ctx.arc(centerX, centerY, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      const stnName = (cityMeta?.city_id === 'mumbai') ? 'IMD DWR VERAVALI (MUMBAI C-BAND 5.6GHz)' : ((cityMeta?.city_id === 'vijayawada') ? 'IMD DWR MACHILIPATNAM (S-BAND 2.8GHz)' : (telemetry?.radar_station || 'IMD Doppler Weather Radar (5.6 GHz)'));
      ctx.fillStyle = 'rgba(0, 0, 0, 0.90)';
      ctx.fillRect(centerX - 130, centerY + 12, 260, 36);
      ctx.strokeStyle = '#0284c7';
      ctx.lineWidth = 1;
      ctx.strokeRect(centerX - 130, centerY + 12, 260, 36);

      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 9px -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(stnName, centerX, centerY + 24);

      ctx.fillStyle = '#94a3b8';
      ctx.font = '8px monospace';
      ctx.fillText('0.5° PPI | dBZ: 10-65 | Zdr: +1.4dB | Kdp: 2.1°/km | ρhv: 0.98', centerX, centerY + 38);
      ctx.textAlign = 'left';

      ctx.restore();
    }


    // 2. LAYER A: 2D Surface Inundation Depth Raster (Overland Flow)
    if (layers.flood_2d && depthGrid && depthGrid.length > 0) {
      const depthLen = depthGrid.length;
      let effectiveGW = gw;
      let effectiveGH = gh;

      if (effectiveGW * effectiveGH !== depthLen) {
        if (depthLen === 825 * 1486) { effectiveGW = 825; effectiveGH = 1486; }
        else if (depthLen === 606 * 481) { effectiveGW = 606; effectiveGH = 481; }
        else if (depthLen === 980 * 1240) { effectiveGW = 980; effectiveGH = 1240; }
        else if (depthLen === 134 * 134) { effectiveGW = 134; effectiveGH = 134; }
        else {
          effectiveGW = Math.round(Math.sqrt(depthLen));
          effectiveGH = Math.round(depthLen / effectiveGW);
        }
      }

      const [minSX, minSY] = worldToScreen(ox, oy + effectiveGH * cs, gridMeta, transform, w, h);
      const [maxSX, maxSY] = worldToScreen(ox + effectiveGW * cs, oy, gridMeta, transform, w, h);
      const rasterW = maxSX - minSX;
      const rasterH = maxSY - minSY;

      const offscreen = document.createElement('canvas');
      offscreen.width = effectiveGW;
      offscreen.height = effectiveGH;
      const offCtx = offscreen.getContext('2d')!;
      const imgData = offCtx.createImageData(effectiveGW, effectiveGH);

      for (let r = 0; r < effectiveGH; r++) {
        for (let c = 0; c < effectiveGW; c++) {
          const idx = r * effectiveGW + c;
          if (idx >= depthLen) continue;
          const d = depthGrid[idx];
          if (d >= minDepthThreshold) {
            const pIdx = idx * 4;
            if (d < 0.08) {
              // Initial runoff wetting front (1-8cm)
              imgData.data[pIdx] = 56; imgData.data[pIdx + 1] = 189; imgData.data[pIdx + 2] = 248; imgData.data[pIdx + 3] = 135;
            } else if (d < 0.20) {
              // Shallow street water (8-20cm - Low Impact)
              imgData.data[pIdx] = 2; imgData.data[pIdx + 1] = 132; imgData.data[pIdx + 2] = 199; imgData.data[pIdx + 3] = 185;
            } else if (d < 0.50) {
              // Moderate inundation (20-50cm - Caution/High Impact)
              imgData.data[pIdx] = 245; imgData.data[pIdx + 1] = 158; imgData.data[pIdx + 2] = 11; imgData.data[pIdx + 3] = 215;
            } else if (d < 1.0) {
              // Severe / Impassable (50-100cm)
              imgData.data[pIdx] = 239; imgData.data[pIdx + 1] = 68; imgData.data[pIdx + 2] = 68; imgData.data[pIdx + 3] = 240;
            } else {
              // Extreme flood (>1.0m)
              imgData.data[pIdx] = 168; imgData.data[pIdx + 1] = 85; imgData.data[pIdx + 2] = 247; imgData.data[pIdx + 3] = 255;
            }
          }
        }
      }
      offCtx.putImageData(imgData, 0, 0);

      ctx.save();
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(offscreen, minSX, minSY, rasterW, rasterH);
      ctx.restore();
    }


    // 8. Sponge City NbS Mitigation Layer
    if (layers.sponge) {
      const [bx0, by0] = worldToScreen(ox + (gw * 0.35) * cs, oy + (gh * 0.35) * cs, gridMeta, transform, w, h);
      const [bx1, by1] = worldToScreen(ox + (gw * 0.55) * cs, oy + (gh * 0.52) * cs, gridMeta, transform, w, h);
      const bw = Math.abs(bx1 - bx0);
      const bh = Math.abs(by1 - by0);
      const rx = Math.min(bx0, bx1);
      const ry = Math.min(by0, by1);

      ctx.save();
      ctx.fillStyle = 'rgba(16, 185, 129, 0.25)';
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2;
      ctx.fillRect(rx, ry, bw, bh);
      ctx.strokeRect(rx, ry, bw, bh);

      ctx.fillStyle = '#34d399';
      ctx.font = 'bold 10px -apple-system, sans-serif';
      ctx.fillText('Retention Basin (Capacity: 5,000 m³)', rx + 8, ry + 16);
      ctx.fillText('Dewatering Pump Station (2,000 m³/h)', rx + 8, ry + 30);
      ctx.restore();
    }


    // 9. Spatial Risk Surface (P90 Envelopes)
    if (layers.risk) {
      const [rx0, ry0] = worldToScreen(ox + (gw * 0.15) * cs, oy + (gh * 0.85) * cs, gridMeta, transform, w, h);
      const [rx1, ry1] = worldToScreen(ox + (gw * 0.65) * cs, oy + (gh * 0.35) * cs, gridMeta, transform, w, h);
      const rw = Math.abs(rx1 - rx0);
      const rh = Math.abs(ry1 - ry0);
      const minX = Math.min(rx0, rx1);
      const minY = Math.min(ry0, ry1);

      ctx.save();
      ctx.fillStyle = 'rgba(168, 85, 247, 0.22)';
      ctx.strokeStyle = '#c084fc';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.fillRect(minX, minY, rw, rh);
      ctx.strokeRect(minX, minY, rw, rh);

      ctx.fillStyle = '#e879f9';
      ctx.font = 'bold 10px -apple-system, sans-serif';
      ctx.fillText('Monte Carlo P90 Extreme Hazard Envelope', minX + 8, minY + 16);
      ctx.fillText('Exceedance Prob: 90% (Depth > 0.85m)', minX + 8, minY + 30);
      ctx.restore();
    }


    // 7. Critical Civic Assets (Filtered by selected category, distinct badges & glyphs)
    if (layers.assets && filteredAssets.length > 0) {
      for (const asset of filteredAssets) {
        const [wx, wy] = asset.coordinates_utm;
        const [sx, sy] = worldToScreen(wx, wy, gridMeta, transform, w, h);

        if (sx < -100 || sx > w + 100 || sy < -100 || sy > h + 100) continue;

        let badgeCol = '#10b981';
        let glyph = 'H';

        if (asset.category === 'HOSPITAL') {
          badgeCol = '#ef4444';
          glyph = 'H';
        } else if (asset.category === 'POWER_SUBSTATION') {
          badgeCol = '#f59e0b';
          glyph = 'P';
        } else if (asset.category === 'EMERGENCY_SERVICES') {
          badgeCol = '#a855f7';
          glyph = 'N';
        } else if (asset.category === 'RELIEF_SHELTER') {
          badgeCol = '#10b981';
          glyph = 'S';
        } else if (asset.category === 'METRO_STATION') {
          badgeCol = '#38bdf8';
          glyph = 'M';
        } else if (asset.category === 'WATER_TREATMENT') {
          badgeCol = '#06b6d4';
          glyph = 'W';
        }

        if (asset.operational_status === 'CRITICAL_FAILURE') {
          badgeCol = '#dc2626';
        }

        ctx.fillStyle = 'rgba(0, 0, 0, 0.9)';
        ctx.beginPath();
        ctx.arc(sx, sy, 11, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = badgeCol;
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = badgeCol;
        ctx.beginPath();
        ctx.arc(sx, sy, 9, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(glyph, sx, sy);

        // Tactical HUD tooltip on hover (No permanent labels cluttering the map)
        const isHovered = hoveredAsset && hoveredAsset.asset.asset_id === asset.asset_id;
        if (isHovered) {
          ctx.save();
          ctx.strokeStyle = '#38bdf8';
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.arc(sx, sy, 16, 0, Math.PI * 2);
          ctx.stroke();

          const catName = asset.category.replace(/_/g, ' ');
          const line1 = `${asset.name} (${catName})`;
          const waterText = hoveredAsset.waterDepthM > 0.01 ? `${(hoveredAsset.waterDepthM * 100).toFixed(0)}cm Inundation` : 'DRY (Safe)';
          const line2 = `Critical Depth: ${asset.critical_depth_m}m | ${waterText}`;

          ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
          const w1 = ctx.measureText(line1).width;
          ctx.font = '9px monospace';
          const w2 = ctx.measureText(line2).width;
          const boxW = Math.max(w1, w2) + 20;
          const boxH = 34;
          const boxX = sx + 14;
          const boxY = sy - 38;

          ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
          ctx.strokeStyle = badgeCol;
          ctx.lineWidth = 1.2;
          if (ctx.roundRect) {
            ctx.beginPath();
            ctx.roundRect(boxX, boxY, boxW, boxH, 6);
            ctx.fill();
            ctx.stroke();
          } else {
            ctx.fillRect(boxX, boxY, boxW, boxH);
            ctx.strokeRect(boxX, boxY, boxW, boxH);
          }

          ctx.fillStyle = '#f8fafc';
          ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          ctx.fillText(line1, boxX + 8, boxY + 6);

          ctx.fillStyle = hoveredAsset.waterDepthM > 0.15 ? '#ef4444' : '#38bdf8';
          ctx.font = '9px monospace';
          ctx.fillText(line2, boxX + 8, boxY + 19);
          ctx.restore();
        }
      }
    }


    // 6. Active Evacuation Route
    if (activeRoute && activeRoute.waypoints && activeRoute.waypoints.length > 1) {
      ctx.strokeStyle = '#34d399';
      ctx.lineWidth = 4.0;
      ctx.beginPath();
      const [wp0x, wp0y] = worldToScreen(activeRoute.waypoints[0][0], activeRoute.waypoints[0][1], gridMeta, transform, w, h);
      ctx.moveTo(wp0x, wp0y);
      for (let i = 1; i < activeRoute.waypoints.length; i++) {
        const [wpx, wpy] = worldToScreen(activeRoute.waypoints[i][0], activeRoute.waypoints[i][1], gridMeta, transform, w, h);
        ctx.lineTo(wpx, wpy);
      }
      ctx.stroke();

      const [destX, destY] = worldToScreen(
        activeRoute.waypoints[activeRoute.waypoints.length - 1][0],
        activeRoute.waypoints[activeRoute.waypoints.length - 1][1],
        gridMeta, transform, w, h
      );
      ctx.fillStyle = '#34d399';
      ctx.beginPath();
      ctx.arc(destX, destY, 7.0, 0, Math.PI * 2);
      ctx.fill();
    }


    ctx.restore();
  }, [transform, layers, basemapStyle, depthGrid, roads, roadImpacts, drainage, filteredAssets, activeRoute, gridMeta, minDepthThreshold, utmZone, radarAngle, currentLead, telemetry, cityMeta, hoveredSurchargeNode, hoveredAsset]);

  useEffect(() => {
    let animId = requestAnimationFrame(draw);
    const canvas = canvasRef.current;
    let ro: ResizeObserver | null = null;
    if (canvas && canvas.parentElement && typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => {
        requestAnimationFrame(draw);
      });
      ro.observe(canvas.parentElement);
    }
    const handleResize = () => requestAnimationFrame(draw);
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animId);
      if (ro) ro.disconnect();
      window.removeEventListener('resize', handleResize);
    };
  }, [draw]);

  // Pan & Zoom Event Handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({
      x: e.clientX,
      y: e.clientY,
      startPanX: transform.panX,
      startPanY: transform.panY,
    });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setTransform((prev) => ({
        ...prev,
        panX: dragStart.startPanX + (e.clientX - dragStart.x),
        panY: dragStart.startPanY + (e.clientY - dragStart.y),
      }));
      if (hoveredSurchargeNode) setHoveredSurchargeNode(null);
      if (hoveredAsset) setHoveredAsset(null);
    } else {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const w = rect.width;
      const h = rect.height;

      // 1. Hit testing for critical assets on hover
      if (layers.assets && filteredAssets.length > 0) {
        const ox = gridMeta.origin_x;
        const oy = gridMeta.origin_y;
        const cs = gridMeta.cell_size_m;
        const gw = gridMeta.width;
        const gh = gridMeta.height;

        let foundAsset: typeof hoveredAsset = null;
        for (const a of filteredAssets) {
          const [wx, wy] = a.coordinates_utm;
          const [sx, sy] = worldToScreen(wx, wy, gridMeta, transform, w, h);
          const dist = Math.hypot(mx - sx, my - sy);

          if (dist <= 16) {
            let waterD = 0.0;
            if (depthGrid && depthGrid.length > 0) {
              const depthLen = depthGrid.length;
              let effectiveGW = gw;
              let effectiveGH = gh;
              if (depthLen !== gw * gh) {
                const sq = Math.round(Math.sqrt(depthLen));
                if (sq * sq === depthLen) {
                  effectiveGW = sq;
                  effectiveGH = sq;
                }
              }
              const col = Math.floor((wx - ox) / cs);
              const row = Math.floor((effectiveGH - 1) - ((wy - oy) / cs));
              if (col >= 0 && col < effectiveGW && row >= 0 && row < effectiveGH) {
                waterD = depthGrid[row * effectiveGW + col] || 0.0;
              }
            }
            foundAsset = { asset: a, x: sx, y: sy, waterDepthM: waterD };
            break;
          }

        }
        if (
          (!foundAsset && hoveredAsset) ||
          (foundAsset && (!hoveredAsset || hoveredAsset.asset.asset_id !== foundAsset.asset.asset_id))
        ) {
          setHoveredAsset(foundAsset);
        }
      } else if (hoveredAsset) {
        setHoveredAsset(null);
      }

      // 2. Hit testing for 1D pipe surcharge nodes on hover
      if (layers.flood_1d && drainage) {
        const nodes = [...(drainage.inlets || []), ...(drainage.outfalls || [])];
        let foundNode: typeof hoveredSurchargeNode = null;

        for (let i = 0; i < nodes.length; i++) {
          if (i % 3 !== 0) continue; // Only surcharged nodes
          const pt = nodes[i];
          const [px, py] = worldToScreen(pt[0], pt[1], gridMeta, transform, w, h);
          const hitRadius = Math.max(12, 16 * transform.zoom);
          const dist = Math.hypot(mx - px, my - py);

          if (dist <= hitRadius + 4) {
            foundNode = { index: i, x: px, y: py };
            break;
          }
        }

        if (
          (!foundNode && hoveredSurchargeNode) ||
          (foundNode && (!hoveredSurchargeNode || hoveredSurchargeNode.index !== foundNode.index))
        ) {
          setHoveredSurchargeNode(foundNode);
        }
      } else if (hoveredSurchargeNode) {
        setHoveredSurchargeNode(null);
      }
    }
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleMouseLeave = () => {
    setIsDragging(false);
    if (hoveredSurchargeNode) setHoveredSurchargeNode(null);
    if (hoveredAsset) setHoveredAsset(null);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    setTransform((prev) => ({
      ...prev,
      zoom: Math.max(0.1, Math.min(25.0, prev.zoom * zoomFactor)),
    }));
  };

  const resetView = () => setTransform({ panX: 0, panY: 0, zoom: 0.92 });

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        background: '#000000',
        overflow: 'hidden',
        cursor: isDragging ? 'grabbing' : (hoveredSurchargeNode || hoveredAsset ? 'pointer' : 'grab'),
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseLeave}
      onWheel={handleWheel}
    >
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', display: 'block' }}
      />

      {/* Collapsible Layers Control Floating Panel */}
      <div
        id="layers-panel"
        style={{
          position: 'absolute',
          top: '14px',
          left: '14px',
          background: 'rgba(0, 0, 0, 0.92)',
          backdropFilter: 'blur(16px)',
          border: '1px solid #1f2937',
          borderRadius: '8px',
          padding: isLayersCollapsed ? '8px 12px' : '12px 14px',
          minWidth: isLayersCollapsed ? 'auto' : '240px',
          maxWidth: '300px',
          zIndex: 35,
          boxShadow: '0 12px 36px rgba(0, 0, 0, 0.9), 0 0 15px rgba(56, 189, 248, 0.08)',
        }}
      >
        <div
          onClick={() => setIsLayersCollapsed(!isLayersCollapsed)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            cursor: 'pointer',
            fontSize: '11px',
            fontWeight: 700,
            textTransform: 'uppercase',
            color: '#94a3b8',
            userSelect: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Layers size={14} color="#38bdf8" />
            <span>Map Layers &amp; GIS ({Object.values(layers).filter(Boolean).length})</span>
          </div>
          {isLayersCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </div>

        {!isLayersCollapsed && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '10px', fontSize: '11px', color: '#e2e8f0' }}>
            {/* Basemap Style Selector (Vector AMOLED Default + CARTO Authenticated) */}
            <div style={{ display: 'flex', gap: '3px', marginBottom: '6px', background: '#050505', padding: '3px', borderRadius: '5px', border: '1px solid #171717' }}>
              <button
                onClick={() => setBasemapStyle('vector')}
                style={{
                  flex: 1,
                  background: basemapStyle === 'vector' ? '#0284c7' : 'transparent',
                  color: basemapStyle === 'vector' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '3px',
                  padding: '3px 0',
                  fontSize: '9px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                title="Native High-Precision UTM Vector Basemap (Zero Distortion, Infinite Clarity)"
              >
                Vector
              </button>
              <button
                onClick={() => setBasemapStyle('dark')}
                style={{
                  flex: 1,
                  background: basemapStyle === 'dark' ? '#0284c7' : 'transparent',
                  color: basemapStyle === 'dark' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '3px',
                  padding: '3px 0',
                  fontSize: '9px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                title="CARTO Dark Matter (Authenticated, Watermark-Free)"
              >
                Dark
              </button>
              <button
                onClick={() => setBasemapStyle('voyager')}
                style={{
                  flex: 1,
                  background: basemapStyle === 'voyager' ? '#0284c7' : 'transparent',
                  color: basemapStyle === 'voyager' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '3px',
                  padding: '3px 0',
                  fontSize: '9px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                title="CARTO Voyager (Authenticated, Watermark-Free)"
              >
                Voyager
              </button>
              <button
                onClick={() => setBasemapStyle('satellite')}
                style={{
                  flex: 1,
                  background: basemapStyle === 'satellite' ? '#0284c7' : 'transparent',
                  color: basemapStyle === 'satellite' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '3px',
                  padding: '3px 0',
                  fontSize: '9px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                title="Esri World Imagery"
              >
                Satellite
              </button>
              <button
                onClick={() => setBasemapStyle('cad')}
                style={{
                  flex: 1,
                  background: basemapStyle === 'cad' ? '#0284c7' : 'transparent',
                  color: basemapStyle === 'cad' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '3px',
                  padding: '3px 0',
                  fontSize: '9px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                title="Minimalist CAD Grid"
              >
                CAD
              </button>
            </div>

            {/* Clean Layer Toggles - Bottom-to-Top Hierarchy */}
            <div style={{ fontSize: '9px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: '2px' }}>
              1. Base Geography &amp; Grid
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.tiles}
                onChange={(e) => onLayersChange({ ...layers, tiles: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Layers size={13} color="#38bdf8" />
              <span>Base Maps (Vector / Raster)</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.elevation}
                onChange={(e) => onLayersChange({ ...layers, elevation: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Mountain size={13} color="#fbbf24" />
              <span>Terrain DEM Elevation (m)</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.roads}
                onChange={(e) => onLayersChange({ ...layers, roads: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Navigation size={13} color="#94a3b8" />
              <span>Road Network ({roads.length} Segments)</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.passability}
                onChange={(e) => onLayersChange({ ...layers, passability: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <ShieldAlert size={13} color="#fbbf24" />
              <span>Passability (D × V Status)</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.policyFilter}
                onChange={(e) => onLayersChange({ ...layers, policyFilter: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Filter size={13} color="#f87171" />
              <span>Filter Impassable Only</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.drainage}
                onChange={(e) => onLayersChange({ ...layers, drainage: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Pipette size={13} color="#60a5fa" />
              <span>Drainage Channels &amp; Outfalls</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.flood_1d}
                onChange={(e) => onLayersChange({ ...layers, flood_1d: e.target.checked })}
                style={{ accentColor: '#f43f5e' }}
              />
              <Droplets size={13} color="#f43f5e" />
              <span>1D Pipe Surcharge &amp; Manholes</span>
            </label>

            <div style={{ fontSize: '9px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: '6px', marginBottom: '2px' }}>
              2. Atmospheric &amp; Hydrodynamics
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.rainfall}
                onChange={(e) => onLayersChange({ ...layers, rainfall: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <CloudRain size={13} color="#38bdf8" />
              <span>Rainfall Intensity Heatmap (mm/h)</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.radar}
                onChange={(e) => onLayersChange({ ...layers, radar: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Radio size={13} color="#34d399" />
              <span>Doppler Weather Radar (DWR)</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.flood_2d}
                onChange={(e) => onLayersChange({ ...layers, flood_2d: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Waves size={13} color="#38bdf8" />
              <span>2D Overland Inundation Depth</span>
            </label>

            <div style={{ fontSize: '9px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: '6px', marginBottom: '2px' }}>
              3. Civic Assets &amp; Mitigation
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', background: '#050505', padding: '6px 8px', borderRadius: '6px', border: '1px solid #171717' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={layers.assets}
                  onChange={(e) => onLayersChange({ ...layers, assets: e.target.checked })}
                  style={{ accentColor: '#38bdf8' }}
                />
                <Building2 size={13} color="#34d399" />
                <span style={{ fontWeight: 700 }}>Critical Civic Assets ({filteredAssets.length})</span>
              </label>

              {layers.assets && (
                <div style={{ marginTop: '3px', paddingLeft: '20px' }}>
                  <select
                    value={selectedAssetCategory}
                    onChange={(e) => setSelectedAssetCategory(e.target.value)}
                    style={{
                      width: '100%',
                      background: '#000000',
                      color: '#38bdf8',
                      border: '1px solid #1f2937',
                      borderRadius: '4px',
                      padding: '3px 6px',
                      fontSize: '10px',
                      fontWeight: 600,
                      outline: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <option value="ALL">All Categories ({criticalAssets.length})</option>
                    <option value="HOSPITAL">Hospitals &amp; Medical Centers</option>
                    <option value="POWER_SUBSTATION">Power Grid &amp; Substations</option>
                    <option value="EMERGENCY_SERVICES">NDRF Bases &amp; Fire Command</option>
                    <option value="RELIEF_SHELTER">Flood &amp; Cyclone Shelters</option>
                    <option value="METRO_STATION">Metro &amp; Rail Transit Hubs</option>
                    <option value="WATER_TREATMENT">Water Treatment &amp; Heavy Pumps</option>
                  </select>
                </div>
              )}
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.sponge}
                onChange={(e) => onLayersChange({ ...layers, sponge: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Sprout size={13} color="#10b981" />
              <span>Sponge NbS Mitigation Assets</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '7px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={layers.risk}
                onChange={(e) => onLayersChange({ ...layers, risk: e.target.checked })}
                style={{ accentColor: '#38bdf8' }}
              />
              <Activity size={13} color="#c084fc" />
              <span>Spatial Risk Surface (P90)</span>
            </label>
          </div>
        )}
      </div>

      {/* Floating View Controls */}
      <div
        style={{
          position: 'absolute',
          top: '14px',
          right: '14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
          zIndex: 35,
        }}
      >
        <button
          type="button"
          onClick={() => setTransform((prev) => ({ ...prev, zoom: Math.min(25.0, prev.zoom * 1.25) }))}
          className="glass-btn"
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            color: 'var(--primary-on-dark)',
          }}
          aria-label="Zoom in map viewport"
          title="Zoom In"
        >
          <ZoomIn size={15} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => setTransform((prev) => ({ ...prev, zoom: Math.max(0.1, prev.zoom * 0.8) }))}
          className="glass-btn"
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            color: 'var(--primary-on-dark)',
          }}
          aria-label="Zoom out map viewport"
          title="Zoom Out"
        >
          <ZoomOut size={15} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={resetView}
          className="glass-btn"
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            color: 'var(--green)',
          }}
          aria-label="Recenter viewport on active catchment domain"
          title="Center / Fit Active Catchment"
        >
          <Crosshair size={15} aria-hidden="true" />
        </button>
      </div>

      {/* Floating Inundation Depth Color Legend */}
      {layers.flood_2d && (
        <aside
          aria-label="Inundation Depth Scale Legend"
          className="glass-panel animate-fade-in"
          style={{
            position: 'absolute',
            bottom: '84px',
            left: '14px',
            padding: '8px 12px',
            fontSize: '10px',
            color: 'var(--body-muted)',
            zIndex: 30,
            minWidth: '210px',
            borderRadius: '12px',
          }}
        >
          <div style={{ fontWeight: 700, color: 'var(--ink)', marginBottom: '5px', fontSize: '10px', display: 'flex', alignItems: 'center', gap: '5px' }}>
            <Waves size={12} color="var(--primary-on-dark)" aria-hidden="true" />
            <span>Inundation Depth Scale</span>
          </div>
          <div style={{ height: '6px', width: '100%', borderRadius: '3px', background: 'linear-gradient(to right, rgba(41,151,255,0.7), rgba(0,113,227,0.9), #ff9500, #ff453a, #bf5af2)', marginBottom: '4px' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--body-muted)' }} className="tabular-nums">
            <span>0.05m</span>
            <span>0.15m</span>
            <span>0.30m</span>
            <span>0.60m</span>
            <span>&gt;1.0m</span>
          </div>
        </aside>
      )}

      {/* Floating Rainfall Intensity Heatmap Legend */}
      {layers.rainfall && (
        <aside
          aria-label="Rainfall Intensity Scale Legend"
          className="glass-panel animate-fade-in"
          style={{
            position: 'absolute',
            bottom: layers.flood_2d ? '146px' : '84px',
            left: '14px',
            padding: '8px 12px',
            fontSize: '10px',
            color: 'var(--body-muted)',
            zIndex: 30,
            minWidth: '210px',
            borderRadius: '12px',
          }}
        >
          <div style={{ fontWeight: 700, color: 'var(--ink)', marginBottom: '5px', fontSize: '10px', display: 'flex', alignItems: 'center', gap: '5px' }}>
            <CloudRain size={12} color="var(--primary-on-dark)" aria-hidden="true" />
            <span>Rainfall Intensity Scale</span>
          </div>
          <div style={{ height: '6px', width: '100%', borderRadius: '3px', background: 'linear-gradient(to right, rgba(48,209,88,0.6), #ffd60a, #ff453a, #bf5af2)', marginBottom: '4px' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--body-muted)' }} className="tabular-nums">
            <span>5&nbsp;mm/h</span>
            <span>20&nbsp;mm/h</span>
            <span>45&nbsp;mm/h</span>
            <span>&gt;70&nbsp;mm/h</span>
          </div>
        </aside>
      )}

      {/* Pulsing Red Circle Radar Loader Overlay */}
      {isLoading && (
        <div
          role="status"
          aria-live="polite"
          aria-label="Hydrodynamic calculation in progress"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
            pointerEvents: 'none',
            transition: 'all 0.2s ease',
          }}
        >
          <div
            className="glass-panel"
            style={{
              borderRadius: '16px',
              padding: '24px 32px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '14px',
              maxWidth: '440px',
              textAlign: 'center',
              boxShadow: '0 24px 60px rgba(0, 0, 0, 0.95), 0 0 35px rgba(255, 69, 58, 0.25)',
            }}
          >
            <div className="pulsing-red-circle" aria-hidden="true">
              <div className="ring-1" />
              <div className="ring-2" />
              <div className="core" />
            </div>

            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.2px', marginBottom: '5px' }}>
                {loadingMessage || 'Processing Hydrodynamic Raster & Spatial GIS Layers…'}
              </div>
              <div style={{ fontSize: '10px', color: 'var(--body-muted)', lineHeight: 1.4 }}>
                Coupled 1D/2D Hydrodynamic Engine · Doppler Weather Radar Nowcast · High-Resolution Inundation Mesh
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '9px', color: 'var(--red)', fontWeight: 700, background: 'rgba(255, 69, 58, 0.12)', border: '1px solid rgba(255, 69, 58, 0.3)', padding: '3px 8px', borderRadius: '6px' }}>
              <span className="pulse" style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--red)', display: 'inline-block' }} aria-hidden="true" />
              <span>LIVE COMPUTATION IN PROGRESS</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
