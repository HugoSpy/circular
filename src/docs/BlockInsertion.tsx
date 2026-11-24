import { useLayoutEffect, useRef } from 'react';
import { Extension, type ChainedCommands, type Editor } from '@tiptap/core';
import { closeHistory } from '@tiptap/pm/history';
import { Plugin, PluginKey, TextSelection, type EditorState } from '@tiptap/pm/state';
import type { AttachmentKind, EmbeddedRequest } from './api';

type Command = {
  name: string;
  icon: string;
  keywords: string;
  toolbar?: { name: string; label: string };
  apply?: (chain: ChainedCommands) => ChainedCommands;
  attachment?: AttachmentKind;
  embedded?: boolean;
};

export const blockCommands = {
  paragraph: { name: 'Texte', icon: '¶', keywords: 'paragraphe', apply: chain => chain.setParagraph() },
  heading: {
    name: 'Titre', icon: 'H2', keywords: 'entête heading', toolbar: { name: 'Titre de section', label: 'Titre' },
    apply: chain => chain.toggleHeading({ level: 2 }),
  },
  bulletList: {
    name: 'Liste à puces', icon: '•', keywords: 'liste puces', toolbar: { name: 'Liste à puces', label: 'Liste' },
    apply: chain => chain.toggleBulletList(),
  },
  orderedList: {
    name: 'Liste numérotée', icon: '1.', keywords: 'liste ordre', toolbar: { name: 'Liste numérotée', label: '1.' },
    apply: chain => chain.toggleOrderedList(),
  },
  taskList: {
    name: 'Liste à cocher', icon: '☐', keywords: 'tâche checklist', toolbar: { name: 'Liste de tâches', label: 'Tâche' },
    apply: chain => chain.toggleTaskList(),
  },
  quote: {
    name: 'Citation', icon: '❝', keywords: 'extrait', toolbar: { name: 'Citation', label: 'Citation' },
    apply: chain => chain.toggleBlockquote(),
  },
  codeBlock: {
    name: 'Bloc de code', icon: '<>', keywords: 'code', toolbar: { name: 'Bloc de code', label: 'Bloc de code' },
    apply: chain => chain.toggleCodeBlock(),
  },
} satisfies Record<string, Command>;

const commands: Command[] = [
  ...Object.values(blockCommands),
  { name: 'Tableau simple', icon: '▦', keywords: 'table colonnes', apply: chain =>
    chain.insertTable({ rows: 2, cols: 2, withHeaderRow: true }) },
  { name: 'Encadré', icon: '!', keywords: 'note callout', apply: chain =>
    chain.insertContent({ type: 'docsCallout', attrs: { title: 'À retenir' }, content: [{ type: 'paragraph' }] }) },
  { name: 'Volet', icon: '▸', keywords: 'replier déplier', apply: chain =>
    chain.insertContent({ type: 'docsCallout', attrs: { title: 'Détails', fold: true }, content: [{ type: 'paragraph' }] }) },
  { name: 'Fichier', icon: '↧', keywords: 'pdf pièce jointe', attachment: 'file' },
  { name: 'Image', icon: '▧', keywords: 'photo pièce jointe', attachment: 'image' },
  { name: 'Vue de collection', icon: '▦', keywords: 'tableau liste kanban intégrée', embedded: true },
];
type OpenAttachment = (kind: AttachmentKind) => void;
type ChooseView = (insert: EmbeddedRequest) => void;
type Query = { from: number; to: number; text: string; manual?: boolean };
type Menu = { query: Query; choices: Command[]; active: number };
type PluginState = { menu: Menu | null; dismissed: Query | null; composing: boolean };
type MenuEvent = 'up' | 'down' | 'dismiss' | 'compositionStart' | 'compositionEnd' | 'open';

const key = new PluginKey<PluginState>('docsBlockInsertion');
const menuId = 'docs-block-choices';

function normalized(text: string) {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('fr').trim();
}

function queryAtCursor(state: EditorState): Query | null {
  const { selection } = state;
  if (!(selection instanceof TextSelection) || !selection.empty) return null;
  const { $from } = selection;
  if ($from.depth !== 1 || $from.parent.type.name !== 'paragraph') return null;
  const prefix = $from.parent.textBetween(0, $from.parentOffset, '', '\ufffc');
  const match = /^\/([\p{L}\p{M}\d -]{0,60})$/u.exec(prefix);
  if (!match || $from.marks().some(mark => mark.type.name === 'code' || mark.type.name === 'link')) return null;
  return { from: $from.start(), to: $from.pos, text: match[1] };
}

