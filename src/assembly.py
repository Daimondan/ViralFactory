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

    def __init__(
        self,
        models_config: dict,
        db_path: str = "data/viralfactory.db",
        config_dir: str = "config",
        modules_dir: str = "modules",
        business_slug: str = "",
    ):
        self.models_config = models_config
        self.db_path = db_path
        self.config_dir = config_dir
        self.modules_dir = modules_dir
        self.business_slug = business_slug
        self._render_styles = None
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
            # Privacy guard: never resolve session_upload materials.
            # These are personal voice recordings, not content for public videos.
            if mat.get("channel") == "session_upload":
                raise AssemblyError(
                    f"Privacy guard: material {ref_id} is a session_upload "
                    f"(personal recording) and cannot be used in content."
                )
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
            # Support both numeric IDs (stock:42) and string slugs (stock:my_clip_name)
            try:
                stock_id = int(ref_id)
                row = conn.execute(
                    "SELECT local_path FROM stock_cache WHERE id = ?",
                    (stock_id,),
                ).fetchone()
            except ValueError:
                # String slug — look up by title match
                row = conn.execute(
                    "SELECT local_path FROM stock_cache WHERE title LIKE ?",
                    (f"%{ref_id}%",),
                ).fetchone()
            conn.close()
            if not row or not row["local_path"]:
                raise AssemblyError(
                    f"Stock item not found: {source_ref}. "
                    f"No stock clips are cached — the edit plan referenced stock footage "
                    f"that hasn't been downloaded. Stock footage must be cached before rendering."
                )
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
        """Get media file duration in seconds via ffprobe.

        Returns the format (container) duration, which includes the
        longest stream. For the video-stream duration specifically, use
        _get_video_duration.
        """
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

    def _get_video_duration(self, file_path: str) -> float:
        """Get the VIDEO stream duration specifically.

        The xfade filter can produce a video stream shorter than the
        audio stream (and shorter than the format/container duration).
        When deciding whether to tpad-extend the video to cover the VO,
        we must use the video stream duration, not the container duration.
        (QA-loop F-005)
        """
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", file_path],
                capture_output=True, text=True, timeout=30,
            )
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    return float(stream.get("duration", 0))
            return 0.0
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
        if business_slug and business_slug != self.business_slug:
            self.business_slug = business_slug
            self._render_styles = None

        # Validate plan
        segments = plan.get("segments", [])
        if not segments:
            raise AssemblyError("Edit plan has no segments")

        canvas = plan.get("canvas", {})
        resolution = canvas.get("resolution", "1080x1920")
        width, height = resolution.split("x")
        width_i = int(width)
        height_i = int(height)

        # Ensure output directory
        media_dir = os.path.join("data", "media", str(asset_id))
        os.makedirs(media_dir, exist_ok=True)

        # Generate cut list for operator review
        cut_list = self._build_cut_list(plan)

        # Pre-flight: resolve sources AND validate in/out against real durations
        # The edit plan uses cumulative timeline timestamps (0→2, 2→4.5…) but
        # ffmpeg -ss seeks *within the source file*. If in/out exceed the
        # source's actual duration, ffmpeg produces a file with no streams,
        # which crashes the concat filter with "matches no streams".
        source_files = []
        segment_warnings = []
        for seg in segments:
            try:
                path = self._resolve_source(seg["source"], asset_id)
                source_files.append(path)
            except AssemblyError as e:
                self._log_render(asset_id, draft_id, f"Source resolution failed: {e}",
                                 business_slug, "failed")
                raise

            # Validate in/out against the source file's actual duration
            # The edit plan v2 schema uses source_in/source_out, but legacy
            # plans used in/out. Support both.
            in_pt = seg.get("source_in", seg.get("in", 0))
            out_pt = seg.get("source_out", seg.get("out", 0))
            is_image = path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            if not is_image:
                actual_dur = self._get_duration(path)
                if actual_dur > 0 and out_pt > actual_dur:
                    segment_warnings.append(
                        f"Segment source {seg['source']} is {actual_dur:.1f}s but plan "
                        f"requests out={out_pt:.1f}s — clamping"
                    )
                    out_pt = min(out_pt, actual_dur)
                    seg["source_out"] = out_pt
                    if in_pt >= actual_dur:
                        in_pt = 0.0
                        out_pt = actual_dur
                        seg["source_in"] = 0.0
                        seg["source_out"] = actual_dur

        # Log validation warnings to provenance (non-fatal)
        for w in segment_warnings:
            self._log_render(asset_id, draft_id, f"Plan validation: {w}",
                             business_slug, "done")

        # Build ffmpeg command
        # Strategy: concatenate segments with trims, apply transitions, burn in captions
        # For v1, we use a straightforward concat with xfade transitions between segments.

        # Prepare trimmed segment files
        temp_files = []
        try:
            for i, (seg, src_path) in enumerate(zip(segments, source_files)):
                in_pt = seg.get("source_in", seg.get("in", 0))
                out_pt = seg.get("source_out", seg.get("out", 0))
                duration = out_pt - in_pt if out_pt > in_pt else 0

                # Check if source is an image (images need different handling)
                is_image = src_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))

                # Check if source is audio-only (no video stream)
                # WhatsApp voice memos and audio recordings may be saved as .mp4
                # with only an audio track — concat filter needs video from every input.
                is_audio_only = not is_image and not self._has_video_stream(src_path)

                seg_file = os.path.join(media_dir, f"seg_{i}.mp4")

                if is_image:
                    # Create a video clip from the image with Ken Burns motion.
                    # The movement field from the enriched frame schema drives
                    # the zoompan direction: slow push-in (default), static, or
                    # pull-back. zoompan needs the image pre-scaled to a larger
                    # canvas so the zoom has pixels to work with.
                    movement = seg.get("movement", "slow push-in")
                    clip_dur = max(duration, 1)
                    fps = 30
                    total_frames = int(clip_dur * fps)

                    if movement == "static":
                        # No motion — scale and pad only
                        vf = (f"scale={width_i}:{height_i}:force_original_aspect_ratio=decrease,"
                              f"pad={width_i}:{height_i}:(ow-iw)/2:(oh-ih)/2,setsar=1")
                    else:
                        # Ken Burns: pre-scale to 2x, then zoompan back to target.
                        # Use force_original_aspect_ratio=decrease + pad to ensure
                        # the 2x canvas is fully filled (zoompan needs filled frames).
                        if movement == "pull-back":
                            z_expr = "min(zoom+0.0005,1.5)"
                        else:
                            # Default: slow push-in (zoom from 1.0 to 1.15)
                            z_expr = "min(zoom+0.0003,1.15)"
                        vf = (f"scale={width_i*2}:{height_i*2}:force_original_aspect_ratio=decrease,"
                              f"pad={width_i*2}:{height_i*2}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                              f"zoompan=z='{z_expr}':d={total_frames}:"
                              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                              f"s={width_i}x{height_i}:fps={fps}")

                    cmd = [
                        "ffmpeg", "-y",
                        "-loop", "1", "-i", src_path,
                        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-t", str(clip_dur),
                        "-vf", vf,
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        "-r", str(fps),
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
                        "-vf", "setsar=1",
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
                    # F-009: If the video clip is shorter than the segment
                    # duration (e.g. 5s Kling clip for an 8s beat), extend
                    # by holding the last frame via tpad.
                    has_audio = self._has_audio_stream(src_path)
                    src_dur = self._get_duration(src_path)
                    needs_tpad = (src_dur > 0 and duration > src_dur + 0.1)
                    tpad_vf = ""
                    if needs_tpad:
                        tpad_vf = f",tpad=stop_mode=clone:stop_duration={duration - src_dur:.3f}"
                    vf_str = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1{tpad_vf}"
                    if has_audio:
                        cmd = [
                            "ffmpeg", "-y",
                            "-ss", str(in_pt),
                            "-i", src_path,
                            "-t", str(duration),
                            "-vf", vf_str,
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
                            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                            "-t", str(duration),
                            "-vf", vf_str,
                            "-map", "0:v:0", "-map", "1:a:0",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac",
                            "-r", "30",
                            "-shortest",
                            seg_file,
                        ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    # Extract only the error portion — not the full ffmpeg banner
                    stderr_lines = result.stderr.strip().split("\n")
                    error_lines = [l for l in stderr_lines if l.startswith(("Error", "[error", "Conversion"))]
                    error_msg = "\n".join(error_lines[-3:]) if error_lines else result.stderr[-500:]
                    raise AssemblyError(f"ffmpeg trim failed for segment {i}: {error_msg}")

                temp_files.append(seg_file)

            # Concatenate segments with transitions
            # Reads transition_in from each segment (cut, crossfade, slide, whip)
            # and applies xfade transitions between segments. Falls back to hard
            # cut concat for "cut" or when there are only 1-2 segments.
            version = 1
            existing_finals = [f for f in os.listdir(media_dir) if f.startswith("final_")]
            version = len(existing_finals) + 1
            output_file = os.path.join(media_dir, f"final_{version}.mp4")

            # Collect transition types (segment[0] has no transition_in — it's the first)
            transition_types = []
            for i, seg in enumerate(segments):
                if i == 0:
                    continue  # first segment has no incoming transition
                transition_types.append(seg.get("transition_in", "cut"))

            # Check if any non-cut transitions exist
            has_transitions = any(t in ("crossfade", "slide", "whip") for t in transition_types)

            if len(temp_files) == 1:
                # Single segment — just copy
                cmd = ["ffmpeg", "-y", "-i", temp_files[0], "-c", "copy", output_file]
            elif has_transitions and len(temp_files) >= 2:
                # Use xfade transitions between segments
                # xfade offset = cumulative duration minus transition duration
                xfade_dur = 0.5  # 500ms transitions
                xfade_map = {
                    "crossfade": "fade",
                    "slide": "slideleft",
                    "whip": "wipeleft",
                }

                # Get durations of each segment
                seg_durations = []
                for tf in temp_files:
                    sd = self._get_duration(tf)
                    seg_durations.append(sd)

                # Build xfade chain
                # [0:v][1:v]xfade=transition=fade:duration=0.5:offset=d0-0.5[v01]
                # [v01][2:v]xfade=transition=slideleft:duration=0.5:offset=d0+d1-1.0[v012]
                # etc.
                concat_inputs = []
                for tf in temp_files:
                    concat_inputs.extend(["-i", tf])

                filter_parts = []
                # Start with first video + audio
                prev_v_label = "0:v"
                prev_a_label = "0:a"
                cumulative_dur = seg_durations[0]

                for idx, trans_type in enumerate(transition_types):
                    seg_idx = idx + 1
                    xfade_type = xfade_map.get(trans_type, "fade")
                    # "cut" transitions are hard cuts — no overlap, no time lost.
                    # Only crossfade/slide/whip consume 0.5s of overlap.
                    # Without this guard, the old code applied a 0.5s fade to
                    # every "cut" transition, silently eating 0.5s per cut and
                    # truncating the tail of the video (QA-loop F-005).
                    # We use a near-zero duration (0.001s) for cuts to keep the
                    # xfade filter chain uniform (mixing concat and xfade in one
                    # filter_complex fails with "Invalid argument"). 5ms total
                    # over 5 cuts is negligible and far below the 2.5s loss
                    # that caused the cut-off.
                    cur_xfade_dur = xfade_dur if trans_type in xfade_map else 0.001
                    offset = max(cumulative_dur - cur_xfade_dur, 0)

                    v_out_label = f"vt{idx}" if idx < len(transition_types) - 1 else "vout"
                    a_out_label = f"at{idx}" if idx < len(transition_types) - 1 else "aout"

                    filter_parts.append(
                        f"[{prev_v_label}][{seg_idx}:v]xfade=transition={xfade_type}:"
                        f"duration={cur_xfade_dur}:offset={offset:.3f}[{v_out_label}]"
                    )
                    # Audio crossfade (acrossfade)
                    filter_parts.append(
                        f"[{prev_a_label}][{seg_idx}:a]acrossfade=d={cur_xfade_dur}[{a_out_label}]"
                    )

                    prev_v_label = v_out_label
                    prev_a_label = a_out_label
                    cumulative_dur += seg_durations[seg_idx] - cur_xfade_dur

                filter_str = ";".join(filter_parts)

                cmd = [
                    "ffmpeg", "-y",
                ] + concat_inputs + [
                    "-filter_complex", filter_str,
                    "-map", "[vout]", "-map", "[aout]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    output_file,
                ]
            else:
                # Simple concat (cut transitions only)
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
                # Extract only the error portion — not the full ffmpeg banner
                stderr_lines = result.stderr.strip().split("\n")
                error_lines = [l for l in stderr_lines if l.startswith(("Error", "[error", "Conversion"))]
                error_msg = "\n".join(error_lines[-3:]) if error_lines else result.stderr[-500:]
                raise AssemblyError(f"ffmpeg concat failed: {error_msg}")

            # Burn in text overlays (captions, text cards, highlights)
            # The edit plan's per-segment overlays have start/end relative to
            # each segment. We convert these to cumulative timeline timestamps
            # and apply all drawtext filters in a single ffmpeg pass.
            overlay_result = self._burn_overlays(plan, segments, output_file, media_dir, version,
                                                  asset_id, draft_id, business_slug)
            if overlay_result:
                output_file = overlay_result

            # Mix in SFX cues (whoosh, pop, hit, riser)
            # The edit plan's per-segment sfx array has offsets relative to each
            # segment. We convert to cumulative timeline positions and generate
            # short synthetic audio tones mixed into the output.
            sfx_result = self._mix_sfx(plan, segments, output_file, media_dir, version,
                                       asset_id, draft_id, business_slug)
            if sfx_result:
                output_file = sfx_result

            # Audio strategy: driven by the edit plan's audio block, not a heuristic.
            # The LLM decided the audio strategy in the edit plan; the renderer
            # executes it. This replaced the old post-concat audio bed that looped
            # the first video clip's ambient sound — a charter violation (judgment
            # in code). Per CORRECTION-final-output-review-and-audio-fix-v1.0 AUDIO-1.
            audio_block = plan.get("audio", {})
            audio_evidence = self._apply_audio_strategy(
                output_file, audio_block, media_dir, version,
                asset_id, draft_id, business_slug, plan,
            )

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
                "audio_evidence": audio_evidence,
            }

        finally:
            # Clean up temp segment files
            for f in temp_files:
                try:
                    os.remove(f)
                except OSError:
                    pass

    # ── Text overlay burn-in ────────────────────────────────────────────

    # Font path — config-driven via models.yaml rendering.font_path, with
    # a system fallback to DejaVuSans-Bold (always present on Debian/Ubuntu).
    _DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def _get_font_path(self) -> str:
        """Resolve body font path from config or fall back to system default."""
        try:
            render_cfg = (self.models_config or {}).get("rendering", {})
            font = render_cfg.get("font_path", "")
            if font and os.path.exists(font):
                return font
        except Exception:
            pass
        return self._DEFAULT_FONT

    def _get_display_font_path(self) -> str:
        """Resolve display font path (Anton) for hooks/titles."""
        try:
            render_cfg = (self.models_config or {}).get("rendering", {})
            font = render_cfg.get("font_display", "")
            if font and os.path.exists(font):
                return font
        except Exception:
            pass
        return self._DEFAULT_FONT

    def _resolved_render_styles(self) -> dict:
        """Load and cache merged generic and tenant renderer styles."""
        if self._render_styles is None:
            from render_style_config import load_render_styles

            self._render_styles = load_render_styles(
                config_dir=self.config_dir,
                modules_dir=self.modules_dir,
                business_slug=self.business_slug,
            )
        return self._render_styles

    def _resolve_overlay_style(self, style_ref: str) -> dict:
        """Resolve drawtext params from tenant module overrides and config."""
        styles = self._resolved_render_styles()["overlay_styles"]
        return styles.get(style_ref) or styles["default"]

    def _overlay_position_y(self, position: str, height: int) -> int:
        """Map a position name to a pixel y-coordinate for PIL rendering.

        Safe zones: Instagram/TikTok UI covers the bottom ~250px and top ~100px.
        We keep text within the safe zone to avoid being hidden by platform UI.
        """
        if position == "top":
            return 120  # below top safe zone
        if position == "bottom":
            return height - 450  # above bottom safe zone (room for multi-line captions)
        if position == "bottom-third":
            return int(height * 0.65)  # was 0.72, moved up for safety
        # center
        return (height - 100) // 2

    def _render_pil_overlay(
        self, text: str, style: dict, position: str,
        width: int, height: int, font_path: str,
    ) -> str | None:
        """Render a single text overlay as a transparent PNG using PIL.

        Produces a TikTok/Reels-style overlay: auto-wrapped text on a rounded
        semi-transparent pill background with shadow, using modern fonts.
        """
        from PIL import Image, ImageDraw, ImageFont, ImageFilter

        # Parse font color — handle hex colors
        fontcolor = style.get("fontcolor", "white")
        if fontcolor.startswith("#"):
            # Hex color — convert to RGBA
            hex_val = fontcolor[1:]
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            text_color = (r, g, b, 255)
        else:
            text_color = (255, 255, 255, 255)

        font_size = int(style.get("fontsize", 48))
        try:
            font = ImageFont.truetype(font_path, font_size)
        except (IOError, OSError):
            font = ImageFont.truetype(self._DEFAULT_FONT, font_size)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Auto-wrap text to fit within margins
        max_text_width = width - 120  # 60px margin each side
        lines = []
        for raw_line in text.split("\n"):
            words = raw_line.split()
            current = []
            for word in words:
                test = " ".join(current + [word])
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] <= max_text_width or not current:
                    current.append(word)
                else:
                    lines.append(" ".join(current))
                    current = [word]
            if current:
                lines.append(" ".join(current))

        if not lines:
            return None

        line_height = font_size + 14
        total_height = len(lines) * line_height

        # Find max line width for pill background
        max_w = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            max_w = max(max_w, bbox[2] - bbox[0])

        # Y position
        y_start = self._overlay_position_y(position, height)

        # Pill background parameters
        padding_x = 30
        padding_y = 18
        pill_x0 = (width - max_w) // 2 - padding_x
        pill_y0 = y_start - padding_y
        pill_x1 = (width + max_w) // 2 + padding_x
        pill_y1 = y_start + total_height + padding_y - 14

        # Draw shadow first (offset + blur)
        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            [pill_x0 + 4, pill_y0 + 4, pill_x1 + 4, pill_y1 + 4],
            radius=16, fill=(0, 0, 0, 80),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        overlay = Image.alpha_composite(overlay, shadow)
        draw = ImageDraw.Draw(overlay)

        # Draw pill background — semi-transparent dark for light text,
        # semi-transparent light for dark text
        is_dark_text = sum(text_color[:3]) < 384
        pill_fill = (255, 255, 255, 180) if is_dark_text else (0, 0, 0, 160)
        draw.rounded_rectangle(
            [pill_x0, pill_y0, pill_x1, pill_y1],
            radius=16, fill=pill_fill,
        )

        # Draw text lines — centered horizontally with shadow for readability
        borderw = int(style.get("borderw", 0))
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (width - line_w) // 2
            y = y_start + i * line_height
            # Shadow stroke for contrast
            if borderw > 0:
                bordercolor = style.get("bordercolor", "black")
                if bordercolor.startswith("#"):
                    bc = bordercolor[1:]
                    br, bg, bb = int(bc[0:2], 16), int(bc[2:4], 16), int(bc[4:6], 16)
                else:
                    br, bg, bb = 0, 0, 0
                for dx, dy in [(-borderw, 0), (borderw, 0), (0, -borderw), (0, borderw),
                               (-borderw, -borderw), (borderw, -borderw),
                               (-borderw, borderw), (borderw, borderw)]:
                    draw.text((x + dx, y + dy), line, font=font, fill=(br, bg, bb, 255))
            # Main text
            draw.text((x, y), line, font=font, fill=text_color)

        return overlay

    def _burn_overlays(self, plan: dict, segments: list, output_file: str,
                       media_dir: str, version: int,
                       asset_id: int, draft_id: int,
                       business_slug: str) -> Optional[str]:
        """Burn in text overlays using PIL-rendered PNGs composited via ffmpeg.

        Overlays have start/end times relative to their segment. We compute
        cumulative timeline positions by summing preceding segment durations,
        render each overlay as a transparent PNG with PIL (auto-wrapped text,
        rounded pill background, modern fonts), then composite them onto the
        video with timed ffmpeg overlay filters in a single pass.

        Returns the path to the overlay-burned file, or None if no overlays
        were found (the original output_file is used as-is).
        """
        # Collect all overlays with cumulative timeline positions
        cumulative = 0.0
        all_overlays = []
        for seg in segments:
            seg_in = seg.get("source_in", seg.get("in", 0))
            seg_out = seg.get("source_out", seg.get("out", 0))
            seg_duration = seg_out - seg_in if seg_out > seg_in else 0
            for ov in seg.get("overlays", []):
                if not ov.get("text"):
                    continue
                # start/end are relative to the segment's start in the timeline
                ov_start = cumulative + ov.get("start", 0)
                ov_end = cumulative + ov.get("end", seg_duration)
                all_overlays.append({
                    "text": ov["text"],
                    "start": ov_start,
                    "end": ov_end,
                    "style_ref": ov.get("style_ref", "default"),
                    "position": ov.get("position", "center"),
                })
            cumulative += seg_duration

        if not all_overlays:
            return None

        # Also check for global captions block
        captions = plan.get("captions", {})
        if captions.get("burned_in") and captions.get("source") == "vo_script":
            pass

        canvas = plan.get("canvas", {})
        resolution = canvas.get("resolution", "1080x1920")
        width_s, height_s = resolution.split("x")
        width, height = int(width_s), int(height_s)

        body_font = self._get_font_path()
        display_font = self._get_display_font_path()

        # Render each overlay as a PNG
        overlay_inputs = []
        filter_parts = []
        for i, ov in enumerate(all_overlays):
            style = self._resolve_overlay_style(ov["style_ref"])
            # Use display font for hooks and titles, body font for everything else
            style_name = ov["style_ref"]
            font_path = display_font if style_name in ("hook", "title") else body_font
            png_path = os.path.join(media_dir, f"overlay_{version}_{i}.png")
            pil_img = self._render_pil_overlay(
                ov["text"], style, ov["position"],
                width, height, font_path,
            )
            if pil_img is None:
                continue
            pil_img.save(png_path)
            overlay_inputs.append(png_path)
            # Build ffmpeg overlay filter for this PNG
            # [prev][N+1:v]overlay=0:0:enable='between(t,start,end)'[next]
            input_idx = i + 1  # input 0 is the video
            if i == 0:
                prev_label = "0:v"
            else:
                prev_label = f"v{i - 1}"
            if i == len(all_overlays) - 1:
                next_label = "vout"
            else:
                next_label = f"v{i}"
            filter_parts.append(
                f"[{prev_label}][{input_idx}:v]overlay=0:0:"
                f"enable='between(t,{ov['start']:.2f},{ov['end']:.2f})'[{next_label}]"
            )

        if not filter_parts:
            return None

        # Build ffmpeg command with all overlay PNGs as inputs
        overlay_file = os.path.join(media_dir, f"final_{version}_overlay.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", output_file,
        ]
        for png in overlay_inputs:
            cmd.extend(["-i", png])
        cmd.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", "[vout]", "-map", "0:a:0?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            overlay_file,
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        # Clean up PNGs
        for png in overlay_inputs:
            if os.path.exists(png):
                os.remove(png)

        if result.returncode == 0 and os.path.exists(overlay_file):
            os.replace(overlay_file, output_file)
            self._log_render(asset_id, draft_id,
                             f"Burned {len(all_overlays)} PIL text overlays",
                             business_slug, "done")
            return output_file
        else:
            stderr_lines = result.stderr.strip().split("\n")
            error_lines = [l for l in stderr_lines if l.startswith(("Error", "[error"))]
            error_msg = "\n".join(error_lines[-3:]) if error_lines else result.stderr[-300:]
            self._log_render(asset_id, draft_id,
                             f"Overlay burn failed (non-fatal, continuing): {error_msg}",
                             business_slug, "failed")
            if os.path.exists(overlay_file):
                os.remove(overlay_file)
            return None

    # ── SFX mixing ──────────────────────────────────────────────────────

    def _resolve_sfx_preset(self, sfx_type: str) -> dict:
        """Resolve deterministic SFX synthesis parameters from config/modules."""
        render_styles = self._resolved_render_styles()
        presets = render_styles.get("sfx_presets") or {}
        default_name = render_styles.get("sfx_default_preset")
        if not default_name or default_name not in presets:
            raise AssemblyError("A configured default SFX preset is required")
        return presets.get(sfx_type) or presets[default_name]

    def _mix_sfx(self, plan: dict, segments: list, output_file: str,
                 media_dir: str, version: int,
                 asset_id: int, draft_id: int,
                 business_slug: str) -> Optional[str]:
        """Mix SFX cues into the output video's audio track.

        Generates short synthetic audio tones for each SFX cue and mixes
        them into the existing audio at the correct cumulative timeline
        positions. If the output has no audio track, SFX are mixed against
        silence.

        Returns the path to the mixed file (in-place), or None if no SFX
        cues were found.
        """
        # Collect all SFX with cumulative timeline positions
        cumulative = 0.0
        all_sfx = []
        for seg in segments:
            seg_in = seg.get("in", 0)
            seg_out = seg.get("out", 0)
            seg_duration = seg_out - seg_in if seg_out > seg_in else 0
            for sfx in seg.get("sfx", []):
                sfx_t = cumulative + sfx.get("t", 0)
                all_sfx.append({
                    "t": sfx_t,
                    "type": sfx.get("type", ""),
                })
            cumulative += seg_duration

        if not all_sfx:
            return None

        # Build ffmpeg command with one sine input per SFX, delayed and mixed
        # Strategy: generate each SFX as a short sine tone, delay it to its
        # timeline position, then amix all into the existing audio.
        duration = self._get_duration(output_file)

        # Build inputs: [0] = original video, [1+] = SFX tones
        inputs = ["-i", output_file]
        filter_parts = []
        sfx_labels = []

        for i, sfx in enumerate(all_sfx):
            preset = self._resolve_sfx_preset(sfx["type"])
            sfx_idx = i + 1
            # Generate a short sine tone at the SFX frequency
            inputs.extend([
                "-f", "lavfi", "-i",
                f"sine=frequency={preset['freq']}:duration={preset['duration']}",
            ])
            # Delay the SFX to its timeline position, set volume
            delay_s = sfx["t"]
            # adelay takes milliseconds
            delay_ms = int(delay_s * 1000)
            label = f"sfx{i}"
            filter_parts.append(
                f"[{sfx_idx}:a]volume={preset['volume']},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            sfx_labels.append(f"[{label}]")

        # Mix SFX into existing audio (or silence if no audio track)
        has_audio = self._has_audio_stream(output_file)
        # Episode-format plans carry an enforced loudnorm target (I=-14)
        ln = (plan or {}).get("loudnorm_target") or {}
        ln_I = ln.get("I", -16.0)
        ln_TP = ln.get("TP", -1.5)
        ln_LRA = ln.get("LRA", 11.0)
        if has_audio:
            filter_parts.append(f"[0:a]loudnorm=I={ln_I}:TP={ln_TP}:LRA={ln_LRA}[base]")
            mix_inputs = "[base]" + "".join(sfx_labels)
            n_inputs = len(sfx_labels) + 1
            filter_parts.append(
                f"{mix_inputs}amix=inputs={n_inputs}:duration=first:dropout_transition=0[aout]"
            )
        else:
            # No existing audio — mix SFX against silence
            mix_inputs = "".join(sfx_labels)
            n_inputs = len(sfx_labels)
            filter_parts.append(
                f"{mix_inputs}amix=inputs={n_inputs}:duration=longest:dropout_transition=0[aout]"
            )

        filter_str = ";".join(filter_parts)

        sfx_file = os.path.join(media_dir, f"final_{version}_sfx.mp4")
        cmd = [
            "ffmpeg", "-y",
        ] + inputs + [
            "-filter_complex", filter_str,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac",
            "-t", str(max(duration, 1)),
            sfx_file,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(sfx_file):
            os.replace(sfx_file, output_file)
            self._log_render(asset_id, draft_id,
                             f"Mixed {len(all_sfx)} SFX cues",
                             business_slug, "done")
            return output_file
        else:
            stderr_lines = result.stderr.strip().split("\n")
            error_lines = [l for l in stderr_lines if l.startswith(("Error", "[error"))]
            error_msg = "\n".join(error_lines[-3:]) if error_lines else result.stderr[-300:]
            self._log_render(asset_id, draft_id,
                             f"SFX mix failed (non-fatal, continuing): {error_msg}",
                             business_slug, "failed")
            if os.path.exists(sfx_file):
                os.remove(sfx_file)
            return None

    # ── Audio strategy (AUDIO-1) ───────────────────────────────────────
    # The edit plan's audio block drives all audio decisions. The renderer
    # executes the LLM's strategy — it does not invent audio.

    def _resolve_audio_strategy(self, audio_block: dict,
                                asset_id: int = None) -> str:
        """Determine the audio strategy from the edit plan's audio block.

        Returns one of: "silent", "original", "music", "vo".
        The exact persisted VO path is authoritative. Only legacy plans without
        a path fall back to take-id resolution.
        """
        original_audio = audio_block.get("original_audio", False)
        music = audio_block.get("music", {})
        vo = audio_block.get("vo", {})
        music_ref = music.get("stock_ref") if music else None
        vo_take_id = vo.get("take_id") if vo else None
        exact_vo_path = vo.get("path") if vo else None

        if exact_vo_path:
            return "vo"
        if vo_take_id:
            vo_path = self._resolve_plan_vo_path(vo, asset_id)
            if vo_path and os.path.exists(vo_path):
                return "vo"
            # No VO file — degrade gracefully
            if music_ref:
                return "music"
            elif original_audio:
                return "original"
            else:
                return "silent"
        elif music_ref:
            return "music"
        elif original_audio:
            return "original"
        else:
            return "silent"

    def _apply_audio_strategy(self, output_file: str, audio_block: dict,
                              media_dir: str, version: int,
                              asset_id: int, draft_id: int,
                              business_slug: str, plan: dict = None):
        """Apply the edit plan's audio strategy to the rendered output.

        Per CORRECTION-final-output-review-and-audio-fix-v1.0 AUDIO-1:
        - original_audio == false, no music → silent video (add silent AAC track)
        - original_audio == true, no music  → keep concat audio as-is (each segment's source audio)
        - music stock_ref present           → mix music at specified volume
        - vo take_id present                → duck clip/music under VO (deferred: if no VO file, proceed as empty)

        Episode-format plans carry a loudnorm_target in the plan dict —
        enforced I=-14 for this format (§3.3 + §6), not the default I=-16.
        """
        # Episode-format loudnorm target (enforced I=-14) or default (-16)
        ln = (plan or {}).get("loudnorm_target") or {}
        loudnorm_I = ln.get("I", -16.0)
        loudnorm_TP = ln.get("TP", -1.5)
        loudnorm_LRA = ln.get("LRA", 11.0)
        original_audio = audio_block.get("original_audio", False)
        music = audio_block.get("music", {})
        vo = audio_block.get("vo", {})
        music_ref = music.get("stock_ref") if music else None

        strategy = self._resolve_audio_strategy(audio_block, asset_id)

        self._log_render(
            asset_id, draft_id,
            f"audio strategy: {strategy}, source: {json.dumps(audio_block)}",
            business_slug, "done",
        )

        evidence = {
            "strategy": strategy,
            "applied": False,
            "source_ids": [],
            "audible_windows": {},
        }

        if strategy == "silent":
            self._apply_silent_audio(output_file, media_dir, version)
        elif strategy == "original":
            # Concat already preserved each segment's source audio.
            # Just loudnorm for consistent levels.
            self._apply_loudnorm(output_file, media_dir, version,
                                 loudnorm_I, loudnorm_TP, loudnorm_LRA)
        elif strategy == "music":
            music_volume = music.get("volume", 0.3) if music else 0.3
            music_path = self._resolve_music_path(music_ref)
            if music_path and os.path.exists(music_path):
                if original_audio:
                    self._mix_music_with_original(
                        output_file, music_path, music_volume, media_dir, version,
                        loudnorm_I, loudnorm_TP, loudnorm_LRA)
                else:
                    self._apply_music_only(
                        output_file, music_path, music_volume, media_dir, version,
                        loudnorm_I, loudnorm_TP, loudnorm_LRA)
            else:
                # Music ref unresolved — fall back to loudnorm or silent
                if original_audio:
                    self._apply_loudnorm(output_file, media_dir, version,
                                         loudnorm_I, loudnorm_TP, loudnorm_LRA)
                else:
                    self._apply_silent_audio(output_file, media_dir, version)
        elif strategy == "vo":
            # VO is primary audio; duck everything under it.
            # Music + original audio become secondary layers.
            vo_path = self._resolve_plan_vo_path(vo, asset_id)
            music_volume = music.get("volume", 0.15) if music else 0.15
            music_path = None
            if music_ref:
                music_path = self._resolve_music_path(music_ref)
            applied = self._mix_vo(
                output_file, vo_path, music_path, music_volume,
                original_audio, media_dir, version,
                loudnorm_I, loudnorm_TP, loudnorm_LRA)

            evidence["applied"] = applied
            if applied:
                evidence["vo_source_id"] = vo.get("take_id") or vo_path
                if music_ref and music_path:
                    evidence["source_ids"].append(music_ref)

        return evidence

    def _resolve_plan_vo_path(self, vo: dict, asset_id: int) -> Optional[str]:
        """Resolve exact measured VO path, with take-id fallback for legacy plans."""
        exact_path = vo.get("path") if vo else None
        if exact_path:
            return exact_path
        take_id = vo.get("take_id") if vo else None
        if take_id and asset_id:
            return self._resolve_vo_path(take_id, asset_id)
        return None

    def _resolve_vo_path(self, take_id: str, asset_id: int) -> Optional[str]:
        """Resolve a VO take_id to a file path.

        VO files are stored in data/media/<asset_id>/vo_<take_id>.wav
        (or .mp3). The VO pipeline is deferred — if the file doesn't
        exist, return None so the caller degrades gracefully.
        """
        media_dir = os.path.join("data", "media", str(asset_id))
        for ext in [".wav", ".mp3", ".m4a"]:
            candidate = os.path.join(media_dir, f"vo_{take_id}{ext}")
            if os.path.exists(candidate):
                return candidate
        return None

    def _resolve_music_path(self, stock_ref: str) -> Optional[str]:
        """Resolve a music stock_ref (stock:<id>) to a file path."""
        if not stock_ref or ":" not in stock_ref:
            return None
        kind, ref_id = stock_ref.split(":", 1)
        if kind != "stock":
            return None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                stock_id = int(ref_id)
                row = conn.execute(
                    "SELECT local_path FROM stock_cache WHERE id = ?",
                    (stock_id,),
                ).fetchone()
            except ValueError:
                row = conn.execute(
                    "SELECT local_path FROM stock_cache WHERE title LIKE ?",
                    (f"%{ref_id}%",),
                ).fetchone()
            conn.close()
            if row and row["local_path"]:
                path = row["local_path"]
                if os.path.exists(path):
                    return path
        except Exception:
            pass
        return None

    def _apply_silent_audio(self, output_file: str, media_dir: str, version: int):
        """Replace the output's audio with a silent AAC track for player compatibility.

        When the plan says original_audio=false, we strip any audio from the
        concat (e.g. from a video clip that has ambient sound) and replace it
        with silence. This ensures no looping or unexpected audio leaks through.
        """
        normalized = os.path.join(media_dir, f"final_{version}_silence.mp4")
        duration = self._get_duration(output_file)
        cmd = [
            "ffmpeg", "-y",
            "-i", output_file,
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(max(duration, 1)),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            normalized,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(normalized):
            os.replace(normalized, output_file)
        elif os.path.exists(normalized):
            os.remove(normalized)

    def _apply_loudnorm(self, output_file: str, media_dir: str, version: int,
                        loudnorm_I: float = -16.0, loudnorm_TP: float = -1.5,
                        loudnorm_LRA: float = 11.0):
        """Apply loudnorm normalization to the output's audio track.

        Episode-format plans pass loudnorm_I=-14 (enforced per §3.3 + §6).
        Default remains -16 for non-episode formats.
        """
        if not self._has_audio_stream(output_file):
            return
        normalized = os.path.join(media_dir, f"final_{version}_norm.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", output_file,
            "-af", f"loudnorm=I={loudnorm_I}:TP={loudnorm_TP}:LRA={loudnorm_LRA}",
            "-c:v", "copy", "-c:a", "aac",
            normalized,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(normalized):
            os.replace(normalized, output_file)
        elif os.path.exists(normalized):
            os.remove(normalized)

    def _apply_music_only(self, output_file: str, music_path: str,
                          volume: float, media_dir: str, version: int,
                          loudnorm_I: float = -16.0, loudnorm_TP: float = -1.5,
                          loudnorm_LRA: float = 11.0):
        """Replace audio with music track, trimmed/looped to output duration."""
        duration = self._get_duration(output_file)
        normalized = os.path.join(media_dir, f"final_{version}_music.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", output_file,
            "-i", music_path,
            "-filter_complex",
            f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{duration},"
            f"volume={volume},loudnorm=I={loudnorm_I}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[music]",
            "-map", "0:v:0", "-map", "[music]",
            "-c:v", "copy", "-c:a", "aac",
            "-t", str(max(duration, 1)),
            normalized,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(normalized):
            os.replace(normalized, output_file)
        elif os.path.exists(normalized):
            os.remove(normalized)

    def _mix_music_with_original(self, output_file: str, music_path: str,
                                 volume: float, media_dir: str, version: int,
                                 loudnorm_I: float = -16.0, loudnorm_TP: float = -1.5,
                                 loudnorm_LRA: float = 11.0):
        """Mix original clip audio with music bed at specified volume."""
        duration = self._get_duration(output_file)
        normalized = os.path.join(media_dir, f"final_{version}_mix.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", output_file,
            "-i", music_path,
            "-filter_complex",
            f"[0:a]loudnorm=I={loudnorm_I}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[main];"
            f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{duration},"
            f"volume={volume},loudnorm=I={loudnorm_I - 4}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[bed];"
            f"[main][bed]amix=inputs=2:duration=first:dropout_transition=0[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac",
            normalized,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(normalized):
            os.replace(normalized, output_file)
        elif os.path.exists(normalized):
            os.remove(normalized)

    def _mix_vo(self, output_file: str, vo_path: str,
                music_path: Optional[str], music_volume: float,
                original_audio: bool, media_dir: str, version: int,
                loudnorm_I: float = -16.0, loudnorm_TP: float = -1.5,
                loudnorm_LRA: float = 11.0):
        """Mix VO as primary audio, ducking clip/music under it.

        The VO is the master timeline — the output must be at least as
        long as the VO. If the concatenated video is shorter than the VO
        (e.g. due to transition overlap), the video is extended (last
        frame held) to cover the full VO. Trimming the VO to the video
        duration silently discards the tail — QA-loop F-005.
        """
        video_duration = self._get_video_duration(output_file)
        vo_duration = self._get_duration(vo_path) if vo_path and os.path.exists(vo_path) else 0.0
        # Master timeline: output must cover the full VO.
        target_duration = max(video_duration, vo_duration) if vo_duration > 0 else video_duration
        normalized = os.path.join(media_dir, f"final_{version}_vo.mp4")

        # If the video is shorter than the VO, extend the video (tpad) so
        # the VO is not trimmed. We extend the last frame to fill the gap.
        video_input = output_file
        extend_needed = (vo_duration > 0 and target_duration > video_duration + 0.05)
        if extend_needed:
            extended = os.path.join(media_dir, f"final_{version}_ext.mp4")
            cmd_ext = [
                "ffmpeg", "-y", "-i", output_file,
                "-vf", f"tpad=stop_mode=clone:stop_duration={target_duration - video_duration:.3f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-an", extended,
            ]
            r = subprocess.run(cmd_ext, capture_output=True, text=True, timeout=300)
            if r.returncode == 0 and os.path.exists(extended):
                video_input = extended
            elif os.path.exists(extended):
                os.remove(extended)

        inputs = ["-i", video_input, "-i", vo_path]
        # Only process [0:a] (concat audio) if we'll actually use it
        # — i.e., when original_audio is true (we mix clip audio under VO)
        if original_audio:
            filter_parts = [f"[0:a]loudnorm=I={loudnorm_I}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[main]"]
        else:
            filter_parts = []

        if music_path and os.path.exists(music_path):
            inputs.extend(["-i", music_path])
            music_idx = 2
            filter_parts.append(
                f"[{music_idx}:a]aloop=loop=-1:size=2e9,atrim=0:{target_duration},"
                f"volume={music_volume},loudnorm=I={loudnorm_I - 8}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[bed]"
            )
            if original_audio:
                filter_parts.append(
                    f"[1:a]loudnorm=I={loudnorm_I}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[vo]")
                filter_parts.append(
                    "[main][bed]amix=inputs=2:duration=first:dropout_transition=0[ducked]")
                filter_parts.append(
                    "[ducked][vo]amix=inputs=2:duration=first:dropout_transition=0,"
                    "volume=1.5[aout]")
            else:
                filter_parts.append(
                    f"[1:a]loudnorm=I={loudnorm_I}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[vo]")
                filter_parts.append(
                    "[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,"
                    "volume=1.5[aout]")
        else:
            # VO only (no music, no original audio)
            if original_audio:
                filter_parts.append(
                    f"[1:a]loudnorm=I={loudnorm_I}:TP={loudnorm_TP}:LRA={loudnorm_LRA}[vo]")
                filter_parts.append(
                    "[main][vo]amix=inputs=2:duration=first:dropout_transition=0,"
                    "volume=1.5[aout]")
            else:
                # VO replaces audio entirely. The VO is the master timeline —
                # do NOT trim it to the (possibly shorter) video duration.
                # Just normalize and map the full VO. The video was extended
                # above to cover the full VO. (QA-loop F-005)
                # Use TP=-2.0 for VO-only to ensure true peak stays below -1.0
                # (single-pass loudnorm can overshoot by ~1.5 dB)
                filter_parts.append(
                    f"[1:a]loudnorm=I={loudnorm_I}:TP=-2.0:LRA={loudnorm_LRA},"
                    f"alimiter=limit=0.79[aout]")

        filter_str = ";".join(filter_parts)
        cmd = [
            "ffmpeg", "-y",
        ] + inputs + [
            "-filter_complex", filter_str,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac",
            "-t", str(max(target_duration, 1)),
            normalized,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(normalized):
            os.replace(normalized, output_file)
            return True
        elif os.path.exists(normalized):
            os.remove(normalized)
        return False

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