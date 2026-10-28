import { useState } from 'react';
import { Plus } from '@phosphor-icons/react';
import { api } from './api';
import { PRIORITIES, PRIORITY_NAMES, STATUSES, STATUS_NAMES, type IssueInput, type Label, type Project } from './types';
import { ErrorMessage, message } from './ui';

type LabelPickerProps = {
  labels: Label[];
  selected: number[];
  onChange: (ids: number[]) => void;
  onCreated: (label: Label) => void;
  onBusy: (value: boolean) => void;
};

export function LabelPicker({ labels, selected, onChange, onCreated, onBusy }: LabelPickerProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function create() {
    if (!name.trim() || pending || selected.length >= 20) return;
    setPending(true);
    onBusy(true);
    setError('');
    try {
      const label = await api.createLabel(name.trim(), '#F2CF63');
      onCreated(label);
      onChange([...selected, label.id]);
      setName('');
      setCreating(false);
    } catch (error) {
      setError(message(error));
    } finally {
      setPending(false);
      onBusy(false);
    }
  }

  return (
    <fieldset className="label-editor">
      <legend>Étiquettes</legend>
      <div className="label-editor-content">
        <div className="label-options">
          {labels.length ? labels.map(label => (
            <label key={label.id} className="label-option">
              <input
                type="checkbox"
                disabled={pending || (selected.length >= 20 && !selected.includes(label.id))}
                checked={selected.includes(label.id)}
                onChange={event => onChange(event.target.checked ? [...selected, label.id] : selected.filter(id => id !== label.id))}
              />
              <span className="label-option-dot" style={{ background: label.color }} aria-hidden="true" />
              {label.name}
            </label>
          )) : <p className="label-empty">Aucune étiquette pour le moment.</p>}
        </div>
        {creating ? (
          <div className="label-create">
            <input
              aria-label="Nom de l’étiquette"
              maxLength={40}
              value={name}
              onChange={event => setName(event.target.value)}
              placeholder="Nom de l’étiquette"
              onKeyDown={event => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  event.stopPropagation();
                  void create();
                }
              }}
            />
            <button type="button" className="button" disabled={pending || !name.trim()} onClick={() => void create()}>
              {pending ? 'Création…' : 'Créer l’étiquette'}
            </button>
            <button type="button" className="button subtle" disabled={pending} onClick={() => { setCreating(false); setError(''); }}>
              Annuler
            </button>
          </div>
        ) : (
          <button type="button" className="label-create-toggle" disabled={selected.length >= 20} onClick={() => setCreating(true)}>
            <Plus size={14} aria-hidden="true" />Nouvelle étiquette
          </button>
        )}
      </div>
      {selected.length >= 20 && <p className="field-hint label-limit">20 étiquettes maximum par ticket.</p>}
      <ErrorMessage>{error}</ErrorMessage>
    </fieldset>
  );
}

type IssueFieldsProps = {
  data: IssueInput;
  setData: (data: IssueInput) => void;
  projects: Project[];
  labels: Label[];
  onLabelCreated: (label: Label) => void;
  onLabelBusy: (value: boolean) => void;
};

export function IssueFields({ data, setData, projects, labels, onLabelCreated, onLabelBusy }: IssueFieldsProps) {
  return (
    <>
      <div className="issue-writing">
        <label className="issue-title-field">
          <span className="field-label">Titre<span className="required-marker" aria-hidden="true"> *</span></span>
          <input className="title-input" required maxLength={240} value={data.title} onChange={event => setData({ ...data, title: event.target.value })} placeholder="Que faut-il accomplir ?" />
        </label>
        <label className="issue-description-field">
          <span className="field-label">Description</span>
          <textarea rows={4} maxLength={20000} value={data.description} onChange={event => setData({ ...data, description: event.target.value })} placeholder="Contexte, objectif, critères de réussite…" />
        </label>
      </div>
      <div className="issue-properties">
        <label className="issue-project-field">
          <span className="field-label">Projet<span className="required-marker" aria-hidden="true"> *</span></span>
          <select required value={data.projectId} onChange={event => setData({ ...data, projectId: Number(event.target.value) })}>
            {projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>
        <label>
          <span className="field-label">Statut</span>
          <select value={data.status} onChange={event => setData({ ...data, status: event.target.value as IssueInput['status'] })}>
            {STATUSES.map(status => <option key={status} value={status}>{STATUS_NAMES[status]}</option>)}
          </select>
        </label>
        <label>
          <span className="field-label">Priorité</span>
          <select value={data.priority} onChange={event => setData({ ...data, priority: event.target.value as IssueInput['priority'] })}>
            {PRIORITIES.map(priority => <option key={priority} value={priority}>{PRIORITY_NAMES[priority]}</option>)}
          </select>
        </label>
        <label className="issue-due-field">
          <span className="field-label">Échéance</span>
          <input type="date" value={data.dueDate || ''} onChange={event => setData({ ...data, dueDate: event.target.value || null })} />
        </label>
      </div>
      <LabelPicker labels={labels} selected={data.labelIds} onChange={labelIds => setData({ ...data, labelIds })} onCreated={onLabelCreated} onBusy={onLabelBusy} />
    </>
  );
}
