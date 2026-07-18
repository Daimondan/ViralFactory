"""
ViralFactory — Transcription Worker

Background daemon thread that polls the materials table for pending audio
and transcribes it using faster-whisper (CTranslate2). Runs in-process,
started with the Flask app.

Per DECISION-transcription-whisper-v1.0.md:
- faster-whisper, CPU, int8, model from config (default medium)
- One daemon thread, polls every few seconds
- Lazy-loads the model on first job and keeps it resident
- Backfills pending audio on startup
- Never leaves a file stuck in "processing" — wrapped in try/finally
"""

import os
import time
import sqlite3
import threading
import logging

logger = logging.getLogger("viralfactory.transcription")

# Polling interval (seconds)
POLL_INTERVAL = 5


class TranscriptionWorker:
    """Background worker that transcribes audio materials."""

    def __init__(self, db_path: str, upload_dir: str, models_config: dict):
        self.db_path = db_path
        self.upload_dir = upload_dir
        self.models_config = models_config
        self._model = None
        self._thread = None
        self._running = False

        # Transcription config
        trans_config = models_config.get("transcription", {})
        self.enabled = trans_config.get("enabled", True)
        self.model_name = trans_config.get("model", "medium")
        self.compute_type = trans_config.get("compute_type", "int8")
        self.language = trans_config.get("language", "en")

    def _load_model(self):
        """Lazy-load the faster-whisper model on first job."""
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Whisper model '{self.model_name}' (compute_type={self.compute_type})...")
            self._model = WhisperModel(
                self.model_name,
                compute_type=self.compute_type,
            )
            logger.info(f"Whisper model loaded successfully.")
            return self._model
        except ImportError:
            logger.error("faster-whisper not installed. Run: pip install faster-whisper")
            return None
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            return None

    def _get_pending_audio(self) -> list[dict]:
        """Get the oldest pending audio material."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM materials
                   WHERE material_type = 'audio'
                   AND (transcription_status = 'pending' OR transcription_status IS NULL)
                   AND normalized_content LIKE '%transcription pending%'
                   ORDER BY id ASC LIMIT 1""",
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def _find_audio_file(self, material: dict) -> str | None:
        """Find the audio file on disk for a material."""
        filename = material.get("filename", "")
        material_id = material["id"]
        upload_dir = self.upload_dir

        # Try material_{id}.{ext} pattern first
        if filename:
            ext = os.path.splitext(filename)[1]
            candidate = os.path.join(upload_dir, f"material_{material_id}{ext}")
            if os.path.exists(candidate):
                return candidate

        # Try the raw filename
        if filename:
            candidate = os.path.join(upload_dir, filename)
            if os.path.exists(candidate):
                return candidate

        # Try common extensions
        for ext in [".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4", ".opus", ".aac", ".flac"]:
            candidate = os.path.join(upload_dir, f"material_{material_id}{ext}")
            if os.path.exists(candidate):
                return candidate

        return None

    def _transcribe(self, audio_path: str) -> tuple[str, int]:
        """Transcribe an audio file. Returns (transcript, word_count)."""
        model = self._load_model()
        if model is None:
            raise RuntimeError("Whisper model not available")

        segments, info = model.transcribe(
            audio_path,
            language=self.language if self.language != "auto" else None,
            beam_size=5,
        )

        transcript_parts = []
        for segment in segments:
            transcript_parts.append(segment.text.strip())

        transcript = " ".join(transcript_parts)
        word_count = len(transcript.split()) if transcript else 0
        return transcript, word_count

    def _update_material(self, material_id: int, status: str,
                         normalized_content: str = None, word_count: int = None):
        """Update a material's transcription status and content."""
        conn = sqlite3.connect(self.db_path)
        try:
            if normalized_content is not None and word_count is not None:
                conn.execute(
                    """UPDATE materials
                       SET transcription_status = ?, normalized_content = ?, word_count = ?
                       WHERE id = ?""",
                    (status, normalized_content, word_count, material_id),
                )
            elif normalized_content is not None:
                conn.execute(
                    """UPDATE materials
                       SET transcription_status = ?, normalized_content = ?
                       WHERE id = ?""",
                    (status, normalized_content, material_id),
                )
            else:
                conn.execute(
                    "UPDATE materials SET transcription_status = ? WHERE id = ?",
                    (status, material_id),
                )
            conn.commit()
        finally:
            conn.close()

    def _process_one(self, material: dict) -> bool:
        """Process a single audio material. Returns True on success."""
        material_id = material["id"]
        filename = material.get("filename", "unknown")

        # Mark as processing
        self._update_material(material_id, "processing")

        try:
            audio_path = self._find_audio_file(material)
            if not audio_path:
                self._update_material(
                    material_id, "failed",
                    normalized_content=f"[Transcription failed: audio file not found on disk]",
                )
                logger.warning(f"Material {material_id} ({filename}): file not found")
                return False

            logger.info(f"Transcribing material {material_id} ({filename})...")
            transcript, word_count = self._transcribe(audio_path)

            if not transcript.strip():
                self._update_material(
                    material_id, "failed",
                    normalized_content=f"[Transcription failed: no speech detected]",
                    word_count=0,
                )
                logger.warning(f"Material {material_id} ({filename}): no speech detected")
                return False

            self._update_material(
                material_id, "done",
                normalized_content=transcript,
                word_count=word_count,
            )
            logger.info(f"Material {material_id} ({filename}): transcribed ({word_count} words)")
            return True

        except Exception as e:
            self._update_material(
                material_id, "failed",
                normalized_content=f"[Transcription failed: {str(e)[:200]}]",
            )
            logger.error(f"Material {material_id} ({filename}): transcription failed: {e}")
            return False

    def _backfill(self):
        """On startup, queue every audio material whose file exists and status is pending."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM materials
                   WHERE material_type = 'audio'
                   AND (transcription_status = 'pending'
                        OR (transcription_status IS NULL AND normalized_content LIKE '%transcription pending%'))
                   ORDER BY id ASC""",
            ).fetchall()
        finally:
            conn.close()

        count = len(rows)
        if count > 0:
            logger.info(f"Backfill: {count} pending audio material(s) found")

        for row in rows:
            material = dict(row)
            # Verify the file exists before queueing
            if self._find_audio_file(material):
                self._process_one(material)
            else:
                self._update_material(
                    material["id"], "failed",
                    normalized_content="[Transcription failed: audio file not found on disk]",
                )

    def _run(self):
        """Main worker loop."""
        # Backfill on startup
        try:
            self._backfill()
        except Exception as e:
            logger.error(f"Backfill failed: {e}")

        # Main loop
        while self._running:
            try:
                pending = self._get_pending_audio()
                if pending:
                    for material in pending:
                        self._process_one(material)
                else:
                    time.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(POLL_INTERVAL)

    def start(self):
        """Start the transcription worker thread."""
        if not self.enabled:
            logger.info("Transcription worker disabled (transcription.enabled = false)")
            return

        if self._thread is not None and self._thread.is_alive():
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="transcription-worker")
        self._thread.start()
        logger.info("Transcription worker started")

    def stop(self):
        """Stop the transcription worker."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            logger.info("Transcription worker stopped")
