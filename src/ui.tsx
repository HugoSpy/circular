import { useEffect, useRef, type ReactNode } from 'react';
import { X, Circle, CircleDashed, CircleHalf, CheckCircle, WarningCircle, Minus, Eye } from '@phosphor-icons/react';
import { PRIORITY_NAMES, STATUS_NAMES, type Priority, type Status } from './types';

export function message(error: unknown) { return error instanceof Error ? error.message : 'Impossible de contacter le serveur.'; }
export function ErrorMessage({ children }: { children?: ReactNode }) { return children ? <div role="alert" className="error-message"><WarningCircle size={17} /><span>{children}</span></div> : null; }
export function StatusMark({ status }: { status: Status }) {
  const Icon = { backlog: CircleDashed, todo: Circle, in_progress: CircleHalf, in_review: Eye, done: CheckCircle }[status];
  return <Icon size={16} className={`status-mark ${status}`} aria-label={STATUS_NAMES[status]} />;
}
export function PriorityMark({ priority }: { priority: Priority }) {
  const level = { none: 0, low: 1, medium: 2, high: 3, urgent: 4 }[priority];
  return <span className={`priority-mark ${priority}`} role="img" aria-label={PRIORITY_NAMES[priority]} title={`Priorité : ${PRIORITY_NAMES[priority]}`}>{priority === 'none' ? <Minus size={16} /> : priority === 'urgent' ? <WarningCircle size={16} weight="fill" /> : <span className="priority-bars" aria-hidden="true">{[1, 2, 3].map(bar => <i key={bar} className={bar <= level ? 'filled' : ''} />)}</span>}</span>;
}
export function Dialog({ title, children, onClose, dirty = false, pending = false, drawer = false, onSave }: { title: string; children: ReactNode; onClose: () => void; dirty?: boolean; pending?: boolean; drawer?: boolean; onSave?: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = () => { if (!pending && (!dirty || window.confirm('Abandonner les modifications non enregistrées ?'))) onClose(); };
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusKey = previous?.dataset.focusKey;
    const dialog = ref.current!;
    dialog.showModal();
    dialog.querySelector<HTMLElement>('input:not([type="checkbox"]):not([type="color"]), textarea, select')?.focus();
    return () => {
      dialog.close();
      requestAnimationFrame(() => {
        if (document.querySelector('dialog[open]')) return;
        const replacement = focusKey ? document.querySelector<HTMLElement>(`[data-focus-key="${CSS.escape(focusKey)}"]`) : null;
        const target = previous?.isConnected ? previous : replacement || document.querySelector<HTMLElement>('main h1');
        target?.focus({ preventScroll: true });
      });
    };
  }, []);
  return <dialog ref={ref} aria-label={title} className={drawer ? 'dialog drawer' : 'dialog'} onCancel={event => { event.preventDefault(); close(); }} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && onSave) { event.preventDefault(); if (!pending) onSave(); } }}>
    <header className="dialog-header"><h2>{title}</h2><button type="button" className="icon-button" aria-label="Fermer" disabled={pending} onClick={close}><X size={18} /></button></header>
    {children}
  </dialog>;
}
