import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { ApiError, BardiApiClient } from '../lib/api';
import type {
  AutomationConfigInput,
  DeviceCreateInput,
  DeviceUpdateInput,
  DeviceView,
  DiscoveredDevice,
  EnergySummaryView,
  LightingCommandInput,
  PresetView,
  ScheduleCreateInput,
  ScheduleView,
  TimerInput,
} from '../types/bardi';

class InMemoryBardiClient extends BardiApiClient {
  devices: DeviceView[];
  presets: PresetView[];
  schedules: ScheduleView[] = [];
  authRequired = false;
  expectedToken = 'secret-bardi-pin';
  failNextCommandWith503 = false;
  commandCalls: { deviceId: string; command: LightingCommandInput }[] = [];
  automationCalls: { deviceId: string; config: AutomationConfigInput }[] = [];
  timerCalls: { deviceId: string; timer: TimerInput }[] = [];

  constructor(initialDevices: DeviceView[] = []) {
    super();
    this.devices = initialDevices;
    this.presets = [
      {
        id: 'focus-daylight',
        name: 'Focus Daylight',
        mode: 'white',
        brightness_pct: 100,
        cct_pct: 100,
        kelvin: 6500,
        rgb: { r: 255, g: 255, b: 255 },
        is_builtin: true,
      },
    ];
  }

  override async getAuthStatus() {
    if (!this.authRequired) {
      return { auth_required: false, authenticated: true };
    }
    return {
      auth_required: true,
      authenticated: this.getAccessToken() === this.expectedToken,
    };
  }

  override async listDevices(): Promise<DeviceView[]> {
    if (this.authRequired && this.getAccessToken() !== this.expectedToken) {
      throw new ApiError(401, 'ERR_UNAUTHORIZED', 'Token akses tidak valid');
    }
    return [...this.devices];
  }

  override async listPresets(): Promise<PresetView[]> {
    return [...this.presets];
  }

  override async sendCommand(
    deviceId: string,
    command: LightingCommandInput,
  ): Promise<DeviceView> {
    this.commandCalls.push({ deviceId, command });
    const target = this.devices.find((d) => d.device_id === deviceId);
    if (!target) throw new ApiError(404, 'ERR_NOT_FOUND', 'Not found');
    if (this.failNextCommandWith503) {
      this.failNextCommandWith503 = false;
      const offlineView: DeviceView = {
        ...target,
        online: false,
        last_error: "Device 'bardi_lan_01' is unreachable on local LAN: TCP 6668 timeout",
      };
      this.devices = this.devices.map((d) => (d.device_id === deviceId ? offlineView : d));
      throw new ApiError(
        503,
        'ERR_DEVICE_UNREACHABLE',
        "Device 'bardi_lan_01' is unreachable on local LAN: TCP 6668 timeout",
      );
    }
    const updated: DeviceView = {
      ...target,
      online: true,
      last_error: null,
      state: {
        ...target.state,
        ...(command.power !== undefined ? { power: command.power } : {}),
        ...(command.mode !== undefined ? { mode: command.mode } : {}),
        ...(command.brightness_pct !== undefined
          ? { brightness_pct: command.brightness_pct }
          : {}),
        ...(command.cct_pct !== undefined ? { cct_pct: command.cct_pct } : {}),
        ...(command.rgb !== undefined ? { rgb: command.rgb } : {}),
      },
    };
    this.devices = this.devices.map((d) => (d.device_id === deviceId ? updated : d));
    return updated;
  }

  override async refreshDevice(deviceId: string): Promise<DeviceView> {
    const target = this.devices.find((d) => d.device_id === deviceId);
    if (!target) throw new ApiError(404, 'ERR_NOT_FOUND', 'Not found');
    const recovered: DeviceView = {
      ...target,
      online: true,
      last_error: null,
    };
    this.devices = this.devices.map((d) => (d.device_id === deviceId ? recovered : d));
    return recovered;
  }

  override async scanDevices(): Promise<DiscoveredDevice[]> {
    return [
      {
        device_id: 'bardi_virtual_strip_living',
        ip_address: '192.168.1.103',
        protocol_version: '3.3',
        product_key: 'bardi_strip',
        connection_mode: 'virtual',
        suggested_name: 'BARDI LED Strip 2M (Simulator)',
        already_registered: false,
        registered_name: null,
      },
    ];
  }

