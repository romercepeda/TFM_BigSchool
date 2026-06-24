import { signal } from '@preact/signals-core';
import type { Notification } from '../api/types.js';

export const pendingNotifications = signal<Notification[]>([]);

let _timerId: ReturnType<typeof setInterval> | null = null;

export function startPolling(
  fetchFn: () => Promise<Notification[]>,
  intervalSeconds: number,
): void {
  stopPolling();
  const tick = async (): Promise<void> => {
    try {
      pendingNotifications.value = await fetchFn();
    } catch {
      // silent — polling failures don't break the UI
    }
  };
  void tick();
  _timerId = setInterval(() => void tick(), intervalSeconds * 1000);
}

export function stopPolling(): void {
  if (_timerId !== null) {
    clearInterval(_timerId);
    _timerId = null;
  }
}
