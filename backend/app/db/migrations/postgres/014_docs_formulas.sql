ALTER TABLE docs_fields ADD COLUMN formula TEXT;
ALTER TABLE docs_fields DROP CONSTRAINT docs_fields_kind_check;
ALTER TABLE docs_fields ADD CONSTRAINT docs_fields_kind_check
    CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox', 'url', 'multi', 'relation', 'aggregate', 'formula'));
ALTER TABLE docs_fields ADD CHECK ((kind = 'formula') = (formula IS NOT NULL));
