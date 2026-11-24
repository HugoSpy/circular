import { createContext, useContext } from 'react';
import { attachmentHref } from './api';
import { Node } from '@tiptap/core';
import { NodeViewContent, NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';

const assetId = '([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})';
const attachmentPattern = new RegExp('^/attachments/' + assetId + '$', 'i');
const inlineAsset = new RegExp(String.raw`^(!?)\[((?:\\.|[^\]\\\r\n])*)\]\(/attachments/` + assetId + String.raw`\)`, 'i');

export const isAttachment = (url: string) => attachmentPattern.test(url);
export const AttachmentLinks = createContext<(id: string, preview?: boolean) => string>(() => '');

function AttachmentView({ node }: NodeViewProps) {
  const href = useContext(AttachmentLinks);
  const label = String(node.attrs.label).replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])/g, '$1');
  return <NodeViewWrapper as="span" className="docs-asset" contentEditable={false}>
    {node.attrs.image && <img src={href(node.attrs.id, true)} alt={label} loading="lazy" />}
    <a href={href(node.attrs.id)} download>{node.attrs.image ? 'Télécharger' : label || 'Télécharger la pièce jointe'}</a>
  </NodeViewWrapper>;
}

export const DocsAttachment = Node.create({
  name: 'docsAttachment', inline: true, group: 'inline', atom: true,
  addAttributes: () => ({ id: { default: '' }, label: { default: '' }, image: { default: false } }),
  renderHTML: ({ node }) => ['span', {}, node.attrs.label || 'Pièce jointe'],
  addNodeView: () => ReactNodeViewRenderer(AttachmentView),
  markdownTokenizer: {
    name: 'docsAttachment',
    level: 'inline',
    start(source) { return source.search(/!?\[/); },
    tokenize(source) {
      const match = inlineAsset.exec(source);
      return match ? { type: 'docsAttachment', raw: match[0], image: match[1] === '!', label: match[2], id: match[3] } : undefined;
    },
  },
  parseMarkdown: token => ({ type: 'docsAttachment', attrs: { image: token.image, label: token.label, id: token.id } }),
  renderMarkdown: node => (node.attrs?.image ? '!' : '') + '[' + node.attrs?.label + '](' + attachmentHref(node.attrs?.id) + ')',
});

function CalloutView({ node, updateAttributes, editor }: NodeViewProps) {
  const title = <input aria-label="Titre du bloc" value={node.attrs.title} maxLength={160}
    disabled={!editor.isEditable} onChange={event => updateAttributes({ title: event.target.value })} onClick={event => event.stopPropagation()} />;
  return <NodeViewWrapper className="docs-callout">
    {node.attrs.fold
      ? <details><summary contentEditable={false}><span className="visually-hidden">Déplier ou replier le volet</span>{title}</summary><NodeViewContent /></details>
      : <div><div contentEditable={false}>{title}</div><NodeViewContent /></div>}
  </NodeViewWrapper>;
}

export const DocsCallout = Node.create({
  name: 'docsCallout',
  group: 'block',
  content: 'block+',
  defining: true,
  addAttributes: () => ({ title: { default: '' }, fold: { default: false } }),
  renderHTML: ({ node }) => ['blockquote', { 'data-fold': node.attrs.fold }, 0],
  addNodeView: () => ReactNodeViewRenderer(CalloutView),
  markdownTokenizer: {
    name: 'docsCallout',
    level: 'block',
    start(source) { return source.search(/^> \[!NOTE\]/m); },
    tokenize(source, _tokens, lexer) {
      const match = /^> \[!NOTE\](-?)(?: ([^\r\n]*))?(?:\r?\n|$)((?:>(?: ?[^\r\n]*)?(?:\r?\n|$))*)/.exec(source);
      if (!match) return undefined;
      const body = match[3].replace(/^> ?/gm, '');
      return { type: 'docsCallout', raw: match[0], fold: match[1] === '-', title: match[2] ?? '', tokens: lexer.blockTokens(body) };
    },
  },
  parseMarkdown(token, helpers) {
    const content = helpers.parseChildren(token.tokens ?? []);
    return { type: 'docsCallout', attrs: { fold: token.fold, title: token.title }, content: content.length ? content : [{ type: 'paragraph' }] };
  },
  renderMarkdown(node, helpers) {
    const title = node.attrs?.title || '';
    const head = '> [!NOTE]' + (node.attrs?.fold ? '-' : '') + (title ? ' ' + title : '');
    const body = helpers.renderChildren(node.content ?? [], '\n\n');
    return body.trim() ? head + '\n' + helpers.wrapInBlock('> ', body) : head;
  },
});
