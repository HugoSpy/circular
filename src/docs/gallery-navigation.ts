export type GalleryOrigin = {
  kind: 'collection' | 'embedded';
  destinationId: string;
  viewId?: string;
  blockIndex?: number;
};

export type GalleryReturnTarget = GalleryOrigin & { cardPageId: string };
export type OpenGalleryPage = (pageId: string, origin: GalleryOrigin) => boolean;
