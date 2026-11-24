import { useState } from 'react';
import { Dialog, ErrorMessage } from '../ui';
import { useTemplates } from './useTemplates';
import { DocsForm } from './DocsForms';
import type { CollectionSummary, DocsApi, DocTemplate } from './api';

export function TemplateManager({ api, collections, close }: {
  api: DocsApi; collections: CollectionSummary[]; close: () => void;
}) {
  const templates = useTemplates(api);
  const [action, setAction] = useState<{ mode: 'rename' | 'archive'; template: DocTemplate }>();
  if (action) {
    const rename = action.mode === 'rename';
    const title = rename ? 'Renommer le modèle' : 'Archiver le modèle';
    return <DocsForm key={action.template.id} title={title} action={rename ? 'Renommer' : 'Archiver'} destructive={!rename}
      close={() => setAction(undefined)} submit={async values => {
        if (rename) await api.renameTemplate(action.template.id, String(values.get('name')));
        else await api.archiveTemplate(action.template.id);
        templates.reload();
      }}>
      {rename ? <label>Nouveau nom<input name="name" required maxLength={160} defaultValue={action.template.name} /></label> :
        <p>Archiver « {action.template.name} » ? Les pages déjà créées depuis ce modèle sont conservées.</p>}
    </DocsForm>;
  }
  return <Dialog title="Modèles de l’espace" onClose={close}>
    <div className="form-body">
      <ErrorMessage>{templates.error}</ErrorMessage>
      {templates.error && <button className="button" onClick={templates.reload}>Réessayer</button>}
      {templates.loading ? <p role="status">Chargement des modèles…</p> :
        !templates.error && (templates.items.length ? templates.items.map(template => <div className="docs-template" key={template.id}>
          <div><strong>{template.name}</strong><br />
            <small>{collections.find(collection => collection.id === template.collectionId)?.title ?? 'Espace'}</small></div>
          <div className="docs-row">
            <button className="button" onClick={() => setAction({ mode: 'rename', template })}>Renommer</button>
            <button className="button" onClick={() => setAction({ mode: 'archive', template })}>Archiver</button>
          </div>
        </div>) : <p>Aucun modèle disponible.</p>)}
    </div>
    <div className="dialog-footer"><button className="button" onClick={close}>Fermer</button></div>
  </Dialog>;
}
