import React, { useEffect, useState } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  SkipBack,
  SkipForward,
  Zap,
} from 'lucide-react';

interface TimelineControllerProps {
  currentLead: number;
  onLeadChange: (lead: number) => void;
  maxLead?: number;
  step?: number;
  onStepChange?: (step: number) => void;
  bufferedLeads?: number[];
  isBuffering?: boolean;
  onPreloadHorizon?: (horizon: number) => void;
}

const MILESTONE_JUMPS = [
  { label: 'T+0m', lead: 0, desc: 'Initial Inundation' },
  { label: 'T+15m', lead: 15, desc: 'Surface Runoff' },
  { label: 'T+30m', lead: 30, desc: 'Pipe Backflow' },
  { label: 'T+60m', lead: 60, desc: '1h Ahead Peak' },
  { label: 'T+120m', lead: 120, desc: 'Recession' },
  { label: 'T+180m', lead: 180, desc: 'Horizon End' },
];

export const TimelineController: React.FC<TimelineControllerProps> = ({
  currentLead,
  onLeadChange,
  maxLead = 180,
  step = 5,
  onStepChange,
  bufferedLeads = [],
  isBuffering = false,
  onPreloadHorizon,
}) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  
  // Custom Step & Lead Direct Editing State
  const [currentStep, setCurrentStep] = useState<number>(step);
  const [isCustomStep, setIsCustomStep] = useState<boolean>(false);
  const [customStepInput, setCustomStepInput] = useState<string>('5');
  const [isEditingLead, setIsEditingLead] = useState<boolean>(false);
  const [leadInput, setLeadInput] = useState<string>(currentLead.toString());

  useEffect(() => {
    setLeadInput(currentLead.toString());
  }, [currentLead]);

  const handleStepSelect = (s: number) => {
    setIsCustomStep(false);
    setCurrentStep(s);
    if (onStepChange) onStepChange(s);
  };

  const handleCustomStepSubmit = () => {
    const val = parseInt(customStepInput, 10);
    if (!isNaN(val) && val >= 1 && val <= 60) {
      setCurrentStep(val);
      if (onStepChange) onStepChange(val);
    }
  };

  const handleLeadSubmit = () => {
    const val = parseInt(leadInput, 10);
    if (!isNaN(val) && val >= 0 && val <= maxLead) {
      onLeadChange(val);
    }
    setIsEditingLead(false);
  };

  // Playback Loop
  useEffect(() => {
    let interval: any = null;
    if (isPlaying) {
      interval = setInterval(() => {
        onLeadChange(currentLead >= maxLead ? 0 : Math.min(maxLead, currentLead + currentStep));
      }, 1000 / playbackSpeed);
    }
    return () => clearInterval(interval);
  }, [isPlaying, currentLead, maxLead, currentStep, playbackSpeed, onLeadChange]);

  // Buffer percentage calculation (0 to 180m)
  const bufferedCount = bufferedLeads.length;
  const totalPossibleFrames = Math.floor(maxLead / Math.max(1, currentStep)) + 1;
  const bufferPct = Math.min(100, Math.round((bufferedCount / Math.max(1, totalPossibleFrames)) * 100));

  return (
    <nav
      aria-label="Nowcast Forecast Horizon Timeline Scrubber"
      style={{
        background: 'rgba(24, 24, 26, 0.88)',
        backdropFilter: 'blur(28px) saturate(190%)',
        WebkitBackdropFilter: 'blur(28px) saturate(190%)',
        borderTop: '1px solid var(--hairline)',
        padding: '8px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        zIndex: 45,
      }}
    >
      {/* Top Row: Playback Controls, Step Selector, Lead Scrubber, Milestone Jumps */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', width: '100%' }}>
        
        {/* Play / Pause / Reset / Step Jump Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            type="button"
            onClick={() => setIsPlaying(!isPlaying)}
            aria-label={isPlaying ? 'Pause simulation playback' : 'Play simulation timeline'}
            className="glass-circle-btn"
            style={{
              background: isPlaying ? 'linear-gradient(135deg, #3b82f6, #1d4ed8)' : 'rgba(40, 40, 48, 0.85)',
              borderColor: isPlaying ? 'var(--primary-on-dark)' : 'var(--hairline)',
              color: '#ffffff',
              boxShadow: isPlaying ? '0 4px 14px rgba(37, 99, 235, 0.45)' : 'none',
            }}
            title={isPlaying ? 'Pause' : 'Play Continuous Hydrodynamic Timeline'}
          >
            {isPlaying ? <Pause size={14} aria-hidden="true" /> : <Play size={14} style={{ marginLeft: '2px' }} aria-hidden="true" />}
          </button>

          <button
            type="button"
            onClick={() => {
              setIsPlaying(false);
              onLeadChange(0);
            }}
            aria-label="Reset timeline to T+0m baseline"
            className="glass-circle-btn"
            title="Reset to T+0m"
          >
            <RotateCcw size={13} aria-hidden="true" />
          </button>

          <button
            type="button"
            onClick={() => onLeadChange(Math.max(0, currentLead - currentStep))}
            aria-label={`Step back ${currentStep} minutes`}
            className="glass-circle-btn"
            title={`Step Back -${currentStep}m`}
          >
            <SkipBack size={13} aria-hidden="true" />
          </button>

          <button
            type="button"
            onClick={() => onLeadChange(Math.min(maxLead, currentLead + currentStep))}
            aria-label={`Step forward ${currentStep} minutes`}
            className="glass-circle-btn"
            title={`Step Forward +${currentStep}m`}
          >
            <SkipForward size={13} aria-hidden="true" />
          </button>
        </div>

        {/* Lead Direct Input / Badge */}
        <div style={{ minWidth: '84px', textAlign: 'center' }}>
          {isEditingLead ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
              <span style={{ fontSize: '11px', color: 'var(--primary-on-dark)', fontWeight: 700 }}>T+</span>
              <input
                type="number"
                min="0"
                max={maxLead}
                value={leadInput}
                onChange={(e) => setLeadInput(e.target.value)}
                onBlur={handleLeadSubmit}
                onKeyDown={(e) => e.key === 'Enter' && handleLeadSubmit()}
                autoFocus
                aria-label="Direct lead minute entry"
                style={{
                  width: '46px',
                  background: 'rgba(20, 20, 26, 0.95)',
                  border: '1px solid var(--primary-on-dark)',
                  borderRadius: '8px',
                  color: 'var(--primary-on-dark)',
                  fontWeight: 700,
                  fontSize: '11px',
                  textAlign: 'center',
                  padding: '3px',
                  outline: 'none',
                }}
              />
              <span style={{ fontSize: '11px', color: 'var(--primary-on-dark)', fontWeight: 700 }}>m</span>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setIsEditingLead(true)}
              aria-label={`Current lead time T+${currentLead} minutes. Click to edit.`}
              className="chip-btn"
              style={{
                background: 'linear-gradient(135deg, rgba(37, 99, 235, 0.3), rgba(30, 64, 175, 0.3))',
                borderColor: 'var(--primary-on-dark)',
                color: '#ffffff',
                fontWeight: 700,
                fontSize: '12px',
                padding: '5px 12px',
                borderRadius: '9999px',
                boxShadow: '0 2px 10px var(--primary-glow)',
              }}
              title="Click to manually enter forecast minute"
            >
              <span className="tabular-nums">T+{currentLead}m</span>
            </button>
          )}
        </div>

        {/* Timeline Slider with Multi-Horizon Sub-Segments & Buffer Visualizer */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <div style={{ position: 'relative', width: '100%', display: 'flex', alignItems: 'center' }}>
            <label htmlFor="timeline-range-slider" className="sr-only">
              Forecast Horizon Lead Slider
            </label>
            <input
              id="timeline-range-slider"
              type="range"
              min="0"
              max={maxLead}
              step={currentStep}
              value={currentLead}
              aria-label={`Timeline slider at ${currentLead} minutes of ${maxLead}`}
              onChange={(e) => onLeadChange(parseInt(e.target.value, 10))}
              style={{
                width: '100%',
                cursor: 'pointer',
                zIndex: 2,
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--ink-muted-48)', letterSpacing: '-0.1px' }}>
            <span style={{ color: currentLead === 0 ? 'var(--primary-on-dark)' : 'inherit', fontWeight: currentLead === 0 ? 600 : 400 }}>T+0m (Analysis)</span>
            <span style={{ color: currentLead > 0 && currentLead <= 30 ? 'var(--green)' : 'inherit', fontWeight: currentLead > 0 && currentLead <= 30 ? 600 : 400 }}>
              0–30m Optical Flow
            </span>
            <span style={{ color: currentLead > 30 && currentLead <= 120 ? 'var(--primary-on-dark)' : 'inherit', fontWeight: currentLead > 30 && currentLead <= 120 ? 600 : 400 }}>
              30–120m Coupled SWMM/2D
            </span>
            <span style={{ color: currentLead > 120 ? 'var(--purple)' : 'inherit', fontWeight: currentLead > 120 ? 600 : 400 }}>
              120–180m NWP
            </span>
            <span>T+180m</span>
          </div>
        </div>

        {/* Time Step Jump Options: +1m, +5m, +15m, Custom */}
        <div className="glass-pill" style={{ display: 'flex', alignItems: 'center', gap: '3px', padding: '2px 6px' }}>
          <span style={{ fontSize: '10px', color: 'var(--body-muted)', fontWeight: 600, paddingLeft: '2px' }}>Step:</span>
          {[1, 5, 15].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleStepSelect(s)}
              aria-label={`Set step increment to ${s} minutes`}
              style={{
                background: (!isCustomStep && currentStep === s) ? 'var(--primary-focus)' : 'transparent',
                color: (!isCustomStep && currentStep === s) ? '#ffffff' : 'var(--body-muted)',
                border: 'none',
                borderRadius: '4px',
                padding: '2px 6px',
                fontSize: '10px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
              title={`Step by ${s} minute(s)`}
            >
              +{s}m
            </button>
          ))}
          
          {/* Custom Step */}
          {isCustomStep ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
              <input
                type="number"
                min="1"
                max="60"
                value={customStepInput}
                onChange={(e) => setCustomStepInput(e.target.value)}
                onBlur={handleCustomStepSubmit}
                onKeyDown={(e) => e.key === 'Enter' && handleCustomStepSubmit()}
                autoFocus
                aria-label="Custom step minute entry"
                style={{
                  width: '28px',
                  background: 'rgba(20, 20, 22, 0.95)',
                  border: '1px solid var(--primary-on-dark)',
                  borderRadius: '3px',
                  color: 'var(--primary-on-dark)',
                  fontSize: '10px',
                  fontWeight: 700,
                  textAlign: 'center',
                  padding: '1px',
                  outline: 'none',
                }}
              />
              <span style={{ fontSize: '10px', color: 'var(--primary-on-dark)' }}>m</span>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setIsCustomStep(true);
                setCustomStepInput(currentStep.toString());
              }}
              aria-label="Enter custom step interval"
              style={{
                background: 'transparent',
                color: 'var(--ink-muted-48)',
                border: 'none',
                borderRadius: '3px',
                padding: '2px 4px',
                fontSize: '10px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
              title="Enter custom time step (1–60m)"
            >
              Custom
            </button>
          )}
        </div>

        {/* Speed Multipliers */}
        <div className="glass-pill" style={{ display: 'flex', gap: '2px', padding: '2px 4px' }}>
          {[1, 2, 5, 10].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setPlaybackSpeed(s)}
              aria-label={`Set playback speed to ${s}x`}
              style={{
                background: playbackSpeed === s ? 'var(--primary-focus)' : 'transparent',
                color: playbackSpeed === s ? '#ffffff' : 'var(--body-muted)',
                border: 'none',
                borderRadius: '4px',
                padding: '2px 6px',
                fontSize: '10px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Bottom Sub-Row: Milestone Jump Pills & Pre-Buffer Status */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--hairline-soft)', paddingTop: '4px' }}>
        
        {/* Quick Milestone Time Jump Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ fontSize: '10px', color: 'var(--body-muted)', fontWeight: 600 }}>Quick Jump:</span>
          {MILESTONE_JUMPS.map((m) => (
            <button
              key={m.lead}
              type="button"
              onClick={() => onLeadChange(m.lead)}
              aria-label={`Jump to milestone ${m.label}: ${m.desc}`}
              className="chip-btn"
              style={{
                background: currentLead === m.lead ? 'rgba(0, 113, 227, 0.25)' : 'rgba(42, 42, 44, 0.5)',
                color: currentLead === m.lead ? 'var(--primary-on-dark)' : 'var(--body-muted)',
                borderColor: currentLead === m.lead ? 'var(--primary-on-dark)' : 'var(--hairline-soft)',
                padding: '1px 7px',
                fontSize: '10px',
              }}
              title={m.desc}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* 1-Hour Pre-Buffer & Cache Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {onPreloadHorizon && (
            <button
              type="button"
              onClick={() => onPreloadHorizon(60)}
              disabled={isBuffering}
              aria-label="Pre-buffer 1 hour forecast horizon into memory"
              className="chip-btn"
              style={{
                background: isBuffering ? 'rgba(191, 90, 242, 0.15)' : 'rgba(42, 42, 44, 0.6)',
                color: isBuffering ? 'var(--purple)' : 'var(--primary-on-dark)',
                borderColor: isBuffering ? 'var(--purple)' : 'var(--hairline-soft)',
                cursor: isBuffering ? 'wait' : 'pointer',
                padding: '2px 8px',
                fontSize: '10px',
              }}
              title="Pre-fetch and buffer the next 1 hour (60 min) of hydrodynamics into browser RAM"
            >
              <Zap size={10} color={isBuffering ? 'var(--purple)' : 'var(--primary-on-dark)'} aria-hidden="true" />
              <span>{isBuffering ? 'Buffering 1h Ahead…' : 'Pre-Buffer 1h'}</span>
            </button>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px', color: 'var(--body-muted)' }}>
            <span>RAM Cache:</span>
            <strong style={{ color: bufferedCount > 0 ? 'var(--green)' : 'var(--body-muted)' }} className="tabular-nums">
              {bufferedCount}&nbsp;frames ({bufferPct}%)
            </strong>
          </div>
        </div>
      </div>
    </nav>
  );
};
