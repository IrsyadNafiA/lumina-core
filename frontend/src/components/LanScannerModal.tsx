import React from 'react';
import { CheckCircle2, PlusCircle, Radar, RefreshCw } from 'lucide-react';
import type { DiscoveredDevice } from '../types/bardi';
import { Modal } from './ui/Modal';

interface LanScannerModalProps {
  open: boolean;
  scanning: boolean;
  discovered: DiscoveredDevice[];
  error: string | null;
  onClose: () => void;
  onRescan: () => Promise<void>;
  onSelectDevice: (device: DiscoveredDevice) => void;
}

export const LanScannerModal: React.FC<LanScannerModalProps> = ({
  open,
  scanning,
  discovered,
  error,
  onClose,
  onRescan,
  onSelectDevice,
}) => {
  return (
    <Modal title="Auto-Discovery Scanner (Wi-Fi LAN & Simulator)" open={open} onClose={onClose}>
      <div className="space-y-4 text-sm">
        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 p-3">
          <div className="flex items-center gap-2.5 text-xs text-slate-300">
            <Radar
              className={`h-5 w-5 text-cyan-400 ${scanning ? 'animate-spin' : ''}`}
            />
            <span>
              {scanning
                ? 'Memindai paket UDP Tuya (port 6666/6667/7000) & perangkat virtual...'
                : `Ditemukan ${discovered.length} perangkat BARDI.`}
            </span>
          </div>
          <button
            type="button"
            disabled={scanning}
            onClick={() => void onRescan()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${scanning ? 'animate-spin' : ''}`} />
            Scan Ulang
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-3 text-xs text-rose-200"
          >
            {error}
          </div>
        )}

        <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
          {discovered.map((item) => (
            <div
              key={item.device_id}
              className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 p-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-100">
                    {item.suggested_name || item.registered_name || item.device_id}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      item.connection_mode === 'virtual'
                        ? 'bg-violet-500/15 text-violet-300'
                        : 'bg-cyan-500/15 text-cyan-300'
                    }`}
                  >
                    {item.connection_mode === 'virtual' ? 'Simulator' : 'Physical LAN'}
                  </span>
                </div>
                <p className="mt-0.5 font-mono text-xs text-slate-400">
                  ID: {item.device_id} • IP: {item.ip_address} • v{item.protocol_version}
                </p>
              </div>

              {item.already_registered ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
                  <CheckCircle2 className="h-4 w-4" />
                  Terdaftar
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => onSelectDevice(item)}
                  className="inline-flex items-center gap-1 rounded-xl bg-cyan-500 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400"
                >
                  <PlusCircle className="h-3.5 w-3.5" />
                  Gunakan
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
};
