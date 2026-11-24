import { useContext, useState } from 'react';
import { Node } from '@tiptap/core';
import { NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';
import { ApiError } from '../api';
import { ErrorMessage, message } from '../ui';
import { CollectionRows } from './DocsCollection';
import { EmbeddedViews, type EmbeddedContext } from './DocsEmbeddedViewPicker';
import { useCollection } from './useCollection';
import { docHref, followDoc, viewReferenceHref } from './api';

const uuid = '([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})';
const path = '/collections/' + uuid + '/views/' + uuid;
const viewPath = new RegExp('^' + path + '$', 'i');
const block = String.raw`^\[((?:\\.|[^\]\\\r\n])*)\]\(` + path + String.raw`\)[ \t]*(?=\r?\n[ \t]*\r?\n|\r?\n?$)`;
const viewBlock = new RegExp(block, 'i');
const blockStart = new RegExp(block, 'im');

export const isViewReference = (href: string) => viewPath.test(href);

function EmbeddedViewContent({ context, node, editor, deleteNode, getPos }: NodeViewProps & { context: EmbeddedContext }) {
  const collectionId = String(node.attrs.collectionId).toLowerCase();
  const viewId = String(node.attrs.viewId).toLowerCase();
  const position = getPos();
  let blockIndex = 0;
  editor.state.doc.descendants((candidate, candidatePosition) => {
    if (candidate.type.name === 'docsEmbeddedView' && position !== undefined && candidatePosition < position) blockIndex++;
  });
  const present = context.collections.some(collection => collection.id === collectionId);
  const [retry, setRetry] = useState(0);
  const result = useCollection(context.api, present ? collectionId : undefined, context.refreshKey + retry);
  const collection = result?.collection;
  const view = collection?.views.find(item => item.id === viewId);
  const pending = present && !result;
  const failed = result?.error != null && !(result.error instanceof ApiError && [403, 404].includes(result.error.status));
  const title = view?.name ?? (pending || failed ? 'Vue de collection' : 'Vue indisponible');
  return <NodeViewWrapper className="docs-embedded-view" contentEditable={false}
    data-doc-embedded-index={blockIndex} data-doc-embedded-view-id={viewId}
    data-doc-embedded-layout={view && 'layout' in view ? view.layout : undefined}>
    <section aria-label={title}>
      <header className="docs-embedded-heading">
        <div><h2>{title}</h2>{collection && view && <small>{collection.title}</small>}</div>
        <div className="docs-row">
          {view && <a className="button" href={docHref(collectionId, viewId)}
            onClick={event => followDoc(event, collectionId, context.open, viewId)}>Ouvrir la vue</a>}
          {editor.isEditable && <button type="button" className="button subtle" aria-label={'Retirer le bloc ' + title}
            onClick={() => { deleteNode(); editor.commands.focus(); }}>Retirer</button>}
        </div>
      </header>
      <div className="docs-embedded-body">
        {pending && <p role="status">Chargement de la vue…</p>}
        {failed ? <><ErrorMessage>{message(result.error)}</ErrorMessage>
          <button type="button" className="button" onClick={() => setRetry(value => value + 1)}>Réessayer</button></> : null}
        {view && collection && <CollectionRows collection={collection} view={view} pages={context.pages}
          collections={context.collections} open={context.open} api={context.api} openGalleryPage={context.openGalleryPage}
          galleryOrigin={{ kind: 'embedded', destinationId: context.pageId, viewId, blockIndex }} />}
        {!pending && !failed && !view && <p>Cette vue ne peut plus être ouverte.</p>}
      </div>
    </section>
  </NodeViewWrapper>;
}

function EmbeddedView(props: NodeViewProps) {
  const context = useContext(EmbeddedViews);
  return context ? <EmbeddedViewContent {...props} context={context} /> : <NodeViewWrapper>Vue indisponible</NodeViewWrapper>;
}

export const DocsEmbeddedView = Node.create({
  name: 'docsEmbeddedView',
  group: 'block',
  atom: true,
  addAttributes: () => ({ collectionId: { default: '' }, viewId: { default: '' }, label: { default: '' } }),
  renderHTML: ({ node }) => ['div', {}, node.attrs.label || 'Vue de collection'],
  addNodeView: () => ReactNodeViewRenderer(EmbeddedView, { stopEvent: () => true }),
  markdownTokenizer: {
    name: 'docsEmbeddedView',
    level: 'block',
    start: source => source.search(blockStart),
    tokenize(source) {
      const match = viewBlock.exec(source);
      return match ? { type: 'docsEmbeddedView', raw: match[0], label: match[1], collectionId: match[2], viewId: match[3] } : undefined;
    },
  },
  parseMarkdown: token => ({
    type: 'docsEmbeddedView', attrs: { label: token.label, collectionId: token.collectionId, viewId: token.viewId },
  }),
  renderMarkdown: node => '[' + node.attrs?.label + '](' + viewReferenceHref(node.attrs?.collectionId, node.attrs?.viewId) + ')',
});
