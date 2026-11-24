import { useEffect, useMemo, useRef, useState, type ComponentProps, type RefObject } from 'react';
import { TableKit } from '@tiptap/extension-table';
import { TaskItem, TaskList } from '@tiptap/extension-list';
import { Markdown } from '@tiptap/markdown';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import { DocsEmbeddedView, isViewReference } from './DocsEmbeddedView';
import { InternalPageLink, ReferenceTitles } from './InternalPageLink';
import { BlockInsertion, BlockMenu, blockCommands, openBlockMenu } from './BlockInsertion';
import { AttachmentLinks, DocsAttachment, DocsCallout, isAttachment } from './DocsRichBlocks';
import { escapeLabel, type AttachmentKind, type AttachmentRequest, type EmbeddedRequest, type LinkRequest, type LinkValue, type OpenDoc } from './api';

const parser = unified().use(remarkParse).use(remarkGfm);
const visualNodes = new Set([
  'root', 'paragraph', 'text', 'heading', 'strong', 'emphasis', 'link',
  'inlineCode', 'list', 'listItem', 'blockquote', 'code', 'break', 'table', 'tableRow', 'tableCell', 'image',
]);
const safeLink = (url: string) => /^https?:\/\/[^\s]+$/i.test(url)
  || /^\/pages\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(url);

type Ast = { type: string; url?: string; title?: string | null; children?: Ast[] };
function supports(node: Ast, parent?: Ast): boolean {
  if (node.type === 'image') return !!node.url && isAttachment(node.url) && !node.title;
  if (node.type === 'link' && node.url && isViewReference(node.url)) {
    return parent?.type === 'paragraph' && parent.children?.length === 1 && !node.title
      && !!node.children?.every(child => child.type === 'text');
  }
  if (node.type === 'link' && (!node.url || !(safeLink(node.url) ||
    (isAttachment(node.url) && !node.title && node.children?.every(child => child.type === 'text'))))) return false;
  return visualNodes.has(node.type) && (node.children?.every(child => supports(child, node)) ?? true);
}

function syntaxTree(source: string) {
  const document = parser.parse(source);
  return { document, fingerprint: JSON.stringify(document, (key, value) => key === 'position' ? undefined : value) };
}

const extensions = [
  StarterKit.configure({
    horizontalRule: false, strike: false, underline: false,
    link: { autolink: false, linkOnPaste: false, openOnClick: 'whenNotEditable',
      isAllowedUri: url => safeLink(url) },
  }),
  Markdown.configure({ markedOptions: { gfm: true } }),
  InternalPageLink,
  DocsAttachment,
  DocsCallout,
  DocsEmbeddedView,
  TableKit.configure({ table: { HTMLAttributes: { 'aria-label': 'Tableau simple' } } }),
  TaskList,
  TaskItem.configure({ nested: true }),
];

