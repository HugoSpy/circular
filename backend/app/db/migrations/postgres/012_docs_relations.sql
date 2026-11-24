ALTER TABLE docs_fields ADD COLUMN target_collection_id TEXT;
ALTER TABLE docs_fields DROP CONSTRAINT docs_fields_kind_check;
ALTER TABLE docs_fields ADD CONSTRAINT docs_fields_kind_check
    CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox', 'url', 'multi', 'relation'));
ALTER TABLE docs_fields ADD FOREIGN KEY (workspace_id, target_collection_id)
    REFERENCES docs_collections(workspace_id, id);
ALTER TABLE docs_fields ADD CHECK ((kind = 'relation') = (target_collection_id IS NOT NULL));
ALTER TABLE docs_fields ADD CHECK (target_collection_id <> collection_id);

CREATE TABLE docs_page_relations (
    workspace_id BIGINT NOT NULL,
    source_page_id TEXT NOT NULL,
    source_collection_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    target_page_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, source_page_id, field_id, target_page_id),
    FOREIGN KEY (workspace_id, source_page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, target_page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, source_collection_id, field_id) REFERENCES docs_fields(workspace_id, collection_id, id) ON DELETE CASCADE
);
CREATE INDEX docs_page_relations_target ON docs_page_relations(workspace_id, target_page_id);
