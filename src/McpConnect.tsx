import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import { Dialog, ErrorMessage, message } from './ui';
import type { User } from './types';

type Consent = { client: string; workspaces: { id: number; name: string }[] };
type Connection = { id: string; client: string; workspace: string; createdAt: string };
type Connections = { url: string | null; connections: Connection[] };

export function McpConsent({ requestId, user }: { requestId: string; user: User }) {
  const [consent, setConsent] = useState<Consent>();
  const [workspaceId, setWorkspaceId] = useState('');
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let active = true;
    request<Consent>('/mcp/consent', { method: 'POST', body: JSON.stringify({ requestId }) }, null)
      .then(data => { if (active) setConsent(data); })
      .catch(cause => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 404) setExpired(true);
        else setError(message(cause));
      });
    return () => { active = false; };
  }, [requestId, attempt]);
  useEffect(() => { if (consent || expired) heading.current?.focus(); }, [consent, expired]);
  async function decide(approved: boolean) {
    if (busy || (approved && !workspaceId)) return;
    setBusy(true);
    setError('');
    try {
      const { redirectUrl } = await request<{ redirectUrl: string }>('/mcp/consent/decision', {
        method: 'POST', body: JSON.stringify({ requestId, workspaceId: approved ? Number(workspaceId) : null }),
      }, null);
      history.replaceState(null, '', location.pathname);
      location.replace(redirectUrl);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404 && message(cause).includes('expiré')) setExpired(true);
      else setError(message(cause));
      setBusy(false);
    }
  }
  return <main className="auth-shell"><div className="auth-card mcp-consent">
    <div className="auth-brand"><span className="brand-mark" aria-hidden="true" />Circular</div>
    {expired ? <>
      <h1 ref={heading} tabIndex={-1}>La demande a expiré</h1>
      <p className="auth-intro">Relancez la connexion depuis votre assistant IA pour obtenir une nouvelle demande.</p>
      <a href="/?settings=integrations">Retour aux intégrations</a>
    </> : consent ? <>
      <h1 ref={heading} tabIndex={-1}>Autoriser {consent.client} à lire dans Circular</h1>
      <p className="auth-intro">Connecté en tant que {user.displayName || user.username}.</p>
      <form aria-busy={busy} onSubmit={event => { event.preventDefault(); void decide(true); }}>
        <fieldset disabled={busy}>
          <label>Espace autorisé<select value={workspaceId} onChange={event => setWorkspaceId(event.target.value)}>
            <option value="">Choisir un espace</option>
            {consent.workspaces.map(space => <option key={space.id} value={space.id}>{space.name}</option>)}
          </select></label>
        </fieldset>
        {!consent.workspaces.length && <p className="field-hint">Rejoignez un espace Circular pour pouvoir autoriser la lecture.</p>}
        <h2>Accès demandé</h2>
        <ul><li>Lister les projets auxquels vous avez accès.</li><li>Rechercher et consulter les tickets de ces projets.</li></ul>
        <p className="auth-intro">Les résultats sont transmis à {consent.client}. Vous pouvez retirer cet accès dans Paramètres › Intégrations.</p>
        <ErrorMessage>{error}</ErrorMessage>
        <div className="mcp-actions">
          <button className="button" type="button" disabled={busy} onClick={() => void decide(false)}>Refuser</button>
          <button className="button primary" disabled={busy || !workspaceId} type="submit">Autoriser la lecture</button>
        </div>
      </form>
    </> : <>
      <h1>Autorisation de l’assistant</h1>
      <ErrorMessage>{error}</ErrorMessage>
      {error ? <button className="button" onClick={() => { setError(''); setAttempt(value => value + 1); }}>Réessayer</button>
        : <p role="status">Chargement de la demande…</p>}
    </>}
  </div></main>;
}

export function McpConnections() {
  const [data, setData] = useState<Connections>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<Connection>();
  const [busy, setBusy] = useState(false);
  const address = useRef<HTMLInputElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let active = true;
    request<Connections>('/mcp/connections', {}, null).then(result => { if (active) setData(result); })
      .catch(cause => { if (active) setError(message(cause)); });
    return () => { active = false; };
  }, [attempt]);
  async function copy() {
    if (!data?.url) return;
    try { await navigator.clipboard.writeText(data.url); setNotice('Adresse copiée.'); }
    catch { address.current?.select(); setNotice('Sélectionnez et copiez l’adresse du serveur.'); }
  }
  async function revoke(connection: Connection) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await request<void>(`/mcp/connections/${connection.id}`, { method: 'DELETE' }, null);
      setData(current => current && { ...current, connections: current.connections.filter(item => item.id !== connection.id) });
      setNotice(`Accès de ${connection.client} révoqué.`);
      setSelected(undefined);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }
  if (!data) return error
    ? <><ErrorMessage>{error}</ErrorMessage><button className="button" onClick={() => { setError(''); setAttempt(value => value + 1); }}>Réessayer</button></>
    : <p className="field-hint" role="status">Chargement des connexions…</p>;
  if (!data.url) return null;
  return <section className="integration-card mcp-connections" aria-labelledby="mcp-title">
    <h3 id="mcp-title" ref={heading} tabIndex={-1}>Assistants IA</h3>
    <p>Ajoutez cette adresse comme connecteur MCP dans votre assistant IA, puis autorisez l’accès depuis Circular.</p>
    <label htmlFor="mcp-address">Adresse du serveur MCP</label>
    <div className="mcp-actions"><input id="mcp-address" ref={address} readOnly value={data.url} /><button className="button" onClick={() => void copy()}>Copier l’adresse</button></div>
    {notice && <p className="settings-notice" role="status">{notice}</p>}
    <h4>Connexions autorisées</h4>
    {data.connections.length ? data.connections.map(connection => <div className="mcp-connection" key={connection.id}>
      <div><strong>{connection.client}</strong><p>{connection.workspace} · Lecture des projets et tickets</p></div>
      <button className="button danger" aria-label={`Révoquer ${connection.client} pour ${connection.workspace}`} onClick={() => { setError(''); setSelected(connection); }}>Révoquer</button>
    </div>) : <p>Aucune connexion autorisée.</p>}
    {selected && <Dialog title={`Révoquer l’accès de ${selected.client} ?`} pending={busy} onClose={() => setSelected(undefined)} fallbackFocus={heading}>
      <div className="form-body"><ErrorMessage>{error}</ErrorMessage><p>{selected.client} devra obtenir une nouvelle autorisation pour consulter cet espace.</p></div>
      <div className="dialog-footer mcp-actions">
        <button className="button" type="button" disabled={busy} onClick={() => setSelected(undefined)}>Annuler</button>
        <button className="button danger" type="button" disabled={busy} onClick={() => void revoke(selected)}>Révoquer l’accès</button>
      </div>
    </Dialog>}
  </section>;
}
