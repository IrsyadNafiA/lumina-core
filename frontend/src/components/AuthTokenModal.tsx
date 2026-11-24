import React, { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Modal } from './ui/Modal';

interface AuthTokenModalProps {
  open: boolean;
  onClose: () => void;
  onSubmitToken: (token: string) => Promise<void>;
}

export const AuthTokenModal: React.FC<AuthTokenModalProps> = ({
  open,
  onClose,
  onSubmitToken,
}) => {
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) {
      setError('Masukkan BARDI_ACCESS_TOKEN terlebih dahulu.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await onSubmitToken(token.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Token akses tidak valid');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="Autentikasi Akses Lokal BARDI" open={open} onClose={onClose}>
      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 text-sm">
        <p className="text-xs text-slate-300">
          Server ini mengaktifkan proteksi <code className="text-cyan-300">BARDI_ACCESS_TOKEN</code>.
          Masukkan PIN atau Access Token Anda untuk mengontrol lampu.
        </p>
        {error && (
          <div
            role="alert"
            className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-3 text-xs text-rose-200"
          >
            {error}
          </div>
        )}
        <div>
          <label
            htmlFor="field-access-token"
            className="mb-1 block text-xs font-medium text-slate-300"
          >
            PIN / Access Token (X-Bardi-Token)
          </label>
          <div className="relative">
            <KeyRound className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-slate-500" />
            <input
              id="field-access-token"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Masukkan token akses"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2 pr-3 pl-9 text-xs text-slate-100"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="submit"
            disabled={loading}
            className="rounded-xl bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-400"
          >
            {loading ? 'Memverifikasi...' : 'Buka Dashboard'}
          </button>
        </div>
      </form>
    </Modal>
  );
};