function sameQuery(left: Query | null, right: Query | null) {
  return !!left && !!right && left.from === right.from && left.to === right.to && left.text === right.text;
}

function matchesSelection(state: EditorState, query: Query) {
  if (!query.manual) return sameQuery(query, queryAtCursor(state));
  const { selection } = state;
  return selection.empty && selection.from === query.from;
}

export function openBlockMenu(editor: Editor) {
  const view = editor.view;
  if (!view.state.selection.empty) editor.commands.setTextSelection(view.state.selection.to);
  view.focus();
  view.dispatch(view.state.tr.setMeta(key, 'open'));
}

function currentMenu(editor: Editor) {
  return key.getState(editor.state)?.menu;
}

function applyBlock(editor: Editor, command: Command, attach: OpenAttachment, chooseView: ChooseView): boolean {
  const menu = currentMenu(editor);
  if (!editor.isEditable || !menu || !menu.choices.includes(command) || !matchesSelection(editor.state, menu.query)) return false;

  const { from, to } = menu.query;
  if (command.embedded) {
    const document = editor.state.doc;
    editor.view.dispatch(editor.state.tr.setMeta(key, 'dismiss'));
    chooseView(reference => {
      if (editor.isDestroyed || !editor.isEditable || !editor.state.doc.eq(document)) return;
      editor.chain().command(({ tr }) => { closeHistory(tr); return true; })
        .insertContentAt({ from, to }, { type: 'docsEmbeddedView', attrs: reference }).focus().run();
    });
    return true;
  }
  if (command.apply && !command.apply(editor.can().chain().deleteRange({ from, to })).run()) return false;
  const chain = editor.chain().command(({ tr }) => {
    closeHistory(tr).setMeta(key, 'dismiss');
    return true;
  }).deleteRange({ from, to });
  if (command.attachment) {
    if (!chain.run()) return false;
    attach(command.attachment);
    return true;
  }
  return command.apply?.(chain).focus().run() ?? false;
}

export const BlockInsertion = Extension.create<{ onMenu: (menu: Menu | null) => void; attach: OpenAttachment; chooseView: ChooseView }>({
  name: 'docsBlockInsertion',
  priority: 110,
  addOptions: () => ({ onMenu: () => undefined, attach: () => undefined, chooseView: () => undefined }),
  addProseMirrorPlugins() {
    const { editor, options } = this;
    return [new Plugin<PluginState>({
      key,
      state: {
        init: () => ({ menu: null, dismissed: null, composing: false }),
        apply(transaction, previous, _old, state) {
          const event: MenuEvent | undefined = transaction.getMeta(key);
          const query = queryAtCursor(state);
          if (event === 'open' && editor.isEditable) {
            const { from, to } = state.selection;
            return { menu: { query: { from, to, text: '', manual: true }, choices: commands, active: 0 },
              dismissed: null, composing: false };
          }
          if (event === 'compositionStart') return { menu: null, dismissed: null, composing: true };
          if (event === 'dismiss') return { ...previous, menu: null, dismissed: query };
          if (previous.composing && event !== 'compositionEnd') return previous;

          const menu = previous.menu;
          if (menu && !transaction.docChanged && matchesSelection(state, menu.query)) {
            if (!menu.choices.length || (event !== 'up' && event !== 'down')) return previous;
            const step = event === 'up' ? -1 : 1;
            return { ...previous, menu: { ...menu, active: (menu.active + step + menu.choices.length) % menu.choices.length } };
          }
          if (!query || sameQuery(previous.dismissed, query) || (!transaction.docChanged && event !== 'compositionEnd')
            || transaction.getMeta('preventUpdate') || !editor.isEditable) {
            return { menu: null, dismissed: query, composing: false };
          }

          const term = normalized(query.text);
          const choices = commands.filter(command => normalized(command.name + ' ' + command.keywords).includes(term));
          return { menu: { query, choices, active: 0 }, dismissed: null, composing: false };
        },
      },
      props: {
        handleKeyDown(view, event) {
          const menu = key.getState(view.state)?.menu;
          if (!menu || !editor.isEditable || view.composing || event.isComposing) return false;
          if (event.key === 'Escape') {
            view.dispatch(view.state.tr.setMeta(key, 'dismiss'));
            return true;
          }
          if (!menu.choices.length || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return false;
          if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
            view.dispatch(view.state.tr.setMeta(key, event.key === 'ArrowUp' ? 'up' : 'down'));
            return true;
          }
          return event.key === 'Enter' && applyBlock(editor, menu.choices[menu.active], options.attach, options.chooseView);
        },
        handleDOMEvents: {
          blur(view) {
            if (key.getState(view.state)?.menu) view.dispatch(view.state.tr.setMeta(key, 'dismiss'));
            return false;
          },
          compositionstart(view) {
            view.dispatch(view.state.tr.setMeta(key, 'compositionStart'));
            return false;
          },
          compositionend(view) {
            requestAnimationFrame(() => {
              if (!view.isDestroyed) view.dispatch(view.state.tr.setMeta(key, 'compositionEnd'));
            });
            return false;
          },
        },
      },
      view() {
        let displayed: Menu | null = null;
        return {
          update(view) {
            const menu = view.hasFocus() && editor.isEditable ? key.getState(view.state)?.menu ?? null : null;
            if (menu !== displayed) {
              displayed = menu;
              options.onMenu(menu);
            }
          },
          destroy() { if (displayed) options.onMenu(null); },
        };
      },
    })];
  },
});

