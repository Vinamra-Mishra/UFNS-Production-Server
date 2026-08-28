import React, { useEffect, useState } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  SkipBack,
  SkipForward,
  CloudRain,
  Activity,
  Zap,
  FastForward,
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
  const [nowcastMode, setNowcastMode] = useState<'scenario' | 'radar_flow'>('radar_flow');
  
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
    <div
      style={{
        background: '#000000',
        borderTop: '1px solid #171717',
        padding: '6px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        zIndex: 45,
      }}
    >
      {/* Top Row: Playback Controls, Step Selector, Lead Scrubber, Milestone Jumps, Mode */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', width: '100%' }}>
        
        {/* Play / Pause / Reset / Step Jump Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <button
            onClick={() => {
              setIsPlaying(!isPlaying);
            }}
            style={{
              background: isPlaying ? '#0284c7' : '#050505',
              color: '#fff',
              border: '1px solid #1f2937',
              borderRadius: '5px',
              width: '30px',
              height: '30px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
            title={isPlaying ? 'Pause' : 'Play Smooth Buffered Timeline'}
          >
            {isPlaying ? <Pause size={13} /> : <Play size={13} style={{ marginLeft: '1px' }} />}
          </button>

          <button
            onClick={() => {
              setIsPlaying(false);
              onLeadChange(0);
            }}
            style={{
              background: '#050505',
              color: '#94a3b8',
              border: '1px solid #1f2937',
              borderRadius: '5px',
              width: '30px',
              height: '30px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
            title="Reset to T+0m"
          >
            <RotateCcw size={12} />
          </button>

          <button
            onClick={() => onLeadChange(Math.max(0, currentLead - currentStep))}
            style={{
              background: '#050505',
              color: '#94a3b8',
              border: '1px solid #1f2937',
              borderRadius: '5px',
              width: '28px',
              height: '30px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
            title={`Step Back -${currentStep}m`}
          >
            <SkipBack size={12} />
          </button>

          <button
            onClick={() => onLeadChange(Math.min(maxLead, currentLead + currentStep))}
            style={{
              background: '#050505',
              color: '#94a3b8',
              border: '1px solid #1f2937',
              borderRadius: '5px',
              width: '28px',
              height: '30px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
            title={`Step Forward +${currentStep}m`}
          >
            <SkipForward size={12} />
          </button>
        </div>

        {/* Lead Direct Input / Badge */}
        <div style={{ minWidth: '70px', textAlign: 'center' }}>
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
                  background: '#0a0a0a',
                  border: '1px solid #0284c7',
                  borderRadius: '3px',
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
                borderRadius: '4px',
                border: '1px dashed transparent',
                transition: 'all 0.15s',
              }}
              title="Click to jump to any custom minute"
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#0284c7')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'transparent')}
            >
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#38bdf8', fontVariantNumeric: 'tabular-nums' }}>
                T+{currentLead}m
              </div>
              <div style={{ fontSize: '9px', color: '#64748b' }}>Forecast Lead</div>
            </div>
          )}
        </div>

        {/* Timeline Slider with Multi-Horizon Sub-Segments & Buffer Visualizer */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <div style={{ position: 'relative', width: '100%', display: 'flex', alignItems: 'center' }}>
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
                zIndex: 2,
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: '#64748b' }}>
            <span style={{ color: currentLead === 0 ? '#38bdf8' : '#64748b' }}>T+0m (Analysis)</span>
            <span style={{ color: currentLead > 0 && currentLead <= 30 ? '#34d399' : '#64748b' }}>
              0-30m Optical Flow
            </span>
            <span style={{ color: currentLead > 30 && currentLead <= 120 ? '#38bdf8' : '#64748b' }}>
              30-120m Coupled SWMM/2D
            </span>
            <span style={{ color: currentLead > 120 ? '#c084fc' : '#64748b' }}>
              120-180m NWP
            </span>
            <span>T+180m</span>
          </div>
        </div>

        {/* Time Step Jump Options: +1m, +5m, +15m, Custom */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', background: '#050505', padding: '2px 5px', borderRadius: '5px', border: '1px solid #1f2937' }}>
          <span style={{ fontSize: '9px', color: '#64748b', fontWeight: 700 }}>Step:</span>
          {[1, 5, 15].map((s) => (
            <button
              key={s}
              onClick={() => handleStepSelect(s)}
              style={{
                background: (!isCustomStep && currentStep === s) ? '#0284c7' : 'transparent',
                color: (!isCustomStep && currentStep === s) ? '#fff' : '#94a3b8',
                border: 'none',
                borderRadius: '3px',
                padding: '2px 5px',
                fontSize: '9px',
                fontWeight: 700,
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
                style={{
                  width: '28px',
                  background: '#0a0a0a',
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
              <span style={{ fontSize: '9px', color: '#38bdf8' }}>m</span>
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
                borderRadius: '3px',
                padding: '2px 4px',
                fontSize: '9px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
              title="Enter custom time step (1-60m)"
            >
              Custom
            </button>
          )}
        </div>

        {/* Speed Multipliers */}
        <div style={{ display: 'flex', gap: '2px', background: '#050505', padding: '2px', borderRadius: '5px', border: '1px solid #1f2937' }}>
          {[1, 2, 5, 10].map((s) => (
            <button
              key={s}
              onClick={() => setPlaybackSpeed(s)}
              style={{
                background: playbackSpeed === s ? '#0284c7' : 'transparent',
                color: playbackSpeed === s ? '#fff' : '#64748b',
                border: 'none',
                borderRadius: '3px',
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #111827', paddingTop: '4px' }}>
        
        {/* Quick Milestone Time Jump Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ fontSize: '9px', color: '#64748b', fontWeight: 700 }}>Quick Jump:</span>
          {MILESTONE_JUMPS.map((m) => (
            <button
              key={m.lead}
              onClick={() => onLeadChange(m.lead)}
              style={{
                background: currentLead === m.lead ? '#1e293b' : '#050505',
                color: currentLead === m.lead ? '#38bdf8' : '#94a3b8',
                border: currentLead === m.lead ? '1px solid #0284c7' : '1px solid #171717',
                borderRadius: '3px',
                padding: '1px 6px',
                fontSize: '9px',
                fontWeight: 600,
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
              style={{
                background: isBuffering ? '#1e1b4b' : '#050505',
                color: isBuffering ? '#c084fc' : '#38bdf8',
                border: '1px solid #1f2937',
                borderRadius: '3px',
                padding: '2px 7px',
                fontSize: '9px',
                fontWeight: 700,
                cursor: isBuffering ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
              title="Pre-fetch and buffer the next 1 hour (60 min) of hydrodynamics into browser RAM"
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
