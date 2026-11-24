import React from 'react';
import type { BulbState } from '../types/bardi';

interface BulbVisualizerProps {
  state: BulbState;
  online: boolean;
  brand?: string;
}

export function computeBulbCssColor(state: BulbState, online: boolean): string {
  if (!online || !state.power) {
    return 'rgb(51, 65, 85)';
  }
  if (state.mode === 'colour') {
    const { r, g, b } = state.rgb;
    return `rgb(${r}, ${g}, ${b})`;
  }
  const ratio = Math.max(0, Math.min(100, state.cct_pct)) / 100;
  const r = Math.round(255 - ratio * 30);
  const g = Math.round(180 + ratio * 62);
  const b = Math.round(95 + ratio * 160);
  return `rgb(${r}, ${g}, ${b})`;
}

export const BulbVisualizer: React.FC<BulbVisualizerProps> = ({
  state,
  online,
  brand = 'LUMINA',
}) => {
  const active = online && state.power;
  const fillColor = computeBulbCssColor(state, online);
  const glowOpacity = active ? Math.max(0.2, state.brightness_pct / 100) : 0;
  const neckLabel = (brand || 'LUMINA').slice(0, 7).toUpperCase();

  return (
    <div
      className="relative flex flex-col items-center justify-center rounded-xl border border-slate-800/80 bg-slate-950/70 py-5 overflow-hidden"
      data-testid="bulb-visualizer"
    >
      <div
        className="pointer-events-none absolute h-28 w-28 rounded-full blur-2xl transition-all duration-300"
        style={{
          backgroundColor: fillColor,
          opacity: glowOpacity * 0.75,
          transform: `scale(${0.85 + glowOpacity * 0.45})`,
        }}
      />

      <svg
        viewBox="0 0 120 150"
        className="relative z-10 h-24 w-24 transition-transform duration-300"
        aria-label="Visualisasi Lampu Pintar"
      >
        <path
          d="M60 12 C32 12 16 32 16 56 C16 74 28 88 36 98 L84 98 C92 88 104 74 104 56 C104 32 88 12 60 12 Z"
          fill={fillColor}
          fillOpacity={active ? 0.35 + glowOpacity * 0.65 : 0.25}
          stroke={active ? fillColor : '#475569'}
          strokeWidth="3"
        />
        <path
          d="M36 98 L41 118 L79 118 L84 98 Z"
          fill="#e2e8f0"
          stroke="#94a3b8"
          strokeWidth="2"
        />
        <text
          x="60"
          y="112"
          textAnchor="middle"
          fill="#0f172a"
          fontSize="7.5"
          fontWeight="bold"
        >
          {neckLabel}
        </text>
        <rect x="44" y="118" width="32" height="16" rx="3" fill="#94a3b8" />
        <line x1="44" y1="124" x2="76" y2="124" stroke="#475569" strokeWidth="2" />
        <line x1="44" y1="129" x2="76" y2="129" stroke="#475569" strokeWidth="2" />
        <path d="M52 134 L68 134 L63 141 L57 141 Z" fill="#334155" />
      </svg>

      <div className="relative z-10 mt-2 flex items-center gap-2 text-xs text-slate-400">
        <span>
          {!online
            ? 'Tidak Terjangkau'
            : !state.power
              ? 'Lampu Mati (OFF)'
              : state.mode === 'colour'
                ? `RGB (${state.rgb.r}, ${state.rgb.g}, ${state.rgb.b}) • ${state.brightness_pct}%`
                : `${state.kelvin}K Putih • ${state.brightness_pct}%`}
        </span>
      </div>
    </div>
  );
};
