import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarClock,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  FileJson,
  Lightbulb,
  Lock,
  PanelTopClose,
  PanelTopOpen,
  Plus,
  Power,
  Radar,
  Sparkles,
  Trash2,
  Wifi,
  Zap,
} from 'lucide-react';
import type {
  AutomationConfigInput,
  DeviceCreateInput,
  DeviceUpdateInput,
  DeviceView,
  DiscoveredDevice,
  EnergySummaryView,
  LightingCommandInput,
  PresetView,
  ScheduleView,
  TimerInput,
} from './types/bardi';
import { ApiError, BardiApiClient } from './lib/api';
import { useBardiSocket } from './hooks/useBardiSocket';
import { DeviceCard } from './components/DeviceCard';
import { DeviceFormModal } from './components/DeviceFormModal';
import { LanScannerModal } from './components/LanScannerModal';
import { AuthTokenModal } from './components/AuthTokenModal';
import { Modal } from './components/ui/Modal';

interface AppProps {
  apiClient?: BardiApiClient;
}

export const App: React.FC<AppProps> = ({ apiClient }) => {
  const client = useMemo(() => apiClient ?? new BardiApiClient(), [apiClient]);

  const [devices, setDevices] = useState<DeviceView[]>([]);
  const [presets, setPresets] = useState<PresetView[]>([]);
  const [schedules, setSchedules] = useState<ScheduleView[]>([]);
  const [energySummary, setEnergySummary] = useState<EnergySummaryView | null>(null);
  const [loading, setLoading] = useState(true);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<string>('ALL');
  const [studioTab, setStudioTab] = useState<'control' | 'energy' | 'schedules'>('control');
  const [navbarCollapsed, setNavbarCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem('luminacore_navbar_collapsed') === 'true';
    } catch {
      return false;
    }
  });
  const [telemetryCollapsed, setTelemetryCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem('luminacore_telemetry_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const toggleNavbarCollapsed = useCallback(() => {
    setNavbarCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem('luminacore_navbar_collapsed', String(next));
      } catch {
        // Ignore storage errors
      }
      return next;
    });
  }, []);

  const toggleTelemetryCollapsed = useCallback(() => {
    setTelemetryCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem('luminacore_telemetry_collapsed', String(next));
      } catch {
        // Ignore storage errors
      }
      return next;
    });
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        toggleNavbarCollapsed();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleNavbarCollapsed]);

  const [formOpen, setFormOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<DeviceView | null>(null);
  const [prefillDiscovered, setPrefillDiscovered] = useState<DiscoveredDevice | null>(
    null,
  );

  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredDevice[]>([]);
  const [scanError, setScanError] = useState<string | null>(null);

  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [schedName, setSchedName] = useState('Malam Hemat Energi');
  const [schedTime, setSchedTime] = useState('22:30');
  const [schedTarget, setSchedTarget] = useState('ALL');
  const [schedPower, setSchedPower] = useState(false);

  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importJsonText, setImportJsonText] = useState('');
  const [importError, setImportError] = useState<string | null>(null);

  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [accessToken, setAccessToken] = useState(client.getAccessToken());

  const refreshTelemetry = useCallback(async () => {
    try {
      const [energy, scheds] = await Promise.all([
        client.getEnergySummary(),
        client.listSchedules(),
      ]);
      setEnergySummary(energy);
      setSchedules(scheds);
    } catch {
      // Optional telemetry endpoints
    }
  }, [client]);

  const loadInitialData = useCallback(async () => {
    setLoading(true);
    setBannerError(null);
    try {
      const authStatus = await client.getAuthStatus();
      if (authStatus.auth_required && !authStatus.authenticated) {
        setAuthModalOpen(true);
        setLoading(false);
        return;
      }
      const [devList, presetList] = await Promise.all([
        client.listDevices(),
        client.listPresets(),
      ]);
      setDevices(devList);
      setPresets(presetList);
      await refreshTelemetry();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthModalOpen(true);
      } else {
        setBannerError(
          err instanceof Error ? err.message : 'Gagal memuat data perangkat',
        );
      }
    } finally {
      setLoading(false);
    }
  }, [client, refreshTelemetry]);

  useEffect(() => {
    void loadInitialData();
  }, [loadInitialData]);

  const handleSnapshot = useCallback((snapshot: DeviceView[]) => {
    setDevices(snapshot);
  }, []);

  const handleDeviceUpdated = useCallback((updated: DeviceView) => {
    setDevices((prev) => {
      const idx = prev.findIndex((d) => d.device_id === updated.device_id);
      if (idx === -1) return [...prev, updated];
      const clone = [...prev];
      clone[idx] = updated;
      return clone;
    });
  }, []);

  const handleDeviceRemoved = useCallback((deviceId: string) => {
    setDevices((prev) => prev.filter((d) => d.device_id !== deviceId));
  }, []);

  const { connected: wsConnected } = useBardiSocket({
    accessToken,
    enabled: !authModalOpen,
    onSnapshot: handleSnapshot,
    onDeviceUpdated: handleDeviceUpdated,
    onDeviceRemoved: handleDeviceRemoved,
  });

  const handleApiError = useCallback((err: unknown, fallbackMessage: string) => {
    if (err instanceof ApiError && err.status === 401) {
      setAuthModalOpen(true);
      return;
    }
    setBannerError(err instanceof Error ? err.message : fallbackMessage);
  }, []);

  const handleCommand = async (deviceId: string, command: LightingCommandInput) => {
    setBannerError(null);
    try {
      const updated = await client.sendCommand(deviceId, command);
      handleDeviceUpdated(updated);
      void refreshTelemetry();
    } catch (err) {
      handleApiError(err, 'Gagal mengirim perintah ke lampu pintar');
      try {
        const refreshed = await client.listDevices();
        setDevices(refreshed);
      } catch {
        // Keep existing list
      }
    }
  };

  const handleAutomation = async (
    deviceId: string,
    config: AutomationConfigInput,
  ) => {
    setBannerError(null);
    try {
      const updated = await client.setAutomation(deviceId, config);
      handleDeviceUpdated(updated);
    } catch (err) {
      handleApiError(err, 'Gagal mengaktifkan mode otomasi warna');
    }
  };

  const handleTimer = async (deviceId: string, timer: TimerInput) => {
    setBannerError(null);
    try {
      const updated = await client.setTimer(deviceId, timer);
      handleDeviceUpdated(updated);
    } catch (err) {
      handleApiError(err, 'Gagal mengatur countdown timer');
    }
  };

  const handleRefreshDevice = async (deviceId: string) => {
    setBannerError(null);
    try {
      const updated = await client.refreshDevice(deviceId);
      handleDeviceUpdated(updated);
      void refreshTelemetry();
    } catch (err) {
      handleApiError(err, 'Lampu tidak merespons di jaringan lokal');
      try {
        const refreshed = await client.listDevices();
        setDevices(refreshed);
      } catch {
        // Keep existing list
      }
    }
  };

  const handleCreateDevice = async (input: DeviceCreateInput) => {
    const created = await client.createDevice(input);
    handleDeviceUpdated(created);
    void refreshTelemetry();
  };

  const handleUpdateDevice = async (deviceId: string, input: DeviceUpdateInput) => {
    const updated = await client.updateDevice(deviceId, input);
    handleDeviceUpdated(updated);
    void refreshTelemetry();
  };

  const handleDeleteDevice = async (deviceId: string) => {
    setBannerError(null);
    try {
      await client.deleteDevice(deviceId);
      handleDeviceRemoved(deviceId);
      void refreshTelemetry();
    } catch (err) {
      handleApiError(err, 'Gagal menghapus perangkat');
    }
  };

  const handleRunScan = async () => {
    setScannerOpen(true);
    setScanning(true);
    setScanError(null);
    try {
      const found = await client.scanDevices();
      setDiscovered(found);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setScannerOpen(false);
        setAuthModalOpen(true);
      } else {
        setScanError(
          err instanceof Error ? err.message : 'Gagal melakukan pemindaian LAN',
        );
      }
    } finally {
      setScanning(false);
    }
  };

  const handleAllPower = async (powerState: boolean) => {
    setBannerError(null);
    try {
      const onlineDevices = devices.filter((d) => d.online);
      const results = await Promise.allSettled(
        onlineDevices.map((d) => client.sendCommand(d.device_id, { power: powerState })),
      );
      const unauthorized = results.find(
        (r) =>
          r.status === 'rejected' &&
          r.reason instanceof ApiError &&
          r.reason.status === 401,
      );
      if (unauthorized) {
        setAuthModalOpen(true);
        return;
      }
      const refreshed = await client.listDevices();
      setDevices(refreshed);
      void refreshTelemetry();
    } catch (err) {
      handleApiError(err, 'Gagal mengubah status daya seluruh lampu');
    }
  };

  const handleCreateSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await client.createSchedule({
        name: schedName,
        time_hhmm: schedTime,
        target_device_id: schedTarget,
        action_power: schedPower,
        enabled: true,
      });
      setSchedules((prev) => [...prev, created]);
      setSchedName('');
    } catch (err) {
      handleApiError(err, 'Gagal menyimpan jadwal');
    }
  };

  const handleToggleSchedule = async (scheduleId: string, enabled: boolean) => {
    setBannerError(null);
    try {
      const updated = await client.toggleSchedule(scheduleId, enabled);
      setSchedules((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      handleApiError(err, 'Gagal memperbarui status jadwal');
    }
  };

  const handleDeleteSchedule = async (scheduleId: string) => {
    setBannerError(null);
    try {
      await client.deleteSchedule(scheduleId);
      setSchedules((prev) => prev.filter((item) => item.id !== scheduleId));
    } catch (err) {
      handleApiError(err, 'Gagal menghapus jadwal');
    }
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setImportError(null);
    try {
      const parsed = JSON.parse(importJsonText) as unknown;
      const list = Array.isArray(parsed)
        ? (parsed as Record<string, unknown>[])
        : parsed &&
            typeof parsed === 'object' &&
            Array.isArray((parsed as { devices?: unknown }).devices)
          ? ((parsed as { devices: Record<string, unknown>[] }).devices)
          : null;
      if (!list || list.length === 0) {
        setImportError('Format JSON harus berupa array perangkat dari devices.json TinyTuya.');
        return;
      }
      await client.importTinyTuyaDevices(list);
      const refreshed = await client.listDevices();
      setDevices(refreshed);
      await refreshTelemetry();
      setImportModalOpen(false);
      setImportJsonText('');
    } catch (err) {
      setImportError(
        err instanceof Error ? err.message : 'Format JSON tidak valid',
      );
    }
  };

  const rooms = useMemo(() => {
    const unique = new Set(devices.map((d) => d.room));
    return ['ALL', ...Array.from(unique)];
  }, [devices]);

  const filteredDevices = useMemo(() => {
    if (selectedRoom === 'ALL') return devices;
    return devices.filter((d) => d.room === selectedRoom);
  }, [devices, selectedRoom]);

  const virtualCount = devices.filter((d) => d.connection_mode === 'virtual').length;
  const lanCount = devices.filter((d) => d.connection_mode === 'lan').length;
  const totalLiveWatts =
    energySummary?.total_live_watts ??
    devices.reduce((acc, d) => acc + (d.live_watts ?? 0), 0);
  const estMonthlyIdr =
    energySummary?.estimated_monthly_cost_idr ??
    Math.round(((totalLiveWatts * 6 * 30) / 1000) * 1444.7);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Dynamic Collapsible Top Navigation Bar / Floating Mini Pill (REQ-110) */}
      {navbarCollapsed ? (
        <div
          className="fixed top-3 right-4 z-40 flex items-center gap-2 rounded-2xl border border-slate-800/90 bg-slate-900/90 px-3 py-2 shadow-2xl backdrop-blur-md"
          data-testid="collapsed-navbar-pill"
        >
          <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-300">
            <img
              src="/luminacore-icon.svg"
              alt="LuminaCore"
              className="h-5 w-5 shrink-0"
            />
            <span>LuminaCore</span>
          </div>
          <span className="font-mono text-xs text-amber-300">
            {totalLiveWatts.toFixed(1)}W
          </span>
          <button
            type="button"
            onClick={() => {
              setEditingDevice(null);
              setPrefillDiscovered(null);
              setFormOpen(true);
            }}
            title="Tambah Lampu Manual"
            className="rounded-lg bg-cyan-500/20 p-1.5 text-cyan-300 hover:bg-cyan-500/30"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={toggleNavbarCollapsed}
            aria-label="Buka Navbar"
            data-testid="expand-navbar-btn"
            title="Buka Navbar (Alt+N)"
            className="inline-flex items-center gap-1 rounded-xl bg-cyan-500 px-2.5 py-1 text-xs font-semibold text-slate-950 hover:bg-cyan-400"
          >
            <PanelTopOpen className="h-3.5 w-3.5" />
            <span>Buka Menu</span>
          </button>
        </div>
      ) : (
        <header
          className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md transition-all"
          data-testid="expanded-navbar"
        >
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-900/90 p-1.5 ring-1 ring-cyan-500/30 shadow-sm shadow-cyan-500/10">
                <img
                  src="/luminacore-icon.svg"
                  alt="LuminaCore Studio Logo"
                  className="h-full w-full object-contain"
                />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-lg font-bold tracking-tight text-slate-100">
                    LuminaCore Studio
                  </h1>
                  <span className="rounded-full bg-cyan-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-cyan-300">
                    Universal Smart Lighting & Local IoT Hub
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Multi-Brand Control (BARDI, Krisbow, Hannochs, Arbit, Avaro, Tuya) • Powercalc • Ambience Engine
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium ${
                  wsConnected
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                    : 'border-slate-800 bg-slate-900 text-slate-400'
                }`}
              >
                <Wifi className="h-3.5 w-3.5" />
                {wsConnected ? 'WebSocket Live' : 'REST Sync'}
              </span>

              <button
                type="button"
                onClick={() => setScheduleModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-violet-500/40 bg-violet-500/10 px-3 py-2 text-xs font-semibold text-violet-300 transition hover:bg-violet-500/20"
              >
                <CalendarClock className="h-4 w-4" />
                Jadwal ({schedules.length})
              </button>

              <button
                type="button"
                onClick={() => setImportModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-800"
              >
                <FileJson className="h-4 w-4 text-amber-400" />
                Import TinyTuya
              </button>

              <button
                type="button"
                onClick={() => void handleRunScan()}
                className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-3.5 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/20"
              >
                <Radar className="h-4 w-4" />
                Scan Wi-Fi Lokal
              </button>

              <button
                type="button"
                onClick={() => {
                  setEditingDevice(null);
                  setPrefillDiscovered(null);
                  setFormOpen(true);
                }}
                className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500 px-3.5 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400"
              >
                <Plus className="h-4 w-4" />
                Tambah Lampu Manual
              </button>

              <button
                type="button"
                onClick={() => setAuthModalOpen(true)}
                aria-label="Konfigurasi Token Akses"
                className="rounded-xl border border-slate-800 bg-slate-900 p-2 text-slate-400 hover:text-slate-200"
              >
                <Lock className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={toggleNavbarCollapsed}
                aria-label="Sembunyikan Navbar"
                data-testid="collapse-navbar-btn"
                title="Lipat Navbar ke Mode Fokus (Alt+N)"
                className="inline-flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900 px-2.5 py-2 text-xs font-medium text-slate-300 hover:border-slate-700 hover:text-slate-100"
              >
                <PanelTopClose className="h-4 w-4 text-cyan-400" />
                <span className="hidden sm:inline">Lipat Navbar</span>
              </button>
            </div>
          </div>
        </header>
      )}

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {/* Toggle Bar for Collapsible Telemetry & Info Panels */}
        <div className="mb-3 flex items-center justify-between">
          <button
            type="button"
            onClick={toggleTelemetryCollapsed}
            data-testid="toggle-telemetry-btn"
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-slate-700 hover:text-slate-100"
          >
            {telemetryCollapsed ? (
              <>
                <Eye className="h-3.5 w-3.5 text-cyan-400" />
                <span>Tampilkan Ringkasan Daya & Info</span>
                <ChevronDown className="h-3.5 w-3.5" />
              </>
            ) : (
              <>
                <EyeOff className="h-3.5 w-3.5 text-slate-400" />
                <span>Sembunyikan Ringkasan Daya & Info</span>
                <ChevronUp className="h-3.5 w-3.5" />
              </>
            )}
          </button>

          {devices.length > 0 && telemetryCollapsed && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void handleAllPower(true)}
                className="inline-flex items-center gap-1 rounded-xl bg-emerald-500/20 px-2.5 py-1 text-xs font-semibold text-emerald-300"
              >
                <Power className="h-3 w-3" />
                Nyalakan Semua
              </button>
              <button
                type="button"
                onClick={() => void handleAllPower(false)}
                className="inline-flex items-center gap-1 rounded-xl bg-slate-800 px-2.5 py-1 text-xs font-semibold text-slate-300"
              >
                Matikan Semua
              </button>
            </div>
          )}
        </div>

        {/* Smart Powercalc & PLN Cost Telemetry Cards */}
        {!telemetryCollapsed && (
          <>
            <section
              className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
              data-testid="energy-summary-bar"
            >
              <div className="rounded-2xl border border-amber-500/25 bg-slate-900/90 p-4">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Daya Aktif Real-Time</span>
                  <Zap className="h-4 w-4 text-amber-400" />
                </div>
                <p className="mt-1 font-mono text-xl font-bold text-amber-300">
                  {totalLiveWatts.toFixed(2)} W
                </p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  Smart Powercalc + Standby Wi-Fi 0.4W
                </p>
              </div>

              <div className="rounded-2xl border border-cyan-500/25 bg-slate-900/90 p-4">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Energi Terpakai Hari Ini</span>
                  <Sparkles className="h-4 w-4 text-cyan-400" />
                </div>
                <p className="mt-1 font-mono text-xl font-bold text-cyan-300">
                  {(energySummary?.total_wh_today ?? 0).toFixed(1)} Wh
                </p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  {(energySummary?.total_kwh_today ?? 0).toFixed(4)} kWh terakumulasi
                </p>
              </div>

              <div className="rounded-2xl border border-emerald-500/25 bg-slate-900/90 p-4">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Estimasi Biaya Listrik PLN</span>
                  <span className="font-mono text-[11px] text-emerald-400">IDR</span>
                </div>
                <p className="mt-1 font-mono text-xl font-bold text-emerald-300">
                  Rp {estMonthlyIdr.toLocaleString('id-ID')}
                  <span className="text-xs font-normal text-slate-400">/bln</span>
                </p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  Tarif Rp {(energySummary?.tariff_idr_per_kwh ?? 1444.7).toLocaleString('id-ID')}/kWh
                </p>
              </div>

              <div className="rounded-2xl border border-violet-500/25 bg-slate-900/90 p-4">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Mode Perangkat Terdaftar</span>
                  <Lightbulb className="h-4 w-4 text-violet-400" />
                </div>
                <p className="mt-1 font-mono text-xl font-bold text-violet-300">
                  {virtualCount} Virtual • {lanCount} LAN
                </p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  Siap untuk semua merek lampu Tuya
                </p>
              </div>
            </section>

            {/* Dual-Mode Information & Group Power Banner */}
            <section className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-violet-500/30 bg-gradient-to-r from-violet-950/40 via-slate-900 to-cyan-950/30 p-4">
              <div className="flex items-start gap-3">
                <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-violet-400" />
                <div className="text-xs">
                  <p className="font-semibold text-slate-100">
                    LuminaCore Multi-Brand Hub ({virtualCount} Simulator Virtual, {lanCount} Fisik LAN)
                  </p>
                  <p className="mt-0.5 text-slate-300">
                    Mendukung bohlam pintar BARDI, Krisbow Sync, Hannochs, Arbit, Avaro, Deon, dan
                    seluruh ekosistem Tuya Local LAN. Klik{' '}
                    <strong className="text-cyan-300">Pengaturan</strong> pada kartu lampu untuk
                    beralih ke <strong className="text-cyan-300">Physical LAN (TinyTuya)</strong>.
                  </p>
                </div>
              </div>

              {devices.length > 0 && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleAllPower(true)}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/20 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/30"
                  >
                    <Power className="h-3.5 w-3.5" />
                    Nyalakan Semua
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleAllPower(false)}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700"
                  >
                    Matikan Semua
                  </button>
                </div>
              )}
            </section>
          </>
        )}

        {bannerError && (
          <div
            role="alert"
            className="mb-6 rounded-xl border border-rose-500/40 bg-rose-950/50 p-4 text-xs text-rose-200"
          >
            {bannerError}
          </div>
        )}

        {/* Studio View Navigation Tabs (REQ-108) */}
        <div
          className="mb-6 flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3"
          role="tablist"
          aria-label="Navigasi LuminaCore Studio"
        >
          {(
            [
              { id: 'control', label: 'Kontrol & Ambience' },
              { id: 'energy', label: 'Pemantauan Daya & Biaya' },
              { id: 'schedules', label: `Jadwal & Timer (${schedules.length})` },
            ] as { id: 'control' | 'energy' | 'schedules'; label: string }[]
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={studioTab === tab.id}
              onClick={() => setStudioTab(tab.id)}
              className={`rounded-xl px-4 py-2 text-xs font-semibold transition ${
                studioTab === tab.id
                  ? 'bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/20'
                  : 'border border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Energy Breakdown Tab View (REQ-105, REQ-108) */}
        {studioTab === 'energy' && (
          <section
            className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-5"
            data-testid="energy-tab-panel"
          >
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-semibold text-slate-100">
                  Rincian Pemantauan Daya & Sumber Telemetri per Lampu
                </h2>
                <p className="text-xs text-slate-400">
                  Menampilkan perbandingan beban Watt aktif, akumulasi Wh harian, serta sumber
                  pembacaan (powercalc_estimate vs hardware_sensor DPS 19).
                </p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-800 text-slate-400">
                  <tr>
                    <th className="py-2 pr-4">Perangkat</th>
                    <th className="py-2 pr-4">Merek & Ruangan</th>
                    <th className="py-2 pr-4">Daya Aktif / Maks</th>
                    <th className="py-2 pr-4">Energi Hari Ini</th>
                    <th className="py-2">Sumber Telemetri</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {(energySummary?.devices ??
                    devices.map((d) => ({
                      device_id: d.device_id,
                      name: d.name,
                      brand: d.brand ?? 'Tuya Generic',
                      room: d.room,
                      online: d.online,
                      power: d.state.power,
                      rated_wattage: d.rated_wattage ?? 9,
                      live_watts: d.live_watts ?? 0,
                      wh_today: d.energy_wh_today ?? 0,
                      power_source: d.power_source ?? 'powercalc_estimate',
                    }))
                  ).map((item) => (
                    <tr key={item.device_id}>
                      <td className="py-2.5 pr-4 font-semibold text-slate-100">
                        {item.name}
                      </td>
                      <td className="py-2.5 pr-4 text-slate-300">
                        {item.brand} • {item.room}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-amber-300">
                        {item.live_watts.toFixed(2)}W / {item.rated_wattage}W
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-cyan-300">
                        {item.wh_today.toFixed(2)} Wh
                      </td>
                      <td className="py-2.5">
                        <span className="rounded-full bg-slate-800 px-2.5 py-0.5 font-mono text-[11px] text-slate-200">
                          {item.power_source}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Schedules Tab View (REQ-107, REQ-108) */}
        {studioTab === 'schedules' && (
          <section
            className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-5"
            data-testid="schedules-tab-panel"
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-slate-100">
                  Jadwal Otomatis Harian (Time-of-Day Scheduler)
                </h2>
                <p className="text-xs text-slate-400">
                  Jadwal dieksekusi otomatis oleh backend Python berdasarkan waktu lokal.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setScheduleModalOpen(true)}
                className="rounded-xl bg-cyan-500 px-3.5 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-400"
              >
                Kelola / Tambah Jadwal
              </button>
            </div>
            {schedules.length === 0 ? (
              <p className="text-xs text-slate-400">
                Belum ada jadwal harian tersimpan. Klik &quot;Kelola / Tambah Jadwal&quot; untuk membuat jadwal baru.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {schedules.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs"
                  >
                    <div>
                      <span className="font-mono text-sm font-bold text-cyan-300">
                        {s.time_hhmm}
                      </span>{' '}
                      <span className="font-semibold text-slate-100">{s.name}</span>
                      <p className="text-[11px] text-slate-400">
                        Target: {s.target_device_id} •{' '}
                        {s.action_power ? 'Nyalakan (ON)' : 'Matikan (OFF)'}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void handleToggleSchedule(s.id, !s.enabled)}
                        className={`rounded-lg px-2.5 py-1 font-medium ${
                          s.enabled
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {s.enabled ? 'Aktif' : 'Nonaktif'}
                      </button>
                      <button
                        type="button"
                        aria-label={`Hapus jadwal ${s.name}`}
                        onClick={() => void handleDeleteSchedule(s.id)}
                        className="rounded-lg bg-rose-500/15 p-1.5 text-rose-300"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {devices.length > 0 && (
          <div className="mb-5 flex flex-wrap items-center gap-2">
            {rooms.map((roomName) => (
              <button
                key={roomName}
                type="button"
                onClick={() => setSelectedRoom(roomName)}
                className={`rounded-xl px-3.5 py-1.5 text-xs font-medium transition ${
                  selectedRoom === roomName
                    ? 'bg-cyan-500 text-slate-950 font-semibold'
                    : 'border border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700'
                }`}
              >
                {roomName === 'ALL' ? `Semua Ruangan (${devices.length})` : roomName}
              </button>
            ))}
          </div>
        )}

        {loading ? (
          <div
            className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3"
            data-testid="loading-skeleton"
          >
            {[1, 2].map((n) => (
              <div
                key={n}
                className="h-96 animate-pulse rounded-2xl border border-slate-800 bg-slate-900/50 p-5"
              />
            ))}
          </div>
        ) : filteredDevices.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-6 py-16 text-center"
            data-testid="empty-state"
          >
            <Lightbulb className="h-12 w-12 text-cyan-400" />
            <h2 className="mt-4 text-lg font-semibold text-slate-100">
              Belum Ada Smart Lamp Terdaftar
            </h2>
            <p className="mt-1 max-w-md text-xs text-slate-400">
              Gunakan fitur Auto-Discovery untuk memindai lampu pintar (atau Simulator Virtual) di
              jaringan Wi-Fi lokal Anda, impor file TinyTuya, atau tambahkan secara manual.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <button
                type="button"
                onClick={() => void handleRunScan()}
                className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400"
              >
                <Radar className="h-4 w-4" />
                Scan Wi-Fi Lokal & Simulator
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditingDevice(null);
                  setPrefillDiscovered(null);
                  setFormOpen(true);
                }}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
              >
                <Plus className="h-4 w-4" />
                Tambah Lampu Manual
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {filteredDevices.map((device) => (
              <DeviceCard
                key={device.device_id}
                device={device}
                presets={presets}
                onCommand={handleCommand}
                onAutomation={handleAutomation}
                onTimer={handleTimer}
                onRefresh={handleRefreshDevice}
                onEdit={(dev) => {
                  setEditingDevice(dev);
                  setPrefillDiscovered(null);
                  setFormOpen(true);
                }}
                onDelete={handleDeleteDevice}
              />
            ))}
          </div>
        )}
      </main>

      <DeviceFormModal
        open={formOpen}
        editingDevice={editingDevice}
        prefillDiscovered={prefillDiscovered}
        onClose={() => setFormOpen(false)}
        onCreate={handleCreateDevice}
        onUpdate={handleUpdateDevice}
      />

      <LanScannerModal
        open={scannerOpen}
        scanning={scanning}
        discovered={discovered}
        error={scanError}
        onClose={() => setScannerOpen(false)}
        onRescan={handleRunScan}
        onSelectDevice={(disc) => {
          setScannerOpen(false);
          setEditingDevice(null);
          setPrefillDiscovered(disc);
          setFormOpen(true);
        }}
      />

      {/* Daily Scheduler Modal */}
      <Modal
        title="Jadwal Otomatis Harian (Time-of-Day Scheduler)"
        open={scheduleModalOpen}
        onClose={() => setScheduleModalOpen(false)}
      >
        <div className="space-y-4 text-xs">
          <form onSubmit={(e) => void handleCreateSchedule(e)} className="space-y-3 rounded-xl border border-slate-800 bg-slate-950 p-3.5">
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              <div>
                <label htmlFor="sched-name" className="mb-1 block text-slate-300">
                  Nama Jadwal
                </label>
                <input
                  id="sched-name"
                  type="text"
                  value={schedName}
                  onChange={(e) => setSchedName(e.target.value)}
                  placeholder="Malam Hemat Energi"
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100"
                />
              </div>
              <div>
                <label htmlFor="sched-time" className="mb-1 block text-slate-300">
                  Jam Eksekusi (24 Jam)
                </label>
                <input
                  id="sched-time"
                  type="time"
                  value={schedTime}
                  onChange={(e) => setSchedTime(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-mono text-slate-100"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              <div>
                <label htmlFor="sched-target" className="mb-1 block text-slate-300">
                  Target Perangkat
                </label>
                <select
                  id="sched-target"
                  value={schedTarget}
                  onChange={(e) => setSchedTarget(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100"
                >
                  <option value="ALL">Seluruh Lampu (ALL)</option>
                  {devices.map((d) => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="sched-action" className="mb-1 block text-slate-300">
                  Aksi Daya
                </label>
                <select
                  id="sched-action"
                  value={schedPower ? 'ON' : 'OFF'}
                  onChange={(e) => setSchedPower(e.target.value === 'ON')}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100"
                >
                  <option value="ON">Nyalakan Lampu (ON)</option>
                  <option value="OFF">Matikan Lampu (OFF)</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                className="rounded-lg bg-cyan-500 px-3.5 py-1.5 font-semibold text-slate-950 hover:bg-cyan-400"
              >
                Tambah Jadwal
              </button>
            </div>
          </form>

          <div className="max-h-56 space-y-2 overflow-y-auto">
            {schedules.length === 0 ? (
              <p className="py-4 text-center text-slate-400">
                Belum ada jadwal harian tersimpan.
              </p>
            ) : (
              schedules.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 p-3"
                >
                  <div>
                    <span className="font-mono text-sm font-bold text-cyan-300">
                      {s.time_hhmm}
                    </span>{' '}
                    <span className="font-semibold text-slate-100">{s.name}</span>
                    <p className="text-[11px] text-slate-400">
                      Target: {s.target_device_id} • Aksi:{' '}
                      {s.action_power ? 'Nyalakan (ON)' : 'Matikan (OFF)'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void handleToggleSchedule(s.id, !s.enabled)}
                      className={`rounded-lg px-2.5 py-1 font-medium ${
                        s.enabled
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {s.enabled ? 'Aktif' : 'Nonaktif'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDeleteSchedule(s.id)}
                      className="rounded-lg bg-rose-500/15 p-1.5 text-rose-300"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </Modal>

      {/* 1-Click TinyTuya devices.json Import Modal */}
      <Modal
        title="Import Perangkat dari devices.json TinyTuya Wizard"
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
      >
        <form onSubmit={(e) => void handleImportSubmit(e)} className="space-y-3 text-xs">
          <p className="text-slate-300">
            Tempelkan isi file <code className="text-cyan-300">devices.json</code> hasil{' '}
            <code className="text-cyan-300">python -m tinytuya wizard</code> untuk mendaftarkan
            banyak lampu pintar lintas merek sekaligus.
          </p>
          {importError && (
            <div
              role="alert"
              className="rounded-xl border border-rose-500/40 bg-rose-950/50 p-3 text-rose-200"
            >
              {importError}
            </div>
          )}
          <textarea
            rows={7}
            value={importJsonText}
            onChange={(e) => setImportJsonText(e.target.value)}
            placeholder='[{"id": "a34a2155107e11628clk7m", "name": "Lampu Kamar", "brand": "BARDI", "rated_wattage": 9, "ip": "192.168.1.55", "key": "0123456789abcdef", "version": "3.3"}]'
            className="w-full rounded-xl border border-slate-700 bg-slate-950 p-3 font-mono text-xs text-slate-100"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setImportModalOpen(false)}
              className="rounded-xl border border-slate-700 px-4 py-2 text-slate-300"
            >
              Batal
            </button>
            <button
              type="submit"
              className="rounded-xl bg-cyan-500 px-4 py-2 font-semibold text-slate-950 hover:bg-cyan-400"
            >
              Import Semua Perangkat
            </button>
          </div>
        </form>
      </Modal>

      <AuthTokenModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onSubmitToken={async (token) => {
          client.setAccessToken(token);
          setAccessToken(token);
          await loadInitialData();
        }}
      />
    </div>
  );
};

export default App;
