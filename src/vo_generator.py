"""
ViralFactory — VO Generation

Generates voiceover audio from script text using Gemini TTS.
The system has voice_cloning config in models.yaml, but the qwen3_tts engine
requires GPU and model download. As a practical first step, we use Google's
Gemini TTS API (gemini-3.1-flash-tts-preview) which is available via the
GEMINI_API_KEY already configured for video generation.

This module:
1. Extracts VO lines from the script content
2. Sends them to Gemini TTS with style instructions
3. Saves the audio as vo_<take_id>.wav in the asset's media directory
4. The renderer's _resolve_vo_path() finds this file and mixes it as primary audio

Config-driven: voice, style instructions, and model are in models.yaml.
"""

import base64
import json
import os
import re
import sqlite3
import subprocess
import time
import wave
from datetime import datetime, timezone
from typing import Optional

try:
    from .provenance import ProvenanceLog
except ImportError:
    from provenance import ProvenanceLog


class VOGenerationError(Exception):
    """Raised when VO generation fails."""
    pass


class VOGenerator:
    """
    Generates voiceover audio from script text using Gemini TTS.

    Usage:
        gen = VOGenerator(models_config, db_path="data/viralfactory.db")
        result = gen.generate_vo(asset_id, script_text, business_slug="my-business")
        # result = {"path": "data/media/2/vo_take_1.wav", "duration": 15.3, "take_id": "take_1"}
    """

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.models_config = models_config
        self.db_path = db_path
        self.provenance = ProvenanceLog(db_path)

    def _extract_vo_lines(self, content: str, posts: str = None) -> str:
        """Extract VO/spoken dialogue lines from the script.

        Looks for patterns like:
          VO: "text here"
          Voiceover: "text here"
          Narrator: "text here"

        Returns the concatenated VO text, or empty string if none found.
        """
        posts_text = posts or ""
        if isinstance(posts_text, str):
            try:
                decoded_posts = json.loads(posts_text)
            except (json.JSONDecodeError, TypeError):
                decoded_posts = None
            if isinstance(decoded_posts, list):
                # Handle both string posts (backward-compat) and frame objects
                # (enriched schema v4 — extract vo_text from dicts)
                lines = []
                for item in decoded_posts:
                    if isinstance(item, str):
                        lines.append(item)
                    elif isinstance(item, dict):
                        lines.append(item.get("vo_text", ""))
                posts_text = "\n".join(lines)

        text = (content or "") + "\n" + posts_text
        if not text.strip():
            return ""

        vo_lines = []
        # Match VO:, Voiceover:, Voice over:, Voice-over:, Narrator:
        # followed by quoted or unquoted text
        vo_pattern = re.compile(
            r'(?:VO|Voiceover|Voice[\s-]?over|Narrator)\s*:\s*["\']?(.+?)["\']?\s*(?:\n|$)',
            re.IGNORECASE,
        )

        for match in vo_pattern.finditer(text):
            line = match.group(1).strip()
            if line:
                vo_lines.append(line)

        return " ".join(vo_lines)

    def _get_engine(self) -> str:
        """Get the configured voice cloning engine."""
        return self.models_config.get("voice_cloning", {}).get("engine", "gemini_tts")

    def _get_gemini_tts_config(self) -> dict:
        """Get TTS configuration from models.yaml."""
        voice_config = self.models_config.get("voice_cloning", {})
        tts_config = voice_config.get("tts", {})

        return {
            "model": tts_config.get("model", "gemini-3.1-flash-tts-preview"),
            "voice": tts_config.get("voice", "Kore"),
            "style": tts_config.get("style", ""),
            "api_key_env": tts_config.get("api_key_env", "GEMINI_API_KEY"),
            "sample_rate": tts_config.get("sample_rate", 24000),
        }

    def _get_chatterbox_config(self) -> dict:
        """Get Chatterbox configuration from models.yaml."""
        voice_config = self.models_config.get("voice_cloning", {})
        cb_config = voice_config.get("chatterbox", {})
        return {
            "model": cb_config.get("model", "chatterbox_tts"),
            "device": cb_config.get("device", "cpu"),
            "exaggeration": cb_config.get("exaggeration", 0.5),
            "cfg_weight": cb_config.get("cfg_weight", 0.5),
            "sample_rate": voice_config.get("sample_rate", 24000),
        }

    def _get_default_reference_audio(self, business_slug: str = None) -> str:
        """Find the best reference audio file for the business's cloned voice.

        If ``preferred_reference`` is set in the chatterbox config, use that
        file specifically (operator-calibrated clip). Otherwise fall back to
        the longest WAV (better for zero-shot cloning).
        """
        voice_config = self.models_config.get("voice_cloning", {})
        ref_dir_pattern = voice_config.get(
            "reference_audio_dir", "modules/{business}/voice-samples/"
        )
        if business_slug:
            ref_dir = ref_dir_pattern.replace("{business}", business_slug)
        else:
            return None

        if not os.path.isdir(ref_dir):
            return None

        wavs = [f for f in os.listdir(ref_dir) if f.endswith(".wav")]
        if not wavs:
            return None

        # Check for operator-calibrated preferred reference
        preferred = voice_config.get("chatterbox", {}).get("preferred_reference")
        if preferred:
            preferred_path = os.path.join(ref_dir, preferred)
            if os.path.exists(preferred_path):
                return preferred_path

        # Fall back: sort by duration (longest first)
        def get_dur(f):
            try:
                r = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", os.path.join(ref_dir, f)],
                    capture_output=True, text=True, timeout=10,
                )
                return float(r.stdout.strip() or 0)
            except Exception:
                return 0.0

        wavs.sort(key=get_dur, reverse=True)
        return os.path.join(ref_dir, wavs[0])

    # Chatterbox model is loaded lazily and kept resident (same pattern as Whisper).
    # Combined RAM budget is tight on the VPS — may need load/unload per job.
    _chatterbox_model = None
    _chatterbox_config_cache = None

    def _load_chatterbox(self, config: dict):
        """Load the Chatterbox model (lazy, cached)."""
        if self._chatterbox_model is not None:
            if self._chatterbox_config_cache == config["model"]:
                return self._chatterbox_model
            # Config changed — release old model
            self._chatterbox_model = None

        model_name = config["model"]
        device = config["device"]

        if model_name == "chatterbox_turbo_tts":
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            self._chatterbox_model = ChatterboxTurboTTS.from_pretrained(device=device)
        else:
            from chatterbox.tts import ChatterboxTTS
            self._chatterbox_model = ChatterboxTTS.from_pretrained(device=device)

        self._chatterbox_config_cache = model_name
        return self._chatterbox_model

    def _call_chatterbox(self, text: str, reference_audio: str,
                         config: dict) -> str:
        """Call Chatterbox to generate speech and return the output WAV path.

        Chatterbox generates to a temp file via torchaudio.save.
        We return the path — the caller moves/renames it as needed.
        """
        import tempfile
        import torchaudio as ta

        model = self._load_chatterbox(config)

        # Generate with cloned voice
        wav = model.generate(
            text,
            audio_prompt_path=reference_audio,
            exaggeration=config["exaggeration"],
            cfg_weight=config["cfg_weight"],
        )

        # Save to temp file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", dir="/tmp")
        os.close(tmp_fd)
        ta.save(tmp_path, wav, model.sr)

        return tmp_path

    def _call_gemini_tts(self, text: str, voice: str, style: str,
                         model: str, api_key: str) -> bytes:
        """Call Gemini TTS API and return PCM audio data.

        Uses the generateContent endpoint with response_modalities=["AUDIO"].
        """
        import requests

        # Style is optional. Its business-specific direction lives in config;
        # without one, ask for neutral delivery instead of injecting a default.
        prompt = f"Say in a {style} voice: {text}" if style else f"Say: {text}"

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice
                        }
                    }
                }
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        response = requests.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            raise VOGenerationError(
                f"Gemini TTS API error {response.status_code}: {response.text[:500]}"
            )

        data = response.json()

        # Extract audio data from the response
        candidates = data.get("candidates", [])
        if not candidates:
            raise VOGenerationError("Gemini TTS returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                audio_b64 = part["inlineData"].get("data", "")
                if audio_b64:
                    return base64.b64decode(audio_b64)

        raise VOGenerationError("Gemini TTS returned no audio data in response")

    def _save_wav(self, pcm_data: bytes, file_path: str, sample_rate: int = 24000):
        """Save PCM audio data as a WAV file."""
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)

    def _get_duration(self, file_path: str) -> float:
        """Get audio file duration via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", file_path],
                capture_output=True, text=True, timeout=30,
            )
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception:
            return 0.0

    def _record_vo_media(self, asset_id: int, path: str, duration: float,
                         model: str, take_id: str):
        """Record the VO file in asset_media."""
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO asset_media
               (asset_id, kind, path, model, prompt, cost_usd, created_at)
               VALUES (?, 'vo', ?, ?, ?, NULL, ?)""",
            (asset_id, path, model, f"vo_take={take_id}, duration={duration:.1f}s", ts),
        )
        conn.commit()
        conn.close()

    def _log_provenance(self, asset_id: int, take_id: str, message: str,
                        verdict: str, model: str, business_slug: str = None):
        """Log VO generation to provenance."""
        import hashlib
        self.provenance.log(
            input_hash=hashlib.sha256(f"vo_gen:{asset_id}:{take_id}".encode()).hexdigest(),
            prompt_file="(vo_generator)",
            prompt_version="1.0",
            model=model,
            provider="google",
            raw_output=message,
            validated_output={"asset_id": asset_id, "take_id": take_id, "message": message},
            validator_verdict=verdict,
            context=f"VO generation for asset {asset_id}",
            temperature=0,
            business_slug=business_slug,
        )

    def generate_vo_per_frame(self, asset_id: int, posts: list,
                              business_slug: str = None,
                              take_id: str = None) -> dict:
        """Generate one VO segment per frame/post.

        VO is the master timeline — each post in the script's posts array is
        one beat. This method generates a separate TTS call per post,
        measures each segment's real duration, and returns the timeline.

        Returns: {
            "take_id": "take_...",
            "segments": [
                {"frame": 1, "path": "...", "duration": 6.2, "text": "..."},
                ...
            ],
            "total_duration": 61.5,
            "combined_path": "..."  # concatenated WAV for backward compat
        }
        """
        if not take_id:
            take_id = f"take_{int(time.time())}"

        media_dir = os.path.join("data", "media", str(asset_id))
        os.makedirs(media_dir, exist_ok=True)

        engine = self._get_engine()
        use_chatterbox = (engine == "chatterbox")

        if use_chatterbox:
            cb_config = self._get_chatterbox_config()
            reference_audio = self._resolve_reference_audio(None, business_slug)
            if not reference_audio:
                raise VOGenerationError(
                    "No reference audio found for voice cloning. "
                    "Upload voice samples to modules/{business}/voice-samples/ "
                    "or select a voice in the voice registry."
                )
        else:
            gemini_config = self._get_gemini_tts_config()
            api_key = os.environ.get(gemini_config["api_key_env"], "")
            if not api_key:
                raise VOGenerationError(
                    f"{gemini_config['api_key_env']} not set — cannot generate VO via Gemini TTS"
                )

        segments = []
        segment_paths = []

        for i, post in enumerate(posts, 1):
            # Handle both string posts (backward-compat) and frame objects (v4)
            if isinstance(post, dict):
                vo_text = post.get("vo_text", "")
                if not vo_text:
                    vo_text = post.get("label", f"Frame {i}")  # fallback
            else:
                # Extract spoken lines from this post/frame
                vo_text = self._extract_vo_lines(post, json.dumps([post]))
                if not vo_text:
                    vo_text = post  # use the raw post if extraction finds nothing

            seg_path = os.path.join(media_dir, f"vo_{take_id}_frame{i}.wav")

            try:
                if use_chatterbox:
                    tmp_path = self._call_chatterbox(vo_text, reference_audio, cb_config)
                    import shutil
                    shutil.move(tmp_path, seg_path)
                    model_name = cb_config["model"]
                else:
                    pcm_data = self._call_gemini_tts(
                        vo_text, gemini_config["voice"], gemini_config["style"],
                        gemini_config["model"], api_key,
                    )
                    self._save_wav(pcm_data, seg_path, gemini_config["sample_rate"])
                    model_name = gemini_config["model"]
            except VOGenerationError:
                raise
            except Exception as e:
                self._log_provenance(
                    asset_id, take_id, f"VO frame {i} failed: {e}",
                    "failed", model_name if 'model_name' in dir() else "unknown", business_slug,
                )
                raise VOGenerationError(f"TTS call failed for frame {i}: {e}")
            duration = self._get_duration(seg_path)

            segments.append({
                "frame": i,
                "path": seg_path,
                "duration": duration,
                "text": vo_text[:200],
            })
            segment_paths.append(seg_path)

            self._log_provenance(
                asset_id, take_id,
                f"VO frame {i}: {duration:.1f}s, text={len(vo_text)} chars",
                "done", model_name, business_slug,
            )

        # Concatenate all segments into one WAV for backward compatibility
        combined_path = os.path.join(media_dir, f"vo_{take_id}.wav")
        if segment_paths:
            self._concat_wavs(segment_paths, combined_path)

        total_duration = sum(s["duration"] for s in segments)

        # Record the combined file in asset_media
        self._record_vo_media(asset_id, combined_path, total_duration,
                              model_name, take_id)

        voice_label = cb_config["model"] if use_chatterbox else gemini_config["voice"]
        self._log_provenance(
            asset_id, take_id,
            f"VO complete: {len(segments)} frames, {total_duration:.1f}s total, "
            f"voice={voice_label}, engine={engine}",
            "done", model_name, business_slug,
        )

        return {
            "take_id": take_id,
            "segments": segments,
            "total_duration": total_duration,
            "combined_path": combined_path,
        }

    def _concat_wavs(self, wav_paths: list, output_path: str):
        """Concatenate multiple WAV files into one using ffmpeg."""
        try:
            cmd = ["ffmpeg", "-y"]
            for wp in wav_paths:
                cmd.extend(["-i", wp])
            cmd.extend([
                "-filter_complex", "".join(
                    f"[{i}:a]" for i in range(len(wav_paths))
                ) + f"concat=n={len(wav_paths)}:v=0:a=1[out]",
                "-map", "[out]",
                "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
                output_path,
            ])
            subprocess.run(cmd, capture_output=True, timeout=60)
        except Exception:
            # Fallback: just copy the first segment as the combined file
            if wav_paths and not os.path.exists(output_path):
                import shutil
                shutil.copy2(wav_paths[0], output_path)

    def has_vo_segments_for_asset(self, asset_id: int) -> Optional[str]:
        """Check if per-frame VO segments exist for an asset.

        Returns the combined path if found, None otherwise.
        """
        media_dir = os.path.join("data", "media", str(asset_id))
        if not os.path.exists(media_dir):
            return None
        # Look for frame segment files
        for f in os.listdir(media_dir):
            if f.startswith("vo_") and "_frame" in f and f.endswith(".wav"):
                # Segments exist — return the combined file if available
                for cf in os.listdir(media_dir):
                    if cf.startswith("vo_") and "_frame" not in cf and cf.endswith(".wav"):
                        return os.path.join(media_dir, cf)
                return os.path.join(media_dir, f)  # at least segments exist
        return None

    def generate_vo(self, asset_id: int, content: str,
                    posts: str = None, business_slug: str = None,
                    take_id: str = None,
                    voice_id: int = None) -> dict:
        """Generate a VO take from script text.

        1. Extracts VO lines from content + posts
        2. Sends to configured TTS engine (chatterbox or gemini_tts)
        3. Saves as data/media/<asset_id>/vo_<take_id>.wav
        4. Records in asset_media + provenance

        Returns: {"path": ..., "duration": ..., "take_id": ...}
        Raises VOGenerationError on failure.
        """
        # Extract VO lines
        vo_text = self._extract_vo_lines(content, posts)
        if not vo_text:
            raise VOGenerationError("No VO lines found in script content")

        # Generate take_id if not provided
        if not take_id:
            take_id = f"take_{int(time.time())}"

        # Ensure output directory
        media_dir = os.path.join("data", "media", str(asset_id))
        os.makedirs(media_dir, exist_ok=True)

        output_path = os.path.join(media_dir, f"vo_{take_id}.wav")

        engine = self._get_engine()

        if engine == "chatterbox":
            # --- Chatterbox path (voice cloning) ---
            config = self._get_chatterbox_config()

            # Get reference audio — from voice_id or default
            reference_audio = self._resolve_reference_audio(voice_id, business_slug)
            if not reference_audio:
                raise VOGenerationError(
                    "No reference audio found for voice cloning. "
                    "Upload voice samples to modules/{business}/voice-samples/ "
                    "or select a voice in the voice registry."
                )

            try:
                tmp_path = self._call_chatterbox(vo_text, reference_audio, config)
            except Exception as e:
                self._log_provenance(
                    asset_id, take_id, f"VO generation failed: {e}",
                    "failed", "chatterbox_tts", business_slug,
                )
                raise VOGenerationError(f"Chatterbox TTS call failed: {e}")

            # Move temp file to output location
            import shutil
            shutil.move(tmp_path, output_path)

            model_name = config["model"]

        else:
            # --- Gemini TTS path (fallback, preset voices) ---
            config = self._get_gemini_tts_config()
            api_key = os.environ.get(config["api_key_env"], "")

            if not api_key:
                raise VOGenerationError(
                    f"{config['api_key_env']} not set — cannot generate VO via Gemini TTS"
                )

            try:
                pcm_data = self._call_gemini_tts(
                    vo_text, config["voice"], config["style"],
                    config["model"], api_key,
                )
            except Exception as e:
                self._log_provenance(
                    asset_id, take_id, f"VO generation failed: {e}",
                    "failed", config["model"], business_slug,
                )
                raise VOGenerationError(f"Gemini TTS call failed: {e}")

            self._save_wav(pcm_data, output_path, config["sample_rate"])
            model_name = config["model"]

        # Get duration
        duration = self._get_duration(output_path)

        # Record in asset_media
        self._record_vo_media(asset_id, output_path, duration, model_name, take_id)

        # Log to provenance
        self._log_provenance(
            asset_id, take_id,
            f"VO generated: {duration:.1f}s, engine={engine}, "
            f"text_length={len(vo_text)} chars",
            "done", model_name, business_slug,
        )

        return {
            "path": output_path,
            "duration": duration,
            "take_id": take_id,
            "vo_text": vo_text[:200],
        }

    def _resolve_reference_audio(self, voice_id: int = None,
                                 business_slug: str = None) -> str:
        """Resolve the reference audio path for voice cloning.

        Priority:
        1. If voice_id is given, look up the voices table for that voice's reference_path
        2. If no voice_id, look up the default voice for this business
        3. If no default, fall back to the longest file in voice-samples/
        """
        if voice_id:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT reference_path FROM voices WHERE id = ?", (voice_id,)
            ).fetchone()
            conn.close()
            if row and row[0] and os.path.isfile(row[0]):
                return row[0]

        # Look for default voice in the registry
        if business_slug:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT reference_path FROM voices WHERE business_slug = ? "
                "AND is_default = 1 AND kind = 'cloned' LIMIT 1",
                (business_slug,)
            ).fetchone()
            conn.close()
            if row and row[0] and os.path.isfile(row[0]):
                return row[0]

        # Fall back to longest file in voice-samples dir
        return self._get_default_reference_audio(business_slug)

    def has_vo_for_asset(self, asset_id: int) -> Optional[str]:
        """Check if a VO file already exists for an asset.

        Returns the path if found, None otherwise.
        Skips per-frame segment files (vo_*_frame*.wav) — those are
        intermediate segments, not the combined take.
        """
        media_dir = os.path.join("data", "media", str(asset_id))
        if not os.path.exists(media_dir):
            return None
        for ext in [".wav", ".mp3", ".m4a"]:
            for f in os.listdir(media_dir):
                if f.startswith("vo_") and f.endswith(ext) and "_frame" not in f:
                    return os.path.join(media_dir, f)
        return None