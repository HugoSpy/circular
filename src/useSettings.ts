import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { DEFAULT_SETTINGS, type Settings } from './types';
import { message } from './ui';

/** Serialize changed fields without overwriting unrelated preferences from another tab. */
export function useSettings() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(0);
  const latest = useRef(DEFAULT_SETTINGS);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const failedChanges = useRef<Partial<Settings>>({});
  const generation = useRef(0);
  const failedLoad = useRef(false);
  const mounted = useRef(true);
  const load = useCallback(async () => {
    const version = ++generation.current;
    try {
      await queue.current.catch(() => undefined);
      const stored = await api.settings();
      if (!mounted.current || version !== generation.current) return;
      latest.current = stored;
      setSettings(stored);
      setReady(true);
      setError('');
      failedLoad.current = false;
      failedChanges.current = {};
    } catch (error) { if (mounted.current && version === generation.current) { failedLoad.current = true; setError(message(error)); } }
  }, []);
  useEffect(() => { mounted.current = true; void load(); return () => { mounted.current = false; }; }, [load]);
  const save = useCallback((patch: Partial<Settings>) => {
    generation.current++;
    const snapshot = { ...latest.current, ...patch };
    latest.current = snapshot;
    setSettings(snapshot);
    setPending(count => count + 1);
    const task = queue.current.catch(() => undefined).then(async () => {
      const changes = { ...failedChanges.current, ...patch };
      if (!Object.keys(changes).length) return;
      try {
        await api.updateSettings(changes);
        failedChanges.current = {};
      } catch (error) {
        failedChanges.current = changes;
        throw error;
      }
    });
    queue.current = task;
    return task.then(() => { failedLoad.current = false; if (mounted.current) setError(''); }).catch(error => {
      failedLoad.current = false;
      if (mounted.current) setError(`Réglages non enregistrés : ${message(error)}`);
      throw error;
    }).finally(() => { if (mounted.current) setPending(count => count - 1); });
  }, []);
  useEffect(() => {
    document.documentElement.dataset.fontSize = settings.fontSize;
    document.documentElement.dataset.density = settings.density;
    document.documentElement.dataset.reduceMotion = String(settings.reduceMotion);
  }, [settings.fontSize, settings.density, settings.reduceMotion]);
  const retry = () => failedLoad.current ? load() : save({});
  return { settings, ready, error, saving: pending > 0, save, reload: load, retry };
}
