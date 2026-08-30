-- Catalog search index. Rebuildable from pricebooks/ at any time.
--
-- Two rules shape this schema:
--
--   1. A partially indexed catalog must never be searchable. Rows are built in
--      `products_staging`, which has no FTS triggers, and move into `products`
--      in one transaction. So "not exposed until ready" is structural rather
--      than a filter every query has to remember.
--
--   2. Deleting a catalog must leave nothing behind. `ON DELETE CASCADE` plus the
--      FTS delete trigger makes that a single statement with no cleanup to
--      interrupt half-way.
--
-- SQLite 3.40.1 ships in the image, so `contentless_delete=1` (3.43+) is not
-- available; this uses external-content FTS5 with triggers, which is the pattern
-- that works there.

CREATE TABLE IF NOT EXISTS catalogs (
  catalog_id    TEXT PRIMARY KEY,
  vendor        TEXT NOT NULL,
  file_name     TEXT NOT NULL,
  file_hash     TEXT NOT NULL,
  page_count    INTEGER,
  status        TEXT NOT NULL DEFAULT 'uploaded',
  version       INTEGER NOT NULL DEFAULT 0,
  product_count INTEGER NOT NULL DEFAULT 0,
  error         TEXT,
  extractor     TEXT,
  effective_date TEXT,
  created_at    TEXT NOT NULL,
  indexed_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_catalog_file ON catalogs(vendor, file_name);
CREATE INDEX IF NOT EXISTS idx_catalog_status ON catalogs(status);

-- Active rows only. If a row is here, it is searchable.
CREATE TABLE IF NOT EXISTS products (
  id           INTEGER PRIMARY KEY,
  catalog_id   TEXT NOT NULL REFERENCES catalogs(catalog_id) ON DELETE CASCADE,
  version      INTEGER NOT NULL DEFAULT 0,
  vendor       TEXT NOT NULL,
  product_code TEXT,
  code_norm    TEXT,
  name         TEXT,
  description  TEXT,
  category     TEXT,
  price        REAL,
  unit         TEXT,
  page_number  INTEGER NOT NULL,
  raw_text     TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_code_norm ON products(code_norm);
CREATE INDEX IF NOT EXISTS idx_products_catalog   ON products(catalog_id);
CREATE INDEX IF NOT EXISTS idx_products_vendor    ON products(vendor, code_norm);

-- Same shape, no triggers, not searchable. A catalog is built here first.
CREATE TABLE IF NOT EXISTS products_staging (
  id           INTEGER PRIMARY KEY,
  build_id     TEXT NOT NULL,
  catalog_id   TEXT NOT NULL,
  version      INTEGER NOT NULL DEFAULT 0,
  vendor       TEXT NOT NULL,
  product_code TEXT,
  code_norm    TEXT,
  name         TEXT,
  description  TEXT,
  category     TEXT,
  price        REAL,
  unit         TEXT,
  page_number  INTEGER NOT NULL,
  raw_text     TEXT
);
CREATE INDEX IF NOT EXISTS idx_staging_build ON products_staging(build_id);

-- tokenchars keeps B-2888, 150CX18 and 1-1/2" whole instead of splitting them
-- into fragments that rank against every other number on the page.
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
  product_code, name, description, category, vendor,
  content='products',
  content_rowid='id',
  tokenize="unicode61 tokenchars '-./#'",
  prefix='2 3 4'
);

CREATE TRIGGER IF NOT EXISTS products_ai AFTER INSERT ON products BEGIN
  INSERT INTO products_fts(rowid, product_code, name, description, category, vendor)
  VALUES (new.id, new.product_code, new.name, new.description, new.category, new.vendor);
END;

CREATE TRIGGER IF NOT EXISTS products_ad AFTER DELETE ON products BEGIN
  INSERT INTO products_fts(products_fts, rowid, product_code, name, description, category, vendor)
  VALUES ('delete', old.id, old.product_code, old.name, old.description, old.category, old.vendor);
END;

CREATE TRIGGER IF NOT EXISTS products_au AFTER UPDATE ON products BEGIN
  INSERT INTO products_fts(products_fts, rowid, product_code, name, description, category, vendor)
  VALUES ('delete', old.id, old.product_code, old.name, old.description, old.category, old.vendor);
  INSERT INTO products_fts(rowid, product_code, name, description, category, vendor)
  VALUES (new.id, new.product_code, new.name, new.description, new.category, new.vendor);
END;
