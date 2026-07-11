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
                posts_text = "\n".join(
                    item for item in decoded_posts if isinstance(item, str)
                )

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

    def generate_vo(self, asset_id: int, content: str,
                    posts: str = None, business_slug: str = None,
                    take_id: str = None) -> dict:
        """Generate a VO take from script text.

        1. Extracts VO lines from content + posts
        2. Sends to Gemini TTS with style instructions
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

        # Get TTS config
        config = self._get_gemini_tts_config()
        api_key = os.environ.get(config["api_key_env"], "")

        if not api_key:
            raise VOGenerationError(
                f"{config['api_key_env']} not set — cannot generate VO via Gemini TTS"
            )

        # Ensure output directory
        media_dir = os.path.join("data", "media", str(asset_id))
        os.makedirs(media_dir, exist_ok=True)

        output_path = os.path.join(media_dir, f"vo_{take_id}.wav")

        # Call Gemini TTS
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

        # Save as WAV
        self._save_wav(pcm_data, output_path, config["sample_rate"])

        # Get duration
        duration = self._get_duration(output_path)

        # Record in asset_media
        self._record_vo_media(asset_id, output_path, duration, config["model"], take_id)

        # Log to provenance
        self._log_provenance(
            asset_id, take_id,
            f"VO generated: {duration:.1f}s, voice={config['voice']}, "
            f"text_length={len(vo_text)} chars",
            "done", config["model"], business_slug,
        )

        return {
            "path": output_path,
            "duration": duration,
            "take_id": take_id,
            "vo_text": vo_text[:200],
        }

    def has_vo_for_asset(self, asset_id: int) -> Optional[str]:
        """Check if a VO file already exists for an asset.

        Returns the path if found, None otherwise.
        """
        media_dir = os.path.join("data", "media", str(asset_id))
        if not os.path.exists(media_dir):
            return None
        for ext in [".wav", ".mp3", ".m4a"]:
            for f in os.listdir(media_dir):
                if f.startswith("vo_") and f.endswith(ext):
                    return os.path.join(media_dir, f)
        return None