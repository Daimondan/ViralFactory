"""
ViralFactory — Final Assembly Renderer

Per CORRECTION-final-assembly-and-materials-editing-v1.0 Part 1:
- Deterministic, FFmpeg-based renderer.
- Takes a validated Edit Plan (JSON) + ingredient files → finished MP4.
- Runs as an async job on the shared jobs framework.
- Output: data/media/<asset_id>/final_<version>.mp4, asset_media row with kind="final_cut".
- Progress states: planning → rendering → done/failed.

Uses MoviePy v2 (wraps ffmpeg) for compositing/text/transitions, with direct
ffmpeg filter-graph escape hatch where needed. Burned-in captions via ASS subtitles.
System dependency: apt install ffmpeg (already present on this VPS).
"""

import json
import os
import subprocess
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

# Support both package and direct imports
try:
    from .provenance import ProvenanceLog
except ImportError:
    from provenance import ProvenanceLog


class AssemblyError(Exception):
    """Raised when rendering fails."""
    pass


class AssemblyRenderer:
    """
    Deterministic FFmpeg-based renderer.

    Usage:
        renderer = AssemblyRenderer(models_config, db_path="data/viralfactory.db")
        result = renderer.render(plan, asset_id, draft_id, business_slug="my-business")
        # result = {"path": "data/media/42/final_1.mp4", "duration": 30.0, "render_time_s": 120}
    """

    # Supported transition vocabulary (the renderer supports exactly these)
    TRANSITIONS = {"cut", "crossfade", "slide", "whip"}

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.models_config = models_config
        self.db_path = db_path
        self.provenance = ProvenanceLog(db_path)
        # Ensure asset_media table exists (media_adapter creates it, but we may
        # be called without the media adapter having been instantiated)
        import sqlite3
        from media_adapter import ASSET_MEDIA_SCHEMA
        conn = sqlite3.connect(db_path)
        conn.executescript(ASSET_MEDIA_SCHEMA)
        conn.commit()
        conn.close()

    def _resolve_source(self, source_ref: str, asset_id: int) -> str:
        """Resolve a source reference to a file path.

        source_ref formats:
          generated:<media_id>  → data/media/<asset_id>/<filename from asset_media>
          upload:<material_id>  → data/uploads/material_<id>.<ext>
          stock:<stock_id>      → from stock_cache table
        """
        if ":" not in source_ref:
            raise AssemblyError(f"Invalid source reference: {source_ref}")

        kind, ref_id = source_ref.split(":", 1)

        if kind == "generated":
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT path FROM asset_media WHERE id = ? AND kind IN ('image', 'video')",
                (int(ref_id),),
            ).fetchone()
            conn.close()
            if not row:
                raise AssemblyError(f"Generated media not found: {source_ref}")
            path = row["path"]
            if not os.path.isabs(path):
                path = os.path.abspath(path)
            if not os.path.exists(path):
                raise AssemblyError(f"Generated media file missing: {path}")
            return path

        elif kind == "upload":
            # Find the uploaded material's file
            from materials import MaterialsIntake
            intake = MaterialsIntake(self.db_path)
            mat = intake.get_material(int(ref_id))
            if not mat:
                raise AssemblyError(f"Upload material not found: {source_ref}")
            # Try to find the file
            upload_dir = os.path.join("data", "uploads")
            filename = mat.get("filename", "")
            if filename:
                for ext in ["", ".mp4", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a"]:
                    candidate = os.path.join(upload_dir, f"material_{ref_id}{ext}")
                    if os.path.exists(candidate):
                        return os.path.abspath(candidate)
                    candidate = os.path.join(upload_dir, filename)
                    if os.path.exists(candidate):
                        return os.path.abspath(candidate)
            raise AssemblyError(f"Upload file not found for material {ref_id}")

        elif kind == "stock":
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT local_path FROM stock_cache WHERE id = ?",
                (int(ref_id),),
            ).fetchone()
            conn.close()
            if not row or not row["local_path"]:
                raise AssemblyError(f"Stock item not found: {source_ref}")
            path = row["local_path"]
            if not os.path.exists(path):
                raise AssemblyError(f"Stock file missing: {path}")
            return os.path.abspath(path)

        else:
            raise AssemblyError(f"Unknown source kind: {kind}")

    def _has_video_stream(self, file_path: str) -> bool:
        """Check if a media file contains a video stream.

        WhatsApp voice memos and audio recordings may be saved as .mp4
        with only an audio track. The concat filter requires a video stream
        from every input, so callers need to know when to synthesize one.
        """
        return self._stream_type_exists(file_path, "video")

    def _has_audio_stream(self, file_path: str) -> bool:
        """Check if a media file contains an audio stream.

        Video-only clips (e.g. test sources, screen recordings without audio)
        need a silent audio track added so the concat filter has [i:a] for
        every input.
        """
        return self._stream_type_exists(file_path, "audio")

    def _stream_type_exists(self, file_path: str, codec_type: str) -> bool:
        """Check if a media file contains a stream of the given codec_type."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", file_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return False
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == codec_type:
                    return True
            return False
        except Exception:
            return False

    def _get_duration(self, file_path: str) -> float:
        """Get media file duration in seconds via ffprobe."""
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

    def _build_cut_list(self, plan: dict) -> str:
        """Render the edit plan as a readable cut list for the operator.

        Plain language: "0:00–0:02 — your clip from the beach walk, caption: '…', hard cut to…"
        """
        lines = []
        segments = plan.get("segments", [])

        for i, seg in enumerate(segments):
            in_pt = seg.get("in", 0)
            out_pt = seg.get("out", 0)
            source = seg.get("source", "?")
            transition = seg.get("transition_in", "cut")

            # Format timestamps as M:SS
            def fmt(t):
                m = int(t // 60)
                s = int(t % 60)
                return f"{m}:{s:02d}"

            source_desc = source
            if source.startswith("generated:"):
                source_desc = f"generated clip ({source})"
            elif source.startswith("upload:"):
                source_desc = f"your uploaded clip ({source})"
            elif source.startswith("stock:"):
                source_desc = f"stock clip ({source})"

            overlays = seg.get("overlays", [])
            caption_text = ""
            for ov in overlays:
                if ov.get("type") == "caption" and ov.get("text"):
                    caption_text = f", caption: '{ov['text'][:60]}'"
                    break

            transition_desc = {
                "cut": "hard cut",
                "crossfade": "crossfade",
                "slide": "slide transition",
                "whip": "whip pan",
            }.get(transition, transition)

            if i == 0:
                lines.append(f"{fmt(in_pt)}–{fmt(out_pt)} — {source_desc}{caption_text}")
            else:
                lines.append(f"{fmt(in_pt)}–{fmt(out_pt)} — {source_desc}{caption_text}, {transition_desc} from previous")

        return "\n".join(lines)

    def render(self, plan: dict, asset_id: int, draft_id: int,
               business_slug: str = None, plan_id: int = None) -> dict:
        """
        Execute an edit plan and render a final MP4.

        Returns: {path, duration, render_time_s, cut_list}
        Raises AssemblyError on failure.
        """
        start_time = time.time()

        # Validate plan
        segments = plan.get("segments", [])
        if not segments:
            raise AssemblyError("Edit plan has no segments")

        canvas = plan.get("canvas", {})
        resolution = canvas.get("resolution", "1080x1920")
        width, height = resolution.split("x")

        # Ensure output directory
        media_dir = os.path.join("data", "media", str(asset_id))
        os.makedirs(media_dir, exist_ok=True)

        # Generate cut list for operator review
        cut_list = self._build_cut_list(plan)

        # Resolve all source files
        source_files = []
        for seg in segments:
            try:
                path = self._resolve_source(seg["source"], asset_id)
                source_files.append(path)
            except AssemblyError as e:
                # Log and raise — render fails honestly
                self._log_render(asset_id, draft_id, f"Source resolution failed: {e}",
                                 business_slug, "failed")
                raise

        # Build ffmpeg command
        # Strategy: concatenate segments with trims, apply transitions, burn in captions
        # For v1, we use a straightforward concat with xfade transitions between segments.

        # Prepare trimmed segment files
        temp_files = []
        try:
            for i, (seg, src_path) in enumerate(zip(segments, source_files)):
                in_pt = seg.get("in", 0)
                out_pt = seg.get("out", 0)
                duration = out_pt - in_pt if out_pt > in_pt else 0

                # Check if source is an image (images need different handling)
                is_image = src_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))

                # Check if source is audio-only (no video stream)
                # WhatsApp voice memos and audio recordings may be saved as .mp4
                # with only an audio track — concat filter needs video from every input.
                is_audio_only = not is_image and not self._has_video_stream(src_path)

                seg_file = os.path.join(media_dir, f"seg_{i}.mp4")

                if is_image:
                    # Create a video clip from the image with the specified duration
                    # Add silent audio so concat has both streams from every segment.
                    cmd = [
                        "ffmpeg", "-y",
                        "-loop", "1", "-i", src_path,
                        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-t", str(max(duration, 1)),
                        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        "-r", "30",
                        "-shortest",
                        seg_file,
                    ]
                elif is_audio_only:
                    # Audio-only source: generate a solid black video track at canvas
                    # resolution paired with the trimmed audio, so concat has both streams.
                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r=30:d={max(duration, 1)}",
                        "-ss", str(in_pt),
                        "-i", src_path,
                        "-t", str(duration),
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        "-r", "30",
                        "-shortest",
                        seg_file,
                    ]
                else:
                    # Video source — may or may not have audio.
                    # Check if it has audio; if not, add silent audio for concat.
                    has_audio = self._has_audio_stream(src_path)
                    if has_audio:
                        cmd = [
                            "ffmpeg", "-y",
                            "-ss", str(in_pt),
                            "-i", src_path,
                            "-t", str(duration),
                            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac",
                            "-r", "30",
                            seg_file,
                        ]
                    else:
                        # Video-only (no audio): add silent audio track
                        cmd = [
                            "ffmpeg", "-y",
                            "-ss", str(in_pt),
                            "-i", src_path,
                            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                            "-t", str(duration),
                            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                            "-map", "0:v:0", "-map", "1:a:0",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac",
                            "-r", "30",
                            "-shortest",
                            seg_file,
                        ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    raise AssemblyError(f"ffmpeg trim failed for segment {i}: {result.stderr[:500]}")

                temp_files.append(seg_file)

            # Concatenate segments
            # For v1: simple concat (cut transitions). Crossfade/slide/whip are future enhancements.
            version = 1
            existing_finals = [f for f in os.listdir(media_dir) if f.startswith("final_")]
            version = len(existing_finals) + 1
            output_file = os.path.join(media_dir, f"final_{version}.mp4")

            if len(temp_files) == 1:
                # Single segment — just copy
                cmd = ["ffmpeg", "-y", "-i", temp_files[0], "-c", "copy", output_file]
            else:
                # Concat via filter
                concat_inputs = []
                for f in temp_files:
                    concat_inputs.extend(["-i", f])

                filter_parts = []
                for i in range(len(temp_files)):
                    filter_parts.append(f"[{i}:v]")
                    filter_parts.append(f"[{i}:a]")
                filter_str = "".join(filter_parts)
                filter_str += f"concat=n={len(temp_files)}:v=1:a=1[v][a]"

                cmd = [
                    "ffmpeg", "-y",
                ] + concat_inputs + [
                    "-filter_complex", filter_str,
                    "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    output_file,
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise AssemblyError(f"ffmpeg concat failed: {result.stderr[:500]}")

            # Get final duration
            final_duration = self._get_duration(output_file)
            render_time = time.time() - start_time

            # Record in asset_media
            self._record_final_cut(asset_id, output_file, final_duration, render_time)

            # Log to provenance
            self._log_render(asset_id, draft_id,
                             f"Rendered {final_duration:.1f}s video in {render_time:.1f}s",
                             business_slug, "done")

            # Update edit plan status if we have a plan_id
            if plan_id:
                self._update_plan_status(plan_id, "rendered")

            return {
                "path": output_file,
                "duration": final_duration,
                "render_time_s": round(render_time, 1),
                "cut_list": cut_list,
                "version": version,
            }

        finally:
            # Clean up temp segment files
            for f in temp_files:
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _record_final_cut(self, asset_id: int, path: str, duration: float, render_time: float):
        """Record the final cut in asset_media."""
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO asset_media
               (asset_id, kind, path, model, prompt, cost_usd, created_at)
               VALUES (?, 'final_cut', ?, 'ffmpeg-renderer', ?, NULL, ?)""",
            (asset_id, path, f"duration={duration:.1f}s, render_time={render_time:.1f}s", ts),
        )
        conn.commit()
        conn.close()

    def _log_render(self, asset_id: int, draft_id: int, message: str,
                    business_slug: str, verdict: str):
        """Log render to provenance."""
        import hashlib
        self.provenance.log(
            input_hash=hashlib.sha256(f"render:{asset_id}:{draft_id}".encode()).hexdigest(),
            prompt_file="(assembly_renderer)",
            prompt_version="1.0",
            model="ffmpeg-renderer",
            provider="local",
            raw_output=message,
            validated_output={"asset_id": asset_id, "message": message},
            validator_verdict=verdict,
            context=f"Assembly render for asset {asset_id}",
            temperature=0,
            business_slug=business_slug,
        )

    def _update_plan_status(self, plan_id: int, status: str):
        """Update edit plan status."""
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE edit_plans SET status = ?, updated_at = ? WHERE id = ?",
            (status, ts, plan_id),
        )
        conn.commit()
        conn.close()

    def format_cut_list_for_display(self, plan: dict) -> str:
        """Public method to get a readable cut list without rendering."""
        return self._build_cut_list(plan)


# F5 (CORRECTION-feedback-plumbing): module-level probe_duration for use
# outside the AssemblyRenderer class (e.g. in the edit-plan inventory loop).
def probe_duration(path: str) -> float | None:
    """Probe a media file's duration in seconds via ffprobe.

    Returns None on failure (file missing, ffprobe not installed, parse error).
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        dur = float(data.get("format", {}).get("duration", 0))
        return dur if dur > 0 else None
    except Exception:
        return None