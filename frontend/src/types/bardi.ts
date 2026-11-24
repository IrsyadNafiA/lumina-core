export type ProtocolVersion = '3.3' | '3.4' | '3.5';
export type BulbType = 'A' | 'B';
export type WorkMode = 'white' | 'colour' | 'scene';
export type ConnectionMode = 'lan' | 'virtual';
export type AutomationMode = 'none' | 'color_cycle' | 'circadian' | 'pomodoro' | 'sleep_fade';
export type ColorPalette = 'aurora' | 'cyberpunk' | 'sunset' | 'ocean';
export type PowerSource = 'powercalc_estimate' | 'hardware_sensor';

export interface RGBColor {
  r: number;
  g: number;
  b: number;
}

export interface BulbState {
  power: boolean;
  mode: WorkMode;
  brightness_pct: number;
  cct_pct: number;
  kelvin: number;
  rgb: RGBColor;
}

export interface DeviceView {
  device_id: string;
  name: string;
  brand?: string;
  rated_wattage?: number;
  live_watts?: number;
  energy_wh_today?: number;
  power_source?: PowerSource;
  ip_address: string;
  protocol_version: ProtocolVersion;
  bulb_type: BulbType;
  connection_mode: ConnectionMode;
  room: string;
  has_local_key: boolean;
  masked_key: string;
  online: boolean;
  state: BulbState;
  automation_mode?: AutomationMode;
  automation_palette?: ColorPalette;
  automation_interval_sec?: number;
  automation_expires_at?: string | null;
  automation_total_seconds?: number | null;
  timer_expires_at?: string | null;
  timer_total_seconds?: number | null;
  timer_target_power?: boolean | null;
  last_seen_at: string | null;
  last_error: string | null;
}

export interface DeviceCreateInput {
  device_id: string;
  name: string;
  brand?: string;
  rated_wattage?: number;
  ip_address: string;
  local_key: string;
  protocol_version: ProtocolVersion;
  bulb_type: BulbType;
  connection_mode: ConnectionMode;
  room: string;
}

export interface DeviceUpdateInput {
  name: string;
  brand?: string;
  rated_wattage?: number;
  ip_address: string;
  local_key?: string;
  protocol_version: ProtocolVersion;
  bulb_type: BulbType;
  connection_mode: ConnectionMode;
  room: string;
}

export interface LightingCommandInput {
  power?: boolean;
  mode?: WorkMode;
  brightness_pct?: number;
  cct_pct?: number;
  rgb?: RGBColor;
  preset_id?: string;
}

export interface AutomationConfigInput {
  mode: AutomationMode;
  palette?: ColorPalette;
  interval_sec?: number;
  duration_minutes?: number;
}

export interface TimerInput {
  minutes: number;
  action_power?: boolean;
}

export interface ScheduleCreateInput {
  name: string;
  time_hhmm: string;
  target_device_id: string;
  action_power: boolean;
  preset_id?: string | null;
  enabled?: boolean;
}

export interface ScheduleView {
  id: string;
  name: string;
  time_hhmm: string;
  target_device_id: string;
  action_power: boolean;
  preset_id: string | null;
  enabled: boolean;
  last_triggered_date: string | null;
}

export interface DeviceEnergyItem {
  device_id: string;
  name: string;
  brand: string;
  room: string;
  online: boolean;
  power: boolean;
  rated_wattage: number;
  live_watts: number;
  wh_today: number;
  power_source: PowerSource;
}

export interface EnergySummaryView {
  total_live_watts: number;
  total_wh_today: number;
  total_kwh_today: number;
  estimated_monthly_kwh: number;
  estimated_monthly_cost_idr: number;
  tariff_idr_per_kwh: number;
  active_lamp_count: number;
  total_lamp_count: number;
  devices: DeviceEnergyItem[];
}

export interface DiscoveredDevice {
  device_id: string;
  ip_address: string;
  protocol_version: ProtocolVersion;
  product_key: string | null;
  connection_mode: ConnectionMode;
  suggested_name: string | null;
  already_registered: boolean;
  registered_name: string | null;
}

export interface PresetView {
  id: string;
  name: string;
  mode: WorkMode;
  brightness_pct: number;
  cct_pct: number;
  kelvin: number;
  rgb: RGBColor;
  is_builtin: boolean;
}

export interface AuthStatusResponse {
  auth_required: boolean;
  authenticated: boolean;
}

export interface WsEventFrame {
  event: 'snapshot' | 'device_updated' | 'device_removed' | 'scan_completed' | 'pong';
  payload: unknown;
  timestamp?: string;
}
