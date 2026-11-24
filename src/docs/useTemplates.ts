import { useEffect, useState } from 'react';
import { message } from '../ui';
import type { DocsApi, DocTemplate } from './api';

export function useTemplates(api: DocsApi) {
  const [items, setItems] = useState<DocTemplate[]>([]);
  const [error, setError] = useState('');
  const [attempt, retry] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    void api.templates().then(result => {
      if (active) setItems(result);
    }).catch(reason => {
      if (active) setError(message(reason));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [api, attempt]);
  return { items, loading, error, reload: () => retry(value => value + 1) };
}
