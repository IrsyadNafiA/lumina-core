import React, { useEffect, useState } from 'react';
import {
  Clock,
  Edit3,
  Palette,
  Power,
  RefreshCw,
  Repeat,
  Sparkles,
  Sun,
  Trash2,
  WifiOff,
  Zap,
} from 'lucide-react';
import type {
  AutomationConfigInput,
  AutomationMode,
  ColorPalette,
  DeviceView,
  LightingCommandInput,
  PresetView,
  RGBColor,
  TimerInput,
  WorkMode,
} from '../types/bardi';
import { useDebouncedCallback } from '../hooks/useDebouncedCallback';
import { StatusBadge } from './ui/StatusBadge';
import { SliderControl } from './ui/SliderControl';
import { BulbVisualizer } from './BulbVisualizer';

interface DeviceCardProps {
  device: DeviceView;
  presets: PresetView[];
  onCommand: (deviceId: string, command: LightingCommandInput) => Promise<void>;
  onAutomation?: (deviceId: string, config: AutomationConfigInput) => Promise<void>;
  onTimer?: (deviceId: string, timer: TimerInput) => Promise<void>;
  onRefresh: (deviceId: string) => Promise<void>;
  onEdit: (device: DeviceView) => void;
  onDelete: (deviceId: string) => Promise<void>;
}

