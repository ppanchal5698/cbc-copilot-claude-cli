"""The catalog search index.

The vendor PDFs in `pricebooks/` are the source of truth. This package keeps a
SQLite FTS5 index of what is inside them so a search costs milliseconds instead of
re-reading 1 391 pages, and it is **disposable**: delete the file and
`python -m catalog_index.rebuild` reconstructs it from the PDFs.

Nothing here is a product master database. There are no rows to maintain by hand -
adding, replacing or deleting a catalog file is the only way products change.

    from catalog_index import db, registry, search
    connection = db.connect()                 # readers get query_only=1
    search.search(connection, "stainless steel grab bar")

Deliberately no re-exports: `catalog_index.search` is the module, and binding the
function to that name here would shadow it.
"""
