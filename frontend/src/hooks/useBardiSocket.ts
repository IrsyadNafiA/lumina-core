import { useEffect, useRef, useState } from 'react';
import { resolveWsUrl } from '../lib/api';
import type { DeviceView, WsEventFrame } from '../types/bardi';

interface UseBardiSocketOptions {
  accessToken: string;
  enabled: boolean;
  onSnapshot: (devices: DeviceView[]) => void;
  onDeviceUpdated: (device: DeviceView) => void;
  onDeviceRemoved: (deviceId: string) => void;
}

export function useBardiSocket({
  accessToken,
  enabled,
  onSnapshot,
  onDeviceUpdated,
  onDeviceRemoved,
}: UseBardiSocketOptions): { connected: boolean } {
  const [connected, setConnected] = useState(false);
  const callbacksRef = useRef({ onSnapshot, onDeviceUpdated, onDeviceRemoved });

  useEffect(() => {
    callbacksRef.current = { onSnapshot, onDeviceUpdated, onDeviceRemoved };
  }, [onSnapshot, onDeviceUpdated, onDeviceRemoved]);

  useEffect(() => {
    if (!enabled || typeof WebSocket === 'undefined') {
      setConnected(false);
      return;
    }

    let unmounted = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let ws: WebSocket | null = null;

    const connect = () => {
      if (unmounted) return;
      const url = resolveWsUrl(accessToken);

      try {
        ws = new WebSocket(url);
      } catch {
        setConnected(false);
        return;
      }

      ws.onopen = () => {
        if (!unmounted) setConnected(true);
      };

      ws.onmessage = (event) => {
        if (unmounted) return;
        try {
          const frame = JSON.parse(String(event.data)) as WsEventFrame;
          if (frame.event === 'snapshot' && Array.isArray(frame.payload)) {
            callbacksRef.current.onSnapshot(frame.payload as DeviceView[]);
          } else if (frame.event === 'device_updated' && frame.payload) {
            callbacksRef.current.onDeviceUpdated(frame.payload as DeviceView);
          } else if (
            frame.event === 'device_removed' &&
            frame.payload &&
            typeof (frame.payload as { device_id?: string }).device_id === 'string'
          ) {
            callbacksRef.current.onDeviceRemoved(
              (frame.payload as { device_id: string }).device_id,
            );
          }
        } catch {
          // Ignore malformed frame
        }
      };

      ws.onclose = (evt) => {
        if (unmounted) return;
        setConnected(false);
        if (evt.code !== 4401) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        if (!unmounted) setConnected(false);
      };
    };

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      if (ws !== null) {
        try {
          ws.close();
        } catch {
          // Ignore close errors on unmount
        }
      }
    };
  }, [accessToken, enabled]);

  return { connected };
}
