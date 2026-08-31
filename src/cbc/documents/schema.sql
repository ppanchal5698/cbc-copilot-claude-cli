CREATE TABLE IF NOT EXISTS sections (
  id INTEGER PRIMARY KEY,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  section_title TEXT,
  raw_text TEXT NOT NULL,
  extracted_records TEXT NOT NULL,
  entities_present TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sections_pages ON sections(page_start, page_end);
