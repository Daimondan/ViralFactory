# CORRECTION — Repo Health: Deployability, Worker Safety, Render Spec — v1.0

**Date:** 2026-07-25
**Author:** Architect (Claude)
**Status:** Approved by operator (verbal, this session)
**Repo state reviewed:** `2b793f1` — "Thread publish fix: send actual thread posts to Buffer, not summary line"
**Supersedes:** Nothing. Companion document: `CORRECTION-app-blueprint-split-v1.0.md` (structural, sequence after this batch).
**Priority:** P0 items are deployment-blocking and mechanically small — land them as one batch before any milestone work.

---

## How this review was conducted

Fresh `--depth 1` clone at `2b793f1`. `compileall` across `src`, `tests`, `scripts`. Full
test suite via `PYTHONPATH=src pytest` (824 passed; the single failure was `fal_client`
absent from the review sandbox, not a repo defect — no action required). `create_app()`
booted and every parameterless `GET` route exercised through the Flask test client. AST
sweep for empty function bodies. Static audit of all 19 declared processes in
`processes.yaml` against `prompts/`. Secret scan across all tracked text files.

**What is healthy, stated plainly so it is not re-litigated:** no `TODO`/`FIXME`/`HACK`
markers anywhere in `src`; no hardcoded credentials; harness genericity holds (the only
tenant strings in `src` are illustrative comments in `reference_assets.py` and one form
hint in `reference_assets.html`); the Hermes handoff documents are committed to main
(`docs/research/viral-content-meta-analysis-v2.md`,
`docs/playbooks/viral-content-production-playbook-v1.md`,
`modules/stackpenni/viral-patterns.md`) — that Phase 0 precondition is satisfied; the
four `produce_chain.py` `pass` stubs are gone.

---

## P0-1 — `requirements-prod.txt` is corrupted and the environment is unreconstructable

### Defect

The file is 53 bytes and contains a fused line caused by a missing newline:

```
gunicorn>=21.0
python-docx>=1.0faster-whisper>=1.0.0
```

`pip install -r requirements-prod.txt` fails to parse line 2. A rebuild from a clean
checkout **cannot install dependencies at all**.

Worse than the corruption: the file names three packages while `src` imports at least
nineteen third-party modules. Production functions today only because packages were
installed ad hoc into `/home/daimon/ViralFactory/.venv` over months of sessions. That
venv is the only record of what the system needs to run. If the VPS is rebuilt, restored
from a snapshot predating a given install, or migrated, the environment cannot be
reproduced. This is the highest-risk item in the repository.

### Fix

Do **not** hand-write versions from this document — pin them from the live venv, which is
the only authority on what actually works. Split by degradation tier, because the heavy ML
packages back optional paths that already degrade gracefully.

On the VPS, capture the only authoritative record of working versions:

```bash
cd /home/daimon/ViralFactory
.venv/bin/pip freeze > /tmp/frozen.txt
```

The dependency set below was derived by AST across `src`, `tests`, and `scripts`, filtering
standard-library and first-party modules. Take every **version pin verbatim from
`/tmp/frozen.txt`** — do not hand-write versions from this document. The set is authoritative;
the versions are not.

| Import name in code | PyPI package | Tier | Used by |
|---|---|---|---|
| `flask` | `Flask` | core | `src/app.py` |
| — (no import) | `gunicorn` | core | `deploy/viralfactory.service` ExecStart |
| `yaml` | `PyYAML` | core | 38 files |
| `requests` | `requests` | core | 12 files |
| `PIL` | `Pillow` | core | 9 files |
| `numpy` | `numpy` | core | `layer2_qc.py`, + 2 |
| `matplotlib` | `matplotlib` | media | `services/composition_preview.py` |
| `cv2` | `opencv-python-headless` | media | `layer2_qc.py` |
| `docx` | `python-docx` | media | `materials.py` |
| `pdfplumber` | `pdfplumber` | media | `materials.py` |
| `PyPDF2` | `PyPDF2` | media | `materials.py` |
| `feedparser` | `feedparser` | media | `research_job.py` |
| `trafilatura` | `trafilatura` | media | `source_snapshot.py` |
| `fal_client` | `fal-client` | media | `media_adapter.py` |
| `faster_whisper` | `faster-whisper` | media | `transcription.py`, `asset_review.py` |
| `torchaudio` | `torchaudio` | media | `vo_generator.py` |
| `chatterbox` | *see note* | media | `vo_generator.py` |
| `onnxruntime` | `onnxruntime` | media | `layer2_qc.py` |
| `insightface` | `insightface` | media | `layer2_qc.py` |
| `edge_tts` | `edge-tts` | dev | `scripts/render_ai_thinking_edge_tts.py` |
| `pytest` | `pytest` | dev | 150 test files |

Four notes on this table, each a place where an import-name-to-package guess would go wrong:

**`gunicorn` has no import anywhere in the codebase.** It is invoked by systemd, not imported.
Any audit built purely on import scanning drops it and produces a requirements file that
installs cleanly and then cannot serve. It must stay declared.