export function MarkdownVisual({ value, onChange, onUnsupported, readOnly, references, openLinks, visualLink, openDoc, openAttachment, openEmbedded, assetHref }: {
  value: string; onChange: (markdown: string) => void; onUnsupported: () => void; readOnly: boolean;
  references: ReadonlyMap<string, string>; openLinks: (request: LinkRequest) => void;
  openDoc: OpenDoc;
  openAttachment?: (request: AttachmentRequest) => void;
  openEmbedded?: (request: EmbeddedRequest) => void;
  assetHref?: (id: string, preview?: boolean) => string;
  visualLink: RefObject<((kind: LinkValue['kind']) => void) | null>;
}) {
  const last = useRef<string | undefined>(undefined);
  const callbacks = useRef({ onChange, onUnsupported, openLinks, openAttachment, openEmbedded });
  callbacks.current = { onChange, onUnsupported, openLinks, openAttachment, openEmbedded };
  const [error, setError] = useState('');
  const [menu, setMenu] = useState<ComponentProps<typeof BlockMenu>['menu'] | null>(null);
  const editorRef = useRef<ReturnType<typeof useEditor>>(null);
  const attach = useMemo(() => (kind: AttachmentKind) => {
    const current = editorRef.current;
    if (!current || current.isDestroyed) return;
    const { from, to } = current.state.selection;
    callbacks.current.openAttachment?.({ kind, insert(id, label) {
      if (!current.isDestroyed) current.chain().focus().insertContentAt({ from, to }, {
        type: 'docsAttachment', attrs: { id, label: escapeLabel(label), image: kind === 'image' },
      }).run();
    } });
  }, []);
  const chooseView = useMemo(() => (request: EmbeddedRequest) => callbacks.current.openEmbedded?.(request), []);
  const editorExtensions = useMemo(() => [...extensions, BlockInsertion.configure({ onMenu: setMenu, attach, chooseView })], [attach, chooseView]);
  const editor = useEditor({
    extensions: editorExtensions, content: '', editable: !readOnly, immediatelyRender: false,
    editorProps: { attributes: { role: 'textbox', 'aria-label': 'Contenu de la page',
      'aria-multiline': 'true', 'aria-readonly': String(readOnly) } },
    onUpdate({ editor: changed }) {
      const serialized = changed.getMarkdown();
      last.current = serialized;
      callbacks.current.onChange(serialized);
      if (readOnly || !changed.state.selection.empty || changed.isActive('code')) return;
      const { $from } = changed.state.selection;
      if ($from.parent.type.spec.code) return;
      if (!$from.parent.textBetween(0, $from.parentOffset, '', ' ').endsWith('[[')) return;
      const range = { from: $from.pos - 2, to: $from.pos };
      callbacks.current.openLinks({ kind: 'page', apply(link) {
        if (link.kind === 'page') changed.chain().focus().insertContentAt(range, {
          type: 'internalPageLink', attrs: { id: link.id, label: '' },
        }).run();
      } });
    },
  }, [readOnly]);
  editorRef.current = editor;

  useEffect(() => {
    if (!editor || editor.isDestroyed || value === last.current) return;
    if (!editor.markdown) {
      callbacks.current.onUnsupported();
      return;
    }
    try {
      if (!value.trim()) {
        editor.commands.setContent({ type: 'doc', content: [{ type: 'paragraph' }] }, { emitUpdate: false });
        last.current = value;
        return;
      }
      const original = syntaxTree(value);
      if (!supports(original.document)) {
        callbacks.current.onUnsupported();
        return;
      }
      const parsed = editor.markdown.parse(value);
      const normalized = editor.markdown.serialize(parsed);
      if (syntaxTree(normalized).fingerprint !== original.fingerprint) {
        callbacks.current.onUnsupported();
        return;
      }
      last.current = value;
      editor.commands.setContent(parsed, { emitUpdate: false, errorOnInvalidContent: true });
    } catch {
      callbacks.current.onUnsupported();
    }
  }, [editor, value]);

  useEffect(() => {
    if (!editor || readOnly) return;
    visualLink.current = kind => {
      const { from, to } = editor.state.selection;
      if (editor.state.selection.$from.parent.type.spec.code || editor.isActive('code')) return;
      callbacks.current.openLinks({ kind, apply(link) {
        const content = link.kind === 'page'
          ? { type: 'internalPageLink', attrs: { id: link.id, label: '' } }
          : { type: 'text', text: link.label, marks: [{ type: 'link', attrs: { href: link.url } }] };
        editor.chain().focus().insertContentAt({ from, to }, content).run();
      } });
    };
    return () => { visualLink.current = null; };
  }, [editor, readOnly, visualLink]);

  if (!editor) return <p role="status">Chargement de l’éditeur…</p>;

  const formatters = [
    { name: 'Gras', label: <b>G</b>, apply: () => editor.chain().focus().toggleBold().run() },
    { name: 'Italique', label: <i>I</i>, apply: () => editor.chain().focus().toggleItalic().run() },
    ...[blockCommands.heading, blockCommands.bulletList, blockCommands.orderedList, blockCommands.taskList, blockCommands.quote]
      .map(command => ({ ...command.toolbar, apply: () => command.apply(editor.chain().focus()).run() })),
    { name: 'Code en ligne', label: '< />', apply: () => editor.chain().focus().toggleCode().run() },
    { ...blockCommands.codeBlock.toolbar, apply: () => blockCommands.codeBlock.apply(editor.chain().focus()).run() },
  ];

  function addLink() {
    if (!editor) return;
    const url = window.prompt('Adresse du lien', editor.getAttributes('link').href ?? '');
    if (url === null) return;
    const value = url.trim();
    if (!value) {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
      return;
    }
    if (!safeLink(value)) { setError('Saisissez une adresse HTTP, HTTPS ou un lien de page Circular Docs.'); return; }
    if (editor.state.selection.empty && !editor.isActive('link')) {
      editor.chain().focus().insertContent({ type: 'text', text: value, marks: [{ type: 'link', attrs: { href: value } }] }).run();
    } else {
      editor.chain().focus().extendMarkRange('link').setLink({ href: value }).run();
    }
    setError('');
  }

  return <>
    {!readOnly && <div className="markdown-toolbar" role="group" aria-label="Mise en forme">
      {formatters.map(item => <button key={item.name} className="button" type="button" aria-label={item.name} onClick={item.apply}>{item.label}</button>)}
      <button className="button" type="button" aria-expanded={!!menu} onClick={() => openBlockMenu(editor)}>+ Bloc</button>
      <button className="button" type="button" aria-label="Insérer un lien externe" onClick={addLink}>Lien</button>
    </div>}
    {error && <p role="alert" className="error-message">{error}</p>}
    <AttachmentLinks.Provider value={assetHref ?? (() => '')}>
      <ReferenceTitles.Provider value={{ titles: references, open: openDoc }}>
        <EditorContent className="markdown-visual" editor={editor} />
      </ReferenceTitles.Provider>
    </AttachmentLinks.Provider>
    {!readOnly && menu && <BlockMenu editor={editor} menu={menu} attach={attach} chooseView={chooseView} />}
  </>;
}
