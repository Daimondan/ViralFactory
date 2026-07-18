"""
ViralFactory — Materials Intake

Handles user material uploads for the onboarding flow.
Accepts: WhatsApp chat exports, plain text, audio (for transcription), pasted text.
Normalizes: strips other parties' messages, tags samples, stores for playbook use.
"""

import os
import re
import json
import sqlite3
from datetime import datetime
from typing import Optional
from pathlib import Path


class MaterialsIntake:
    """Manages user material collection, normalization, and storage."""

    def __init__(self, db_path: str = "data/viralfactory.db", upload_dir: str = "data/uploads"):
        self.db_path = db_path
        self.upload_dir = upload_dir
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create the materials table."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                business_slug TEXT NOT NULL,
                filename TEXT,
                material_type TEXT NOT NULL,
                -- whatsapp_export, plain_text, audio, pasted, interview_answer
                channel TEXT,
                -- whatsapp, email, voice_note, chat, social_post, interview
                date_approx TEXT,
                audience TEXT,
                -- who it was written/said to
                raw_content TEXT NOT NULL,
                normalized_content TEXT,
                -- stripped of other parties, tagged
                word_count INTEGER,
                created_at TEXT NOT NULL,
                transcription_status TEXT,
                -- NULL for non-audio; pending/processing/done/failed for audio
                file_path TEXT,
                -- durable local path for uploaded binary media
                FOREIGN KEY (run_id) REFERENCES playbook_runs(id)
            );
        """)
        # Additive migration: add transcription_status column if it doesn't exist
        try:
            conn.execute("SELECT transcription_status FROM materials LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE materials ADD COLUMN transcription_status TEXT")
        # Additive migration: add excluded column if it doesn't exist
        try:
            conn.execute("SELECT excluded FROM materials LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE materials ADD COLUMN excluded INTEGER DEFAULT 0")
        # Additive migration: durable binary path for render-ready inventory
        try:
            conn.execute("SELECT file_path FROM materials LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE materials ADD COLUMN file_path TEXT")
        # Material edits log — lightweight versioning (material_id, timestamp, before_hash)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS material_edits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                edited_at TEXT NOT NULL,
                before_hash TEXT,
                FOREIGN KEY (material_id) REFERENCES materials(id)
            );
        """)
        conn.commit()
        conn.close()

    def ingest_text(self, content: str, run_id: Optional[int] = None,
                    business_slug: str = "", material_type: str = "pasted",
                    channel: str = "", date_approx: str = "", audience: str = "") -> int:
        """
        Ingest a text sample. Returns the material ID.

        material_type: 'pasted', 'whatsapp_export', 'plain_text', 'interview_answer'
        channel: 'whatsapp', 'email', 'chat', 'social_post', 'voice_note_transcript', 'interview'
        """
        material_id = self._store(
            run_id=run_id,
            business_slug=business_slug,
            filename=None,
            material_type=material_type,
            channel=channel,
            date_approx=date_approx,
            audience=audience,
            raw_content=content,
        )
        return material_id

    def ingest_file(self, filepath: str, run_id: Optional[int] = None,
                    business_slug: str = "", channel: str = "",
                    date_approx: str = "", audience: str = "") -> int:
        """
        Ingest an uploaded file. Detects type by extension and content.
        Returns the material ID of the first file ingested.

        For .zip files: extracts to a temp directory, ingests each extracted
        file recursively, and returns the first material ID. All extracted
        files are stored as separate materials under the same run.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        filename = path.name
        ext = path.suffix.lower()

        # ── ZIP: extract and ingest each file ──
        if ext == ".zip":
            return self.ingest_zip(filepath, run_id=run_id, business_slug=business_slug,
                                   channel=channel, date_approx=date_approx, audience=audience)

        if ext in (".txt", ".md"):
            content = path.read_text(encoding="utf-8", errors="replace")
            # Check if it's a WhatsApp export (has date/time/sender pattern)
            if self._is_whatsapp_export(content):
                material_type = "whatsapp_export"
                channel = channel or "whatsapp"
            else:
                material_type = "plain_text"
                channel = channel or "text"
        elif ext in (".json",):
            # Could be a chat export in JSON format
            content = path.read_text(encoding="utf-8", errors="replace")
            material_type = "plain_text"
            channel = channel or "chat"
        elif ext in (".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4", ".opus", ".aac", ".flac"):
            # Audio/video file — needs transcription
            # mp4/opus/aac common for WhatsApp voice notes
            content = f"[Audio/video file: {filename} — transcription pending]"
            material_type = "audio"
            channel = channel or "voice_note"
        elif ext == ".pdf":
            # PDF — try to extract text
            content = self._extract_pdf_text(filepath) or f"[PDF file: {filename} — text extraction returned empty]"
            material_type = "plain_text"
            channel = channel or "document"
        elif ext == ".docx":
            # Word document — extract text via python-docx
            content = self._extract_docx_text(filepath) or f"[DOCX file: {filename} — text extraction returned empty]"
            material_type = "plain_text"
            channel = channel or "document"
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            # Image — store as reference, copy to upload dir
            content = f"[Image file: {filename}]"
            material_type = "image"
            channel = channel or "visual_reference"
        else:
            # Unknown type — try as text
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = f"[Binary file: {filename} — could not read as text]"
            material_type = "plain_text"
            channel = channel or "text"

        material_id = self._store(
            run_id=run_id,
            business_slug=business_slug,
            filename=filename,
            material_type=material_type,
            channel=channel,
            date_approx=date_approx,
            audience=audience,
            raw_content=content,
        )

        # If audio, copy the file to upload dir for later transcription
        if material_type == "audio":
            dest = os.path.join(self.upload_dir, f"material_{material_id}{ext}")
            import shutil
            shutil.copy2(filepath, dest)
            self._update_field(material_id, "file_path", dest)
            self._update_field(material_id, "normalized_content",
                             f"[Audio file stored at: {dest} — transcription pending]")
            self._update_field(material_id, "transcription_status", "pending")

        # If image, copy to upload dir for reference
        if material_type == "image":
            dest = os.path.join(self.upload_dir, f"material_{material_id}{ext}")
            import shutil
            shutil.copy2(filepath, dest)
            self._update_field(material_id, "file_path", dest)

        return material_id

    def ingest_zip(self, filepath: str, run_id: Optional[int] = None,
                   business_slug: str = "", channel: str = "",
                   date_approx: str = "", audience: str = "") -> int:
        """
        Extract a zip file and ingest each file inside it.
        Returns the first material ID. All files are stored as separate materials.

        Handles nested directories inside the zip. Skips:
        - Hidden files (starting with .)
        - __MACOSX metadata directories
        - Empty directories
        """
        import zipfile
        import tempfile
        import shutil

        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Zip file not found: {filepath}")

        # Extract to a temp directory
        extract_dir = tempfile.mkdtemp(prefix="vf_zip_")
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                # Filter out junk entries
                valid_names = [
                    name for name in zf.namelist()
                    if not name.startswith("__MACOSX")
                    and not os.path.basename(name).startswith(".")
                    and not name.endswith("/")  # skip directories
                ]
                if not valid_names:
                    # Empty or junk-only zip
                    material_id = self._store(
                        run_id=run_id, business_slug=business_slug,
                        filename=path.name, material_type="plain_text",
                        channel=channel or "archive",
                        date_approx=date_approx, audience=audience,
                        raw_content=f"[Zip file: {path.name} — no readable files found inside]",
                    )
                    return material_id

                zf.extractall(extract_dir, members=valid_names)

            # Ingest each extracted file
            material_ids = []
            for root, dirs, files in os.walk(extract_dir):
                # Skip __MACOSX dirs
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
                for f in sorted(files):
                    if f.startswith("."):
                        continue
                    extracted_path = os.path.join(root, f)
                    rel_path = os.path.relpath(extracted_path, extract_dir)
                    try:
                        mid = self.ingest_file(
                            extracted_path, run_id=run_id,
                            business_slug=business_slug,
                            channel=channel or "zip_extract",
                            date_approx=date_approx, audience=audience,
                        )
                        material_ids.append(mid)
                    except Exception as e:
                        # Log the failure but continue with other files
                        mid = self._store(
                            run_id=run_id, business_slug=business_slug,
                            filename=rel_path, material_type="plain_text",
                            channel="zip_extract_error",
                            date_approx=date_approx, audience=audience,
                            raw_content=f"[Failed to ingest {rel_path}: {e}]",
                        )
                        material_ids.append(mid)

            if not material_ids:
                material_id = self._store(
                    run_id=run_id, business_slug=business_slug,
                    filename=path.name, material_type="plain_text",
                    channel=channel or "archive",
                    date_approx=date_approx, audience=audience,
                    raw_content=f"[Zip file: {path.name} — no files could be ingested]",
                )
                return material_id

            return material_ids[0]

        finally:
            # Clean up the temp directory
            shutil.rmtree(extract_dir, ignore_errors=True)

    def _extract_pdf_text(self, filepath: str) -> Optional[str]:
        """Try to extract text from a PDF file using available libraries."""
        # Try pdfplumber first (best quality), then PyPDF2, then fall back
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
                return text.strip() if text.strip() else None
        except ImportError:
            pass
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip() if text.strip() else None
        except ImportError:
            pass
        return None

    def _extract_docx_text(self, filepath: str) -> Optional[str]:
        """Extract text from a .docx file using python-docx."""
        try:
            from docx import Document
            doc = Document(filepath)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs) if paragraphs else None
        except Exception:
            return None

    def normalize_whatsapp(self, content: str, user_identifiers: list[str]) -> str:
        """
        Keep only lines from the user.

        WhatsApp export formats supported:
        - Android US 12h:  12/31/23, 11:45 PM - Sender Name: message text
        - Android 24h:     31/12/2023, 23:45 - Sender Name: message text
        - iOS 12h:         [12/31/23, 11:45:23 PM] Sender Name: message text
        - iOS 24h:         [31/12/2023, 23:45:07] Sender Name: message text

        user_identifiers: list of sender names that are the user (e.g. ["Daimon", "Daimon Nurse"])
        """
        # WhatsApp export pattern: date, time - Sender: message
        # Also handle multi-line messages (continuation lines have no sender prefix)
        lines = content.split("\n")
        normalized_lines = []
        in_user_message = False
        user_patterns = [uid.lower().strip() for uid in user_identifiers if uid.strip()]

        for line in lines:
            # Match WhatsApp export line across all formats:
            # - Optional opening bracket
            # - Date: dd/dd/dd or dd/dd/dddd
            # - Separator: comma + space
            # - Time: H:MM or HH:MM, optional :SS seconds, optional AM/PM
            # - Optional closing bracket
            # - Separator: - or en-dash
            # - Sender: message
            match = re.match(
                r'^\[?\s*(\d{1,2}/\d{1,2}/\d{2,4})[,\s]+(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:[AP]M)?\]?\s*[-–]?\s*(.+?):\s*(.*)',
                line
            )
            if match:
                sender = match.group(3).strip()
                message = match.group(4).strip()
                if any(uid in sender.lower() for uid in user_patterns):
                    in_user_message = True
                    normalized_lines.append(message)
                else:
                    in_user_message = False
            elif in_user_message and line.strip():
                # Continuation of the user's multi-line message
                normalized_lines.append(line.strip())
            else:
                in_user_message = False

        return "\n".join(normalized_lines)

    def normalize_text(self, content: str) -> str:
        """
        Basic normalization for non-WhatsApp text.
        Strip email signatures, forwarded text markers, but preserve the user's voice.
        Never correct grammar, spelling, or dialect.
        """
        # Strip email signature separators
        content = re.sub(r'^--\s*$', '', content, flags=re.MULTILINE)
        # Strip "On [date], [person] wrote:" forwarded headers
        content = re.sub(r'^On .+ wrote:\s*$', '', content, flags=re.MULTILINE)
        # Strip leading ">" quoted lines
        content = re.sub(r'^>.*$', '', content, flags=re.MULTILINE)
        # Strip "Begin forwarded message:" headers
        content = re.sub(r'^Begin forwarded message:', '', content, flags=re.MULTILINE)
        # Collapse excessive blank lines (3+ to 2)
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    def get_corpus(self, run_id: int) -> dict:
        """
        Get all normalized materials for a playbook run.
        Returns dict with 'samples' (list of dicts) and 'total_words'.

        Audio materials with transcription_status='done' include the transcript
        as corpus. Pending/failed audio is excluded.
        Excluded materials are dropped (never deleted).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM materials WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        conn.close()

        samples = []
        total_words = 0
        for row in rows:
            # Excluded materials drop out of corpus
            if row["excluded"]:
                continue

            content = row["normalized_content"] or row["raw_content"]
            trans_status = row["transcription_status"] if "transcription_status" in row.keys() else None

            # For audio: only count words if transcription is done
            if row["material_type"] == "audio":
                if trans_status == "done" and content and not content.startswith("[Audio"):
                    wc = len(content.split())
                else:
                    wc = 0
                    content = ""  # Don't include pending/failed audio in corpus
            else:
                wc = len(content.split()) if content and not content.startswith("[Audio") else 0

            samples.append({
                "id": row["id"],
                "type": row["material_type"],
                "channel": row["channel"],
                "date": row["date_approx"],
                "audience": row["audience"],
                "word_count": wc,
                "content_preview": content[:200] if content else "",
                "transcription_status": trans_status,
            })
            total_words += wc

        return {"samples": samples, "total_words": total_words}

    def get_material(self, material_id: int) -> dict:
        """Get a single material by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM materials WHERE id = ?", (material_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_materials(self, business_slug: str = None, run_id: int = None) -> list[dict]:
        """List materials, optionally filtered."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if run_id:
            rows = conn.execute(
                "SELECT * FROM materials WHERE run_id = ? ORDER BY id DESC", (run_id,)
            ).fetchall()
        elif business_slug:
            rows = conn.execute(
                "SELECT * FROM materials WHERE business_slug = ? ORDER BY id DESC", (business_slug,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM materials ORDER BY id DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _is_whatsapp_export(self, content: str) -> bool:
        """Detect if text looks like a WhatsApp chat export."""
        # Look for the date/time - Sender: pattern in first 20 lines
        # Supports: 12h with AM/PM, 24h without, iOS with seconds and brackets
        for line in content.split("\n")[:20]:
            if re.match(
                r'^\[?\s*\d{1,2}/\d{1,2}/\d{2,4}[,\s]+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?\]?\s*[-–]?\s*.+?:',
                line
            ):
                return True
        return False

    def _store(self, run_id, business_slug, filename, material_type, channel,
               date_approx, audience, raw_content):
        """Store a material in the database.

        Operator materials (voice notes, uploads, WhatsApp exports) feed the
        playbooks → modules (Voice Profile, Story Frameworks, etc.). They do
        NOT enter the Source Bank — the Source Bank is for external content the
        AI scouts and crosses with modules for ideation. Mixing operator
        materials into the source bank double-counts the operator's own material
        as external inspiration.
        """
        # Auto-normalize based on type
        if material_type == "whatsapp_export":
            # For now, store raw. Normalization with user identifiers happens
            # when the playbook Step 2 runs (user provides their identifiers).
            normalized = raw_content  # will be normalized in Step 2
        elif material_type == "audio":
            normalized = None  # transcription pending
        else:
            normalized = self.normalize_text(raw_content)

        wc = len(raw_content.split()) if raw_content else 0
        ts = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """INSERT INTO materials
               (run_id, business_slug, filename, material_type, channel,
                date_approx, audience, raw_content, normalized_content, word_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, business_slug, filename, material_type, channel,
             date_approx, audience, raw_content, normalized, wc, ts),
        )
        material_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return material_id

    def _update_field(self, material_id: int, field: str, value: str):
        """Update a single field on a material.

        R8/T2.10: field name is validated against an allowlist to prevent
        SQL injection via column name interpolation.
        """
        ALLOWED_FIELDS = {
            "normalized_content",
            "raw_content",
            "word_count",
            "material_type",
            "channel",
            "date_approx",
            "audience",
            "transcription_status",
            "file_path",
            "excluded",
        }
        if field not in ALLOWED_FIELDS:
            raise ValueError(f"Invalid field name: {field!r}. Allowed: {sorted(ALLOWED_FIELDS)}")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            f"UPDATE materials SET {field} = ? WHERE id = ?",
            (value, material_id),
        )
        conn.commit()
        conn.close()

    # ── Materials Library: edit, restore, exclude ──

    def save_edit(self, material_id: int, new_normalized_content: str) -> dict:
        """
        Save an edit to a material's normalized_content.

        - raw_content is NEVER touched (original forever).
        - The previous normalized_content hash is logged to material_edits
          for lightweight versioning (restore-to-original is a separate action).
        - word_count is recomputed from the new content.
        - Returns the updated material dict.
        """
        import hashlib
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT normalized_content, raw_content FROM materials WHERE id = ?",
            (material_id,),
        ).fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Material {material_id} not found")

        # Hash the before-state (whatever the downstream consumer was reading)
        before_content = row["normalized_content"] or row["raw_content"]
        before_hash = hashlib.sha256(before_content.encode("utf-8")).hexdigest()

        wc = len(new_normalized_content.split()) if new_normalized_content else 0
        ts = datetime.now().isoformat()

        conn.execute(
            "UPDATE materials SET normalized_content = ?, word_count = ? WHERE id = ?",
            (new_normalized_content, wc, material_id),
        )
        conn.execute(
            "INSERT INTO material_edits (material_id, edited_at, before_hash) VALUES (?, ?, ?)",
            (material_id, ts, before_hash),
        )
        conn.commit()
        conn.close()

        return self.get_material(material_id)

    def restore_to_raw(self, material_id: int) -> dict:
        """
        Restore a material's normalized_content to its raw_content (the original).

        - raw_content is the original extraction/transcription output.
        - For audio materials, this means re-copying raw → normalized.
        - For text materials, this undoes all normalize_text() edits.
        - The restore is logged in material_edits like any other edit.
        """
        import hashlib
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT normalized_content, raw_content FROM materials WHERE id = ?",
            (material_id,),
        ).fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Material {material_id} not found")

        before_content = row["normalized_content"] or row["raw_content"]
        before_hash = hashlib.sha256(before_content.encode("utf-8")).hexdigest()
        raw = row["raw_content"]
        wc = len(raw.split()) if raw else 0
        ts = datetime.now().isoformat()

        conn.execute(
            "UPDATE materials SET normalized_content = ?, word_count = ? WHERE id = ?",
            (raw, wc, material_id),
        )
        conn.execute(
            "INSERT INTO material_edits (material_id, edited_at, before_hash) VALUES (?, ?, ?)",
            (material_id, ts, before_hash),
        )
        conn.commit()
        conn.close()

        return self.get_material(material_id)

    def toggle_exclude(self, material_id: int, excluded: bool) -> dict:
        """
        Set the excluded flag on a material.

        Excluded materials drop out of corpus, summaries, and drafting packages
        but are never deleted. Toggling back to False restores them.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE materials SET excluded = ? WHERE id = ?",
            (1 if excluded else 0, material_id),
        )
        conn.commit()
        conn.close()

        return self.get_material(material_id)

    def get_edit_history(self, material_id: int) -> list[dict]:
        """Return the edit history log for a material (newest first)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM material_edits WHERE material_id = ? ORDER BY id DESC",
            (material_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_material_with_extras(self, material_id: int) -> dict:
        """Get a single material with edit_count and excluded flag."""
        mat = self.get_material(material_id)
        if not mat:
            return None
        edits = self.get_edit_history(material_id)
        mat["edit_count"] = len(edits)
        mat["edits"] = edits
        # Ensure excluded field exists
        if "excluded" not in mat:
            mat["excluded"] = 0
        return mat