  override async createDevice(input: DeviceCreateInput): Promise<DeviceView> {
    const created: DeviceView = {
      device_id: input.device_id,
      name: input.name,
      ip_address: input.ip_address,
      protocol_version: input.protocol_version,
      bulb_type: input.bulb_type,
      connection_mode: input.connection_mode,
      room: input.room,
      has_local_key: true,
      masked_key: '****key1',
      online: true,
      state: {
        power: true,
        mode: 'white',
        brightness_pct: 80,
        cct_pct: 50,
        kelvin: 4600,
        rgb: { r: 255, g: 180, b: 100 },
      },
      last_seen_at: new Date().toISOString(),
      last_error: null,
    };
    this.devices.push(created);
    return created;
  }

  override async updateDevice(
    deviceId: string,
    input: DeviceUpdateInput,
  ): Promise<DeviceView> {
    const existing = this.devices.find((d) => d.device_id === deviceId)!;
    const updated: DeviceView = { ...existing, ...input };
    this.devices = this.devices.map((d) => (d.device_id === deviceId ? updated : d));
    return updated;
  }

  override async setAutomation(
    deviceId: string,
    config: AutomationConfigInput,
  ): Promise<DeviceView> {
    this.automationCalls.push({ deviceId, config });
    const existing = this.devices.find((d) => d.device_id === deviceId)!;
    const isTimed = config.mode === 'sleep_fade' || config.mode === 'pomodoro';
    const totalSeconds =
      config.mode === 'sleep_fade'
        ? (config.duration_minutes ?? 15) * 60
        : config.mode === 'pomodoro'
          ? 25 * 60
          : null;
    const updated: DeviceView = {
      ...existing,
      automation_mode: config.mode,
      automation_palette: config.palette ?? 'aurora',
      automation_expires_at:
        isTimed && totalSeconds
          ? new Date(Date.now() + totalSeconds * 1000).toISOString()
          : null,
      automation_total_seconds: totalSeconds,
    };
    this.devices = this.devices.map((d) => (d.device_id === deviceId ? updated : d));
    return updated;
  }

  override async setTimer(
    deviceId: string,
    timer: TimerInput,
  ): Promise<DeviceView> {
    this.timerCalls.push({ deviceId, timer });
    const existing = this.devices.find((d) => d.device_id === deviceId)!;
    const updated: DeviceView = {
      ...existing,
      timer_expires_at:
        timer.minutes > 0 ? new Date(Date.now() + timer.minutes * 60000).toISOString() : null,
      timer_total_seconds: timer.minutes > 0 ? timer.minutes * 60 : null,
      timer_target_power: timer.minutes > 0 ? Boolean(timer.action_power) : null,
    };
    this.devices = this.devices.map((d) => (d.device_id === deviceId ? updated : d));
    return updated;
  }

  override async getEnergySummary(): Promise<EnergySummaryView> {
    const totalLive = this.devices.reduce((acc, d) => acc + (d.live_watts ?? 7.2), 0);
    return {
      total_live_watts: totalLive,
      total_wh_today: 42.5,
      total_kwh_today: 0.0425,
      estimated_monthly_kwh: 3.5,
      estimated_monthly_cost_idr: 5056,
      tariff_idr_per_kwh: 1444.7,
      active_lamp_count: this.devices.length,
      total_lamp_count: this.devices.length,
      devices: this.devices.map((d) => ({
        device_id: d.device_id,
        name: d.name,
        brand: d.brand ?? 'Tuya Generic',
        room: d.room,
        online: d.online,
        power: d.state.power,
        rated_wattage: d.rated_wattage ?? 9,
        live_watts: d.live_watts ?? 7.2,
        wh_today: d.energy_wh_today ?? 21.25,
        power_source: d.power_source ?? 'powercalc_estimate',
      })),
    };
  }

  override async listSchedules(): Promise<ScheduleView[]> {
    return [...this.schedules];
  }

  override async createSchedule(input: ScheduleCreateInput): Promise<ScheduleView> {
    const created: ScheduleView = {
      id: `sched-${this.schedules.length + 1}`,
      name: input.name,
      time_hhmm: input.time_hhmm,
      target_device_id: input.target_device_id,
      action_power: input.action_power,
      preset_id: input.preset_id ?? null,
      enabled: input.enabled ?? true,
      last_triggered_date: null,
    };
    this.schedules.push(created);
    return created;
  }

  override async toggleSchedule(
    scheduleId: string,
    enabled: boolean,
  ): Promise<ScheduleView> {
    const target = this.schedules.find((s) => s.id === scheduleId)!;
    const updated = { ...target, enabled };
    this.schedules = this.schedules.map((s) => (s.id === scheduleId ? updated : s));
    return updated;
  }

