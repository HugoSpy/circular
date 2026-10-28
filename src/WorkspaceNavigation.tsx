import { useEffect, useRef, useState } from 'react';
import { MagnifyingGlass } from '@phosphor-icons/react';
import { api } from './api';
import { Dialog, ErrorMessage, message } from './ui';
import type { DisplaySettings, Filters, Issue, SavedView } from './types';
import './navigation-features.css';

export function ViewDialog({ view, filters, display, onClose, onSaved }: { view?: SavedView; filters: Filters; display: DisplaySettings; onClose: () => void; onSaved: (view: SavedView) => void }) {
  const [name, setName] = useState(view?.name || '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const form = useRef<HTMLFormElement>(null);
  async function submit() {
    if (pending || !name.trim()) return;
    setPending(true); setError('');
    try {
      const data = { name: name.trim(), filters, display };
      const saved = view ? await api.updateView(view.id, data) : await api.createView(data);
      onSaved(saved); onClose();
    } catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  return <Dialog title={view ? 'Modifier la vue' : 'Enregistrer une vue'} dirty={name !== (view?.name || '')} pending={pending} onClose={onClose} onSave={() => form.current?.requestSubmit()}>
    <form ref={form} onSubmit={event => { event.preventDefault(); void submit(); }}><div className="form-body">
      <label><span className="field-label">Nom de la vue</span><input value={name} required maxLength={80} onChange={event => setName(event.target.value)} placeholder="Par exemple : Priorités de la semaine" /></label>
      <p className="field-hint">La recherche, les filtres et les réglages d’affichage actuels seront enregistrés dans cette vue.</p><ErrorMessage>{error}</ErrorMessage>
    </div><footer className="dialog-footer"><button type="button" className="button subtle" disabled={pending} onClick={onClose}>Annuler</button><button className="button primary" disabled={pending || !name.trim()}>{pending ? 'Enregistrement…' : 'Enregistrer la vue'}</button></footer></form>
  </Dialog>;
}

export type Command = { id: string; label: string; detail?: string; run: () => void };
export function CommandPalette({ commands, onOpenIssue, onClose }: { commands: Command[]; onOpenIssue: (id: number) => void; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [issues, setIssues] = useState<Issue[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(0);
  useEffect(() => {
    let canceled = false;
    setLoading(true);
    const timeout = setTimeout(() => {
      void api.issues(new URLSearchParams({ q: query.trim() }).toString()).then(items => { if (!canceled) { setIssues(items); setError(''); } }).catch(error => { if (!canceled) setError(message(error)); }).finally(() => { if (!canceled) setLoading(false); });
    }, 180);
    return () => { canceled = true; clearTimeout(timeout); };
  }, [query]);
  const normalized = query.toLocaleLowerCase('fr');
  const results: Command[] = [...commands.filter(command => command.label.toLocaleLowerCase('fr').includes(normalized)), ...issues.slice(0, 20).map(issue => ({ id: `issue-${issue.id}`, label: issue.title, detail: issue.identifier, run: () => onOpenIssue(issue.id) }))];
  const chosen = Math.min(active, Math.max(0, results.length - 1));
  function run(command: Command) { onClose(); command.run(); }
  return <Dialog title="Commandes et recherche" onClose={onClose}><div className="form-body command-palette">
    <label className="palette-search"><MagnifyingGlass size={18} /><input role="combobox" aria-label="Rechercher une commande ou un ticket" aria-expanded="true" aria-controls="command-results" aria-autocomplete="list" aria-activedescendant={results[chosen] ? `command-${results[chosen].id}` : undefined} value={query} maxLength={200} placeholder="Une commande, un titre, un identifiant…" onChange={event => { setQuery(event.target.value); setActive(0); }} onKeyDown={event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setActive(index => Math.max(0, Math.min(results.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)))); }
      if (event.key === 'Enter' && results[chosen]) { event.preventDefault(); run(results[chosen]); }
    }} /></label>
    <ErrorMessage>{error}</ErrorMessage><div className="command-results" role="listbox" id="command-results" aria-label="Commandes et tickets">
      {results.map((command, index) => <button id={`command-${command.id}`} key={command.id} role="option" aria-selected={chosen === index} className="command-option" onClick={() => run(command)}><span>{command.label}</span>{command.detail && <small>{command.detail}</small>}</button>)}
    </div>{!results.length && <p className="field-hint">{loading ? 'Recherche…' : 'Aucun résultat.'}</p>}<p className="field-hint">↑ ↓ pour choisir · Entrée pour ouvrir · Échap pour fermer</p>
  </div></Dialog>;
}
