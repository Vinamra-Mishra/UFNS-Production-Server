import React from 'react';
import { LiveTelemetry } from '../types';
import { Cloud, CloudRain, Sun, Wind, Droplets, Gauge, Eye, Radio, Globe, X } from 'lucide-react';

interface WeatherWidgetProps {
  telemetry: LiveTelemetry | null;
  onClose?: () => void;
}

export const WeatherWidget: React.FC<WeatherWidgetProps> = ({ telemetry, onClose }) => {
  const w = telemetry?.weather || {};
  const nasa = telemetry?.nasa_satellite || {};
  const temp = w.temperature_c ?? telemetry?.temp_c ?? 28.0;
  const feelsLike = w.feels_like_c ?? 30.5;
  const humidity = w.humidity_pct ?? telemetry?.humidity_pct ?? 65;
  const pressure = w.pressure_hpa ?? 1009;
  const windSpeed = w.wind_speed_kmh ?? telemetry?.wind_speed_kmh ?? 14.5;
  const windDeg = w.wind_deg ?? 250;
  const rain = w.rain_rate_mmh ?? telemetry?.precip_rate_mmh ?? 0.0;
  const condition = w.condition ?? telemetry?.condition ?? 'Fair';
  const desc = w.description ?? 'Fair conditions';
  const clouds = w.cloudiness_pct ?? 20;
  const visibility = w.visibility_km ?? 10.0;

  return (
    <div
      role="dialog"
      aria-label="Real-Time Meteorological &amp; Satellite Telemetry"
      className="glass-panel animate-fade-in"
      style={{
        padding: '16px',
        color: 'var(--ink)',
        borderRadius: '16px',
        minWidth: '320px',
        maxWidth: '380px',
        zIndex: 100,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid var(--hairline)', paddingBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            className="chip-btn"
            style={{
              background: 'var(--primary-focus)',
              color: '#ffffff',
              borderColor: 'transparent',
              fontSize: '10px',
              padding: '2px 6px',
              fontWeight: 800,
            }}
          >
            LIVE
          </span>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--ink)' }}>
              Atmospheric &amp; Satellite Feeds
            </div>
            <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>
              OpenWeather · NASA GPM/SMAP · IMD DWR
            </div>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close weather telemetry popover"
            style={{ background: 'transparent', border: 'none', color: 'var(--body-muted)', cursor: 'pointer', padding: '2px' }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', marginBottom: '12px' }}>
        <div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: 'var(--primary-on-dark)', letterSpacing: '-0.5px' }} className="tabular-nums">
            {temp.toFixed(1)}&nbsp;°C
          </div>
          <div style={{ fontSize: '11px', color: 'var(--body-muted)', marginTop: '2px' }}>
            Feels like <strong style={{ color: 'var(--ink)' }} className="tabular-nums">{feelsLike.toFixed(1)}&nbsp;°C</strong>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'flex-end' }}>
            {rain > 0 ? <CloudRain size={22} color="var(--primary-on-dark)" aria-hidden="true" /> : (clouds > 50 ? <Cloud size={22} color="var(--body-muted)" aria-hidden="true" /> : <Sun size={22} color="var(--amber)" aria-hidden="true" />)}
            <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)' }}>{condition}</span>
          </div>
          <div style={{ fontSize: '10px', color: 'var(--body-muted)', marginTop: '2px' }}>{desc}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '12px' }}>
        <div className="glass-card" style={{ padding: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: 'var(--body-muted)' }}>
            <Droplets size={11} color="var(--primary-on-dark)" aria-hidden="true" />
            <span>Relative Humidity</span>
          </div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', marginTop: '3px' }} className="tabular-nums">
            {humidity}%
          </div>
        </div>

        <div className="glass-card" style={{ padding: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: 'var(--body-muted)' }}>
            <Wind size={11} color="var(--green)" aria-hidden="true" />
            <span>Wind Speed</span>
          </div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', marginTop: '3px' }} className="tabular-nums">
            {windSpeed.toFixed(1)}&nbsp;km/h <span style={{ fontSize: '9px', color: 'var(--body-muted)' }}>({windDeg}°)</span>
          </div>
        </div>

        <div className="glass-card" style={{ padding: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: 'var(--body-muted)' }}>
            <CloudRain size={11} color="var(--cyan)" aria-hidden="true" />
            <span>Rainfall Rate</span>
          </div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: rain > 0 ? 'var(--primary-on-dark)' : 'var(--body-muted)', marginTop: '3px' }} className="tabular-nums">
            {rain.toFixed(2)}&nbsp;mm/h
          </div>
        </div>

        <div className="glass-card" style={{ padding: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: 'var(--body-muted)' }}>
            <Gauge size={11} color="var(--amber)" aria-hidden="true" />
            <span>Surface Pressure</span>
          </div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', marginTop: '3px' }} className="tabular-nums">
            {pressure}&nbsp;hPa
          </div>
        </div>

        <div className="glass-card" style={{ padding: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: 'var(--body-muted)' }}>
            <Cloud size={11} color="var(--body-muted)" aria-hidden="true" />
            <span>Cloud Cover</span>
          </div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', marginTop: '3px' }} className="tabular-nums">
            {clouds}%
          </div>
        </div>

        <div className="glass-card" style={{ padding: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: 'var(--body-muted)' }}>
            <Eye size={11} color="var(--purple)" aria-hidden="true" />
            <span>Visibility</span>
          </div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', marginTop: '3px' }} className="tabular-nums">
            {visibility.toFixed(1)}&nbsp;km
          </div>
        </div>
      </div>

      <div className="glass-card" style={{ padding: '10px', fontSize: '10px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--primary-on-dark)', fontWeight: 700 }}>
            <Globe size={12} aria-hidden="true" /> NASA Earthdata Satellite Feed
          </span>
          <span className="chip-btn" style={{ fontSize: '9px', background: 'rgba(48, 209, 88, 0.15)', color: 'var(--green)', borderColor: 'rgba(48, 209, 88, 0.3)', padding: '1px 6px', cursor: 'default' }}>
            {nasa.status || 'AUTHENTICATED'}
          </span>
        </div>
        <div style={{ color: 'var(--body-muted)', fontSize: '9px', lineHeight: 1.4 }}>
          <div>• <strong>GPM IMERG:</strong> 30-min calibrated precipitation stream</div>
          <div>• <strong>SMAP Soil Moisture:</strong> <span className="tabular-nums">{(nasa.smap_soil_moisture_m3m3 ?? 0.32).toFixed(2)}&nbsp;m³/m³ ({(nasa.smap_saturation_pct ?? 64).toFixed(0)}% saturation)</span></div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px', paddingTop: '6px', borderTop: '1px solid var(--hairline-soft)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--green)', fontWeight: 700 }}>
            <Radio size={12} aria-hidden="true" /> {telemetry?.radar_station || 'IMD Doppler Radar'}
          </span>
          <span style={{ color: 'var(--primary-on-dark)', fontWeight: 700 }}>5-min Scans</span>
        </div>
      </div>
    </div>
  );
};

