import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from './api';
import { Dialog, ErrorMessage, message } from './ui';
import type { User } from './types';

type Family = { id: string; label: string; read: string; write: string | null };
type Consent = { client: string; write: boolean; families?: Family[]; workspaces: { id: number; name: string }[] };
type Connection = { id: string; client: string; workspace: string; createdAt: string; write: boolean; families?: Family[] };
type Connections = { url: string | null; connections: Connection[] };
const accessLabel = (write: boolean) => write ? 'Lecture et écriture' : 'Lecture seule';
const connectionLabel = (connection: Connection) => connection.families?.length ? 'Accès personnalisés' : accessLabel(connection.write);
const familyDescription: Record<string, string> = {
  tickets: 'Lire les discussions et l’historique. Modifier les champs des tickets selon vos droits.',
  projects: 'Consulter les projets et la feuille de route. Créer ou mettre à jour des éléments de planification.',
  docs: 'Rechercher et lire les documents. Modifier les documents et leurs discussions selon vos droits.',
  customers: 'Consulter les fiches clients et les demandes. Enregistrer et rattacher des demandes.',
  releases: 'Consulter les pipelines, les releases et les notes. Mettre à jour les releases et leurs critères de revue.',
  agents: 'Consulter les consignes, les notes et les blocages. Mettre à jour le contexte partagé.',
};