**`cv2` should resolve to `opencv-python-headless`, not `opencv-python`.** The VPS has no
display server. The headless wheel omits the GUI dependencies, which removes a large
transitive tree and avoids the `libGL.so.1` failure that the full wheel hits on a minimal
container. Confirm which is currently installed — if it is the full `opencv-python`, switching
is a small improvement to make while here.

**`chatterbox` may not have been installed from PyPI.** Self-hosted Chatterbox is Resemble
AI's MIT-licensed model and may have been installed from git or from a local path. Read the
actual line in `/tmp/frozen.txt`: if it shows a VCS or file URL, reproduce that URL exactly
rather than substituting a package name. Guessing here produces an install that succeeds and a
VO engine that does not work.

**`PyPDF2` is end-of-life**, superseded by `pypdf`. Pin the installed `PyPDF2` version now —
migrating is a separate change and must not ride along in this batch.

Then author three files:

**`requirements.txt`** — core runtime. The app cannot start without these:

```
Flask==<from frozen>
gunicorn==<from frozen>
PyYAML==<from frozen>
requests==<from frozen>
Pillow==<from frozen>
numpy==<from frozen>
```

**`requirements-media.txt`** — media and ML paths. Every one of these backs a code path with a
graceful-degradation fallback, so a slim deploy remains valid, with reduced capability:

```
-r requirements.txt
matplotlib==<from frozen>
opencv-python-headless==<from frozen>
python-docx==<from frozen>
pdfplumber==<from frozen>
PyPDF2==<from frozen>
feedparser==<from frozen>
trafilatura==<from frozen>
fal-client==<from frozen>
faster-whisper==<from frozen>
torchaudio==<from frozen>
<chatterbox line copied verbatim from frozen.txt>
onnxruntime==<from frozen>
insightface==<from frozen>
```

**`requirements-dev.txt`**:

```
-r requirements-media.txt
pytest==<from frozen>
edge-tts==<from frozen>
```

The `-r` chaining means production installs one file and the test environment installs one
file, with no possibility of the two drifting apart.

Delete `requirements-prod.txt`. Update `deploy/README.md` with the install order and a
sentence naming what is lost when `requirements-media.txt` is skipped: transcription, face
identity QC, PDF and DOCX material ingestion, composition previews, RSS and article
extraction, and image generation.

Regenerate the audit before declaring this done rather than trusting the table above, since
`src` will have changed by then:

```bash
python3 - <<'PY'
import ast, os, sys
stdlib = set(sys.stdlib_module_names)
local = set()
for base in ('src','tests','scripts'):
    for r, ds, fs in os.walk(base):
        local |= {f[:-3] for f in fs if f.endswith('.py')}
        local |= {d for d in ds if d != '__pycache__'}
local |= {'tests','scripts','src'}
found = set()
for base in ('src','tests','scripts'):
    for root, dirs, files in os.walk(base):
        if '__pycache__' in root: continue
        for f in files:
            if not f.endswith('.py'): continue
            try: tree = ast.parse(open(os.path.join(root,f)).read())
            except SyntaxError: continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    found |= {a.name.split('.')[0] for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                    found.add(n.module.split('.')[0])
print(sorted(found - stdlib - local))
PY
```

Every name it prints must map to a declared package. Reconcile any addition before closing
this item.

### Acceptance criteria

- `python3 -m venv /tmp/probe && /tmp/probe/bin/pip install -r requirements-dev.txt`
  completes with exit 0 in a container with **no** pre-existing venv.
- `PYTHONPATH=src /tmp/probe/bin/python -m pytest -q` reaches the same pass count as the
  VPS venv, with zero `ModuleNotFoundError`.
- `PYTHONPATH=src /tmp/probe/bin/python -c "import app; app.create_app()"` exits 0.
- `requirements-prod.txt` no longer exists and no file in `deploy/` references it.

---

## P0-2 — The transcription worker logs an error every five seconds forever on a fresh database

### Defect

Booting `create_app()` against a database with no `materials` table produces, immediately
and then indefinitely:

```
Backfill failed: no such table: materials
Worker loop error: no such table: materials
```

`app.py:9610` starts `TranscriptionWorker` unconditionally (absent
`VIRALFACTORY_DISABLE_BACKGROUND_WORKERS=1`). The `materials` table is created lazily by
`MaterialStore._init_db()` — invoked from `MaterialStore.__init__`, i.e. only when a
material is first ingested. Until that happens the worker has no table to query.
`transcription.py:243-253` catches the exception, sleeps `POLL_INTERVAL` (5 s), and retries
without limit. `_backfill()` at `transcription.py:206` has the same problem one layer up.

On every fresh tenant this emits ~17,000 error lines per day. Genuine errors become
undiscoverable, which is the actual harm — the wasted cycles are trivial by comparison.

### Fix

