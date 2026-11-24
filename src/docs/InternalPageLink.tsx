import { createContext, useContext } from 'react';
import { Node } from '@tiptap/core';
import { NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';

import { docHref, followDoc, type OpenDoc } from './api';

export const ReferenceTitles = createContext<{ titles: ReadonlyMap<string, string>; open: OpenDoc }>({
  titles: new Map(), open: () => undefined,
});
const linkPattern = /^\[((?:\\.|[^\]\\\r\n])*)\]\(\/pages\/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\)/i;

function PageLink({ node }: NodeViewProps) {
  const { titles, open } = useContext(ReferenceTitles);
  const identifier = String(node.attrs.id).toLowerCase();
  const label = String(node.attrs.label).replace(/\\([\\[\]])/g, '$1');
  const title = titles.get(identifier);
  return <NodeViewWrapper as="span" contentEditable={false}>
    {title
      ? <a href={docHref(identifier)} onClick={event => followDoc(event, identifier, open)}>{label || title}</a>
      : <span className="page-reference-missing">{label ? label + ' (page indisponible)' : 'Page indisponible'}</span>}
  </NodeViewWrapper>;
}

export const InternalPageLink = Node.create({
  name: 'internalPageLink',
  inline: true,
  group: 'inline',
  atom: true,
  addAttributes: () => ({ id: { default: '' }, label: { default: '' } }),
  renderHTML: ({ node }) => ['span', {}, node.attrs.label || 'Page interne'],
  addNodeView: () => ReactNodeViewRenderer(PageLink),
  markdownTokenizer: {
    name: 'internalPageLink',
    level: 'inline',
    start: source => source.indexOf('['),
    tokenize(source) {
      const match = linkPattern.exec(source);
      return match ? { type: 'internalPageLink', raw: match[0], id: match[2], label: match[1] } : undefined;
    },
  },
  parseMarkdown: token => ({ type: 'internalPageLink', attrs: { id: token.id, label: token.label } }),
  renderMarkdown: node => '[' + node.attrs?.label + '](/pages/' + node.attrs?.id + ')',
});
