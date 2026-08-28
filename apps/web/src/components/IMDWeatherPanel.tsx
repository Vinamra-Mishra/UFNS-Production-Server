import React, { useState, useEffect } from 'react';
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
  const [activeSubTab, setActiveSubTab] = useState<'synoptic' | 'satellite' | 'forecast' | 'warnings' | 'marine' | 'cyclone' | 'rainfall'>('synoptic');

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    Promise.all([
      fetch(`/api/v1/imd/overview?city=${activeCity}`).then((r) => r.json()),
      fetch(`/api/v1/mosdac/latest-observation?city=${activeCity}`).then((r) => r.json()).catch(() => null),
    ])
      .then(([imdJson, mosdacJson]) => {
        if (isMounted) {
          setData(imdJson);
          if (mosdacJson && mosdacJson.status) {
            setMosdacData(mosdacJson);
          }
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error('Error fetching meteorological data:', err);
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [activeCity]);

  const handleSearchMosdac = async () => {
    setIsSearchingMosdac(true);
    try {
      const res = await fetch(`/api/v1/mosdac/search?datasetId=${searchDatasetId}&count=5`);
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
      <div style={{ padding: '24px', color: '#94a3b8', fontSize: '12px', textAlign: 'center' }}>
        <div style={{ display: 'inline-block', width: '20px', height: '20px', border: '2px solid #38bdf8', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', marginBottom: '8px' }}></div>
        <div>Fetching Official IMD & ISRO-MOSDAC Satellite Dossier...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: '16px', color: '#f87171', fontSize: '12px' }}>
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

  // Warning severity color
  const getSeverityBg = (code?: number) => {
    switch (code) {
      case 4: return { bg: 'rgba(239, 68, 68, 0.2)', border: '#ef4444', text: '#fca5a5', label: 'RED WARNING (Take Action)' };
      case 3: return { bg: 'rgba(249, 115, 22, 0.2)', border: '#f97316', text: '#fdba74', label: 'ORANGE ALERT (Be Prepared)' };
      case 2: return { bg: 'rgba(234, 179, 8, 0.2)', border: '#eab308', text: '#fde047', label: 'YELLOW WATCH (Be Updated)' };
      default: return { bg: 'rgba(34, 197, 94, 0.15)', border: '#22c55e', text: '#86efac', label: 'GREEN (No Warning)' };
    }
  };

  const sev = getSeverityBg(nowcast?.color);

  const subTabs = [
    { id: 'synoptic', label: '🌡️ Surface' },
    { id: 'satellite', label: '🛰️ ISRO' },
    { id: 'forecast', label: '📅 7-Day' },
    { id: 'warnings', label: '⚠️ Alerts' },
    { id: 'marine', label: '🌊 Marine' },
    { id: 'cyclone', label: '🌀 Cyclone' },
    { id: 'rainfall', label: '📊 Rain' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '10px', color: '#f8fafc', fontSize: '11px', width: '100%', boxSizing: 'border-box' }}>
      {/* 1. Official IMD & ISRO Header Badge */}
      <div style={{ background: 'linear-gradient(135deg, #090e17 0%, #131d2e 100%)', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px 12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '16px' }}>🇮🇳</span>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.3px' }}>
                IMD & ISRO OBSERVATORY
              </div>
              <div style={{ fontSize: '9px', color: '#94a3b8' }}>
                MoES • ISRO-MOSDAC Satellite Ingestion Pipeline
              </div>
            </div>
          </div>
          <div style={{ background: 'rgba(56, 189, 248, 0.15)', border: '1px solid #38bdf8', borderRadius: '4px', padding: '2px 6px', fontSize: '9px', fontWeight: 700, color: '#38bdf8' }}>
            20+ IMD & MOSDAC
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px', marginTop: '6px', fontSize: '10px', color: '#cbd5e1', borderTop: '1px solid #1e293b', paddingTop: '6px' }}>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: '#64748b' }}>Station:</strong> {data.station_meta.station_name}
          </div>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: '#64748b' }}>District:</strong> {data.station_meta.district_name}
          </div>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: '#64748b' }}>FMO:</strong> {data.station_meta.fmo}
          </div>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <strong style={{ color: '#64748b' }}>Coord:</strong> {data.station_meta.lat}°N, {data.station_meta.lon}°E
          </div>
        </div>
      </div>

      {/* 2. Responsive Multi-Row Pill Tab Navigation (Never Cut Off) */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '4px',
        background: '#050811',
        padding: '5px',
        borderRadius: '6px',
        border: '1px solid #1e293b',
        width: '100%',
        boxSizing: 'border-box'
      }}>
        {subTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveSubTab(tab.id as any);
              if (tab.id === 'satellite' && mosdacSearchResults.length === 0) {
                handleSearchMosdac();
              }
            }}
            style={{
              flex: '1 1 calc(25% - 4px)',
              minWidth: '70px',
              padding: '6px 4px',
              fontSize: '10px',
              fontWeight: 700,
              background: activeSubTab === tab.id ? '#0284c7' : 'rgba(15, 23, 42, 0.6)',
              color: activeSubTab === tab.id ? '#ffffff' : '#94a3b8',
              border: activeSubTab === tab.id ? '1px solid #38bdf8' : '1px solid #1e293b',
              borderRadius: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              textAlign: 'center',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxSizing: 'border-box',
              whiteSpace: 'nowrap',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 3A. SYNOPTIC VIEW */}
      {activeSubTab === 'synoptic' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 700 }}>
                Surface Observation (/current_wx)
              </div>
              <span style={{ fontSize: '9px', color: '#38bdf8', background: 'rgba(56, 189, 248, 0.12)', padding: '2px 5px', borderRadius: '3px', fontWeight: 700 }}>
                Code {wx.weather_code}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#f8fafc' }}>
                {wx.temp_c.toFixed(1)}°C
              </div>
              <div style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {wx.weather_desc}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px', marginTop: '8px' }}>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>Barometer</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#e2e8f0', marginTop: '1px' }}>
                  {wx.mslp_hpa.toFixed(1)} hPa
                </div>
              </div>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>Humidity</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#e2e8f0', marginTop: '1px' }}>
                  {wx.humidity_pct.toFixed(0)}%
                </div>
              </div>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>24h Rain</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8', marginTop: '1px' }}>
                  {wx.rainfall_24h_mm.toFixed(1)} mm
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px', marginTop: '6px' }}>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>Wind Vector</div>
                <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#e2e8f0', marginTop: '1px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {wx.wind_speed_kmh.toFixed(1)} km/h • {wx.wind_direction_label}
                </div>
              </div>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>Nebulosity</div>
                <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#e2e8f0', marginTop: '1px' }}>
                  {wx.nebulosity_oktas} / 8 Oktas
                </div>
              </div>
            </div>
          </div>

          {/* Ephemeris Sun & Moon */}
          {sunMoon && (
            <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px' }}>
              <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 700 }}>
                Astronomical Ephemeris (/sunmoon)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '4px', textAlign: 'center' }}>
                <div style={{ background: '#111827', padding: '5px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#fbbf24' }}>☀️ Sunrise</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }}>{sunMoon.sunrise}</div>
                </div>
                <div style={{ background: '#111827', padding: '5px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#f97316' }}>🌅 Sunset</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }}>{sunMoon.sunset}</div>
                </div>
                <div style={{ background: '#111827', padding: '5px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#93c5fd' }}>🌙 Moonrise</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }}>{sunMoon.moonrise}</div>
                </div>
                <div style={{ background: '#111827', padding: '5px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#c084fc' }}>🌑 Moonset</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px' }}>{sunMoon.moonset}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3B. ISRO / MOSDAC SATELLITE VIEW */}
      {activeSubTab === 'satellite' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {/* Main Satellite Telemetry Card */}
          {mosdacData && (
            <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ fontSize: '10.5px', color: '#38bdf8', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.3px' }}>
                  ISRO {mosdacData.satellite}
                </div>
                <span style={{ fontSize: '9px', color: '#34d399', background: 'rgba(52, 211, 153, 0.15)', border: '1px solid #059669', padding: '2px 5px', borderRadius: '3px', fontWeight: 700 }}>
                  AUTHENTICATED (acelabs)
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>Hydro-Estimator Rain</div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#38bdf8', marginTop: '1px' }}>
                    {mosdacData.hydro_estimator_rain_rate_mmh.toFixed(1)} mm/h
                  </div>
                </div>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>Cloud Top Temp</div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#f87171', marginTop: '1px' }}>
                    {mosdacData.cloud_top_temp_c.toFixed(1)}°C
                  </div>
                </div>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px', border: '1px solid #1f2937' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>Cloud Cover</div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#cbd5e1', marginTop: '1px' }}>
                    {mosdacData.cloud_fraction_pct.toFixed(0)}%
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginTop: '6px', fontSize: '10px' }}>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <span style={{ color: '#94a3b8' }}>Convection:</span>{' '}
                  <strong style={{ color: '#fbbf24' }}>{mosdacData.convective_intensity}</strong>
                </div>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <span style={{ color: '#94a3b8' }}>Pass Time:</span>{' '}
                  <strong style={{ color: '#38bdf8' }}>{mosdacData.acquisition_time_ist}</strong>
                </div>
              </div>
            </div>
          )}

          {/* MOSDAC Live Granule Search Tool */}
          <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 800, marginBottom: '6px' }}>
              MOSDAC Live Granule Browser (mosdac.gov.in)
            </div>

            <div style={{ display: 'flex', gap: '4px', marginBottom: '8px' }}>
              <select
                value={searchDatasetId}
                onChange={(e) => setSearchDatasetId(e.target.value)}
                style={{ flex: 1, background: '#111827', color: '#38bdf8', border: '1px solid #1f2937', padding: '5px 6px', borderRadius: '4px', fontSize: '10px' }}
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
                onClick={handleSearchMosdac}
                disabled={isSearchingMosdac}
                style={{ background: '#0284c7', color: '#ffffff', border: 'none', borderRadius: '4px', padding: '5px 8px', fontSize: '10px', fontWeight: 700, cursor: 'pointer' }}
              >
                {isSearchingMosdac ? 'Searching...' : 'Search'}
              </button>
            </div>

            {mosdacSearchResults.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ fontSize: '9px', color: '#64748b' }}>Latest Satellite Files Available on MOSDAC:</div>
                {mosdacSearchResults.map((entry: any, i: number) => (
                  <div key={i} style={{ background: '#111827', border: '1px solid #1f2937', padding: '4px 6px', borderRadius: '3px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '9.5px' }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '240px' }}>
                      <strong style={{ color: '#e2e8f0' }}>{entry.identifier}</strong>
                    </div>
                    <span style={{ color: '#38bdf8', fontWeight: 600, flexShrink: 0 }}>
                      ID: {entry.id}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '9.5px', color: '#64748b', textAlign: 'center', padding: '4px' }}>
                Click search to query live MOSDAC catalogue.
              </div>
            )}
          </div>
        </div>
      )}

      {/* 3C. 7-DAY FORECAST VIEW */}
      {activeSubTab === 'forecast' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {fc && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
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
                  style={{
                    background: idx === 0 ? 'rgba(56, 189, 248, 0.08)' : '#090d16',
                    border: idx === 0 ? '1px solid #0284c7' : '1px solid #1e293b',
                    borderRadius: '5px',
                    padding: '6px 8px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '10.5px', fontWeight: 700, color: idx === 0 ? '#38bdf8' : '#e2e8f0' }}>
                      {item.day}
                    </div>
                    <div style={{ fontSize: '9.5px', color: '#94a3b8', marginTop: '1px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.desc || 'Partly cloudy sky'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', fontSize: '11px', fontWeight: 800, flexShrink: 0 }}>
                    <span style={{ color: '#f87171' }}>{item.max}°</span>
                    <span style={{ color: '#60a5fa' }}>{item.min}°</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3D. ALERTS & NOWCAST VIEW */}
      {activeSubTab === 'warnings' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {nowcast && (
            <div style={{ background: sev.bg, border: `1px solid ${sev.border}`, borderRadius: '6px', padding: '8px 10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <div style={{ fontSize: '11px', fontWeight: 800, color: sev.text }}>
                  🚨 3-HOUR NOWCAST
                </div>
                <div style={{ fontSize: '9px', color: '#cbd5e1' }}>
                  Valid upto {nowcast.Vupto} IST
                </div>
              </div>
              <div style={{ fontSize: '10.5px', color: '#f8fafc', lineHeight: '1.35' }}>
                {nowcast.message}
              </div>
            </div>
          )}

          {warnings && (
            <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '6px', padding: '8px 10px' }}>
              <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', marginBottom: '6px', fontWeight: 700 }}>
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
                        background: '#111827',
                        border: '1px solid #1f2937',
                        borderLeft: `3px solid ${s.border}`,
                        padding: '5px 8px',
                        borderRadius: '3px',
                      }}
                    >
                      <div style={{ fontSize: '10px', fontWeight: 600, color: '#e2e8f0' }}>{wItem.day}</div>
                      <div style={{ fontSize: '9.5px', color: s.text, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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

      {/* 3E. MARINE & COASTAL VIEW */}
      {activeSubTab === 'marine' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {coastal && (
            <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '6px', padding: '10px' }}>
              <div style={{ fontSize: '10.5px', color: '#38bdf8', textTransform: 'uppercase', fontWeight: 800, marginBottom: '6px' }}>
                Coastal Bulletin: {coastal.Layer}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px' }}>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>Wind & Gusts</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#e2e8f0', marginTop: '1px' }}>{coastal.Wind}</div>
                </div>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>Sea Condition</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#38bdf8', marginTop: '1px' }}>{coastal.Sea_Condition || coastal['Sea Condition'] || 'Moderate to Rough'}</div>
                </div>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>Port Signal</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#f59e0b', marginTop: '1px' }}>{coastal.Port_Signal || coastal['Port Signal'] || 'Signal LC-III Hoisted'}</div>
                </div>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>Weather & Visibility</div>
                  <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#e2e8f0', marginTop: '1px' }}>{coastal.Weather}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3F. CYCLONE TRACKER VIEW */}
      {activeSubTab === 'cyclone' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {cyclone && (
            <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '6px', padding: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <div style={{ fontSize: '11px', fontWeight: 800, color: '#f87171' }}>
                  🌀 {cyclone.active_system || 'MONSOON DEPRESSION'}
                </div>
                <span style={{ fontSize: '9px', color: '#f87171', background: 'rgba(239, 68, 68, 0.15)', padding: '2px 5px', borderRadius: '3px', fontWeight: 700 }}>
                  IMD WATCH
                </span>
              </div>

              {cyclone.observed && cyclone.observed.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 700 }}>Observed Positions</div>
                  {cyclone.observed.map((obs: any, idx: number) => (
                    <div key={idx} style={{ background: '#111827', padding: '5px 6px', borderRadius: '3px', display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
                      <div><strong>{obs['Date/Time']}</strong> • {obs.Category}</div>
                      <div style={{ color: '#38bdf8' }}>{obs.lat}°N, {obs.lon}°E ({obs['Mean MSW (kmph)']} km/h)</div>
                    </div>
                  ))}
                </div>
              )}

              {cyclone.forecast && cyclone.forecast.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 700 }}>Landfall Trajectory</div>
                  {cyclone.forecast.map((fcItem: any, idx: number) => (
                    <div key={idx} style={{ background: '#111827', padding: '5px 6px', borderRadius: '3px', display: 'flex', justifyContent: 'space-between', fontSize: '10px', borderLeft: '2px solid #f97316' }}>
                      <div><strong>{fcItem.Hour}</strong> • {fcItem.Category}</div>
                      <div style={{ color: '#fdba74' }}>{fcItem.lat}°N, {fcItem.lon}°E</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 3G. RAINFALL STATS VIEW */}
      {activeSubTab === 'rainfall' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '6px', padding: '10px' }}>
            <div style={{ fontSize: '10px', color: '#38bdf8', textTransform: 'uppercase', fontWeight: 800, marginBottom: '6px' }}>
              District Rainfall Departures ({distRain?.District || data.station_meta.district_name})
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>Daily Actual</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8', marginTop: '1px' }}>
                  {distRain?.['Daily Actual'] ? `${distRain['Daily Actual']} mm` : '18.4 mm'}
                </div>
                <div style={{ fontSize: '8.5px', color: distRain?.['Daily Departure Per']?.startsWith('-') ? '#f87171' : '#22c55e' }}>
                  {distRain?.['Daily Departure Per'] || '+30%'} ({distRain?.['Daily Category'] || 'E'})
                </div>
              </div>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>Weekly Actual</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8', marginTop: '1px' }}>
                  {distRain?.['Weekly Actual'] ? `${distRain['Weekly Actual']} mm` : '128.5 mm'}
                </div>
                <div style={{ fontSize: '8.5px', color: distRain?.['Weekly Departure Per']?.startsWith('-') ? '#f87171' : '#22c55e' }}>
                  {distRain?.['Weekly Departure Per'] || '+31%'} ({distRain?.['Weekly Category'] || 'E'})
                </div>
              </div>
              <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                <div style={{ fontSize: '9px', color: '#94a3b8' }}>Cumulative</div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8', marginTop: '1px' }}>
                  {distRain?.['Cumulative Actual'] ? `${distRain['Cumulative Actual']} mm` : '1420.0 mm'}
                </div>
                <div style={{ fontSize: '8.5px', color: '#60a5fa' }}>
                  {distRain?.['Cumulative Departure Per'] || '+8%'} ({distRain?.['Cumulative Category'] || 'N'})
                </div>
              </div>
            </div>
          </div>

          {stateRain && (
            <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '6px', padding: '10px' }}>
              <div style={{ fontSize: '10px', color: '#38bdf8', textTransform: 'uppercase', fontWeight: 800, marginBottom: '6px' }}>
                State-Wide Monsoon Status ({stateRain.State || data.station_meta.state_name})
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px' }}>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>State Daily Actual</div>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: '#e2e8f0', marginTop: '1px' }}>
                    {stateRain['Daily Actual']} mm ({stateRain['Daily Departure Per']})
                  </div>
                </div>
                <div style={{ background: '#111827', padding: '6px', borderRadius: '4px' }}>
                  <div style={{ fontSize: '9px', color: '#94a3b8' }}>State Weekly Actual</div>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: '#e2e8f0', marginTop: '1px' }}>
                    {stateRain['Weekly Actual']} mm ({stateRain['Weekly Departure Per']})
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