Two changes. First, give the worker the same schema guarantee every other consumer has, by
reusing the single schema owner rather than adding a second `CREATE TABLE` (a second one
would be a defect in its own right — `materials.py:32` must remain the only definition).
In `TranscriptionWorker.start()`, before the thread is launched:

```python
def start(self):
    """Start the transcription worker thread."""
    if not self.enabled:
        logger.info("Transcription worker disabled (transcription.enabled = false)")
        return

    if self._thread is not None and self._thread.is_alive():
        return

    # The worker may boot before any material has been ingested. MaterialStore
    # owns the schema and _init_db is idempotent; constructing it here guarantees
    # the table exists without introducing a second CREATE TABLE.
    from materials import MaterialStore
    MaterialStore(db_path=self.db_path, upload_dir=self.upload_dir)

    self._running = True
    self._thread = threading.Thread(target=self._run, daemon=True, name="transcription-worker")
    self._thread.start()
    logger.info("Transcription worker started")
```

Confirm `TranscriptionWorker.__init__` retains `upload_dir` as an attribute; if it does not,
pass the value through rather than defaulting it.

Second, make the loop's failure mode non-abusive regardless of cause, since a schema fix
does not protect against the next unexpected error. Replace the bare retry at
`transcription.py:243-253` with capped exponential backoff that logs the first occurrence
at `error` and subsequent repeats at `debug`:

```python
    def _run(self):
        """Main worker loop."""
        try:
            self._backfill()
        except Exception as e:
            logger.error(f"Backfill failed: {e}")

        backoff = POLL_INTERVAL
        last_error = None
        while self._running:
            try:
                pending = self._get_pending_audio()
                if pending:
                    for material in pending:
                        self._process_one(material)
                    backoff = POLL_INTERVAL
                    last_error = None
                else:
                    time.sleep(POLL_INTERVAL)
            except Exception as e:
                message = str(e)
                if message != last_error:
                    logger.error(f"Worker loop error: {message}")
                    last_error = message
                else:
                    logger.debug(f"Worker loop error (repeat, backoff {backoff}s): {message}")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
```

Add `MAX_BACKOFF = 300` beside `POLL_INTERVAL` at `transcription.py:25`.

### Acceptance criteria

- `rm -f /tmp/fresh.db && PYTHONPATH=src python3 -c "import app; app.create_app(db_path='/tmp/fresh.db')"`
  held open for 60 seconds produces **zero** `no such table: materials` lines.
- Injecting an unrelated persistent failure into `_get_pending_audio` yields exactly one
  `error` line, then `debug` repeats at 5, 10, 20, 40… seconds, capping at 300.
- A material ingested after boot is still picked up on the next poll — backoff must not
  strand a healthy worker.

---

## P0-3 — Two gunicorn workers transcribe the same audio file simultaneously

### Defect

`deploy/viralfactory.service` runs `gunicorn --workers 2`. The transcription worker is
started **inside `create_app()`**, which each gunicorn worker process calls. Two threads in
two processes therefore poll the same SQLite database.

The claim is not atomic. `_get_pending_audio()` (`transcription.py:67-81`) selects rows
where `transcription_status` is `'pending'` or `NULL`; `_process_one()`
(`transcription.py:158-165`) then separately calls `_update_material(material_id, "processing")`.
Between the select and the update, the other process can select the same row. Both then run
`faster-whisper` over the same file — minutes of CPU each — and both write
`normalized_content`. Last writer wins, silently.

### Fix

Make the claim a single atomic conditional update and proceed only when this process won
it. Add to `TranscriptionWorker`:

```python
    def _claim(self, material_id: int) -> bool:
        """Atomically claim a material for transcription.

        Returns True only if this process transitioned the row from pending to
        processing. A False return means another worker got there first and this
        process must skip the row.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                """UPDATE materials SET transcription_status = 'processing'
                   WHERE id = ?
                     AND (transcription_status = 'pending' OR transcription_status IS NULL)""",
                (material_id,),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()
```

In `_process_one()`, replace the unconditional `self._update_material(material_id, "processing")`
with the guard, and return early when the claim is lost:

```python
    def _process_one(self, material: dict) -> bool:
        material_id = material["id"]
        filename = material.get("filename", "unknown")

        if not self._claim(material_id):
            logger.debug(f"Material {material_id} claimed by another worker — skipping")
            return False
        ...
```

Apply the same guard in `_backfill()` — it calls `_process_one()` directly, so routing the
claim through `_process_one` covers both paths, but verify no other call site marks
`processing` independently.

The claim makes concurrency correct rather than merely unlikely, which is the right outcome;
do not instead special-case gunicorn worker zero, because that reintroduces the race the
moment the worker count changes or a cron path touches the same table.

### Acceptance criteria

- A test spawning two `TranscriptionWorker` instances against one temp database with one
  pending material asserts `_transcribe` is invoked exactly once. Add it as
  `tests/test_transcription_claim.py`.
- `_claim` returns `True` on first call and `False` on every subsequent call for the same
  row.