  override async deleteSchedule(scheduleId: string): Promise<void> {
    this.schedules = this.schedules.filter((s) => s.id !== scheduleId);
  }

  override async importTinyTuyaDevices(
    items: Record<string, unknown>[],
  ): Promise<DeviceView[]> {
    for (const raw of items) {
      await this.createDevice({
        device_id: String(raw.id ?? raw.device_id),
        name: String(raw.name ?? 'Imported Lamp'),
        brand: String(raw.brand ?? 'Hannochs'),
        rated_wattage: Number(raw.rated_wattage ?? 12),
        ip_address: String(raw.ip ?? '192.168.1.180'),
        local_key: String(raw.key ?? '0123456789abcdef'),
        protocol_version: '3.3',
        bulb_type: 'B',
        connection_mode: 'virtual',
        room: 'Ruang Tamu',
      });
    }
    return [...this.devices];
  }
}

const SAMPLE_VIRTUAL_LAMP: DeviceView = {
  device_id: 'bardi_virtual_9w_bedroom',
  name: 'BARDI 9W RGBWW - Kamar Tidur (Simulator)',
  ip_address: '192.168.1.101',
  protocol_version: '3.4',
  bulb_type: 'B',
  connection_mode: 'virtual',
  room: 'Kamar Tidur',
  has_local_key: true,
  masked_key: '****y_01',
  online: true,
  state: {
    power: true,
    mode: 'white',
    brightness_pct: 80,
    cct_pct: 20,
    kelvin: 3460,
    rgb: { r: 255, g: 180, b: 100 },
  },
  last_seen_at: '2026-11-21T00:00:00Z',
  last_error: null,
};

