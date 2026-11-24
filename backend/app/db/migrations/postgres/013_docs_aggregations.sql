ALTER TABLE docs_fields ADD COLUMN aggregation TEXT;
ALTER TABLE docs_fields DROP CONSTRAINT docs_fields_kind_check;
ALTER TABLE docs_fields ADD CONSTRAINT docs_fields_kind_check
    CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox', 'url', 'multi', 'relation', 'aggregate'));
ALTER TABLE docs_fields ADD CHECK ((kind = 'aggregate') = (aggregation IS NOT NULL));