- Two gunicorn workers running against a database with three pending materials transcribe
  each exactly once — verify from logs on the VPS after deploy.

---

## P0-4 — SQLite runs without WAL, so readers and writers block each other

### Defect

No file in `src` sets `journal_mode` or `busy_timeout` — confirmed by grep across all 254
`sqlite3.connect` call sites. In rollback-journal mode a writer excludes all readers for the
duration of its transaction. With two gunicorn workers, a transcription thread, a reel
worker (`deploy/viralfactory-reel-worker.service`), and an inspiration collector timer all
on one database file, and with render and transcription operations holding long
transactions, `database is locked` is a matter of time. Python's default 5-second lock
timeout is short for a process that may be mid-ffmpeg.

### Fix

`journal_mode=WAL` is a persistent property of the database file — set once, it survives
every subsequent connection and process. That makes the P0 stopgap genuinely five lines,
and it removes the reader/writer conflict outright rather than merely widening the timeout.
In `create_app()`, immediately after `app.config["DB_PATH"] = db_path`:

```python
    # WAL is a persistent database property — setting it once here means readers
    # never block writers for any later connection, in any process. busy_timeout
    # is per-connection and is handled by src/db.py (see P1-5).
    import sqlite3 as _sqlite3_init
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    _wal_conn = _sqlite3_init.connect(db_path)
    try:
        _wal_conn.execute("PRAGMA journal_mode=WAL")
        _wal_conn.execute("PRAGMA synchronous=NORMAL")
    finally:
        _wal_conn.close()
```

Apply the same block at the top of `cron_generate_proposals.py`, `cron_pull_metrics.py`, and
`src/reel_worker.py`, since any of these may be the first process to touch a fresh database.

`synchronous=NORMAL` is the correct pairing with WAL for this workload: it keeps the
durability that matters (no corruption on process crash) and drops the fsync-per-commit cost
that only protects against sudden power loss on a VPS with managed storage.

Note that WAL adds `-wal` and `-shm` sidecar files next to the database. `.gitignore`
already covers `data/`, so no change is needed there, but any backup or snapshot procedure
in `deploy/README.md` must copy all three files together, or use `sqlite3 db ".backup"`.
Update that document accordingly.

### Acceptance criteria

- `sqlite3 data/viralfactory.db "PRAGMA journal_mode;"` returns `wal` on the VPS after
  restart.
- A test opens a long write transaction and asserts a concurrent read succeeds rather than
  raising `database is locked`.
- `deploy/README.md` documents the `-wal`/`-shm` backup requirement.

---

## P1-5 — Centralize connection settings behind one factory

### Defect

`busy_timeout`, unlike `journal_mode`, is per-connection and cannot be set once. There are
254 `sqlite3.connect` sites across `src` (51 in `pipeline.py` alone). Row factory handling
is likewise inconsistent — some sites set `conn.row_factory = sqlite3.Row`, others index
tuples positionally, which is the kind of inconsistency that produces a defect the first
time a column is inserted mid-table.

### Fix

Add `src/db.py`:

```python
"""Single connection factory for the ViralFactory SQLite database.

Every connection in the system should come from here. Direct sqlite3.connect
calls bypass busy_timeout and row_factory and are a defect.
"""
import sqlite3

BUSY_TIMEOUT_MS = 30_000


def connect(db_path: str, row_factory: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn
```

Migrate call sites **one module per commit**, highest-traffic first: `pipeline.py`,
`app.py`, `services/production_orchestrator.py`, `materials.py`, `jobs.py`, then the
remainder. Do not attempt all 254 in one commit — `row_factory=True` changes tuple indexing
behaviour for any site that reads rows positionally, so each module needs its own test run.
Where a module genuinely depends on tuple rows, pass `row_factory=False` and leave a comment
saying why rather than silently reverting to raw `sqlite3.connect`.

Add a guard test that fails on regression:

```python
def test_no_direct_sqlite_connect_in_migrated_modules():
    """Migrated modules must use db.connect so busy_timeout is never skipped."""
    migrated = ["src/pipeline.py", "src/materials.py", "src/jobs.py"]  # extend as migration proceeds
    for path in migrated:
        source = open(path).read()
        assert "sqlite3.connect" not in source, f"{path} still calls sqlite3.connect directly"
```

Extend the `migrated` list in the same commit that migrates each module. The list is the
migration ledger.

### Acceptance criteria

- `src/db.py` exists and is the only place `BUSY_TIMEOUT_MS` is defined.
- The guard test passes and its `migrated` list grows monotonically.
- Full suite green after each module's commit, not merely at the end.

---

## P1-6 — Two of the four video QA fixes never landed

### Defect

The QA pass on recent output identified four renderer defects. Two are fixed correctly and
need no further work: loudnorm is plan-driven and enforced (`assembly.py:1069-1078`,
`1171-1178`, honouring `loudnorm_target` at I=−14/TP=−1.5 with a −16 default), and caption
chunking now emits phrase-level cues (`services/caption_timing.py`). The encode fixes did
not land:

