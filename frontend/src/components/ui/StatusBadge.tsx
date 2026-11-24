import React from 'react';
import type { ConnectionMode } from '../../types/bardi';

interface StatusBadgeProps {
  online: boolean;
  connectionMode: ConnectionMode;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ online, connectionMode }) => {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
          online
            ? 'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30'
            : 'bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30'
        }`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            online ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
          }`}
        />
        {online ? 'Online' : 'Offline'}
      </span>
      <span
        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
          connectionMode === 'virtual'
            ? 'bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/30'
            : 'bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-500/30'
        }`}
      >
        {connectionMode === 'virtual' ? 'Virtual Simulator' : 'Physical LAN'}
      </span>
    </div>
  );
};