function rgbToHex({ r, g, b }: RGBColor): string {
  const toHex = (n: number) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function hexToRgb(hex: string): RGBColor {
  const cleaned = hex.replace('#', '');
  if (cleaned.length !== 6) return { r: 255, g: 180, b: 100 };
  return {
    r: parseInt(cleaned.slice(0, 2), 16) || 0,
    g: parseInt(cleaned.slice(2, 4), 16) || 0,
    b: parseInt(cleaned.slice(4, 6), 16) || 0,
  };
}

export function formatCountdown(remainingSeconds: number): string {
  const clamped = Math.max(0, Math.floor(remainingSeconds));
  const hours = Math.floor(clamped / 3600);
  const minutes = Math.floor((clamped % 3600) / 60);
  const seconds = clamped % 60;
  const mm = String(minutes).padStart(2, '0');
  const ss = String(seconds).padStart(2, '0');
  if (hours > 0) {
    const hh = String(hours).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  }
  return `${mm}:${ss}`;
}

function computeRemainingSec(isoTimestamp: string | null | undefined): number {
  if (!isoTimestamp) return 0;
  const diffMs = new Date(isoTimestamp).getTime() - Date.now();
  if (!Number.isFinite(diffMs) || diffMs <= 0) return 0;
  return Math.ceil(diffMs / 1000);
}

const QUICK_COLORS: { label: string; rgb: RGBColor }[] = [
  { label: 'Merah', rgb: { r: 239, g: 68, b: 68 } },
  { label: 'Oranye', rgb: { r: 249, g: 115, b: 22 } },
  { label: 'Hijau', rgb: { r: 16, g: 185, b: 129 } },
  { label: 'Cyan', rgb: { r: 6, g: 182, b: 212 } },
  { label: 'Biru', rgb: { r: 59, g: 130, b: 246 } },
  { label: 'Ungu', rgb: { r: 168, g: 85, b: 247 } },
];

const AUTOMATION_OPTIONS: { id: AutomationMode; label: string }[] = [
  { id: 'none', label: 'Manual' },
  { id: 'color_cycle', label: 'Auto RGB Loop' },
  { id: 'circadian', label: 'Circadian Sync' },
  { id: 'pomodoro', label: 'Pomodoro 25/5' },
  { id: 'sleep_fade', label: 'Sleep Fade 15m' },
];

export const DeviceCard: React.FC<DeviceCardProps> = ({
  device,
  presets,
  onCommand,
  onAutomation,
  onTimer,
  onRefresh,
  onEdit,
  onDelete,
}) => {
  const [brightness, setBrightness] = useState(device.state.brightness_pct);
  const [cct, setCct] = useState(device.state.cct_pct);
  const [rgb, setRgb] = useState<RGBColor>(device.state.rgb);
  const [palette, setPalette] = useState<ColorPalette>(
    device.automation_palette ?? 'aurora',
  );
  const [customMinutes, setCustomMinutes] = useState<number>(20);
  const [customTimerPower, setCustomTimerPower] = useState<boolean>(false);
  const [timerRemainingSec, setTimerRemainingSec] = useState<number>(() =>
    computeRemainingSec(device.timer_expires_at),
  );
  const [autoRemainingSec, setAutoRemainingSec] = useState<number>(() =>
    computeRemainingSec(device.automation_expires_at),
  );
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setBrightness(device.state.brightness_pct);
    setCct(device.state.cct_pct);
    setRgb(device.state.rgb);
  }, [device.state.brightness_pct, device.state.cct_pct, device.state.rgb]);

  // Live 1-second ticking digital countdown for both Countdown Timer and Sleep Fade / Pomodoro
  useEffect(() => {
    const initialTimerSec = computeRemainingSec(device.timer_expires_at);
    const initialAutoSec = computeRemainingSec(device.automation_expires_at);
    setTimerRemainingSec(initialTimerSec);
    setAutoRemainingSec(initialAutoSec);

    if (initialTimerSec <= 0 && initialAutoSec <= 0) {
      return;
    }

    let expiryTriggered = false;
    const interval = setInterval(() => {
      const nextTimer = computeRemainingSec(device.timer_expires_at);
      const nextAuto = computeRemainingSec(device.automation_expires_at);
      setTimerRemainingSec(nextTimer);
      setAutoRemainingSec(nextAuto);

      if (
        !expiryTriggered &&
        ((device.timer_expires_at && nextTimer === 0) ||
          (device.automation_expires_at && nextAuto === 0))
      ) {
        expiryTriggered = true;
        void onRefresh(device.device_id);
      }

      if (nextTimer === 0 && nextAuto === 0) {
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [
    device.device_id,
    device.timer_expires_at,
    device.automation_expires_at,
    onRefresh,
  ]);

  const [debouncedCommand] = useDebouncedCallback((cmd: LightingCommandInput) => {
    void onCommand(device.device_id, cmd);
  }, 150);

  const handleImmediateCommand = async (cmd: LightingCommandInput) => {
    setBusy(true);
    try {
      await onCommand(device.device_id, cmd);
    } finally {
      setBusy(false);
    }
  };

  const handleRefresh = async () => {
    setBusy(true);
    try {
      await onRefresh(device.device_id);
    } finally {
      setBusy(false);
    }
  };

  const handleBrightnessChange = (val: number) => {
    setBrightness(val);
    debouncedCommand({ brightness_pct: val });
  };

  const handleCctChange = (val: number) => {
    setCct(val);
    debouncedCommand({ cct_pct: val, mode: 'white' });
  };

  const handleColorInput = (hex: string) => {
    const nextRgb = hexToRgb(hex);
    setRgb(nextRgb);
    debouncedCommand({ rgb: nextRgb, mode: 'colour' });
  };

  const handleApplyCustomTimer = () => {
    if (!onTimer) return;
    const clamped = Math.max(1, Math.min(720, Math.round(customMinutes || 1)));
    setCustomMinutes(clamped);
    void onTimer(device.device_id, {
      minutes: clamped,
      action_power: customTimerPower,
    });
  };

  const kelvinPreview = 2700 + Math.round((cct / 100) * 3800);
  const brandName = device.brand ?? 'Tuya Generic';
  const liveWatts = device.live_watts ?? (device.online && device.state.power ? 7.2 : 0.4);
  const ratedWatts = device.rated_wattage ?? 9.0;
  const activeAuto = device.automation_mode ?? 'none';

  const totalTimerSec =
    device.timer_total_seconds && device.timer_total_seconds > 0
      ? device.timer_total_seconds
      : Math.max(timerRemainingSec, 60);
  const timerProgressPct =
    timerRemainingSec > 0
      ? Math.max(2, Math.min(100, Math.round((timerRemainingSec / totalTimerSec) * 100)))
      : 0;

  return (
    <article
      className="flex flex-col justify-between rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-lg transition hover:border-slate-700"
      data-testid={`device-card-${device.device_id}`}
    >
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded-md bg-cyan-500/15 px-2 py-0.5 text-xs font-semibold text-cyan-300">
                {brandName}
              </span>
              <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-300">
                {device.room}
              </span>
              <span className="font-mono text-xs text-slate-400">
                v{device.protocol_version} • Tipe {device.bulb_type}
              </span>
            </div>
            <h3 className="mt-1.5 text-base font-semibold text-slate-100">{device.name}</h3>
            <p className="font-mono text-xs text-slate-400">
              IP: {device.ip_address} • Key: {device.masked_key}
            </p>
          </div>

          <button
            type="button"
            disabled={busy || !device.online}
            onClick={() =>
              void handleImmediateCommand({ power: !device.state.power })
            }
            aria-label={`Power ${device.name}`}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition ${
              device.online && device.state.power
                ? 'border-cyan-400/50 bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/25'
                : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            <Power className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <StatusBadge online={device.online} connectionMode={device.connection_mode} />
          <span
            className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-0.5 font-mono text-xs font-medium text-amber-300 ring-1 ring-amber-500/30"
            title="Konsumsi Daya Real-Time"
          >
            <Zap className="h-3 w-3" />
            {liveWatts.toFixed(1)}W / {ratedWatts}W •{' '}
            {device.power_source === 'hardware_sensor' ? 'Sensor DPS 19' : 'Powercalc'}
          </span>
        </div>

        <div className="mt-4">
          <BulbVisualizer
            brand={brandName}
            state={{
              ...device.state,
              brightness_pct: brightness,
              cct_pct: cct,
              kelvin: kelvinPreview,
              rgb,
            }}
            online={device.online}
          />
        </div>

        {!device.online && (
          <div
            className="mt-4 rounded-xl border border-rose-500/30 bg-rose-950/30 p-3 text-xs text-rose-200"
            role="alert"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 font-semibold">
                <WifiOff className="h-4 w-4 shrink-0 text-rose-400" />
                <span>Lampu Fisik Tidak Terjangkau (Offline)</span>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void handleRefresh()}
                className="inline-flex items-center gap-1 rounded-lg bg-rose-500/20 px-2.5 py-1 font-medium text-rose-200 hover:bg-rose-500/30"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Coba Lagi
              </button>
            </div>
            {device.last_error && (
              <p className="mt-1 font-mono text-[11px] text-rose-300/90">
                {device.last_error}
              </p>
            )}
          </div>
        )}

        <div className="mt-4 grid grid-cols-3 gap-1.5 rounded-xl bg-slate-950 p-1">
          {(
            [
              { id: 'white', label: 'Putih (CCT)', icon: Sun },
              { id: 'colour', label: 'Warna RGB', icon: Palette },
              { id: 'scene', label: 'Scene', icon: Sparkles },
            ] as { id: WorkMode; label: string; icon: React.ElementType }[]
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              disabled={!device.online || busy}
              onClick={() => void handleImmediateCommand({ mode: id, power: true })}
              className={`flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium transition ${
                device.state.mode === id
                  ? 'bg-slate-800 text-cyan-300 shadow'
                  : 'text-slate-400 hover:text-slate-200'
              } disabled:cursor-not-allowed disabled:opacity-40`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-3">
          <SliderControl
            id={`brightness-${device.device_id}`}
            label="Kecerahan (Brightness)"
            value={brightness}
            min={1}
            max={100}
            unit="%"
            disabled={!device.online}
            onChange={handleBrightnessChange}
          />

          <SliderControl
            id={`cct-${device.device_id}`}
            label={`Suhu Warna Putih (${kelvinPreview}K)`}
            value={cct}
            min={0}
            max={100}
            unit="%"
            accentClass="accent-amber-400"
            disabled={!device.online}
            onChange={handleCctChange}
          />

          <div className="space-y-1.5 pt-1">
            <div className="flex items-center justify-between text-xs">
              <label
                htmlFor={`rgb-${device.device_id}`}
                className="font-medium text-slate-300"
              >
                Warna RGB
              </label>
              <span className="font-mono text-slate-300">{rgbToHex(rgb)}</span>
            </div>
            <div className="flex items-center gap-2">
              <input
                id={`rgb-${device.device_id}`}
                type="color"
                disabled={!device.online}
                value={rgbToHex(rgb)}
                onChange={(e) => handleColorInput(e.target.value)}
                className="h-8 w-12 cursor-pointer rounded border border-slate-700 bg-slate-800 p-0.5 disabled:cursor-not-allowed disabled:opacity-40"
              />
              <div className="flex flex-1 flex-wrap items-center gap-1.5">
                {QUICK_COLORS.map((swatch) => (
                  <button
                    key={swatch.label}
                    type="button"
                    disabled={!device.online || busy}
                    title={swatch.label}
                    aria-label={`Warna ${swatch.label}`}
                    onClick={() => {
                      setRgb(swatch.rgb);
                      void handleImmediateCommand({
                        rgb: swatch.rgb,
                        mode: 'colour',
                        power: true,
                      });
                    }}
                    className="h-6 w-6 rounded-full border border-white/20 transition hover:scale-110 disabled:cursor-not-allowed disabled:opacity-40"
                    style={{
                      backgroundColor: `rgb(${swatch.rgb.r}, ${swatch.rgb.g}, ${swatch.rgb.b})`,
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Automatic Color & Ambience Engine */}
        {onAutomation && (
          <div className="mt-4 border-t border-slate-800/80 pt-3">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="inline-flex items-center gap-1.5 font-medium text-slate-300">
                <Repeat className="h-3.5 w-3.5 text-violet-400" />
                Switch Warna Otomatis & Ambience
              </span>
              {activeAuto !== 'none' && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-500/20 px-2.5 py-0.5 font-mono text-[10px] font-semibold text-violet-200">
                  <span>Aktif: {activeAuto}</span>
                  {autoRemainingSec > 0 && (
                    <span data-testid={`auto-countdown-${device.device_id}`}>
                      • {formatCountdown(autoRemainingSec)}
                    </span>
                  )}
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {AUTOMATION_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  disabled={!device.online || busy}
                  onClick={() =>
                    void onAutomation(device.device_id, {
                      mode: opt.id,
                      palette,
                      interval_sec: 5,
                      duration_minutes: 15,
                    })
                  }
                  className={`rounded-lg border px-2.5 py-1 text-xs transition ${
                    activeAuto === opt.id
                      ? 'border-violet-400 bg-violet-500/20 font-semibold text-violet-200'
                      : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-violet-500/40'
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {activeAuto === 'color_cycle' && (
              <div className="mt-2 flex items-center gap-1.5 text-xs">
                <span className="text-slate-400">Palet:</span>
                {(['aurora', 'cyberpunk', 'sunset', 'ocean'] as ColorPalette[]).map(
                  (pal) => (
                    <button
                      key={pal}
                      type="button"
                      onClick={() => {
                        setPalette(pal);
                        void onAutomation(device.device_id, {
                          mode: 'color_cycle',
                          palette: pal,
                          interval_sec: 5,
                        });
                      }}
                      className={`rounded-md px-2 py-0.5 capitalize ${
                        palette === pal
                          ? 'bg-cyan-500/20 text-cyan-300 font-semibold'
                          : 'bg-slate-950 text-slate-400'
                      }`}
                    >
                      {pal}
                    </button>
                  ),
                )}
              </div>
            )}
          </div>
        )}

        {/* Live Digital Countdown Timer + Progress Bar + Custom Minutes (REQ-109) */}
        {onTimer && (
          <div className="mt-3 border-t border-slate-800/80 pt-3">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="inline-flex items-center gap-1.5 font-medium text-slate-300">
                <Clock className="h-3.5 w-3.5 text-cyan-400" />
                Countdown Timer Otomatis
              </span>
              {device.timer_expires_at && timerRemainingSec > 0 && (
                <div className="flex items-center gap-1.5">
                  <span
                    className="rounded-lg bg-cyan-500/20 px-2 py-0.5 font-mono text-xs font-bold text-cyan-300 ring-1 ring-cyan-500/40"
                    data-testid={`countdown-clock-${device.device_id}`}
                  >
                    {formatCountdown(timerRemainingSec)}
                  </span>
                  <span className="text-[10px] font-semibold text-slate-400">
                    → {device.timer_target_power ? 'ON' : 'OFF'}
                  </span>
                </div>
              )}
            </div>

            {/* Active Countdown Visual Progress Bar */}
            {device.timer_expires_at && timerRemainingSec > 0 && (
              <div className="mb-2.5 space-y-1">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-400 transition-all duration-500"
                    style={{ width: `${timerProgressPct}%` }}
                    data-testid={`countdown-progress-${device.device_id}`}
                  />
                </div>
                <p className="text-[11px] text-cyan-300/90">
                  Timer Aktif: Sisa waktu{' '}
                  <strong className="font-mono">{formatCountdown(timerRemainingSec)}</strong>{' '}
                  sebelum lampu otomatis{' '}
                  <strong>{device.timer_target_power ? 'Menyala (ON)' : 'Mati (OFF)'}</strong>
                </p>
              </div>
            )}

            {/* Quick Timer Presets */}
            <div className="flex flex-wrap gap-1.5">
              {[15, 30, 60].map((mins) => (
                <button
                  key={mins}
                  type="button"
                  disabled={!device.online || busy}
                  onClick={() =>
                    void onTimer(device.device_id, { minutes: mins, action_power: false })
                  }
                  className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1 text-xs text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300 disabled:opacity-40"
                >
                  {mins}m OFF
                </button>
              ))}
              {device.timer_expires_at && (
                <button
                  type="button"
                  onClick={() =>
                    void onTimer(device.device_id, { minutes: 0, action_power: false })
                  }
                  className="rounded-lg bg-rose-500/15 px-2.5 py-1 text-xs font-medium text-rose-300 hover:bg-rose-500/25"
                >
                  Batal Timer
                </button>
              )}
            </div>

            {/* Custom Minutes & Action Selector */}
            <div className="mt-2 flex items-center gap-1.5 text-xs">
              <input
                type="number"
                min={1}
                max={720}
                disabled={!device.online || busy}
                aria-label={`Menit Timer Kustom ${device.name}`}
                value={customMinutes}
                onChange={(e) => setCustomMinutes(Number(e.target.value) || 1)}
                className="w-16 rounded-lg border border-slate-800 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100 disabled:opacity-40"
              />
              <span className="text-slate-400">menit →</span>
              <select
                aria-label={`Aksi Timer Kustom ${device.name}`}
                disabled={!device.online || busy}
                value={customTimerPower ? 'ON' : 'OFF'}
                onChange={(e) => setCustomTimerPower(e.target.value === 'ON')}
                className="rounded-lg border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-200 disabled:opacity-40"
              >
                <option value="OFF">Matikan (OFF)</option>
                <option value="ON">Nyalakan (ON)</option>
              </select>
              <button
                type="button"
                disabled={!device.online || busy}
                onClick={handleApplyCustomTimer}
                className="rounded-lg bg-cyan-500/20 px-2.5 py-1 font-semibold text-cyan-300 hover:bg-cyan-500/30 disabled:opacity-40"
              >
                Set Timer
              </button>
            </div>
          </div>
        )}

        {presets.length > 0 && (
          <div className="mt-3 border-t border-slate-800/80 pt-3">
            <p className="mb-2 text-xs font-medium text-slate-400">Preset Cepat</p>
            <div className="flex flex-wrap gap-1.5">
              {presets.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  disabled={!device.online || busy}
                  onClick={() =>
                    void handleImmediateCommand({ preset_id: preset.id, power: true })
                  }
                  className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1 text-xs text-slate-300 transition hover:border-cyan-500/40 hover:text-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {preset.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-slate-800 pt-3 text-xs">
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleRefresh()}
          className="inline-flex items-center gap-1.5 text-slate-400 hover:text-slate-200"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
          Sinkronkan
        </button>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onEdit(device)}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2.5 py-1 text-slate-300 hover:bg-slate-700"
          >
            <Edit3 className="h-3.5 w-3.5" />
            Pengaturan
          </button>
          <button
            type="button"
            onClick={() => void onDelete(device.device_id)}
            aria-label={`Hapus ${device.name}`}
            className="inline-flex items-center gap-1 rounded-lg bg-rose-500/10 px-2.5 py-1 text-rose-300 hover:bg-rose-500/20"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </article>
  );
};