- `-crf` appears **zero** times in `assembly.py`. All nine `libx264` invocations
  (L419, L436, L466, L481, L594, L616, L967, L1428, and the final mux) run at ffmpeg's
  implicit CRF 23 — precisely the too-low-bitrate condition the QA pass flagged.
- `-b:v` appears zero times. No bitrate ceiling for upload masters.
- `-b:a` appears zero times in `assembly.py`. Bare `-c:a aac` takes ffmpeg's default.
- `-ar` is never set to 48000 anywhere in the render path. `vo_generator.py:486` writes
  44.1 kHz and `anullsrc` is instantiated at `sample_rate=44100` (L419, L481), so masters
  ship off-spec for platform upload.

A larger problem sits underneath the missing flags. Segments are encoded lossily
(default CRF), concatenated through `filter_complex` and **re-encoded** lossily (L594/L616),
then the overlay pass at L967 re-encodes the video stream a third time. Three generations of
lossy transcode before the master exists. Raising the final CRF alone will not recover
detail already destroyed in the intermediates — the tiers must differ.

### Fix

Introduce one encode-argument helper and route all nine sites through it, so the spec lives
in a single place and drifts nowhere. This is the fixed normalization stage already scoped
for the assembly engine. In `assembly.py`:

```python
# Encode tiers. Intermediates are near-lossless because segments are re-encoded
# up to three times before the master exists (segment -> concat -> overlay);
# generation loss compounds and cannot be recovered by a better final pass.
INTERMEDIATE_CRF = 16
MASTER_CRF = 20
MASTER_MAX_BITRATE = "8M"
MASTER_BUFSIZE = "16M"
AUDIO_SAMPLE_RATE = "48000"
AUDIO_BITRATE = "256k"


def _video_encode_args(tier: str) -> list[str]:
    """ffmpeg video encode arguments for 'intermediate' or 'master'."""
    if tier == "intermediate":
        return [
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "veryfast", "-crf", str(INTERMEDIATE_CRF),
        ]
    if tier == "master":
        return [
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "medium", "-crf", str(MASTER_CRF),
            "-maxrate", MASTER_MAX_BITRATE, "-bufsize", MASTER_BUFSIZE,
            "-profile:v", "high", "-level", "4.1",
            "-movflags", "+faststart",
        ]
    raise AssemblyError(f"Unknown encode tier: {tier}")


def _audio_encode_args() -> list[str]:
    """ffmpeg audio encode arguments — 48 kHz is the platform upload spec."""
    return ["-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", AUDIO_SAMPLE_RATE]
```

Then replace every occurrence of the literal `["-c:v", "libx264", "-pix_fmt", "yuv420p"]`
with `_video_encode_args("intermediate")` at the segment sites (L419, L436, L466, L481) and
`_video_encode_args("master")` at the sites producing `output_file` (L594, L616) and the
tpad extension (L1428). Replace bare `["-c:a", "aac"]` with `*_audio_encode_args()`.
Leave `-c:a copy` at L967 and `-c:v copy` at L1097/L1340 exactly as they are — those passes
correctly avoid re-encoding, and changing them would *add* a generation.

Set `anullsrc` to `sample_rate=48000` at L419 and L481 so silent tracks match the master
spec and concat does not force a resample.

Change `vo_generator.py:486` from `"-ar", "44100"` to `"-ar", "48000"`. Confirm the TTS
engine's native rate first: if Gemini TTS returns 24 kHz, upsampling to 48 kHz is correct
for spec conformance but gains no quality, and the comment should say so rather than
implying otherwise.

`-movflags +faststart` belongs on the master only; it rewrites the moov atom to the file
head, which matters for upload and streaming and is wasted work on intermediates.

### Acceptance criteria

- `grep -c '"-c:v", "libx264"' src/assembly.py` returns 0 — every site goes through the
  helper.
- `ffprobe` on a rendered master reports `sample_rate=48000`, video bitrate within
  6–8 Mbps for typical short-form content, and `audio_bitrate` at 256k.
- `ffprobe -show_entries format_tags` confirms `faststart` (moov before mdat).
- Loudness verification still reports I≈−14, TP≤−1.5 — the encode change must not regress
  the loudnorm work that already landed.
- Render one asset before and after; the after-master is visibly sharper on high-motion
  stock footage and larger on disk. Attach both `ffprobe` outputs to the changelog entry.

---

## P1-7 — Caption chunking ignores punctuation, and word timestamps are never supplied

### Defect

Two separate issues in the caption path.

`_chunk_words` (`services/caption_timing.py:41-75`) is purely word-count based: 3–6 words
with dangling-tail shrinkage. It has no notion of sentence or clause boundaries, so a chunk
may straddle a period. `"You save the money. Then you invest it."` legally yields
`"You save the money. Then"` — which is the residual awkwardness the QA pass named, not a
new problem.

