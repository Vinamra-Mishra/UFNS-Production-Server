import React, { useState, useEffect } from 'react';
import { CityId, CityMetadata, LiveTelemetry } from '../types';
import { Radio, CloudRain, Waves, MapPin, Maximize2, Minimize2, Thermometer, ShieldCheck } from 'lucide-react';
import { WeatherWidget } from './WeatherWidget';

interface NavbarProps {
  activeCity: CityId;
  onCityChange: (city: CityId) => void;
  cityMeta: CityMetadata | null;
  telemetry: LiveTelemetry | null;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeCity,
  onCityChange,
  cityMeta,
  telemetry,
}) => {
  const [showWeather, setShowWeather] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  const w = telemetry?.weather || {};
  const temp = w.temperature_c ?? telemetry?.temp_c ?? 28.0;

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };


  return (
    <header
      role="banner"
      style={{
        height: '52px',
        background: 'rgba(18, 18, 22, 0.88)',
        backdropFilter: 'blur(24px) saturate(190%)',
        WebkitBackdropFilter: 'blur(24px) saturate(190%)',
        borderBottom: '1px solid var(--hairline)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 18px',
        zIndex: 50,
        position: 'relative',
      }}
    >
      {/* Brand & Project Identity */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
            color: '#ffffff',
            fontWeight: 800,
            fontSize: '13px',
            padding: '4px 10px',
            borderRadius: '10px',
            letterSpacing: '0.4px',
            boxShadow: '0 2px 10px rgba(37, 99, 235, 0.4)',
          }}
          aria-hidden="true"
        >
          UFNS
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: '13px', color: 'var(--ink)', letterSpacing: '-0.2px', whiteSpace: 'nowrap' }}>
            Urban Flood Nowcasting System
          </div>
          <div style={{ fontSize: '10px', color: 'var(--body-muted)', letterSpacing: '-0.1px', whiteSpace: 'nowrap' }}>
            Coupled 1D/2D Hydrodynamics &amp; Radar Nowcasting · SIH26085
          </div>
        </div>
      </div>

      {/* Center City Switcher & Live Feeds */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        {/* One UI Segmented City Selector Pill */}
        <div
          className="glass-pill"
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '4px 12px',
            gap: '8px',
            background: 'rgba(32, 32, 40, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
          }}
        >
          <MapPin size={13} color="var(--primary-on-dark)" aria-hidden="true" />
          <label htmlFor="city-selector" className="sr-only">
            Select Urban Catchment
          </label>
          <select
            id="city-selector"
            aria-label="Select Urban Catchment Basin"
            value={activeCity}
            onChange={(e) => onCityChange(e.target.value as CityId)}
            style={{
              background: 'transparent',
              color: 'var(--primary-on-dark)',
              border: 'none',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
              outline: 'none',
              padding: '2px 0',
            }}
          >
            <option value="MUMBAI" style={{ background: '#1c1c1e', color: '#ffffff' }}>
              Mumbai Metropolitan (Operational Real Data)
            </option>
            <option value="VIJAYAWADA" style={{ background: '#1c1c1e', color: '#ffffff' }}>
              Vijayawada Urban (Krishna Basin Real Data)
            </option>
            <option value="DEMO" style={{ background: '#1c1c1e', color: '#ffffff' }}>
              Synthetic Basin Pilot (M5–M11 Calibrated Baseline)
            </option>
          </select>
        </div>

        {/* Live Weather / Marine Badges */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Weather Widget Trigger Button */}
          <button
            type="button"
            onClick={() => setShowWeather(!showWeather)}
            aria-expanded={showWeather}
            aria-label="Toggle live meteorological telemetry panel"
            className="chip-btn"
            style={{
              background: showWeather ? 'rgba(37, 99, 235, 0.3)' : 'rgba(36, 36, 44, 0.75)',
              borderColor: showWeather ? 'var(--primary-on-dark)' : 'var(--hairline-soft)',
              color: showWeather ? '#ffffff' : 'var(--ink)',
              padding: '5px 12px',
              borderRadius: '9999px',
            }}
            title="Real-Time Meteorological & Satellite Telemetry"
          >
            <Thermometer size={12} color="var(--primary-on-dark)" aria-hidden="true" />
            <span className="tabular-nums">{temp.toFixed(1)}&nbsp;°C {w.condition || 'Clear'}</span>
          </button>

          {/* Doppler Radar Status Pill */}
          <div
            className="chip-btn"
            style={{
              color: !telemetry ? 'var(--body-muted)' : telemetry.radar_status === 'OFFLINE' ? 'var(--red)' : 'var(--green)',
              borderColor: !telemetry ? 'var(--hairline-soft)' : telemetry.radar_status === 'OFFLINE' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)',
              background: telemetry?.radar_status === 'OFFLINE' ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)',
              cursor: 'default',
              padding: '5px 12px',
              borderRadius: '9999px',
            }}
          >
            <Radio size={11} aria-hidden="true" />
            <span>Radar: {telemetry ? telemetry.radar_status || 'ONLINE' : 'UNKNOWN'}</span>
          </div>

          {/* Rainfall Intensity Pill */}
          <div
            className="chip-btn"
            style={{
              color: telemetry?.precip_rate_mmh != null ? 'var(--cyan)' : 'var(--body-muted)',
              borderColor: telemetry?.precip_rate_mmh != null ? 'rgba(6, 182, 212, 0.3)' : 'var(--hairline-soft)',
              background: telemetry?.precip_rate_mmh != null ? 'rgba(6, 182, 212, 0.12)' : 'rgba(36, 36, 44, 0.75)',
              cursor: 'default',
              padding: '5px 12px',
              borderRadius: '9999px',
            }}
          >
            <CloudRain size={11} aria-hidden="true" />
            <span className="tabular-nums">
              Rain: {telemetry?.precip_rate_mmh != null ? `${telemetry.precip_rate_mmh.toFixed(1)} mm/h` : '--'}
            </span>
          </div>

          {/* Tide Level Pill */}
          <div
            className="chip-btn"
            style={{
              color: telemetry?.tide_level_m != null ? 'var(--primary-on-dark)' : 'var(--body-muted)',
              borderColor: telemetry?.tide_level_m != null ? 'rgba(59, 130, 246, 0.3)' : 'var(--hairline-soft)',
              background: telemetry?.tide_level_m != null ? 'rgba(59, 130, 246, 0.12)' : 'rgba(36, 36, 44, 0.75)',
              cursor: 'default',
              padding: '5px 12px',
              borderRadius: '9999px',
            }}
          >
            <Waves size={11} aria-hidden="true" />
            <span className="tabular-nums">
              Tide: {telemetry?.tide_level_m != null ? (telemetry.tide_level_m > 0 ? `+${telemetry.tide_level_m.toFixed(2)}m` : `${telemetry.tide_level_m.toFixed(2)}m`) : '--'}
            </span>
          </div>

        </div>
      </div>

      {/* Right Certification Provenance Badges */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          className="chip-btn"
          style={{
            background: 'rgba(16, 185, 129, 0.12)',
            color: 'var(--green)',
            borderColor: 'rgba(16, 185, 129, 0.3)',
            fontSize: '10px',
            fontWeight: 700,
            cursor: 'default',
            padding: '4px 10px',
            borderRadius: '9999px',
          }}
        >
          <ShieldCheck size={12} aria-hidden="true" />
          <span>PROVISIONAL_SIMULATED</span>
        </span>

        <button
          type="button"
          onClick={toggleFullscreen}
          className="glass-btn"
          style={{
            width: '30px',
            height: '30px',
            borderRadius: '8px',
            color: 'var(--body-muted)',
            marginLeft: '4px',
          }}
          aria-label={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
          title={isFullscreen ? 'Exit Fullscreen (Esc)' : 'Enter Fullscreen'}
        >
          {isFullscreen ? <Minimize2 size={13} aria-hidden="true" /> : <Maximize2 size={13} aria-hidden="true" />}
        </button>
      </div>

      {/* Popover Real-Time Weather Widget */}
      {showWeather && (
        <div style={{ position: 'absolute', top: '52px', right: '16px', zIndex: 100 }}>
          <WeatherWidget telemetry={telemetry} onClose={() => setShowWeather(false)} />
        </div>
      )}
    </header>
  );
};
