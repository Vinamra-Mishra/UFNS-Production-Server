import React, { useEffect, useState } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  SkipBack,
  SkipForward,
  Zap,
} from 'lucide-react';

interface FloatingTimelineProps {
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

export const FloatingTimeline: React.FC<FloatingTimelineProps> = ({
  currentLead,
  onLeadChange,
  maxLead = 180,
  step = 1,
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
  const [customStepInput, setCustomStepInput] = useState<string>('1');
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

  // Playback Loop (Smooth Video Progression)
  useEffect(() => {
    let interval: any = null;
    if (isPlaying) {
      interval = setInterval(() => {
        onLeadChange(currentLead >= maxLead ? 0 : Math.min(maxLead, currentLead + currentStep));
      }, 350 / playbackSpeed);
    }
    return () => clearInterval(interval);
  }, [isPlaying, currentLead, maxLead, currentStep, playbackSpeed, onLeadChange]);

  const bufferedCount = bufferedLeads.length;
  const totalPossibleFrames = Math.floor(maxLead / Math.max(1, currentStep)) + 1;
  const bufferPct = Math.min(100, Math.round((bufferedCount / Math.max(1, totalPossibleFrames)) * 100));

  return (
    <div
      className="glass-panel"
      style={{
        position: 'absolute',
        bottom: '16px',
        left: '50%',
        transform: 'translateX(-50%)',
        width: 'min(880px, calc(100vw - 32px))',
        padding: '8px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        zIndex: 40,
        pointerEvents: 'auto',
      }}
    >
      {/* Top Deck: Controls, Scrubber Slider, Step Selector, Speed */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', width: '100%' }}>
        
        {/* Play / Pause / Reset / Step Jump Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <button
            onClick={() => {
              setIsPlaying(!isPlaying);
            }}
            className="glass-btn"
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '9999px',
              background: isPlaying ? 'linear-gradient(135deg, #0284c7, #2563eb)' : 'rgba(15, 23, 42, 0.8)',
              borderColor: isPlaying ? '#38bdf8' : 'rgba(255, 255, 255, 0.15)',
              boxShadow: isPlaying ? '0 0 12px rgba(56, 189, 248, 0.5)' : 'none',
            }}
            title={isPlaying ? 'Pause' : 'Play Smooth 60fps Video Timeline'}
          >
            {isPlaying ? <Pause size={13} /> : <Play size={13} style={{ marginLeft: '1px' }} />}
          </button>

          <button
            onClick={() => {
              setIsPlaying(false);
              onLeadChange(0);
            }}
            className="glass-btn"
            style={{ width: '28px', height: '28px', borderRadius: '50%' }}
            title="Reset to T+0m"
          >
            <RotateCcw size={11} color="#94a3b8" />
          </button>

          <button
            onClick={() => onLeadChange(Math.max(0, currentLead - currentStep))}
            className="glass-btn"
            style={{ width: '28px', height: '28px', borderRadius: '50%' }}
            title={`Step Back -${currentStep}m`}
          >
            <SkipBack size={11} color="#94a3b8" />
          </button>

          <button
            onClick={() => onLeadChange(Math.min(maxLead, currentLead + currentStep))}
            className="glass-btn"
            style={{ width: '28px', height: '28px', borderRadius: '50%' }}
            title={`Step Forward +${currentStep}m`}
          >
            <SkipForward size={11} color="#94a3b8" />
          </button>
        </div>

        {/* Lead Direct Input / Capsule */}
        <div style={{ minWidth: '65px', textAlign: 'center' }}>
          {isEditingLead ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
              <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 800 }}>T+</span>
              <input
                type="number"
                min="0"
                max={maxLead}
                value={leadInput}
                onChange={(e) => setLeadInput(e.target.value)}
                onBlur={handleLeadSubmit}
                onKeyDown={(e) => e.key === 'Enter' && handleLeadSubmit()}
                autoFocus
                style={{
                  width: '38px',
                  background: '#080d1a',
                  border: '1px solid #0284c7',
                  borderRadius: '4px',
                  color: '#38bdf8',
                  fontWeight: 800,
                  fontSize: '11px',
                  textAlign: 'center',
                  padding: '2px',
                  outline: 'none',
                }}
              />
              <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 800 }}>m</span>
            </div>
          ) : (
            <div
              onClick={() => setIsEditingLead(true)}
              style={{
                cursor: 'pointer',
                padding: '2px 4px',
                borderRadius: '6px',
                border: '1px dashed transparent',
                transition: 'all 0.15s',
              }}
              title="Click to jump to any custom forecast minute"
            >
              <div style={{ fontSize: '13px', fontWeight: 900, color: '#38bdf8', fontVariantNumeric: 'tabular-nums' }}>
                T+{currentLead}m
              </div>
              <div style={{ fontSize: '8px', color: '#64748b' }}>Forecast Lead</div>
            </div>
          )}
        </div>

        {/* Scrubber Slider with Multi-Horizon Sub-Segments */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <input
            type="range"
            min="0"
            max={maxLead}
            step={currentStep}
            value={currentLead}
            onChange={(e) => onLeadChange(parseInt(e.target.value, 10))}
            style={{
              width: '100%',
              accentColor: '#38bdf8',
              cursor: 'pointer',
            }}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: '#64748b' }}>
            <span style={{ color: currentLead === 0 ? '#38bdf8' : '#64748b' }}>T+0m (Analysis)</span>
            <span style={{ color: currentLead > 0 && currentLead <= 30 ? '#34d399' : '#64748b' }}>
              0-30m Optical Flow
            </span>
            <span style={{ color: currentLead > 30 && currentLead <= 120 ? '#38bdf8' : '#64748b' }}>
              30-120m Coupled 1D/2D
            </span>
            <span style={{ color: currentLead > 120 ? '#c084fc' : '#64748b' }}>
              120-180m Recession
            </span>
            <span>T+180m</span>
          </div>
        </div>

        {/* Step Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '3px', background: 'rgba(10, 15, 29, 0.8)', padding: '2px 4px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
          <span style={{ fontSize: '8px', color: '#64748b', fontWeight: 800 }}>STEP:</span>
          {[1, 5, 15].map((s) => (
            <button
              key={s}
              onClick={() => handleStepSelect(s)}
              style={{
                background: (!isCustomStep && currentStep === s) ? '#0284c7' : 'transparent',
                color: (!isCustomStep && currentStep === s) ? '#fff' : '#94a3b8',
                border: 'none',
                borderRadius: '4px',
                padding: '2px 5px',
                fontSize: '9px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              +{s}m
            </button>
          ))}

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
                style={{
                  width: '24px',
                  background: '#080d1a',
                  border: '1px solid #0284c7',
                  borderRadius: '3px',
                  color: '#38bdf8',
                  fontSize: '9px',
                  fontWeight: 700,
                  textAlign: 'center',
                  padding: '1px',
                  outline: 'none',
                }}
              />
              <span style={{ fontSize: '8px', color: '#38bdf8' }}>m</span>
            </div>
          ) : (
            <button
              onClick={() => {
                setIsCustomStep(true);
                setCustomStepInput(currentStep.toString());
              }}
              style={{
                background: 'transparent',
                color: '#64748b',
                border: 'none',
                borderRadius: '4px',
                padding: '2px 4px',
                fontSize: '8px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Custom
            </button>
          )}
        </div>

        {/* Speed Multipliers */}
        <div style={{ display: 'flex', gap: '2px', background: 'rgba(10, 15, 29, 0.8)', padding: '2px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
          {[1, 2, 5].map((s) => (
            <button
              key={s}
              onClick={() => setPlaybackSpeed(s)}
              style={{
                background: playbackSpeed === s ? '#0284c7' : 'transparent',
                color: playbackSpeed === s ? '#fff' : '#64748b',
                border: 'none',
                borderRadius: '4px',
                padding: '2px 5px',
                fontSize: '9px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Bottom Sub-Row: Milestone Jump Pills & Pre-Buffer Status */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '4px' }}>
        
        {/* Quick Milestone Time Jump Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ fontSize: '8px', color: '#64748b', fontWeight: 800, textTransform: 'uppercase' }}>JUMP:</span>
          {MILESTONE_JUMPS.map((m) => (
            <button
              key={m.lead}
              onClick={() => onLeadChange(m.lead)}
              className="glass-pill"
              style={{
                background: currentLead === m.lead ? 'rgba(2, 132, 199, 0.4)' : 'rgba(15, 23, 42, 0.6)',
                color: currentLead === m.lead ? '#38bdf8' : '#94a3b8',
                borderColor: currentLead === m.lead ? '#0284c7' : 'rgba(255, 255, 255, 0.08)',
                padding: '2px 7px',
                fontSize: '9px',
                fontWeight: 700,
                cursor: 'pointer',
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
              onClick={() => onPreloadHorizon(60)}
              disabled={isBuffering}
              className="glass-pill"
              style={{
                background: isBuffering ? 'rgba(126, 34, 206, 0.35)' : 'rgba(15, 23, 42, 0.8)',
                color: isBuffering ? '#c084fc' : '#38bdf8',
                borderColor: isBuffering ? '#7e22ce' : 'rgba(56, 189, 248, 0.3)',
                padding: '2px 8px',
                fontSize: '9px',
                fontWeight: 800,
                cursor: isBuffering ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
              title="Pre-buffer the next 1 hour (60 min) of hydrodynamics into browser RAM"
            >
              <Zap size={10} color={isBuffering ? '#c084fc' : '#38bdf8'} />
              <span>{isBuffering ? 'Buffering 1h Ahead...' : 'Pre-Buffer 1h'}</span>
            </button>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: '#64748b' }}>
            <span>RAM Cache:</span>
            <strong style={{ color: bufferedCount > 0 ? '#34d399' : '#64748b' }}>
              {bufferedCount} frames ({bufferPct}%)
            </strong>
          </div>
        </div>
      </div>
    </div>
  );
};
