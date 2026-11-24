import React, { useEffect, useState } from 'react';
import type {
  BulbType,
  ConnectionMode,
  DeviceCreateInput,
  DeviceUpdateInput,
  DeviceView,
  DiscoveredDevice,
  ProtocolVersion,
} from '../types/bardi';
import { Modal } from './ui/Modal';

interface DeviceFormModalProps {
  open: boolean;
  editingDevice: DeviceView | null;
  prefillDiscovered: DiscoveredDevice | null;
  onClose: () => void;
  onCreate: (input: DeviceCreateInput) => Promise<void>;
  onUpdate: (deviceId: string, input: DeviceUpdateInput) => Promise<void>;
}

const DEVICE_ID_REGEX = /^[A-Za-z0-9_-]{8,64}$/;
const IPV4_REGEX =
  /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;

const SUPPORTED_BRANDS = [
  'BARDI',
  'Krisbow Sync',
  'Hannochs',
  'Arbit',
  'Avaro',
  'Deon',
  'Tuya Generic',
];

export const DeviceFormModal: React.FC<DeviceFormModalProps> = ({
  open,
  editingDevice,
  prefillDiscovered,
  onClose,
  onCreate,
  onUpdate,
}) => {
  const [deviceId, setDeviceId] = useState('');
  const [name, setName] = useState('');
  const [brand, setBrand] = useState('BARDI');
  const [ratedWattage, setRatedWattage] = useState(9);
  const [ipAddress, setIpAddress] = useState('192.168.1.105');
  const [localKey, setLocalKey] = useState('');
  const [protocolVersion, setProtocolVersion] = useState<ProtocolVersion>('3.4');
  const [bulbType, setBulbType] = useState<BulbType>('B');
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>('virtual');
  const [room, setRoom] = useState('Kamar Tidur');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setError(null);
    if (editingDevice) {
      setDeviceId(editingDevice.device_id);
      setName(editingDevice.name);
      setBrand(editingDevice.brand ?? 'Tuya Generic');
      setRatedWattage(editingDevice.rated_wattage ?? 9);
      setIpAddress(editingDevice.ip_address);
      setLocalKey('');
      setProtocolVersion(editingDevice.protocol_version);
      setBulbType(editingDevice.bulb_type);
      setConnectionMode(editingDevice.connection_mode);
      setRoom(editingDevice.room);
    } else if (prefillDiscovered) {
      setDeviceId(prefillDiscovered.device_id);
      setName(
        prefillDiscovered.suggested_name ||
          `Smart Bulb (${prefillDiscovered.ip_address})`,
      );
      setBrand('Tuya Generic');
      setRatedWattage(9);
      setIpAddress(prefillDiscovered.ip_address);
      setLocalKey(
        prefillDiscovered.connection_mode === 'virtual' ? 'virt_bardi_key_99' : '',
      );
      setProtocolVersion(prefillDiscovered.protocol_version);
      setBulbType('B');
      setConnectionMode(prefillDiscovered.connection_mode);
      setRoom('Ruang Tamu');
    } else {
      setDeviceId('');
      setName('');
      setBrand('Tuya Generic');
      setRatedWattage(9);
      setIpAddress('192.168.1.105');
      setLocalKey('virt_bardi_key_99');
      setProtocolVersion('3.4');
      setBulbType('B');
      setConnectionMode('virtual');
      setRoom('Kamar Tidur');
    }
  }, [editingDevice, prefillDiscovered, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanId = deviceId.trim();
    const cleanName = name.trim();
    const cleanIp = ipAddress.trim();
    const cleanKey = localKey.trim();
    const cleanRoom = room.trim();

    if (!editingDevice && !DEVICE_ID_REGEX.test(cleanId)) {
      setError('Device ID wajib berisi 8 hingga 64 karakter alfanumerik/strip/underscore.');
      return;
    }
    if (!cleanName) {
      setError('Nama lampu tidak boleh kosong.');
      return;
    }
    if (!IPV4_REGEX.test(cleanIp)) {
      setError('Format IP Address tidak valid (contoh: 192.168.1.50).');
      return;
    }
    if (!editingDevice && (cleanKey.length < 16 || cleanKey.length > 32)) {
      setError('Local Key Tuya wajib berisi 16 hingga 32 karakter.');
      return;
    }
    if (editingDevice && cleanKey && (cleanKey.length < 16 || cleanKey.length > 32)) {
      setError('Jika diubah, Local Key Tuya wajib berisi 16 hingga 32 karakter.');
      return;
    }

    setSubmitting(true);
    try {
      if (editingDevice) {
        const updatePayload: DeviceUpdateInput = {
          name: cleanName,
          brand,
          rated_wattage: ratedWattage,
          ip_address: cleanIp,
          protocol_version: protocolVersion,
          bulb_type: bulbType,
          connection_mode: connectionMode,
          room: cleanRoom || 'Kamar Tidur',
        };
        if (cleanKey) {
          updatePayload.local_key = cleanKey;
        }
        await onUpdate(editingDevice.device_id, updatePayload);
      } else {
        await onCreate({
          device_id: cleanId,
          name: cleanName,
          brand,
          rated_wattage: ratedWattage,
          ip_address: cleanIp,
          local_key: cleanKey,
          protocol_version: protocolVersion,
          bulb_type: bulbType,
          connection_mode: connectionMode,
          room: cleanRoom || 'Kamar Tidur',
        });
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal menyimpan perangkat');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={editingDevice ? `Pengaturan ${editingDevice.name}` : 'Tambah Smart Lamp'}
      open={open}
      onClose={onClose}
    >
      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3.5 text-sm">
        {error && (
          <div
            role="alert"
            className="rounded-xl border border-rose-500/40 bg-rose-950/50 p-3 text-xs text-rose-200"
          >
            {error}
          </div>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-300">
            Mode Koneksi Perangkat
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => {
                setConnectionMode('virtual');
                if (!localKey) setLocalKey('virt_bardi_key_99');
              }}
              className={`rounded-xl border p-2.5 text-left text-xs transition ${
                connectionMode === 'virtual'
                  ? 'border-violet-400 bg-violet-500/15 text-violet-200'
                  : 'border-slate-800 bg-slate-950 text-slate-400'
              }`}
            >
              <div className="font-semibold">Virtual Simulator</div>
              <div className="mt-0.5 text-[11px] opacity-80">
                Simulasi interaktif tanpa alat fisik
              </div>
            </button>
            <button
              type="button"
              onClick={() => {
                setConnectionMode('lan');
                if (localKey === 'virt_bardi_key_99') {
                  setLocalKey('');
                }
              }}
              className={`rounded-xl border p-2.5 text-left text-xs transition ${
                connectionMode === 'lan'
                  ? 'border-cyan-400 bg-cyan-500/15 text-cyan-200'
                  : 'border-slate-800 bg-slate-950 text-slate-400'
              }`}
            >
              <div className="font-semibold">Physical LAN (TinyTuya)</div>
              <div className="mt-0.5 text-[11px] opacity-80">
                Hubungkan ke lampu pintar asli di Wi-Fi (TCP 6668)
              </div>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label
              htmlFor="field-brand"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              Merek Smart Lamp
            </label>
            <select
              id="field-brand"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
            >
              {SUPPORTED_BRANDS.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="field-wattage"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              Daya Bohlam (Watt — untuk Powercalc)
            </label>
            <input
              id="field-wattage"
              type="number"
              min={1}
              max={200}
              step={0.5}
              value={ratedWattage}
              onChange={(e) => setRatedWattage(Number(e.target.value) || 9)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label
              htmlFor="field-device-id"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              Device ID (8-64 karakter)
            </label>
            <input
              id="field-device-id"
              type="text"
              disabled={Boolean(editingDevice)}
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              placeholder="bf1234567890abcdef"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 disabled:opacity-50"
            />
          </div>
          <div>
            <label
              htmlFor="field-room"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              Ruangan
            </label>
            <input
              id="field-room"
              type="text"
              value={room}
              onChange={(e) => setRoom(e.target.value)}
              placeholder="Kamar Tidur"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label
              htmlFor="field-name"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              Nama Lampu
            </label>
            <input
              id="field-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Smart Bulb 9W Kamar"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
            />
          </div>
          <div>
            <label
              htmlFor="field-ip"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              IP Address Lokal (IPv4)
            </label>
            <input
              id="field-ip"
              type="text"
              value={ipAddress}
              onChange={(e) => setIpAddress(e.target.value)}
              placeholder="192.168.1.50"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100"
            />
          </div>
        </div>

        <div>
          <label
            htmlFor="field-local-key"
            className="mb-1 block text-xs font-medium text-slate-300"
          >
            Tuya Local Key (16-32 karakter){' '}
            {editingDevice && (
              <span className="text-slate-400">
                — Kosongkan jika tidak ingin mengubah ({editingDevice.masked_key})
              </span>
            )}
          </label>
          <input
            id="field-local-key"
            type="password"
            value={localKey}
            onChange={(e) => setLocalKey(e.target.value)}
            placeholder={
              editingDevice
                ? `Tersimpan (${editingDevice.masked_key})`
                : 'Masukkan 16 karakter Local Key'
            }
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label
              htmlFor="field-protocol"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              Versi Protokol Tuya
            </label>
            <select
              id="field-protocol"
              value={protocolVersion}
              onChange={(e) => setProtocolVersion(e.target.value as ProtocolVersion)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
            >
              <option value="3.3">Protocol v3.3 (Standar Tuya)</option>
              <option value="3.4">Protocol v3.4 (Session Handshake)</option>
              <option value="3.5">Protocol v3.5 (AES-GCM 6699)</option>
            </select>
          </div>
          <div>
            <label
              htmlFor="field-bulb-type"
              className="mb-1 block text-xs font-medium text-slate-300"
            >
              Profil DPS Lampu
            </label>
            <select
              id="field-bulb-type"
              value={bulbType}
              onChange={(e) => setBulbType(e.target.value as BulbType)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
            >
              <option value="B">Tipe B (DPS 20-26 RGBWW Modern)</option>
              <option value="A">Tipe A (DPS 1-5 Legacy)</option>
            </select>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
          >
            Batal
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-xl bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
          >
            {submitting
              ? 'Menyimpan...'
              : editingDevice
                ? 'Simpan Perubahan'
                : 'Daftarkan Lampu'}
          </button>
        </div>
      </form>
    </Modal>
  );
};
