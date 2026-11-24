import { FileText, Table } from '@phosphor-icons/react';
import { docHref, followDoc, type OpenDoc } from './api';

export function DocLink({ entry, open, active, icon, relationContext }: {
  entry: { id: string; title: string }; open: OpenDoc; active?: boolean; icon?: 'page' | 'collection'; relationContext?: string;
}) {
  return <a className={icon ? 'nav-item docs-nav-link' + (active ? ' active' : '') : relationContext ? 'docs-link docs-relation-link' : 'docs-link'}
    href={docHref(entry.id)} title={relationContext} aria-label={relationContext ? entry.title + ' · ' + relationContext : undefined} aria-current={active ? 'page' : undefined} onClick={event => followDoc(event, entry.id, open)}>
    {icon === 'page' && <FileText size={16} aria-hidden />}
    {icon === 'collection' && <Table size={16} aria-hidden />}
    <span>{entry.title}</span>
  </a>;
}
