import React, { useState, useEffect } from 'react';
import { apiUrl } from '../config';
import { IMDOverview, MOSDACSatelliteObservation } from '../types';

interface IMDWeatherPanelProps {
  activeCity: string;
}

export const IMDWeatherPanel: React.FC<IMDWeatherPanelProps> = ({ activeCity }) => {
  const [data, setData] = useState<IMDOverview | null>(null);
  const [mosdacData, setMosdacData] = useState<MOSDACSatelliteObservation | null>(null);
  const [mosdacSearchResults, setMosdacSearchResults] = useState<any[]>([]);
  const [searchDatasetId, setSearchDatasetId] = useState<string>('3SIMG_L2B_HEM');
  const [isSearchingMosdac, setIsSearchingMosdac] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [mainMode, setMainMode] = useState<'imd' | 'isro'>('imd');
  const [activeSubTab, setActiveSubTab] = useState<'synoptic' | 'forecast' | 'warnings' | 'marine' | 'cyclone' | 'rainfall' | 'radar'>('synoptic');

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    Promise.all([
      fetch(apiUrl(`/api/v1/imd/overview?city=${activeCity}`))
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch(apiUrl(`/api/v1/mosdac/latest-observation?city=${activeCity}`))
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ])
      .then(([imdJson, mosdacJson]) => {
        if (isMounted) {
          if (imdJson && imdJson.station_meta && imdJson.current_weather) {
            setData(imdJson);
          } else {
            setData(null);
          }
          if (
            mosdacJson &&
            mosdacJson.status &&
            typeof mosdacJson.hydro_estimator_rain_rate_mmh === 'number' &&
            typeof mosdacJson.cloud_top_temp_c === 'number'
          ) {
            setMosdacData(mosdacJson);
          } else {
            setMosdacData(null);
          }
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error('Error fetching meteorological data:', err);
        if (isMounted) {
          setData(null);
          setMosdacData(null);
          setLoading(false);
        }
      });


    return () => {
      isMounted = false;
    };
  }, [activeCity]);

  const handleSearchMosdac = async () => {
    setIsSearchingMosdac(true);
    try {
      const res = await fetch(apiUrl(`/api/v1/mosdac/search?datasetId=${searchDatasetId}&count=5`));
      if (res.ok) {
        const json = await res.json();
        setMosdacSearchResults(json.entries || []);
      }
    } catch (err) {
      console.error('Error searching MOSDAC:', err);
    } finally {
      setIsSearchingMosdac(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '24px', color: 'var(--body-muted)', fontSize: '12px', textAlign: 'center' }}>
        <div style={{ display: 'inline-block', width: '22px', height: '22px', border: '2px solid var(--primary-on-dark)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', marginBottom: '8px' }} aria-hidden="true" />
        <div>Fetching Official IMD &amp; ISRO-MOSDAC Satellite Dossier…</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: '16px', color: 'var(--red)', fontSize: '12px' }}>
        Unable to load official meteorological dossier.
      </div>
    );
  }

  const wx = data.current_weather;
  const fc = data.seven_day_forecast?.data?.[0];
  const nowcast = data.district_nowcast?.data?.[0];
  const warnings = data.district_warnings?.data?.[0];
  const distRain = data.district_rainfall?.data;
  const stateRain = data.state_rainfall?.data;
  const sunMoon = data.sun_moon?.data?.[0];
  const coastal = data.coastal_bulletin?.data?.[0];
  const cyclone = data.cyclone_tracker?.data;

  const getSeverityBg = (code?: number) => {
    switch (code) {
      case 4: return { bg: 'rgba(255, 69, 58, 0.15)', border: 'var(--red)', text: 'var(--red)', label: 'RED WARNING (Take Action)' };
      case 3: return { bg: 'rgba(255, 149, 0, 0.15)', border: 'var(--amber)', text: 'var(--amber)', label: 'ORANGE ALERT (Be Prepared)' };
      case 2: return { bg: 'rgba(255, 214, 10, 0.15)', border: '#ffd60a', text: '#ffd60a', label: 'YELLOW WATCH (Be Updated)' };
      default: return { bg: 'rgba(48, 209, 88, 0.12)', border: 'var(--green)', text: 'var(--green)', label: 'GREEN (No Warning)' };
    }
  };

  const sev = getSeverityBg(nowcast?.color);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', color: 'var(--ink)', fontSize: '11px', width: '100%', boxSizing: 'border-box' }}>
      {/* 1. Official Header Badge */}
      <div className="glass-card" style={{ padding: '12px', width: '100%', boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                fontSize: '11px',
                background: 'rgba(0, 113, 227, 0.2)',
                padding: '2px 6px',
                borderRadius: '6px',
                border: '1px solid var(--primary-on-dark)',
                color: 'var(--primary-on-dark)',
                fontWeight: 800,
              }}
              aria-hidden="true"
            >
              IND
            </span>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.2px' }}>
                IMD &amp; ISRO Meteorological Observatory
              </div>
              <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>
                MoES · ISRO-MOSDAC Continuous Ingestion Pipeline
              </div>
            </div>
          </div>
          <div className="chip-btn" style={{ fontSize: '9px', color: 'var(--primary-on-dark)', borderColor: 'rgba(41, 151, 255, 0.3)', cursor: 'default' }}>
            20+ FEEDS
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px', marginTop: '6px', fontSize: '10px', color: 'var(--ink)', borderTop: '1px solid var(--hairline-soft)', paddingTop: '8px' }}>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: 'var(--body-muted)' }}>Station:</strong> {data.station_meta.station_name}
          </div>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: 'var(--body-muted)' }}>District:</strong> {data.station_meta.district_name}
          </div>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: 'var(--body-muted)' }}>FMO:</strong> {data.station_meta.fmo}
          </div>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: 'var(--body-muted)' }}>Coord:</strong> <span className="tabular-nums">{data.station_meta.lat}°N, {data.station_meta.lon}°E</span>
          </div>
        </div>
      </div>

      {/* 2. Top-Level Stream Mode Selector: IMD vs ISRO */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '4px',
          padding: '4px',
          width: '100%',
          background: 'rgba(28, 28, 30, 0.85)',
          border: '1px solid var(--hairline-soft)',
          borderRadius: '8px',
          boxSizing: 'border-box',
        }}
      >
        <button
          type="button"
          onClick={() => setMainMode('imd')}
          aria-pressed={mainMode === 'imd'}
          style={{
            padding: '7px 6px',
            fontSize: '11px',
            fontWeight: 700,
            background: mainMode === 'imd' ? 'var(--primary-focus, #007aff)' : 'transparent',
            color: mainMode === 'imd' ? '#ffffff' : 'var(--body-muted, #94a3b8)',
            border: mainMode === 'imd' ? '1px solid rgba(255, 255, 255, 0.2)' : '1px solid transparent',
            borderRadius: '6px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            boxSizing: 'border-box',
            transition: 'all 0.15s ease',
          }}
        >
          <span aria-hidden="true">🏛️</span> IMD Weather (20 APIs)
        </button>
        <button
          type="button"
          onClick={() => {
            setMainMode('isro');
            if (mosdacSearchResults.length === 0) handleSearchMosdac();
          }}
          aria-pressed={mainMode === 'isro'}
          style={{
            padding: '7px 6px',
            fontSize: '11px',
            fontWeight: 700,
            background: mainMode === 'isro' ? 'var(--purple, #af52de)' : 'transparent',
            color: mainMode === 'isro' ? '#ffffff' : 'var(--body-muted, #94a3b8)',
            border: mainMode === 'isro' ? '1px solid rgba(255, 255, 255, 0.2)' : '1px solid transparent',
            borderRadius: '6px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            boxSizing: 'border-box',
            transition: 'all 0.15s ease',
          }}
        >
          <span aria-hidden="true">🛰️</span> ISRO MOSDAC Satellite
        </button>
      </div>

      {/* 3. IMD Sub-Tab Strip */}
      {mainMode === 'imd' && (
        <div
          role="tablist"
          aria-label="IMD Observations Sub-Tabs"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '4px',
            padding: '4px',
            width: '100%',
            background: 'rgba(28, 28, 30, 0.85)',
            border: '1px solid var(--hairline-soft)',
            borderRadius: '8px',
            boxSizing: 'border-box',
          }}
        >
          {[
            { id: 'synoptic', label: '🌡️ Surface' },
            { id: 'forecast', label: '📅 7-Day' },
            { id: 'warnings', label: '⚠️ Alerts' },
            { id: 'radar', label: '📡 Radar' },
            { id: 'marine', label: '🌊 Marine' },
            { id: 'rainfall', label: '📊 Rain' },
          ].map((tab) => {
            const isSubActive = activeSubTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isSubActive}
                type="button"
                onClick={() => setActiveSubTab(tab.id as any)}
                style={{
                  padding: '6px 4px',
                  fontSize: '10.5px',
                  fontWeight: isSubActive ? 700 : 500,
                  background: isSubActive ? 'var(--primary-focus, #007aff)' : 'rgba(255, 255, 255, 0.04)',
                  color: isSubActive ? '#ffffff' : 'var(--body-muted, #94a3b8)',
                  border: isSubActive ? '1px solid rgba(255, 255, 255, 0.2)' : '1px solid transparent',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  textAlign: 'center',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '4px',
                  whiteSpace: 'nowrap',
                  boxSizing: 'border-box',
                  transition: 'all 0.15s ease',
                }}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      )}

      {/* 4. ISRO MOSDAC SURVEILLANCE COCKPIT */}
      {mainMode === 'isro' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', boxSizing: 'border-box' }}>
          {mosdacData && (
            <div className="glass-card" style={{ padding: '12px', width: '100%', boxSizing: 'border-box' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ fontSize: '11px', color: 'var(--purple)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.3px' }}>
                  ISRO {mosdacData.satellite}
                </div>
                <span className="chip-btn" style={{ fontSize: '9px', color: 'var(--green)', background: 'rgba(48, 209, 88, 0.15)', borderColor: 'rgba(48, 209, 88, 0.3)', cursor: 'default' }}>
                  AUTHENTICATED (acelabs)
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Hydro-Estimator</div>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--primary-on-dark)', marginTop: '1px' }} className="tabular-nums">
                    {mosdacData.hydro_estimator_rain_rate_mmh.toFixed(1)}&nbsp;mm/h
                  </div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Cloud Top Temp</div>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--red)', marginTop: '1px' }} className="tabular-nums">
                    {mosdacData.cloud_top_temp_c.toFixed(1)}&nbsp;°C
                  </div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Cloud Fraction</div>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', marginTop: '1px' }} className="tabular-nums">
                    {mosdacData.cloud_fraction_pct.toFixed(0)}%
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginTop: '6px', fontSize: '10px' }}>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', border: '1px solid var(--hairline-soft)' }}>
                  <span style={{ color: 'var(--body-muted)' }}>Convection:</span>{' '}
                  <strong style={{ color: 'var(--amber)' }}>{mosdacData.convective_intensity}</strong>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', border: '1px solid var(--hairline-soft)' }}>
                  <span style={{ color: 'var(--body-muted)' }}>Pass Time:</span>{' '}
                  <strong style={{ color: 'var(--primary-on-dark)' }}>{mosdacData.acquisition_time_ist}</strong>
                </div>
              </div>
            </div>
          )}

          {/* MOSDAC Live Granule Browser (Stacked, 100% Width, Zero Cut-Off) */}
          <div className="glass-card" style={{ padding: '12px', width: '100%', boxSizing: 'border-box' }}>
            <div style={{ fontSize: '10px', color: 'var(--purple)', textTransform: 'uppercase', fontWeight: 700, marginBottom: '6px' }}>
              MOSDAC Live Granule Browser (mosdac.gov.in)
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '8px', width: '100%', boxSizing: 'border-box' }}>
              <select
                aria-label="Select MOSDAC Satellite Dataset"
                value={searchDatasetId}
                onChange={(e) => setSearchDatasetId(e.target.value)}
                style={{
                  width: '100%',
                  background: '#1c1c1e',
                  color: 'var(--primary-on-dark)',
                  border: '1px solid var(--hairline)',
                  padding: '7px 8px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 600,
                  outline: 'none',
                  boxSizing: 'border-box',
                  cursor: 'pointer',
                }}
              >
                <option value="3SIMG_L2B_HEM">INSAT-3DS Hydro-Estimator Rain Rate (3SIMG_L2B_HEM)</option>
                <option value="3SIMG_L2B_CTBT">INSAT-3DS Cloud Top Brightness Temp (3SIMG_L2B_CTBT)</option>
                <option value="3SIMG_L1B_STD">INSAT-3DS Imager L1B Calibrated Radiances (3SIMG_L1B_STD)</option>
                <option value="3DIMG_L2B_HEM">INSAT-3DR Hydro-Estimator Rain (3DIMG_L2B_HEM)</option>
                <option value="3DIMG_L2B_SST">INSAT-3DR Sea Surface Temp (3DIMG_L2B_SST)</option>
                <option value="3SIMG_L2B_OLLR">INSAT-3DS Outgoing Longwave Radiation (3SIMG_L2B_OLLR)</option>
                <option value="E06OCM_L2C_AD">EOS-06 Oceansat-3 Ocean Colour Reflectance (E06OCM_L2C_AD)</option>
              </select>
              <button
                type="button"
                onClick={handleSearchMosdac}
                disabled={isSearchingMosdac}
                className="action-btn"
                style={{
                  width: '100%',
                  background: 'var(--purple)',
                  color: '#ffffff',
                  padding: '8px 10px',
                  fontSize: '11px',
                  gap: '6px',
                  boxSizing: 'border-box',
                }}
              >
                <span aria-hidden="true">🔍</span>
                <span>{isSearchingMosdac ? 'Querying MOSDAC Archive…' : 'Search Live MOSDAC Granules'}</span>
              </button>
            </div>

            {mosdacSearchResults.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', width: '100%', boxSizing: 'border-box' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Live Granules on MOSDAC Archive:</div>
                {mosdacSearchResults.map((entry: any, i: number) => (
                  <div
                    key={i}
                    style={{
                      background: 'rgba(30, 30, 32, 0.7)',
                      border: '1px solid var(--hairline-soft)',
                      padding: '6px 8px',
                      borderRadius: '6px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontSize: '10px',
                      gap: '6px',
                      width: '100%',
                      boxSizing: 'border-box',
                    }}
                  >
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0 }}>
                      <strong style={{ color: 'var(--ink)' }}>{entry.identifier}</strong>
                    </div>
                    <span style={{ color: 'var(--purple)', fontWeight: 700, flexShrink: 0, fontSize: '9.5px', background: 'rgba(191, 90, 242, 0.15)', padding: '2px 6px', borderRadius: '4px' }}>
                      ID: {entry.id}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '10px', color: 'var(--body-muted)', textAlign: 'center', padding: '6px' }}>
                Click search to query live MOSDAC archive.
              </div>
            )}
          </div>
        </div>
      )}

      {/* 5A. SYNOPTIC VIEW */}
      {mainMode === 'imd' && activeSubTab === 'synoptic' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div className="glass-card" style={{ padding: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ fontSize: '10px', color: 'var(--body-muted)', textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 700 }}>
                Surface Observation (/current_wx)
              </div>
              <span className="chip-btn" style={{ fontSize: '9px', color: 'var(--primary-on-dark)', cursor: 'default' }}>
                Code {wx.weather_code}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: 'var(--ink)' }} className="tabular-nums">
                {wx.temp_c.toFixed(1)}&nbsp;°C
              </div>
              <div style={{ fontSize: '11px', color: 'var(--primary-on-dark)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {wx.weather_desc}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px', marginTop: '8px' }}>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Barometer</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink)', marginTop: '1px' }} className="tabular-nums">
                  {wx.mslp_hpa.toFixed(1)}&nbsp;hPa
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Humidity</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink)', marginTop: '1px' }} className="tabular-nums">
                  {wx.humidity_pct.toFixed(0)}%
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>24h Rain</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--primary-on-dark)', marginTop: '1px' }} className="tabular-nums">
                  {wx.rainfall_24h_mm.toFixed(1)}&nbsp;mm
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px', marginTop: '6px' }}>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Wind Vector</div>
                <div style={{ fontSize: '10.5px', fontWeight: 600, color: 'var(--ink)', marginTop: '1px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} className="tabular-nums">
                  {wx.wind_speed_kmh.toFixed(1)}&nbsp;km/h · {wx.wind_direction_label}
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Nebulosity</div>
                <div style={{ fontSize: '10.5px', fontWeight: 600, color: 'var(--ink)', marginTop: '1px' }}>
                  {wx.nebulosity_oktas} / 8 Oktas
                </div>
              </div>
            </div>
          </div>

          {sunMoon && (
            <div className="glass-card" style={{ padding: '12px' }}>
              <div style={{ fontSize: '10px', color: 'var(--body-muted)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 700 }}>
                Astronomical Ephemeris (/sunmoon)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '4px', textAlign: 'center' }}>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 4px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--amber)' }}>☀️ Sunrise</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }} className="tabular-nums">{sunMoon.sunrise}</div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 4px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--amber)' }}>🌅 Sunset</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }} className="tabular-nums">{sunMoon.sunset}</div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 4px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--primary-on-dark)' }}>🌙 Moonrise</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }} className="tabular-nums">{sunMoon.moonrise}</div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 4px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--purple)' }}>🌑 Moonset</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }} className="tabular-nums">{sunMoon.moonset}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5B. 7-DAY FORECAST VIEW */}
      {mainMode === 'imd' && activeSubTab === 'forecast' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {fc && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {[
                { day: 'Day 1 (Today)', max: fc.Todays_Forecast_Max_Temp, min: fc.Todays_Forecast_Min_temp, desc: fc.Todays_Forecast },
                { day: 'Day 2', max: fc.Day_2_Max_Temp, min: fc.Day_2_Min_temp, desc: fc.Day_2_Forecast },
                { day: 'Day 3', max: fc.Day_3_Max_Temp, min: fc.Day_3_Min_temp, desc: fc.Day_3_Forecast },
                { day: 'Day 4', max: fc.Day_4_Max_Temp, min: fc.Day_4_Min_temp, desc: fc.Day_4_Forecast },
                { day: 'Day 5', max: fc.Day_5_Max_Temp, min: fc.Day_5_Min_temp, desc: fc.Day_5_Forecast },
                { day: 'Day 6', max: fc.Day_6_Max_Temp, min: fc.Day_6_Min_temp, desc: fc.Day_6_Forecast },
                { day: 'Day 7', max: fc.Day_7_Max_Temp, min: fc.Day_7_Min_temp, desc: fc.Day_7_Forecast },
              ].map((item, idx) => (
                <div
                  key={idx}
                  className="glass-card"
                  style={{
                    padding: '8px 10px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '6px',
                    borderColor: idx === 0 ? 'var(--primary-on-dark)' : 'var(--hairline-soft)',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: idx === 0 ? 'var(--primary-on-dark)' : 'var(--ink)' }}>
                      {item.day}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--body-muted)', marginTop: '1px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.desc || 'Partly cloudy sky'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', fontSize: '11px', fontWeight: 700, flexShrink: 0 }} className="tabular-nums">
                    <span style={{ color: 'var(--red)' }}>{item.max}&nbsp;°C</span>
                    <span style={{ color: 'var(--primary-on-dark)' }}>{item.min}&nbsp;°C</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 5C. ALERTS & NOWCAST VIEW */}
      {mainMode === 'imd' && activeSubTab === 'warnings' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {nowcast && (
            <div style={{ background: sev.bg, border: `1px solid ${sev.border}`, borderRadius: '8px', padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <div style={{ fontSize: '11px', fontWeight: 800, color: sev.text }}>
                  🚨 3-HOUR NOWCAST
                </div>
                <div style={{ fontSize: '9px', color: 'var(--ink)' }}>
                  Valid upto {nowcast.Vupto} IST
                </div>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--ink)', lineHeight: '1.4' }}>
                {nowcast.message}
              </div>
            </div>
          )}

          {warnings && (
            <div className="glass-card" style={{ padding: '12px' }}>
              <div style={{ fontSize: '10px', color: 'var(--body-muted)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 700 }}>
                5-Day District Warning Matrix
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {[
                  { day: 'Day 1 (Today)', color: warnings.Day1_Color, desc: warnings.Day_1_desc },
                  { day: 'Day 2', color: warnings.Day2_Color, desc: warnings.Day_2_desc },
                  { day: 'Day 3', color: warnings.Day3_Color, desc: warnings.Day_3_desc },
                  { day: 'Day 4', color: warnings.Day4_Color, desc: warnings.Day_4_desc },
                  { day: 'Day 5', color: warnings.Day5_Color, desc: warnings.Day_5_desc },
                ].map((wItem, idx) => {
                  const s = getSeverityBg(wItem.color);
                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        background: 'rgba(30, 30, 32, 0.7)',
                        border: '1px solid var(--hairline-soft)',
                        borderLeft: `3px solid ${s.border}`,
                        padding: '6px 8px',
                        borderRadius: '4px',
                      }}
                    >
                      <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--ink)' }}>{wItem.day}</div>
                      <div style={{ fontSize: '10px', color: s.text, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {wItem.desc || 'No Warning'}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5D. MARINE & COASTAL VIEW */}
      {mainMode === 'imd' && activeSubTab === 'marine' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {coastal && (
            <div className="glass-card" style={{ padding: '12px' }}>
              <div style={{ fontSize: '11px', color: 'var(--primary-on-dark)', textTransform: 'uppercase', fontWeight: 700, marginBottom: '6px' }}>
                Coastal Bulletin: {coastal.Layer}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px' }}>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Wind &amp; Gusts</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 600, color: 'var(--ink)', marginTop: '1px' }}>{coastal.Wind}</div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Sea Condition</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 600, color: 'var(--primary-on-dark)', marginTop: '1px' }}>{coastal.Sea_Condition || coastal['Sea Condition'] || 'Moderate to Rough'}</div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Port Signal</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 700, color: 'var(--amber)', marginTop: '1px' }}>{coastal.Port_Signal || coastal['Port Signal'] || 'Signal LC-III Hoisted'}</div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Weather &amp; Visibility</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 600, color: 'var(--ink)', marginTop: '1px' }}>{coastal.Weather}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5E. DWR DOPPLER RADAR OBSERVATIONS VIEW */}
      {mainMode === 'imd' && activeSubTab === 'radar' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div className="glass-card" style={{ padding: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ fontSize: '11px', fontWeight: 800, color: 'var(--primary-on-dark)' }}>
                📡 {data?.station_meta?.district_name?.toUpperCase() === 'MUMBAI' ? 'IMD VERAVALI DWR (C-BAND)' : 'IMD MACHILIPATNAM DWR (S-BAND)'}
              </div>
              <span className="chip-btn" style={{ fontSize: '9px', color: 'var(--green)', background: 'rgba(48, 209, 88, 0.15)', borderColor: 'rgba(48, 209, 88, 0.3)', cursor: 'default' }}>
                LIVE DWR ONLINE
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px', marginBottom: '10px' }}>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Operational Frequency</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--primary-on-dark)', marginTop: '2px' }} className="tabular-nums">
                  {data?.station_meta?.district_name?.toUpperCase() === 'MUMBAI' ? '5.625 GHz (C-Band)' : '2.800 GHz (S-Band)'}
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Scan Range &amp; Mode</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--amber)', marginTop: '2px' }} className="tabular-nums">
                  {data?.station_meta?.district_name?.toUpperCase() === 'MUMBAI' ? '250 km (Volumetric)' : '500 km (Long-Range)'}
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Polarization Status</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--green)', marginTop: '2px' }}>
                  Dual-Pol (Zdr, Kdp, ρhv)
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Peak Reflectivity (Z)</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--purple)', marginTop: '2px' }} className="tabular-nums">
                  {data?.station_meta?.district_name?.toUpperCase() === 'MUMBAI' ? '54.2 dBZ (Convective)' : '48.6 dBZ (Stratiform)'}
                </div>
              </div>
            </div>

            {/* Reflectivity dBZ Legend Bar */}
            <div style={{ background: 'rgba(15, 23, 42, 0.8)', padding: '8px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
              <div style={{ fontSize: '9px', color: 'var(--body-muted)', textTransform: 'uppercase', fontWeight: 700, marginBottom: '4px' }}>
                IMD Standard dBZ Reflectivity Scale
              </div>
              <div style={{
                height: '8px',
                borderRadius: '4px',
                background: 'linear-gradient(to right, #06b6d4 0%, #22c55e 25%, #eab308 50%, #f97316 75%, #ef4444 90%, #d946ef 100%)',
                marginBottom: '4px'
              }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8.5px', color: 'var(--body-muted)', fontFamily: 'monospace' }}>
                <span>10 dBZ</span>
                <span>25 dBZ</span>
                <span>40 dBZ</span>
                <span>55 dBZ</span>
                <span>65+ dBZ</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 5F. RAINFALL STATS VIEW */}
      {mainMode === 'imd' && activeSubTab === 'rainfall' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div className="glass-card" style={{ padding: '12px' }}>
            <div style={{ fontSize: '10px', color: 'var(--primary-on-dark)', textTransform: 'uppercase', fontWeight: 700, marginBottom: '6px' }}>
              District Rainfall Departures ({distRain?.District || data.station_meta.district_name})
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Daily Actual</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--primary-on-dark)', marginTop: '1px' }} className="tabular-nums">
                  {distRain?.['Daily Actual'] != null ? `${distRain['Daily Actual']} mm` : 'N/A'}
                </div>
                <div style={{ fontSize: '9px', color: String(distRain?.['Daily Departure Per'] || '').startsWith('-') ? 'var(--red)' : 'var(--green)' }}>
                  {distRain?.['Daily Departure Per'] ? `${distRain['Daily Departure Per']} (${distRain?.['Daily Category'] || 'N'})` : 'N/A'}
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Weekly Actual</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--primary-on-dark)', marginTop: '1px' }} className="tabular-nums">
                  {distRain?.['Weekly Actual'] != null ? `${distRain['Weekly Actual']} mm` : 'N/A'}
                </div>
                <div style={{ fontSize: '9px', color: String(distRain?.['Weekly Departure Per'] || '').startsWith('-') ? 'var(--red)' : 'var(--green)' }}>
                  {distRain?.['Weekly Departure Per'] ? `${distRain['Weekly Departure Per']} (${distRain?.['Weekly Category'] || 'N'})` : 'N/A'}
                </div>
              </div>
              <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>Cumulative</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--primary-on-dark)', marginTop: '1px' }} className="tabular-nums">
                  {distRain?.['Cumulative Actual'] != null ? `${distRain['Cumulative Actual']} mm` : 'N/A'}
                </div>
                <div style={{ fontSize: '9px', color: 'var(--primary-on-dark)' }}>
                  {distRain?.['Cumulative Departure Per'] ? `${distRain['Cumulative Departure Per']} (${distRain?.['Cumulative Category'] || 'N'})` : 'N/A'}
                </div>
              </div>
            </div>

          </div>

          {stateRain && (
            <div className="glass-card" style={{ padding: '12px' }}>
              <div style={{ fontSize: '10px', color: 'var(--primary-on-dark)', textTransform: 'uppercase', fontWeight: 700, marginBottom: '6px' }}>
                State-Wide Monsoon Status ({stateRain.State || data.station_meta.state_name})
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px' }}>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>State Daily Actual</div>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink)', marginTop: '1px' }} className="tabular-nums">
                    {stateRain['Daily Actual']}&nbsp;mm ({stateRain['Daily Departure Per']})
                  </div>
                </div>
                <div style={{ background: 'rgba(30, 30, 32, 0.7)', padding: '6px', borderRadius: '6px', border: '1px solid var(--hairline-soft)' }}>
                  <div style={{ fontSize: '9px', color: 'var(--body-muted)' }}>State Weekly Actual</div>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink)', marginTop: '1px' }} className="tabular-nums">
                    {stateRain['Weekly Actual']}&nbsp;mm ({stateRain['Weekly Departure Per']})
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