export function McpConsent({ requestId, user }: { requestId: string; user: User }) {
  const [consent, setConsent] = useState<Consent>();
  const [workspaceId, setWorkspaceId] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [legacyWrite, setLegacyWrite] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let active = true;
    request<Consent>('/mcp/consent', { method: 'POST', body: JSON.stringify({ requestId }) }, null)
      .then(data => { if (active) { setConsent(data); setScopes([]); setLegacyWrite(false); setWorkspaceId(''); } })
      .catch(cause => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 404) setExpired(true);
        else setError(message(cause));
      });
    return () => { active = false; };
  }, [requestId, attempt]);
  useEffect(() => { if (consent || expired) heading.current?.focus(); }, [consent, expired]);
  function changeFamily(family: Family, mode: 'read' | 'write', checked: boolean) {
    setScopes(current => {
      const next = new Set(current);
      if (mode === 'read') {
        if (checked) next.add(family.read);
        else {
          next.delete(family.read);
          if (family.write) next.delete(family.write);
        }
      } else if (family.write) {
        if (checked) { next.add(family.read); next.add(family.write); }
        else next.delete(family.write);
      }
      return [...next];
    });
  }
  async function decide(approved: boolean) {
    if (busy || (approved && !workspaceId)) return;
    setBusy(true);
    setError('');
    try {
      const { redirectUrl } = await request<{ redirectUrl: string }>('/mcp/consent/decision', {
        method: 'POST', body: JSON.stringify({ requestId, workspaceId: approved ? Number(workspaceId) : null,
          write: Boolean(approved && (consent?.families ? legacyWrite : consent?.write)),
          scopes: consent?.families ? scopes : undefined }),
      }, null);
      history.replaceState(null, '', location.pathname);
      location.replace(redirectUrl);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404 && message(cause).includes('expiré')) setExpired(true);
      else setError(message(cause));
      setBusy(false);
    }
  }
  return <main className="auth-shell"><div className={`auth-card mcp-consent${consent?.families ? ' mcp-consent-v3' : ''}`}>
    <div className="auth-brand"><span className="brand-mark" aria-hidden="true" />Circular</div>
    {expired ? <>
      <h1 ref={heading} tabIndex={-1}>La demande a expiré</h1>
      <p className="auth-intro">Relancez la connexion depuis votre assistant IA pour obtenir une nouvelle demande.</p>
      <a href="/?settings=integrations">Retour aux intégrations</a>
    </> : consent ? <>
      <h1 ref={heading} tabIndex={-1}>{consent.families ? `Autoriser ${consent.client} dans Circular` : `Autoriser ${consent.client} à ${consent.write ? 'lire et à écrire' : 'lire'} dans Circular`}</h1>
      <p className="auth-intro">Connecté en tant que {user.displayName || user.username}.</p>
      <form aria-busy={busy} onSubmit={event => { event.preventDefault(); void decide(true); }}>
        <fieldset disabled={busy}>
          <label>Espace autorisé<select value={workspaceId} onChange={event => setWorkspaceId(event.target.value)}>
            <option value="">Choisir un espace</option>
            {consent.workspaces.map(space => <option key={space.id} value={space.id}>{space.name}</option>)}
          </select></label>
        </fieldset>
        {!consent.workspaces.length && <p className="field-hint">Rejoignez un espace Circular pour pouvoir autoriser l’accès.</p>}
        <div className="mcp-permissions">
          <h2>{consent.families ? 'Lecture de base' : 'Lecture'}</h2>
          <ul><li>Lister les projets auxquels vous avez accès.</li><li>Rechercher et consulter les tickets de ces projets.</li></ul>
          {consent.write && !consent.families && <div className="mcp-write-permissions">
            <h2>Écriture</h2>
            <ul><li>Créer un ticket dans un projet où vous pouvez le faire.</li><li>Ajouter un commentaire à un ticket que vous pouvez commenter.</li></ul>
          </div>}
          {consent.families && <div className="mcp-families">
            {consent.write && <fieldset disabled={busy}><label className="mcp-scope"><input type="checkbox" checked={legacyWrite} onChange={event => setLegacyWrite(event.target.checked)} />Créer des tickets et ajouter des commentaires</label></fieldset>}
            {consent.families.map(family => <fieldset key={family.id} disabled={busy}>
              <legend>{family.label}</legend>
              <p className="field-hint">{familyDescription[family.id]}</p>
              <div className="mcp-actions">
                <label className="mcp-scope"><input type="checkbox" checked={scopes.includes(family.read)} onChange={event => changeFamily(family, 'read', event.target.checked)} />Consulter</label>
                {family.write && <label className="mcp-scope"><input type="checkbox" checked={scopes.includes(family.write)} onChange={event => changeFamily(family, 'write', event.target.checked)} />Modifier</label>}
              </div>
            </fieldset>)}
          </div>}
        </div>
        <p className="auth-intro">Les résultats sont transmis à {consent.client}. Vous pouvez révoquer cet accès dans Paramètres › Intégrations › Assistants IA.</p>
        <ErrorMessage>{error}</ErrorMessage>
        <div className="mcp-actions">
          <button className="button" type="button" disabled={busy} onClick={() => void decide(false)}>Refuser</button>
          <button className="button primary" disabled={busy || !workspaceId} type="submit">{consent.families ? 'Autoriser les accès sélectionnés' : consent.write ? 'Autoriser la lecture et l’écriture' : 'Autoriser la lecture'}</button>
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
      setNotice(`Connexion de ${connection.client} révoquée pour « ${connection.workspace} ».`);
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
      <div><strong>{connection.client}</strong><p>{connection.workspace} · {connectionLabel(connection)}</p>
        {connection.families && <details><summary>Détail des autorisations</summary><ul>
          <li>Lecture de base</li>
          {connection.write && <li>Création de tickets et commentaires</li>}
          {connection.families.map(family => <li key={family.id}>{family.label} · {family.write ? 'Consultation et modification' : 'Consultation'}</li>)}
        </ul></details>}
      </div>
      <button className="button danger" aria-label={`Révoquer ${connection.client} pour ${connection.workspace} (${connectionLabel(connection).toLowerCase()})`} onClick={() => { setError(''); setSelected(connection); }}>Révoquer</button>
    </div>) : <p>Aucune connexion autorisée.</p>}
    {selected && <Dialog title={selected.families ? `Révoquer cette connexion de ${selected.client} ?` : `Révoquer l’accès de ${selected.client} en ${connectionLabel(selected).toLowerCase()} ?`} pending={busy} onClose={() => setSelected(undefined)} fallbackFocus={heading}>
      <div className="form-body"><ErrorMessage>{error}</ErrorMessage><p>{selected.client} perdra cette autorisation pour l’espace « {selected.workspace} ».</p></div>
      <div className="dialog-footer mcp-actions">
        <button className="button" type="button" disabled={busy} onClick={() => setSelected(undefined)}>Annuler</button>
        <button className="button danger" type="button" disabled={busy} onClick={() => void revoke(selected)}>Révoquer l’accès</button>
      </div>
    </Dialog>}
  </section>;
}
