import { useEffect, useState } from 'react';
import type { DocCollection, DocsApi } from './api';

type Load = { id: string; collection?: DocCollection; error?: unknown };

export function useCollection(api: DocsApi, id: string | undefined, refreshKey: number) {
  const [result, setResult] = useState<Load>();
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    void api.collection(id, controller.signal).then(collection => {
      if (!controller.signal.aborted) setResult({ id, collection });
    }).catch(error => {
      if (!controller.signal.aborted) setResult({ id, error });
    });
    return () => controller.abort();
  }, [api, id, refreshKey]);
  return result?.id === id ? result : undefined;
}
