import { useEffect, useRef, useState } from 'react';
import { Trash } from '@phosphor-icons/react';
import { api } from './api';
import { PROJECT_STATUSES, PROJECT_STATUS_NAMES, type Issue, type IssueInput, type IssueTemplate, type Label, type Project, type Status } from './types';
import { IssueFields } from './IssueFields';
import { Dialog, ErrorMessage, message } from './ui';
import './ticket-features.css';

type ProjectDialogProps = {
  project?: Project;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
};

export function ProjectDialog({ project, onClose, onSaved, onDeleted }: ProjectDialogProps) {
  const [initial] = useState({
    name: project?.name || '',
    key: project?.key || '',
    description: project?.description || '',
    color: project?.color || '#F2CF63',
    status: project?.status || 'planned',
    dueDate: project?.dueDate || null,
  });
  const [data, setData] = useState(initial);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  async function save() {
    if (!form.current?.reportValidity() || pending) return;
    setPending(true);
    setError('');
    try {
      if (project) await api.updateProject(project.id, { name: data.name, description: data.description, color: data.color, status: data.status, dueDate: data.dueDate });
      else await api.createProject(data);
      onSaved();
      onClose();
    } catch (error) {
      setError(message(error));
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (!project || pending || !window.confirm(`Supprimer définitivement le projet « ${project.name} » ?`)) return;
    setPending(true);
    setError('');
    try {
      await api.deleteProject(project.id);
      onDeleted();
      onClose();
    } catch (error) {
      setError(message(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog title={project ? 'Modifier le projet' : 'Nouveau projet'} onClose={onClose} dirty={JSON.stringify(initial) !== JSON.stringify(data)} pending={pending} onSave={save}>
      <form ref={form} className="project-form" aria-busy={pending} onSubmit={event => { event.preventDefault(); void save(); }}>
        <fieldset className="form-body" disabled={pending}>
          <p className="form-intro">{project ? 'Réunissez vos tickets autour d’un même objectif.' : 'Ce projet sera privé. Vous pourrez ensuite inviter des membres depuis sa fiche.'}</p>
          <ErrorMessage>{error}</ErrorMessage>
          <label>
            <span className="field-label">Nom du projet<span className="required-marker" aria-hidden="true"> *</span></span>
            <input required maxLength={100} value={data.name} onChange={event => setData({ ...data, name: event.target.value })} placeholder="Ex. Refonte du site" />
          </label>
          <div className="form-grid project-properties">
            <label className="project-prefix-field">
              <span className="field-label">Préfixe<span className="required-marker" aria-hidden="true"> *</span></span>
              <input required disabled={!!project} pattern="[A-Za-z][A-Za-z0-9]{1,9}" minLength={2} maxLength={10} value={data.key} onChange={event => setData({ ...data, key: event.target.value.toUpperCase() })} placeholder="SITE" aria-describedby="key-help" />
            </label>
            <label className="project-color-field">
              <span className="field-label">Couleur</span>
              <span className="color-control">
                <input type="color" value={data.color} onChange={event => setData({ ...data, color: event.target.value })} />
                <span className="color-value" aria-hidden="true">{data.color.toUpperCase()}</span>
              </span>
            </label>
          </div>
          <p id="key-help" className="field-hint">
            {project ? 'Le préfixe est immuable : les identifiants de vos tickets restent stables.' : '2 à 10 lettres ou chiffres, en commençant par une lettre. Le préfixe sera définitif.'}
          </p>
          <label>
            <span className="field-label">Description du projet</span>
            <textarea rows={3} maxLength={5000} value={data.description} onChange={event => setData({ ...data, description: event.target.value })} placeholder="L’objectif du projet, en quelques mots…" />
          </label>
          <div className="form-grid">
            <label><span className="field-label">Statut du projet</span><select value={data.status} onChange={event => setData({ ...data, status: event.target.value as Project['status'] })}>{PROJECT_STATUSES.map(status => <option key={status} value={status}>{PROJECT_STATUS_NAMES[status]}</option>)}</select></label>
            <label><span className="field-label">Échéance du projet</span><input type="date" value={data.dueDate || ''} onChange={event => setData({ ...data, dueDate: event.target.value || null })} /></label>
          </div>
          {project && project.issueCount > 0 && (
            <p className="field-hint project-delete-hint">
              Ce projet contient {project.issueCount} ticket{project.issueCount > 1 ? 's' : ''}. Déplacez ou supprimez ses tickets avant de le supprimer.
            </p>
          )}
        </fieldset>
        <footer className="dialog-footer save-bar">
          {project ? (
            <button className="button danger" type="button" disabled={pending} onClick={() => void remove()}>
              <Trash size={16} aria-hidden="true" />Supprimer le projet
            </button>
          ) : <span className="shortcut-hint">Ctrl / ⌘ + Entrée pour créer</span>}
          <button className="button primary" disabled={pending} type="submit">
            {pending ? 'Enregistrement…' : project ? 'Enregistrer le projet' : 'Créer le projet'}
          </button>
        </footer>
      </form>
    </Dialog>
  );
}

type TicketDialogProps = {
  projects: Project[];
  labels: Label[];
  projectId?: number;
  status?: Status;
  templates?: IssueTemplate[];
  initialTemplateId?: number;
  onClose: () => void;
  onSaved: (issue?: Issue) => void;
  onLabelCreated: (label: Label) => void;
};

export function TicketDialog({ projects, labels, projectId, status, templates = [], initialTemplateId, onClose, onSaved, onLabelCreated }: TicketDialogProps) {
  const [base] = useState<IssueInput>({
    title: '',
    description: '',
    projectId: projectId || projects[0]?.id || 0,
    status: status || 'todo',
    priority: 'none',
    labelIds: [],
    dueDate: null,
  });
  const fromTemplate = (template: IssueTemplate): IssueInput => ({ ...base, title: template.title, description: template.description, projectId: template.projectId || base.projectId, status: template.status, priority: template.priority, labelIds: template.labelIds.filter(id => labels.some(label => label.id === id)) });
  const [initial, setInitial] = useState<IssueInput>(() => {
    const template = templates.find(item => item.id === initialTemplateId);
    return template ? fromTemplate(template) : base;
  });
  const [data, setData] = useState(initial);
  const [templateId, setTemplateId] = useState(initialTemplateId ? String(initialTemplateId) : '');
  const [createMore, setCreateMore] = useState(false);
  const [created, setCreated] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [labelBusy, setLabelBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const focusAfterCreate = useRef(false);

  useEffect(() => { form.current?.querySelector<HTMLInputElement>('.title-input')?.focus(); }, []);
  useEffect(() => {
    if (!pending && !labelBusy && focusAfterCreate.current) {
      form.current?.querySelector<HTMLInputElement>('.title-input')?.focus();
      focusAfterCreate.current = false;
    }
  }, [pending, labelBusy]);

  async function save() {
    if (!form.current?.reportValidity() || pending || labelBusy) return;
    setPending(true);
    setError('');
    try {
      const issue = await api.createIssue(data);
      onSaved(issue);
      if (createMore) {
        const next = { ...data, title: '', description: '' };
        setData(next);
        setInitial(next);
        setTemplateId('');
        setCreated(`${issue.identifier} créé. Le formulaire est prêt pour le prochain ticket.`);
        focusAfterCreate.current = true;
      } else onClose();
    } catch (error) {
      setError(message(error));
    } finally {
      setPending(false);
    }
  }

  function applyTemplate(value: string) {
    if (JSON.stringify(initial) !== JSON.stringify(data) && !window.confirm('Remplacer le contenu saisi par ce modèle ?')) return;
    const template = templates.find(item => item.id === Number(value));
    const next = template ? fromTemplate(template) : base;
    setTemplateId(value);
    setInitial(next);
    setData(next);
    setCreated('');
  }

  return (
    <Dialog title="Nouveau ticket" onClose={onClose} dirty={JSON.stringify(initial) !== JSON.stringify(data)} pending={pending || labelBusy} onSave={save}>
      <form ref={form} className="ticket-form" aria-busy={pending || labelBusy} onSubmit={event => { event.preventDefault(); void save(); }}>
        <fieldset className="form-body" disabled={pending || labelBusy}>
          <ErrorMessage>{error}</ErrorMessage>
          {created && <p className="ticket-created-note" role="status">{created}</p>}
          {!!templates.length && <label className="ticket-template-field"><span className="field-label">Modèle de ticket</span><select value={templateId} onChange={event => applyTemplate(event.target.value)}><option value="">Sans modèle</option>{templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}</select></label>}
          <IssueFields data={data} setData={setData} projects={projects} labels={labels} onLabelCreated={onLabelCreated} onLabelBusy={setLabelBusy} />
        </fieldset>
        <footer className="dialog-footer save-bar">
          <label className="create-more"><input type="checkbox" checked={createMore} disabled={pending || labelBusy} onChange={event => setCreateMore(event.target.checked)} />Créer un autre</label>
          <button type="submit" className="button primary" disabled={pending || labelBusy}>
            {pending ? 'Création…' : 'Créer le ticket'}
          </button>
        </footer>
      </form>
    </Dialog>
  );
}