Separately, `chunk_captions` accepts `word_timestamps` and times phrases exactly when given
them (`caption_timing.py:117-130`), but `services/cue_compiler.py:210-213` calls it with
only `duration_sec`. Every caption in production is therefore proportionally timed and
flagged `approximate=True`. `faster-whisper` is already a dependency and supports
`word_timestamps=True`; neither `transcription.py:116` nor `asset_review.py:809` requests
it. The exact-timing path is built and unreachable.

### Fix

**Punctuation awareness.** Split on sentence terminators first, then apply the existing
word-count rule within each sentence. Preserve the reconstruction invariant documented at
`caption_timing.py:99-100` — it is the property that makes this safe to change:

```python
import re

# Sentence terminators force a chunk break. Soft punctuation is a preferred
# break point when a chunk must be split anyway.
_SENTENCE_END = re.compile(r"[.!?]['\")\]]?$")
_SOFT_BREAK = re.compile(r"[,;:—]$")


def _chunk_words(
    words: list[str],
    min_words: int = DEFAULT_MIN_WORDS,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[list[str]]:
    """Split words into min..max groups, never straddling a sentence boundary."""
    if not words:
        return []
    if min_words < 1 or max_words < min_words:
        raise ValueError(f"Invalid phrase bounds: min={min_words} max={max_words}")

    # Hard-split into sentences first.
    sentences: list[list[str]] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if _SENTENCE_END.search(word):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)

    chunks: list[list[str]] = []
    for sentence in sentences:
        chunks.extend(_chunk_sentence(sentence, min_words, max_words))
    return chunks
```

`_chunk_sentence` is the current `_chunk_words` body verbatim, with one addition: when a
split is required and a word within `[min_words, max_words]` of the cursor ends in soft
punctuation, break there instead of at `max_words`. A short trailing sentence — "Simple." —
correctly becomes its own one-word cue; the `min_words` floor must not be enforced across a
sentence boundary, because merging sentences to satisfy it is the exact defect being fixed.

**Word timestamps.** In `transcription.py:116`, pass `word_timestamps=True` to
`model.transcribe` and persist the per-word spans. Add a nullable `word_timestamps TEXT`
column to `materials` holding the JSON array, then thread it through so
`cue_compiler.py:210` supplies it:

```python
            phrases = chunk_captions(
                caption_text,
                duration_sec=beat_duration,
                word_timestamps=vo_timing.word_timestamps,
            )
```

`VOTiming` will need the field. Where word timestamps are genuinely unavailable, the
proportional path must remain and keep flagging `approximate=True` — that honest degradation
is correct and must not be papered over with a default.

### Acceptance criteria

- No emitted `CaptionPhrase` contains a sentence terminator anywhere except its final word.
  Add a property test over a corpus of multi-sentence VO lines.
- The reconstruction invariant holds:
  `" ".join(p.text for p in phrases) == " ".join(vo_text.split())` for every test input.
- A rendered asset with word timestamps available reports `approximate=False` on every cue,
  and captions land on the spoken word within 100 ms — verify by eye on one render.
- Assets without word timestamps still render, still flagged `approximate=True`.

---

## P1-8 — Layer-2 identity QC is inert in production

### Defect

`layer2_qc.py:262-300` needs `insightface` and `onnxruntime`. Neither is declared in
`requirements-prod.txt`. The degradation is honest — `status: "skipped"` is surfaced in the
summary and the verdict is explicitly advisory
(`layer2_qc.py:660`: Layer-2 flags never auto-reject), which is correct design and should
not change. But the practical consequence is that character identity consistency has
probably never been checked. Fitzroy and Stackwell must look like themselves across every
episode; this is the check that is least affordable as a silent no-op.

### Fix

Confirm actual state on the VPS before changing code:

```bash
.venv/bin/python -c "import insightface, onnxruntime; print('present')"
ls -la <the resolved layer2 model_path>
```

If either import fails or the ONNX model file is absent, that is the finding — report it in
the changelog with the exact output. P0-1 adds both packages to
`requirements-media.txt`; installing them is the fix, plus fetching the `buffalo_l` model to
the configured `model_path`.

Then make the inert state visible rather than merely logged. The gate surfaces already
render Layer-2 findings; a skipped identity check must read as **"identity check
unavailable — model not installed"** on the asset review surface, not as an absent row that
a reader will mistake for a pass. An advisory check that silently reports nothing is
indistinguishable from a passing one, and that ambiguity is the defect worth fixing even
after the packages are installed.

### Acceptance criteria

- The VPS reports `present` for both imports and the ONNX model resolves on disk.
- A render containing a known Fitzroy reference produces an identity finding with
  `status: "complete"` and a similarity score, not `"skipped"`.
- With the model deliberately absent, the review surface displays an explicit
  "unavailable" state; a screenshot of that state accompanies the changelog entry.
- The verdict remains advisory in both cases — no auto-reject is introduced.

---