describe('BARDI Smart Lamp Web Dashboard (REQ-104, NFR-103, DEC-008)', () => {
  it('renders empty state when zero lamps are registered and allows LAN scanner onboarding', async () => {
    const client = new InMemoryBardiClient([]);
    render(<App apiClient={client} />);

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Scan Wi-Fi Lokal & Simulator'));

    await waitFor(() => {
      expect(screen.getByText('BARDI LED Strip 2M (Simulator)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Gunakan'));

    await waitFor(() => {
      expect(screen.getByDisplayValue('bardi_virtual_strip_living')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Daftarkan Lampu'));

    await waitFor(() => {
      expect(screen.getByText('BARDI LED Strip 2M (Simulator)')).toBeInTheDocument();
    });
  });

  it('debounces rapid Brightness slider drags by 150ms (NFR-103) and renders visual simulator', async () => {
    const client = new InMemoryBardiClient([SAMPLE_VIRTUAL_LAMP]);
    render(<App apiClient={client} />);

    await waitFor(() => {
      expect(
        screen.getByText('BARDI 9W RGBWW - Kamar Tidur (Simulator)'),
      ).toBeInTheDocument();
    });

    expect(screen.getByTestId('bulb-visualizer')).toBeInTheDocument();

    vi.useFakeTimers();
    try {
      const slider = screen.getByLabelText('Kecerahan (Brightness)');
      fireEvent.change(slider, { target: { value: '30' } });
      fireEvent.change(slider, { target: { value: '45' } });
      fireEvent.change(slider, { target: { value: '60' } });

      // Before 150ms expires, no API call should have fired
      expect(client.commandCalls.length).toBe(0);

      await act(async () => {
        vi.advanceTimersByTime(160);
      });

      // Coalesced into a single API command with the latest value (60)
      expect(client.commandCalls.length).toBe(1);
      expect(client.commandCalls[0].command.brightness_pct).toBe(60);
    } finally {
      vi.useRealTimers();
    }
  });

  it('handles 503 ERR_DEVICE_UNREACHABLE command failure and recovers via Coba Lagi reconnect', async () => {
    const lanLamp: DeviceView = {
      ...SAMPLE_VIRTUAL_LAMP,
      device_id: 'bardi_lan_01',
      name: 'BARDI Teras Depan',
      connection_mode: 'lan',
      online: true,
    };
    const client = new InMemoryBardiClient([lanLamp]);
    client.failNextCommandWith503 = true;
    render(<App apiClient={client} />);

    await waitFor(() => {
      expect(screen.getByText('BARDI Teras Depan')).toBeInTheDocument();
    });

    // Trigger power toggle command which fails with 503 ERR_DEVICE_UNREACHABLE
    fireEvent.click(screen.getByLabelText('Power BARDI Teras Depan'));

    await waitFor(() => {
      expect(
        screen.getByText('Lampu Fisik Tidak Terjangkau (Offline)'),
      ).toBeInTheDocument();
    });

    // Click Coba Lagi to reconnect and verify online recovery
    fireEvent.click(screen.getByText('Coba Lagi'));

    await waitFor(() => {
      expect(
        screen.queryByText('Lampu Fisik Tidak Terjangkau (Offline)'),
      ).not.toBeInTheDocument();
    });
  });

  it('opens AuthTokenModal when auth_required is active and unlocks dashboard on valid token (SEC-101)', async () => {
    const client = new InMemoryBardiClient([SAMPLE_VIRTUAL_LAMP]);
    client.authRequired = true;
    render(<App apiClient={client} />);

    await waitFor(() => {
      expect(screen.getByText('Autentikasi Akses Lokal BARDI')).toBeInTheDocument();
    });

    fireEvent.change(
      screen.getByLabelText('PIN / Access Token (X-Bardi-Token)'),
      { target: { value: 'secret-bardi-pin' } },
    );
    fireEvent.click(screen.getByText('Buka Dashboard'));

    await waitFor(() => {
      expect(
        screen.getByText('BARDI 9W RGBWW - Kamar Tidur (Simulator)'),
      ).toBeInTheDocument();
    });
  });

  it('validates Device ID format, IPv4, and clears simulator Local Key when switching to Physical LAN (ERR-102)', async () => {
    const client = new InMemoryBardiClient([]);
    render(<App apiClient={client} />);

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText('Tambah Lampu Manual')[0]);

    // Invalid Device ID with special characters
    fireEvent.change(screen.getByLabelText('Device ID (8-64 karakter)'), {
      target: { value: 'bad!@#id!' },
    });
    fireEvent.change(screen.getByLabelText('Nama Lampu'), {
      target: { value: 'Lampu Baru' },
    });
    fireEvent.click(screen.getByText('Daftarkan Lampu'));

    await waitFor(() => {
      expect(
        screen.getByText(/Device ID wajib berisi 8 hingga 64 karakter/i),
      ).toBeInTheDocument();
    });

    // Fix Device ID, test invalid IPv4
    fireEvent.change(screen.getByLabelText('Device ID (8-64 karakter)'), {
      target: { value: 'bf_valid_new_lamp_01' },
    });
    fireEvent.change(screen.getByLabelText('IP Address Lokal (IPv4)'), {
      target: { value: '999.168.1.1' },
    });
    fireEvent.click(screen.getByText('Daftarkan Lampu'));

    await waitFor(() => {
      expect(screen.getByText(/Format IP Address tidak valid/i)).toBeInTheDocument();
    });

    // Fix IPv4 and switch to Physical LAN -> simulator key is cleared, requiring real 16-32 char key
    fireEvent.change(screen.getByLabelText('IP Address Lokal (IPv4)'), {
      target: { value: '192.168.1.120' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Physical LAN \(TinyTuya\)/i }));
    fireEvent.click(screen.getByText('Daftarkan Lampu'));

    await waitFor(() => {
      expect(
        screen.getByText(/Local Key Tuya wajib berisi 16 hingga 32 karakter/i),
      ).toBeInTheDocument();
    });
  });

  it('displays LuminaCore Studio branding, Smart Powercalc telemetry, and triggers Ambience Automation, Timer, Schedules & Bulk Import (REQ-105..REQ-108)', async () => {
    const client = new InMemoryBardiClient([
      {
        ...SAMPLE_VIRTUAL_LAMP,
        brand: 'Krisbow Sync',
        rated_wattage: 12,
        live_watts: 9.8,
        power_source: 'powercalc_estimate',
      },
    ]);
    render(<App apiClient={client} />);

    await waitFor(() => {
      expect(screen.getByText('LuminaCore Studio')).toBeInTheDocument();
    });

    expect(screen.getByTestId('energy-summary-bar')).toBeInTheDocument();
    expect(screen.getByText('Krisbow Sync')).toBeInTheDocument();

    // 1. Trigger Auto RGB Loop automation (REQ-106)
    fireEvent.click(screen.getByText('Auto RGB Loop'));
    await waitFor(() => {
      expect(client.automationCalls.length).toBe(1);
      expect(client.automationCalls[0].config.mode).toBe('color_cycle');
      expect(screen.getByText('Aktif: color_cycle')).toBeInTheDocument();
    });

    // 1b. Trigger Sleep Fade 15m and verify live automation countdown badge (REQ-109)
    fireEvent.click(screen.getByText('Sleep Fade 15m'));
    await waitFor(() => {
      expect(client.automationCalls.length).toBe(2);
      expect(client.automationCalls[1].config.mode).toBe('sleep_fade');
      expect(
        screen.getByTestId('auto-countdown-bardi_virtual_9w_bedroom'),
      ).toHaveTextContent(/15:00|14:59/);
    });

    // 2. Trigger 15m OFF countdown timer and verify live digital MM:SS countdown & progress bar (REQ-107, REQ-109)
    fireEvent.click(screen.getByText('15m OFF'));
    await waitFor(() => {
      expect(client.timerCalls.length).toBe(1);
      expect(client.timerCalls[0].timer.minutes).toBe(15);
      expect(
        screen.getByTestId('countdown-clock-bardi_virtual_9w_bedroom'),
      ).toHaveTextContent(/15:00|14:59/);
      expect(
        screen.getByTestId('countdown-progress-bardi_virtual_9w_bedroom'),
      ).toBeInTheDocument();
    });

    // 2b. Set custom timer minutes (45m ON)
    fireEvent.change(
      screen.getByLabelText(/Menit Timer Kustom BARDI 9W RGBWW/i),
      { target: { value: '45' } },
    );
    fireEvent.change(
      screen.getByLabelText(/Aksi Timer Kustom BARDI 9W RGBWW/i),
      { target: { value: 'ON' } },
    );
    fireEvent.click(screen.getByText('Set Timer'));
    await waitFor(() => {
      expect(client.timerCalls.length).toBe(2);
      expect(client.timerCalls[1].timer.minutes).toBe(45);
      expect(client.timerCalls[1].timer.action_power).toBe(true);
    });

    // 3. Switch to Pemantauan Daya & Biaya tab and verify powercalc_estimate source (REQ-105, REQ-108)
    fireEvent.click(screen.getByRole('tab', { name: /Pemantauan Daya & Biaya/i }));
    await waitFor(() => {
      expect(screen.getByTestId('energy-tab-panel')).toBeInTheDocument();
      expect(screen.getByText('powercalc_estimate')).toBeInTheDocument();
    });

    // 4. Open Daily Scheduler modal and create a schedule (REQ-107)
    fireEvent.click(screen.getByText(/Jadwal \(0\)/i));
    fireEvent.click(screen.getByText('Tambah Jadwal'));
    await waitFor(() => {
      expect(screen.getByText('Malam Hemat Energi')).toBeInTheDocument();
    });

    // 5. Open TinyTuya Bulk Import modal and import a Hannochs device (REQ-108)
    fireEvent.click(screen.getByText('Import TinyTuya'));
    const textarea = screen.getByPlaceholderText(/a34a2155107e11628clk7m/i);
    fireEvent.change(textarea, {
      target: {
        value: JSON.stringify([
          {
            id: 'hannochs_smart_bulb_01',
            name: 'Hannochs Smart LED 12W',
            brand: 'Hannochs',
            rated_wattage: 12,
            ip: '192.168.1.188',
            key: '0123456789abcdef',
          },
        ]),
      },
    });
    fireEvent.click(screen.getByText('Import Semua Perangkat'));
    await waitFor(() => {
      expect(
        screen.getByTestId('device-card-hannochs_smart_bulb_01'),
      ).toBeInTheDocument();
    });

    // 6. Collapse and expand dynamic navbar + telemetry panel & verify localStorage persistence (REQ-110)
    fireEvent.click(screen.getByTestId('toggle-telemetry-btn'));
    await waitFor(() => {
      expect(window.localStorage.getItem('luminacore_telemetry_collapsed')).toBe('true');
      expect(screen.queryByTestId('energy-summary-bar')).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('toggle-telemetry-btn'));
    await waitFor(() => {
      expect(window.localStorage.getItem('luminacore_telemetry_collapsed')).toBe('false');
      expect(screen.getByTestId('energy-summary-bar')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('collapse-navbar-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('collapsed-navbar-pill')).toBeInTheDocument();
      expect(window.localStorage.getItem('luminacore_navbar_collapsed')).toBe('true');
    });

    // Expand back via Alt+N keyboard shortcut
    fireEvent.keyDown(window, { key: 'n', altKey: true });
    await waitFor(() => {
      expect(screen.getByTestId('expanded-navbar')).toBeInTheDocument();
      expect(window.localStorage.getItem('luminacore_navbar_collapsed')).toBe('false');
    });
  });
});
