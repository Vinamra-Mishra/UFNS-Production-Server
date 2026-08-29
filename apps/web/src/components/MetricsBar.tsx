import React from 'react';
import { MetricsSummary } from '../types';

interface MetricsBarProps {
  metrics: MetricsSummary;
}

export const MetricsBar: React.FC<MetricsBarProps> = ({ metrics }) => {
  const peakDepth = metrics?.peak_depth_m ?? 0;
  const depthColor = peakDepth > 0.5 ? 'var(--red)' : peakDepth > 0.2 ? 'var(--amber)' : 'var(--green)';

  return (
    <section
      id="metrics-strip"
      aria-label="Real-Time Hydrodynamic Telemetry & Road Network Indicators"
      style={{
        background: 'rgba(20, 20, 22, 0.85)',
        backdropFilter: 'blur(24px) saturate(190%)',
        WebkitBackdropFilter: 'blur(24px) saturate(190%)',
        borderTop: '1px solid var(--hairline)',
        padding: '6px 16px',
        display: 'flex',
        gap: '8px',
        overflowX: 'auto',
        alignItems: 'center',
        zIndex: 40,
      }}
    >
      {/* Lead Time Card */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '85px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Lead Time
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--primary-on-dark)' }} className="tabular-nums">
          T+{metrics?.lead_minutes ?? 0}m
        </div>
      </div>

      {/* Rainfall Intensity Card */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '95px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Rainfall Rate
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--green)' }} className="tabular-nums">
          {(metrics?.rainfall_rate_mmh ?? 0).toFixed(1)}&nbsp;<span style={{ fontSize: '10px', fontWeight: 500, color: 'var(--ink-muted-48)' }}>mm/h</span>
        </div>
      </div>

      {/* Peak Depth Card */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '90px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Peak Depth
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: depthColor }} className="tabular-nums">
          {(metrics?.peak_depth_m ?? 0).toFixed(2)}&nbsp;<span style={{ fontSize: '10px', fontWeight: 500, color: 'var(--ink-muted-48)' }}>m</span>
        </div>
      </div>

      {/* Flooded Area Card */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '100px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Flooded Area
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--amber)' }} className="tabular-nums">
          {((metrics?.flooded_area_m2 ?? 0) / 10000).toFixed(1)}&nbsp;<span style={{ fontSize: '10px', fontWeight: 500, color: 'var(--ink-muted-48)' }}>ha</span>
        </div>
      </div>

      {/* Dry Roads Count */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '85px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Dry Roads
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink-muted-80)' }} className="tabular-nums">
          {metrics?.dry_roads_count ?? 0}
        </div>
      </div>

      {/* Passable Roads Count */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '85px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Passable
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--green)' }} className="tabular-nums">
          {metrics?.passable_roads_count ?? 0}
        </div>
      </div>

      {/* Impassable Roads Count */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '95px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Impassable
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: (metrics?.impassable_roads_count ?? 0) > 0 ? 'var(--red)' : 'var(--body-muted)' }} className="tabular-nums">
          {metrics?.impassable_roads_count ?? 0}
        </div>
      </div>

      {/* Surcharged Manholes */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '90px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Surcharged
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: (metrics?.surcharged_nodes_count ?? 0) > 0 ? 'var(--amber)' : 'var(--body-muted)' }} className="tabular-nums">
          {metrics?.surcharged_nodes_count ?? 0}
        </div>
      </div>

      {/* Storage Volume */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '100px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Storage Vol
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--primary-on-dark)' }} className="tabular-nums">
          {((metrics?.storage_volume_m3 ?? 0) / 1000).toFixed(1)}&nbsp;<span style={{ fontSize: '10px', fontWeight: 500, color: 'var(--ink-muted-48)' }}>k&nbsp;m³</span>
        </div>
      </div>

      {/* Outfall Discharge */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '95px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Outfall Q
        </div>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--cyan)' }} className="tabular-nums">
          {(metrics?.outfall_q_m3s ?? 0).toFixed(2)}&nbsp;<span style={{ fontSize: '10px', fontWeight: 500, color: 'var(--ink-muted-48)' }}>m³/s</span>
        </div>
      </div>

      {/* Active Model */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '130px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Active Model
        </div>
        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--purple)', whiteSpace: 'nowrap' }}>
          {metrics?.active_model || 'Hydrodynamic (2D)'}
        </div>
      </div>

      {/* Dataset Source */}
      <div className="glass-card" style={{ padding: '4px 10px', minWidth: '135px', textAlign: 'center' }}>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Dataset Source
        </div>
        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--green)', whiteSpace: 'nowrap' }}>
          {metrics?.dataset_source || 'REAL_OBSERVED'}
        </div>
      </div>
    </section>
  );
};