## P2-9 — Shotstack and Creatomate adapters are selectable but cannot complete a render

### Defect

`ProviderAdapterFactory.create()` (`services/render_adapters.py:518-529`) returns
`ShotstackAdapter` or `CreatomateAdapter` on request. Both `submit()` methods persist a job
with `status="submitted"` and `provider_job_id=""` while the inline comment concedes no API
call is made (`render_adapters.py:387-388`, `471-493`). Both `check_status()` and
`download()` raise `NotImplementedError` (L412, L417, L509, L512). Selecting either provider
creates a job that can never complete, cannot be polled, and gives the operator no signal
about why.

### Fix

Given the ruling that the deterministic FFmpeg renderer is the owned path, do not finish
these. Remove both from the factory so they cannot be selected, and raise a clear error
naming the reason:

```python
    @staticmethod
    def create(provider: str, db_path: str, config: dict = None) -> BaseRenderAdapter:
        if provider == "fake":
            return FakeRenderAdapter(db_path, config)
        elif provider == "local":
            from services.renderer_spec import LocalConformanceAdapter
            return LocalConformanceAdapter()
        elif provider in ("shotstack", "creatomate"):
            raise ProviderAdapterError(
                f"{provider} adapter is not implemented (submit persists a job that "
                f"can never complete; check_status and download raise). The local "
                f"FFmpeg renderer is the supported path."
            )
        else:
            ...
```

Keep the classes and their `lower()` methods — the lowering logic is the researched part and
is worth retaining as reference if a hosted renderer is ever revisited. Add a header comment
to each class stating it is unreachable by decision and pointing at this correction. Update
any test that asserts the factory returns them.

### Acceptance criteria

- `ProviderAdapterFactory.create("shotstack", ...)` raises `ProviderAdapterError` with the
  explanatory message.
- No configuration path in `config/` names either provider.
- Full suite green; tests asserting the old behaviour are updated, not deleted wholesale.

---

## P2-10 — `processes.yaml` declares a process whose prompt does not exist

### Defect

`config/processes.yaml:248-249` declares:

```yaml
  performance_analysis:
    prompt_file: "analysis/performance_analysis_v1.md"
```

There is no `prompts/analysis/` directory. An audit of all 19 declared processes found this
as the only unresolvable reference. Nothing in `src` currently invokes it, so it is dormant
rather than broken — but `processes.yaml` is meant to be a trustworthy source of truth, and a
declaration pointing at nothing undermines that for every future reader.

### Fix

Decide and act, don't leave it ambiguous. If the Analyst performance-analysis loop is
imminent, author `prompts/analysis/performance_analysis_v1.md` matching the declared inputs
(`performance_record`, `creative_fingerprint`, `tenant_baseline`, `matched_formats`) and the
`PERFORMANCE_ANALYSIS_SCHEMA`. Otherwise delete the block and record the removal in the
changelog so the intent survives in history.

Add a startup validator either way — this class of defect should be caught mechanically, not
by review:

```python
def validate_process_registry(config_dir: str = "config", prompts_dir: str = "prompts") -> list[str]:
    """Return a list of processes whose prompt_file does not resolve. Empty is healthy."""
```

Call it from `load_process_registry` and log a warning per unresolved entry at startup.
Warning, not exception — a missing prompt for an uninvoked process should not prevent the
app from booting.

### Acceptance criteria

- `validate_process_registry()` returns `[]` against the committed tree.
- A test adds a bogus `prompt_file` to a temp registry and asserts it is reported.
- Startup logs are clean of unresolved-prompt warnings.

---

## P2-11 — The gated reference asset registry lives inside a gitignored directory

### Defect

`.gitignore` ignores `data/`. Ten files under `data/media/reference/stackpenni/` are
nonetheless tracked, having been force-added: the Fitzroy and Stackwell canon documents,
`fitzroy/reference_render.png`, `grade_token/world_canon.md`, and four lockup SVGs.

The registry is supposed to be canonical, gated once, and deterministically reused. Storing
it inside an ignored path means every asset added later — by Hermes, by the app, by a future
gated approval — is silently untracked. Nobody gets an error; the file simply never enters
version control, and a VPS rebuild loses it. That is a direct threat to the "generated once
and reused" property the registry exists to guarantee.

Related, and consistent with what is already known: `stackwell/` contains
`badge_illustration.png` and `canon.md` but **no** `reference_render.png`. The realism
re-render remains outstanding, and Stackwell cannot appear in an episode until it exists.

### Fix

Separate durable canon from ephemeral state at the path level rather than relying on
force-add discipline. Move the registry out of `data/`:

```
assets/reference/<tenant>/character_ref/...
assets/reference/<tenant>/grade_token/...
assets/reference/<tenant>/lockup_svgs/...
```

`assets/` is tracked normally; `data/` stays fully ignored for databases, uploads, and
render intermediates. Use `git mv` so history follows. Update `reference_assets.py` path
resolution and any config key naming the old root, and confirm the tenant segment stays a
config-derived variable — the new path must not hardcode `stackpenni` anywhere in `src`.