export function BlockMenu({ editor, menu, attach, chooseView }: { editor: Editor; menu: Menu; attach: OpenAttachment; chooseView: ChooseView }) {
  const ref = useRef<HTMLElement>(null);
  const activeId = menu.choices.length ? 'docs-block-choice-' + menu.active : undefined;

  useLayoutEffect(() => {
    if (editor.isDestroyed) return;
    const editable = editor.view.dom;
    editable.setAttribute('aria-autocomplete', 'list');
    editable.setAttribute('aria-controls', menuId);
    if (activeId) editable.setAttribute('aria-activedescendant', activeId);
    return () => {
      editable.removeAttribute('aria-autocomplete');
      editable.removeAttribute('aria-controls');
      editable.removeAttribute('aria-activedescendant');
    };
  }, [activeId, editor]);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const viewport = window.visualViewport;

    function place() {
      if (!element || editor.isDestroyed || !matchesSelection(editor.state, menu.query)) return;
      const cursor = editor.view.coordsAtPos(menu.query.to);
      const margin = 12;
      const viewportLeft = viewport?.offsetLeft ?? 0;
      const viewportTop = viewport?.offsetTop ?? 0;
      const viewportWidth = viewport?.width ?? window.innerWidth;
      const viewportBottom = viewportTop + (viewport?.height ?? window.innerHeight);
      element.style.maxWidth = Math.max(1, viewportWidth - 2 * margin) + 'px';
      element.style.maxHeight = '';
      const left = Math.max(viewportLeft + margin, Math.min(cursor.left, viewportLeft + viewportWidth - element.offsetWidth - margin));
      const topEdge = viewportTop + margin;
      const bottomEdge = Math.max(topEdge, viewportBottom - margin);
      const cursorTop = Math.min(bottomEdge, Math.max(topEdge, cursor.top));
      const cursorBottom = Math.min(bottomEdge, Math.max(cursorTop, cursor.bottom));
      const above = cursorTop - topEdge;
      const below = bottomEdge - cursorBottom;
      const up = element.offsetHeight > below && above > below;
      const gap = 5;
      const available = Math.max(1, (up ? above : below) - gap);
      element.style.maxHeight = available + 'px';
      const top = up ? cursorTop - element.offsetHeight - gap : cursorBottom + gap;
      element.style.inset = `${Math.max(viewportTop + gap, top)}px auto auto ${left}px`;
    }

    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    viewport?.addEventListener('resize', place);
    viewport?.addEventListener('scroll', place);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
      viewport?.removeEventListener('resize', place);
      viewport?.removeEventListener('scroll', place);
    };
  }, [editor, menu.query]);

  useLayoutEffect(() => {
    if (activeId) document.getElementById(activeId)?.scrollIntoView({ block: 'nearest' });
  }, [activeId]);

  return <section className="docs-block-menu" aria-label="Commandes d’insertion" ref={ref}>
    <p className="docs-block-menu-heading">Insérer un bloc</p>
    <div id={menuId} className="docs-block-options" role="listbox" aria-label="Types de bloc" hidden={!menu.choices.length}>
      {menu.choices.map((command, index) => <div key={command.name} id={'docs-block-choice-' + index} role="option"
        aria-selected={index === menu.active} onPointerDown={event => event.preventDefault()}
        onClick={() => applyBlock(editor, command, attach, chooseView)}>
        <span className="docs-block-icon" aria-hidden="true">{command.icon}</span>{command.name}
      </div>)}
    </div>
    {!menu.choices.length && <p className="docs-block-empty" role="status">Aucun bloc trouvé.</p>}
    <p className="docs-block-menu-help" aria-hidden="true">↑ ↓ Choisir · Entrée Insérer · Échap Fermer</p>
  </section>;
}
