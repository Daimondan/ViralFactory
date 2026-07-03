# DIVERGENCE-004 — Zip file support in materials intake

*Repo location: `docs/decisions/DIVERGENCE-004-zip-file-support.md` · Proposed by operator (Daimon), 2026-07-02 · Status: IMPLEMENTED by builder (no charter conflict — this is an intake capability extension, not a design change).*

## What changes

MaterialsIntake.ingest_file() now handles `.zip` archives: extracts to a temp directory, ingests each file inside recursively through the existing intake pipeline (text, audio, images, PDFs, nested zips), and stores each as a separate material under the same run.

Also extends ingest_file() with:
- **PDF text extraction** (tries pdfplumber → PyPDF2 → graceful fallback)
- **Image files** (.png, .jpg, .jpeg, .gif, .bmp, .webp) stored as visual references with the file copied to the upload directory
- **Graceful binary handling** — unknown binary files get a placeholder instead of crashing

## Why

The operator would naturally upload a zip of exported chats, brand docs, photos, and other materials in one shot. Without zip support, a `.zip` fell through to the "unknown type" branch and tried to read binary as text — producing garbage.

## Implementation details

- `ingest_zip()` method: extracts to `tempfile.mkdtemp(prefix="vf_zip_")`, walks the extracted tree, ingests each file via `ingest_file()` (recursive — handles zips inside zips)
- Skips: hidden files (starting with `.`), `__MACOSX` metadata, directory entries
- Failed individual files are logged as materials with `channel="zip_extract_error"` — the zip doesn't fail if one file inside is broken
- Temp directory is cleaned up in a `finally` block
- Works through both the existing `/api/run/<id>/upload` endpoint and the new `/api/session/<id>/upload` session endpoint

## Charter compliance

No conflict. The charter says "one-go intake" — zip support enables that more fully. The charter says "mechanics use boring libraries" — `zipfile` and `tempfile` are stdlib. No business values hardcoded. No judgment in code — file type detection is mechanical, not categorization.

## BUILD_PLAN impact

None. This is a capability extension to the M1 MaterialsIntake module, not a new milestone task.