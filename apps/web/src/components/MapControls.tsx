import React, { useState } from 'react';
import {
  Layers,
  ZoomIn,
  ZoomOut,
  Crosshair,
  Compass,
  Waves,
  Droplets,
  CloudRain,
  Radio,
  ShieldAlert,
  Pipette,
  Building2,
  Mountain,
  Sprout,
  Activity,
  X,
} from 'lucide-react';
import { LayerState, CriticalAssetItem } from '../types';

interface MapControlsProps {
  layers: LayerState;
  onLayersChange: (layers: LayerState) => void;
  basemapStyle: 'vector' | 'dark' | 'voyager' | 'satellite' | 'cad';
  onBasemapChange: (style: 'vector' | 'dark' | 'voyager' | 'satellite' | 'cad') => void;
  roadsCount: number;
  criticalAssets: CriticalAssetItem[];
  selectedAssetCategory: string;
  onSelectAssetCategory: (cat: string) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetView: () => void;
}

export const MapControls: React.FC<MapControlsProps> = ({
  layers,
  onLayersChange,
  basemapStyle,
  onBasemapChange,
  roadsCount,
  criticalAssets,
  selectedAssetCategory,
  onSelectAssetCategory,
  onZoomIn,
  onZoomOut,
  onResetView,
}) => {
  const [showLayersSheet, setShowLayersSheet] = useState<boolean>(false);

  const activeLayerCount = Object.values(layers).filter(Boolean).length;

  return (
    <aside
      aria-label="Map Navigation & Layer Overlay Palette"
      style={{
        position: 'absolute',
        top: '64px',
        right: '16px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: '8px',
        zIndex: 35,
        pointerEvents: 'auto',
      }}
    >
      {/* Floating Vertical Control Stack */}
      <div
        className="glass-panel"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px',
          padding: '4px',
          borderRadius: '14px',
        }}
      >
        {/* Layers Sheet Toggle */}
        <button
          type="button"
          onClick={() => setShowLayersSheet(!showLayersSheet)}
          aria-expanded={showLayersSheet}
          aria-label="Toggle GIS map layers and basemap overlay drawer"
          className="glass-btn"
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            background: showLayersSheet ? 'rgba(0, 113, 227, 0.35)' : 'transparent',
            borderColor: showLayersSheet ? 'var(--primary-on-dark)' : 'transparent',
            position: 'relative',
          }}
          title="Map Layers & GIS Overlay Sheet"
        >
          <Layers size={16} color={showLayersSheet ? 'var(--primary-on-dark)' : 'var(--ink)'} aria-hidden="true" />
          <span
            style={{
              position: 'absolute',
              top: '2px',
              right: '2px',
              background: 'var(--primary-focus)',
              color: '#ffffff',
              fontSize: '8px',
              fontWeight: 800,
              width: '14px',
              height: '14px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            className="tabular-nums"
          >
            {activeLayerCount}
          </span>
        </button>

        <div style={{ width: '20px', height: '1px', background: 'var(--hairline-soft)' }} />

        {/* Center / Fit Catchment */}
        <button
          type="button"
          onClick={onResetView}
          aria-label="Recenter camera on active catchment domain"
          className="glass-btn"
          style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'transparent', border: 'none' }}
          title="Center / Fit Catchment"
        >
          <Crosshair size={16} color="var(--green)" aria-hidden="true" />
        </button>

        {/* Compass / North Align */}
        <button
          type="button"
          onClick={onResetView}
          aria-label="Reset map bearing and align to true north"
          className="glass-btn"
          style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'transparent', border: 'none' }}
          title="Align North"
        >
          <Compass size={16} color="var(--primary-on-dark)" aria-hidden="true" />
        </button>

        <div style={{ width: '20px', height: '1px', background: 'var(--hairline-soft)' }} />

        {/* Zoom Controls */}
        <button
          type="button"
          onClick={onZoomIn}
          aria-label="Zoom in map view"
          className="glass-btn"
          style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'transparent', border: 'none' }}
          title="Zoom In"
        >
          <ZoomIn size={16} color="var(--ink)" aria-hidden="true" />
        </button>

        <button
          type="button"
          onClick={onZoomOut}
          aria-label="Zoom out map view"
          className="glass-btn"
          style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'transparent', border: 'none' }}
          title="Zoom Out"
        >
          <ZoomOut size={16} color="var(--ink)" aria-hidden="true" />
        </button>
      </div>

      {/* Apple Maps Style Floating Layers & Basemap Popover Sheet */}
      {showLayersSheet && (
        <div
          className="glass-panel animate-fade-in"
          style={{
            position: 'absolute',
            top: '0px',
            right: '48px',
            width: '280px',
            padding: '14px',
            borderRadius: '16px',
            zIndex: 45,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 700, color: 'var(--ink)' }}>
              <Layers size={14} color="var(--primary-on-dark)" aria-hidden="true" />
              <span>Map Layers &amp; Basemap</span>
            </div>
            <button
              type="button"
              onClick={() => setShowLayersSheet(false)}
              aria-label="Close layers overlay sheet"
              style={{ background: 'transparent', border: 'none', color: 'var(--body-muted)', cursor: 'pointer' }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>

          {/* Basemap Segmented Pill Selector */}
          <div style={{ marginBottom: '12px' }}>
            <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--body-muted)', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: '6px' }}>
              Basemap Style
            </div>
            <div style={{ display: 'flex', gap: '2px', background: 'rgba(30, 30, 32, 0.85)', padding: '2px', borderRadius: '8px', border: '1px solid var(--hairline-soft)' }}>
              {(['vector', 'dark', 'voyager', 'satellite', 'cad'] as const).map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => onBasemapChange(b)}
                  aria-pressed={basemapStyle === b}
                  style={{
                    flex: 1,
                    background: basemapStyle === b ? 'var(--primary-focus)' : 'transparent',
                    color: basemapStyle === b ? '#ffffff' : 'var(--body-muted)',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '4px 0',
                    fontSize: '10px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {b === 'vector' ? 'Vector' : b === 'dark' ? 'Dark' : b === 'voyager' ? 'Voyager' : b === 'satellite' ? 'Sat' : 'CAD'}
                </button>
              ))}
            </div>
          </div>

          {/* Layer Toggles - Bottom-to-Top Hierarchy */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '11px', color: 'var(--ink)' }}>
            <div style={{ fontSize: '9px', fontWeight: 700, color: 'var(--body-muted)', textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: '2px' }}>
              1. Base Geography &amp; Grid
            </div>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.elevation ? 'rgba(251, 191, 36, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Mountain size={13} color="var(--amber)" aria-hidden="true" />
                <span>DEM Elevation Contours</span>
              </div>
              <input
                type="checkbox"
                checked={layers.elevation}
                onChange={(e) => onLayersChange({ ...layers, elevation: e.target.checked })}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.roads ? 'rgba(56, 189, 248, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Compass size={13} color="var(--primary-on-dark)" aria-hidden="true" />
                <span>Road Network ({roadsCount} Segments)</span>
              </div>
              <input
                type="checkbox"
                checked={layers.roads}
                onChange={(e) => onLayersChange({ ...layers, roads: e.target.checked })}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.passability ? 'rgba(255, 214, 10, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <ShieldAlert size={13} color="var(--amber)" aria-hidden="true" />
                <span>Passability (D × V Status)</span>
              </div>
              <input
                type="checkbox"
                checked={layers.passability}
                onChange={(e) => onLayersChange({ ...layers, passability: e.target.checked })}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.drainage ? 'rgba(100, 210, 255, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Pipette size={13} color="var(--cyan)" aria-hidden="true" />
                <span>Drainage Channels &amp; Outfalls</span>
              </div>
              <input
                type="checkbox"
                checked={layers.drainage}
                onChange={(e) => onLayersChange({ ...layers, drainage: e.target.checked })}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.flood_1d ? 'rgba(255, 69, 58, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Droplets size={13} color="var(--red)" aria-hidden="true" />
                <span>1D Pipe Surcharging</span>
              </div>
              <input
                type="checkbox"
                checked={layers.flood_1d}
                onChange={(e) => onLayersChange({ ...layers, flood_1d: e.target.checked })}
              />
            </label>

            <div style={{ fontSize: '9px', fontWeight: 700, color: 'var(--body-muted)', textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: '6px' }}>
              2. Atmospheric &amp; Hydrodynamics
            </div>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.rainfall ? 'rgba(41, 151, 255, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CloudRain size={13} color="var(--primary-on-dark)" aria-hidden="true" />
                <span>Rainfall Intensity Heatmap</span>
              </div>
              <input
                type="checkbox"
                checked={layers.rainfall}
                onChange={(e) => onLayersChange({ ...layers, rainfall: e.target.checked })}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.radar ? 'rgba(48, 209, 88, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Radio size={13} color="var(--green)" aria-hidden="true" />
                <span>Doppler Weather Radar (DWR)</span>
              </div>
              <input
                type="checkbox"
                checked={layers.radar}
                onChange={(e) => onLayersChange({ ...layers, radar: e.target.checked })}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px', background: layers.flood_2d ? 'rgba(41, 151, 255, 0.12)' : 'transparent' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Waves size={13} color="var(--primary-on-dark)" aria-hidden="true" />
                <span>2D Overland Inundation</span>
              </div>
              <input
                type="checkbox"
                checked={layers.flood_2d}
                onChange={(e) => onLayersChange({ ...layers, flood_2d: e.target.checked })}
              />
            </label>

            <div style={{ fontSize: '9px', fontWeight: 700, color: 'var(--body-muted)', textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: '6px' }}>
              3. Civic Assets &amp; Mitigation
            </div>

            {/* Critical Assets Filter */}
            <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 8px', borderRadius: '8px', border: '1px solid var(--hairline-soft)' }}>
              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', marginBottom: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Building2 size={13} color="var(--green)" aria-hidden="true" />
                  <span style={{ fontWeight: 600 }}>Civic Assets ({criticalAssets.length})</span>
                </div>
                <input
                  type="checkbox"
                  checked={layers.assets}
                  onChange={(e) => onLayersChange({ ...layers, assets: e.target.checked })}
                />
              </label>

              {layers.assets && (
                <select
                  aria-label="Filter civic assets by category"
                  value={selectedAssetCategory}
                  onChange={(e) => onSelectAssetCategory(e.target.value)}
                  style={{
                    width: '100%',
                    background: '#1c1c1e',
                    color: 'var(--primary-on-dark)',
                    border: '1px solid var(--hairline)',
                    borderRadius: '4px',
                    padding: '3px 6px',
                    fontSize: '10px',
                    fontWeight: 600,
                    outline: 'none',
                    cursor: 'pointer',
                  }}
                >
                  <option value="ALL">All Categories</option>
                  <option value="HOSPITAL">Hospitals &amp; Medical</option>
                  <option value="POWER_SUBSTATION">Power Substations</option>
                  <option value="EMERGENCY_SERVICES">NDRF &amp; Fire Command</option>
                  <option value="RELIEF_SHELTER">Cyclone Shelters</option>
                  <option value="METRO_STATION">Metro &amp; Rail Transit</option>
                  <option value="WATER_TREATMENT">Water Treatment</option>
                </select>
              )}
            </div>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Sprout size={13} color="var(--green)" aria-hidden="true" />
                <span>Sponge NbS Assets</span>
              </div>
              <input
                type="checkbox"
                checked={layers.sponge}
                onChange={(e) => onLayersChange({ ...layers, sponge: e.target.checked })}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '4px 8px', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Activity size={13} color="var(--purple)" aria-hidden="true" />
                <span>Spatial Risk (P90)</span>
              </div>
              <input
                type="checkbox"
                checked={layers.risk}
                onChange={(e) => onLayersChange({ ...layers, risk: e.target.checked })}
              />
            </label>
          </div>
        </div>
      )}
    </aside>
  );
};