If the move is deferred, the fallback is an explicit negation in `.gitignore`:

```gitignore
# Data (SQLite databases, user uploads)
data/
# ...except the gated reference asset registry, which is canonical and must be
# versioned. See CORRECTION-repo-health-v1.0 P2-11.
!data/media/reference/
!data/media/reference/**
```

The move is preferred. The negation preserves an arrangement where the most durable
artifacts in the system sit in the directory named for ephemeral state.

While in this area, fix two small things: `.gitignore` has no trailing newline after
`*.pem`, and neither does `pytest.ini`.

### Acceptance criteria

- A new file written to the registry path shows in `git status` as untracked-and-visible,
  not ignored. Verify with `git check-ignore -v <new file>` returning no match.
- All ten existing assets are present at the new path with history intact
  (`git log --follow` resolves).
- `grep -rn "data/media/reference" src/ config/` returns nothing after the move.
- No tenant name appears in any `src` path literal.

---

## P2-12 — Dead code

### Defect

Four helpers inside `create_app()` are referenced nowhere — not by any route, not by any
other helper, not by any test. Confirmed by AST reference analysis plus grep across `src`
and `tests`:

| Helper | Line | Size |
|---|---|---|
| `_get_business_context` | 3755 | 7 lines |
| `_load_all_modules` | 4653 | 13 lines |
| `_get_platforms_from_format_entry` | 4704 | 20 lines |
| `_get_variant_type_from_format_entry` | 4725 | 19 lines |

Note that the last two carry comments identifying them as the charter-compliant
replacements for `_resolve_format_platforms` and `_determine_variant_type` per
AMENDMENT-007. Their being unreferenced means either the migration to them was never
completed, or format metadata is being read another way. **Establish which before deleting** —
if AMENDMENT-007's mechanical parsers were written but never wired in, that is a charter
compliance gap, not dead code, and it needs a divergence file rather than a deletion.

Also: `url_for` is imported at `app.py:16` and used nowhere in the codebase.

### Fix

Resolve the AMENDMENT-007 question first and report the finding. Then delete what is
genuinely dead, including the unused import. Do not delete the two format parsers until the
compliance question has an answer in writing.

### Acceptance criteria

- A written determination on whether AMENDMENT-007's parsers are wired in, filed as a
  changelog note or a divergence file as appropriate.
- Genuinely dead helpers removed; full suite green.
- `url_for` no longer imported.

---

## Definition of Done

This batch is complete when all of the following hold:

1. **Clean-environment reproducibility.** A container with no pre-existing venv installs
   from `requirements-dev.txt`, boots `create_app()`, and runs the full suite green. This is
   demonstrated by pasting the actual terminal transcript into the changelog entry — not
   asserted.
2. **Fresh-database silence.** A newly created database boots and idles for 60 seconds with
   zero `no such table` errors and zero repeated error lines.
3. **Concurrency correctness.** `PRAGMA journal_mode` reports `wal` on the VPS. The
   two-worker claim test passes. No `database is locked` in logs across a full
   seed-to-publish run.
4. **Render spec conformance.** `ffprobe` output for a rendered master, attached to the
   changelog, shows 48 kHz audio, 256k audio bitrate, video bitrate in the 6–8 Mbps band,
   faststart present, and loudness at I≈−14 / TP≤−1.5.
5. **Caption correctness.** No caption cue straddles a sentence boundary; the
   reconstruction invariant holds across the test corpus; one render is inspected by eye and
   the screenshot attached.
6. **Full human UI walkthrough.** Every button on every affected surface clicked, in a
   browser, by Hermes — not a route-level test. The seed-to-publish flow exercised
   end to end: seed → idea gate → draft gate → workbench → composition ratification →
   asset gate → schedule. Any surface touched by P1-6, P1-7, or P1-8 gets explicit
   attention, and the Layer-2 unavailable state is screenshotted.
7. **Route parity.** `scripts/route_parity.py --check` passes against the baseline captured
   before this batch began. Nothing in this correction should alter the route table; if
   parity fails, something unintended happened.
8. **Changelog and progress updated.** One CHANGELOG entry for the batch, listing each item
   by its P-number with the evidence for each. `PROGRESS.md` updated.

Report per item by P-number. Where a fix was not applied, say so and say why — a documented
deferral is a complete answer; a silent omission is not.

---

## Sequencing

P0-1 through P0-4 are independent of each other and of everything else; land them as one
commit series first. P1-5 depends on P0-4 being in place. P1-6 and P1-7 are independent and
can proceed in parallel. P1-8 depends on P0-1 (the packages must be declared before they can
be installed). The P2 items are unblocked but should follow the P0/P1 work.

Do not begin `CORRECTION-app-blueprint-split-v1.0.md` until this batch's Definition of Done
is met. That refactor moves 10,000 lines and needs a known-good baseline underneath it.
