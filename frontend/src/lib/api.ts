import type {
  AuthStatusResponse,
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

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export function resolveApiBaseUrl(): string {
  const envUrl = (
    import.meta.env?.VITE_API_BASE_URL as string | undefined
  )?.trim();
  return envUrl ? envUrl.replace(/\/$/, '') : '';
}

export function resolveWsUrl(accessToken: string, baseUrl = resolveApiBaseUrl()): string {
  const tokenParam = accessToken
    ? `?token=${encodeURIComponent(accessToken)}`
    : '';
  if (baseUrl && /^https?:\/\//i.test(baseUrl)) {
    const wsBase = baseUrl.replace(/^http/i, 'ws');
    return `${wsBase}/ws/devices${tokenParam}`;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/devices${tokenParam}`;
}

export class BardiApiClient {
  private readonly baseUrl: string;
  private accessToken: string;

  constructor(baseUrl = resolveApiBaseUrl(), initialToken = '') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.accessToken = initialToken;
  }

  setAccessToken(token: string): void {
    this.accessToken = token.trim();
  }

  getAccessToken(): string {
    return this.accessToken;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (!headers.has('Content-Type') && init.body) {
      headers.set('Content-Type', 'application/json');
    }
    if (this.accessToken) {
      headers.set('X-Bardi-Token', this.accessToken);
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers,
    });

    if (response.status === 204) {
      return undefined as T;
    }

    let data: Record<string, unknown> = {};
    try {
      data = (await response.json()) as Record<string, unknown>;
    } catch {
      data = {};
    }

    if (!response.ok) {
      const code = typeof data.code === 'string' ? data.code : `HTTP_${response.status}`;
      const msg =
        typeof data.message === 'string'
          ? data.message
          : `Permintaan gagal dengan status ${response.status}`;
      throw new ApiError(response.status, code, msg);
    }

    return data as T;
  }

  async getAuthStatus(): Promise<AuthStatusResponse> {
    return this.request<AuthStatusResponse>('/api/v1/auth/status');
  }

  async listDevices(): Promise<DeviceView[]> {
    const res = await this.request<{ devices: DeviceView[] }>('/api/v1/devices');
    return res.devices;
  }

  async createDevice(input: DeviceCreateInput): Promise<DeviceView> {
    return this.request<DeviceView>('/api/v1/devices', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  async importTinyTuyaDevices(
    devices: Record<string, unknown>[],
  ): Promise<DeviceView[]> {
    const res = await this.request<{ imported: DeviceView[] }>(
      '/api/v1/devices/import-tinytuya',
      {
        method: 'POST',
        body: JSON.stringify({ devices }),
      },
    );
    return res.imported;
  }

  async updateDevice(deviceId: string, input: DeviceUpdateInput): Promise<DeviceView> {
    return this.request<DeviceView>(`/api/v1/devices/${encodeURIComponent(deviceId)}`, {
      method: 'PUT',
      body: JSON.stringify(input),
    });
  }

  async deleteDevice(deviceId: string): Promise<void> {
    await this.request<void>(`/api/v1/devices/${encodeURIComponent(deviceId)}`, {
      method: 'DELETE',
    });
  }

  async scanDevices(): Promise<DiscoveredDevice[]> {
    const res = await this.request<{ discovered: DiscoveredDevice[] }>('/api/v1/devices/scan', {
      method: 'POST',
    });
    return res.discovered;
  }

  async sendCommand(deviceId: string, command: LightingCommandInput): Promise<DeviceView> {
    return this.request<DeviceView>(
      `/api/v1/devices/${encodeURIComponent(deviceId)}/command`,
      {
        method: 'POST',
        body: JSON.stringify(command),
      },
    );
  }

  async setAutomation(
    deviceId: string,
    config: AutomationConfigInput,
  ): Promise<DeviceView> {
    return this.request<DeviceView>(
      `/api/v1/devices/${encodeURIComponent(deviceId)}/automation`,
      {
        method: 'POST',
        body: JSON.stringify(config),
      },
    );
  }

  async setTimer(deviceId: string, timer: TimerInput): Promise<DeviceView> {
    return this.request<DeviceView>(
      `/api/v1/devices/${encodeURIComponent(deviceId)}/timer`,
      {
        method: 'POST',
        body: JSON.stringify(timer),
      },
    );
  }

  async refreshDevice(deviceId: string): Promise<DeviceView> {
    return this.request<DeviceView>(
      `/api/v1/devices/${encodeURIComponent(deviceId)}/refresh`,
      {
        method: 'POST',
      },
    );
  }

  async getEnergySummary(): Promise<EnergySummaryView> {
    return this.request<EnergySummaryView>('/api/v1/energy/summary');
  }

  async listPresets(): Promise<PresetView[]> {
    const res = await this.request<{ presets: PresetView[] }>('/api/v1/presets');
    return res.presets;
  }

  async listSchedules(): Promise<ScheduleView[]> {
    const res = await this.request<{ schedules: ScheduleView[] }>('/api/v1/schedules');
    return res.schedules;
  }

  async createSchedule(input: ScheduleCreateInput): Promise<ScheduleView> {
    return this.request<ScheduleView>('/api/v1/schedules', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  async toggleSchedule(scheduleId: string, enabled: boolean): Promise<ScheduleView> {
    return this.request<ScheduleView>(
      `/api/v1/schedules/${encodeURIComponent(scheduleId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      },
    );
  }

  async deleteSchedule(scheduleId: string): Promise<void> {
    await this.request<void>(`/api/v1/schedules/${encodeURIComponent(scheduleId)}`, {
      method: 'DELETE',
    });
  }
}
