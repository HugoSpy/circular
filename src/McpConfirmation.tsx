import { useEffect, useRef, useState } from 'react';
import { request } from './api';
import { ErrorMessage, message } from './ui';

type ActionState = 'pending' | 'refused' | 'expired' | 'running' | 'done' | 'failed' | 'uncertain';
type Confirmation = {
  id: string; workspace: string; title: string; target: string; details: string[]; state: ActionState;
  result: { message: string; url?: string } | null;
};

const states: Record<Exclude<ActionState, 'pending'>, string> = {
  refused: 'Action refusée.',
  expired: 'La demande a expiré.',
  running: 'Action en cours.',
  done: 'Action confirmée.',
  failed: 'Action refusée par le service.',
  uncertain: 'Résultat à vérifier avant une nouvelle demande.',
};

export function McpConfirmation({ actionId }: { actionId: string }) {
  const [data, setData] = useState<Confirmation>();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const path = '/mcp/actions/' + encodeURIComponent(actionId);

  useEffect(() => {
    const controller = new AbortController();
    void request<Confirmation>(path, { signal: controller.signal }, null)
      .then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(cause => { if (!controller.signal.aborted) setError(message(cause)); });
    return () => controller.abort();
  }, [path]);

  useEffect(() => {
    if (data || error) heading.current?.focus();
  }, [data, error]);

  async function decide(approved: boolean) {
    if (data?.state !== 'pending' || busy || (approved && !checked)) return;
    setError('');
    setBusy(true);
    try {
      setData(await request<Confirmation>(path, { method: 'POST', body: JSON.stringify({ approved }) }, null));
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-shell"><div className="auth-card mcp-consent mcp-consent-v3">
    <div className="auth-brand"><span className="brand-mark" aria-hidden="true" />Circular</div>
    <h1 ref={heading} tabIndex={-1}>{data?.title || 'Confirmation d’une action'}</h1>
    {data && <>
      <p>{data.target}</p>
      <p className="auth-intro">{data.workspace}</p>
      <ul>{data.details.map((detail, index) => <li key={index} className="mcp-action-detail">{detail}</li>)}</ul>
      {data.state === 'pending' ? <form onSubmit={event => { event.preventDefault(); void decide(true); }} aria-busy={busy}>
        <label className="mcp-scope"><input type="checkbox" checked={checked} disabled={busy} onChange={event => setChecked(event.target.checked)} />Je confirme cette action sur la cible indiquée.</label>
        <div className="mcp-actions">
          <button className="button" type="button" disabled={busy} onClick={() => void decide(false)}>Refuser</button>
          <button className="button danger" type="submit" disabled={busy || !checked}>Confirmer</button>
        </div>
      </form> : <div className="mcp-permissions">
        <p role="status">{data.result?.message || states[data.state]}</p>
        {data.result?.url && <a href={data.result.url}>Ouvrir la cible</a>}
        {data.state === 'running' && <button type="button" className="button" onClick={() => location.reload()}>Actualiser</button>}
      </div>}
    </>}
    {!data && !error && <p role="status">Chargement de la demande…</p>}
    <ErrorMessage>{error}</ErrorMessage>
    <p><a href="/">Retour à Circular</a></p>
  </div></main>;
}
