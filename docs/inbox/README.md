# Inbox Protocol

*Repo location: `docs/inbox/README.md` · This file stays in the inbox permanently — it is never filed away. v1.0*

## Purpose

The operator never navigates folders, replaces files, or deletes anything. All incoming files from the Claude architect land in ONE place — `docs/inbox/` — and Hermes does the filing.

## Operator's entire job

1. GitHub → this repo → `docs/inbox/` → **Add file → Upload files** → drag everything Claude provided → **Commit changes**.
2. Tell Hermes: **"check the inbox."**

That's it. Same folder, same phrase, every time.

## Hermes' rules (binding)

1. **On every session start AND whenever told "check the inbox":** list `docs/inbox/`. If it contains anything besides this README, process it before any other work — inbox filing outranks milestone tasks, same priority as `docs/reviews/` corrections.
2. **Read the `MANIFEST-*.md` file first.** It specifies, per file: destination path, and action — `ADD` (new file), `REPLACE` (overwrite existing at destination; the old content is preserved by git history, no separate archive needed), or `SUPERSEDE` (leave the old file in place, add a superseded note at its top pointing to the new file).
3. **File everything, then empty the inbox** — files are *moved* to destinations via git (never deleted from history), and the processed manifest is moved to `docs/inbox/processed/`.
4. **Log one CHANGELOG entry per batch** listing what was filed where.
5. **If a batch arrives with no manifest:** file nothing. Open a GitHub issue listing the orphan files and wait — never guess destinations.
6. **If a manifest instruction conflicts with the charter:** file the documents anyway (they are architect direction), but flag the conflict in the changelog entry and a GitHub issue.
7. **After filing, execute any "APPLY" section** in the manifest (e.g. "bump charter to v3.2 per the amendment") before returning to milestone work.

## Why this exists

The operating loop says all architect direction arrives as versioned files in the repo. This protocol standardizes HOW they arrive: one drop zone, machine-readable filing instructions, builder executes. The operator's attention is spent on gates and seeds — never on file management.
