"""
Quick structure draft: 'AI THINKS FIRST' 34s IG Reel.
Kinetic-typography, ffmpeg drawtext. Silent placeholder audio as master timeline.
Swap placeholder -> Chatterbox cloned VO next, re-render same timeline.

One-off artifact. Output: data/media/ai_thinking_quick_draft/
No tracked repo files touched.
"""
import os
import subprocess

os.chdir("/home/daimon/ViralFactory")
OUT = "data/media/ai_thinking_quick_draft"
os.makedirs(OUT, exist_ok=True)

W, H = 1080, 1920
FPS = 30
DUR = 34.0

# Fonts confirmed present
F_HEAD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_MONO = "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"

# Colors (charter style bible)
BG = "0x0B0E14"
WHITE = "white"
RED = "0xE54B2C"
BLUE = "0x2E7DFF"
GREEN = "0x3DDC84"

# ---------------------------------------------------------------------------
# 1) Silent placeholder audio = master timeline
# ---------------------------------------------------------------------------
silence = f"{OUT}/placeholder_silence.wav"
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
    "-t", str(DUR), "-acodec", "pcm_s16le", silence
], check=True, capture_output=True)


def esc(t):
    """Escape text for ffmpeg drawtext."""
    return (t.replace("\\", "\\\\").replace(":", "\\:")
             .replace("'", "\u2019").replace("%", "\\%")
             .replace("=", "\\=").replace(",", "\\,"))


def dt(text, font, size, color, y, t0, t1, x="(w-text_w)/2",
       box=0, boxcolor="black@0.0", borderw=6, bordercolor="black"):
    """Build one drawtext expr with fade in/out enable window."""
    en = f"between(t\\,{t0}\\,{t1})"
    parts = [
        f"fontfile={font}",
        f"text='{esc(text)}'",
        f"fontsize={size}",
        f"fontcolor={color}",
        f"x={x}",
        f"y={y}",
        f"borderw={borderw}",
        f"bordercolor={bordercolor}",
        f"enable='{en}'",
    ]
    if box:
        parts += [f"box=1", f"boxcolor={boxcolor}", "boxborderw=30"]
    return "drawtext=" + ":".join(parts)


# ---------------------------------------------------------------------------
# 2) Scene text layers (beat-aligned, 128 BPM ~0.47s grid)
# ---------------------------------------------------------------------------
layers = []

# progress bar top edge, fills L->R over full duration
layers.append(
    f"drawbox=x=0:y=0:w='iw*t/{DUR}':h=12:color={BLUE}@0.9:t=fill:enable='between(t,0,{DUR})'"
)

# 0-2  HOOK
layers.append(dt("STOP", F_HEAD, 150, WHITE, "H/2-320", 0.0, 2.0,
                 box=1, boxcolor=f"{RED}@0.9"))
layers.append(dt("THINKING FROM", F_HEAD, 92, WHITE, "H/2-120", 0.0, 2.0))
layers.append(dt("SCRATCH", F_HEAD, 130, WHITE, "H/2+40", 0.0, 2.0))

# 2-5  PROBLEM escalation
layers.append(dt("100 tabs.", F_HEAD, 90, WHITE, "H/2-220", 2.0, 5.0))
layers.append(dt("12 tasks.", F_HEAD, 90, WHITE, "H/2-40", 2.8, 5.0))
layers.append(dt("0 clarity.", F_HEAD, 100, RED, "H/2+150", 3.6, 5.0))

# 5-8  REFRAME (open loop)
layers.append(dt("NEW RULE", F_HEAD, 80, WHITE, "H/2-160", 5.0, 8.0))
layers.append(dt("AI THINKS FIRST", F_HEAD, 104, BLUE, "H/2", 5.4, 8.0))

# 8-12  TRANSFORMATION / drop
layers.append(dt("AI = REPLACEMENT", F_HEAD, 78, RED, "H/2-120", 8.0, 10.0))
layers.append(dt("AI = MENTAL LEVERAGE", F_HEAD, 78, GREEN, "H/2+60", 10.0, 12.0))

# 12-18  DEMONSTRATION arrow chain
layers.append(dt("FOG", F_HEAD, 90, WHITE, "H/2-320", 12.0, 18.0))
layers.append(dt("v", F_HEAD, 70, BLUE, "H/2-210", 13.0, 18.0))
layers.append(dt("OPTIONS", F_HEAD, 90, WHITE, "H/2-120", 13.5, 18.0))
layers.append(dt("v", F_HEAD, 70, BLUE, "H/2-10", 14.5, 18.0))
layers.append(dt("PLAN", F_HEAD, 90, WHITE, "H/2+80", 15.0, 18.0))
layers.append(dt("v", F_HEAD, 70, BLUE, "H/2+190", 16.0, 18.0))
layers.append(dt("ACTION", F_HEAD, 100, GREEN, "H/2+300", 16.5, 18.0))

# 18-23  TENSION / pattern interrupt
layers.append(dt("THE BLANK PAGE", F_HEAD, 92, WHITE, "H/2-100", 18.0, 23.0))
layers.append(dt("IS THE ENEMY", F_HEAD, 100, RED, "H/2+70", 18.6, 23.0))

# 23-29  PAYOFF prompt block (mono)
layers.append(dt("COPY THIS PROMPT", F_HEAD, 70, GREEN, "H/2-420", 23.0, 29.0))
layers.append(dt("Act as my strategist.", F_MONO, 52, WHITE, "H/2-200", 23.4, 29.0, x="140"))
layers.append(dt("Ask what matters.", F_MONO, 52, WHITE, "H/2-100", 23.9, 29.0, x="140"))
layers.append(dt("Give me 3 options.", F_MONO, 52, WHITE, "H/2", 24.4, 29.0, x="140"))
layers.append(dt("Recommend the next step.", F_MONO, 52, GREEN, "H/2+100", 24.9, 29.0, x="140"))

# 29-34  CTA + loop
layers.append(dt("YOU DECIDE.", F_HEAD, 96, WHITE, "H/2-200", 29.0, 31.5))
layers.append(dt("AI ORGANIZES.", F_HEAD, 96, BLUE, "H/2-60", 29.4, 31.5))
layers.append(dt("Save this before", F_HEAD, 72, WHITE, "H/2-40", 31.5, 34.0))
layers.append(dt("your next blank page.", F_HEAD, 72, GREEN, "H/2+70", 31.9, 34.0))

vf = ",".join(layers)

# ---------------------------------------------------------------------------
# 3) Synthetic music bed placeholder (pulsing sine, ducked low)
# ---------------------------------------------------------------------------
draft = f"{OUT}/ai_thinks_first_DRAFT.mp4"
cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:r={FPS}:d={DUR}",
    "-f", "lavfi", "-i",
    f"sine=frequency=110:sample_rate=44100:duration={DUR},"
    f"tremolo=f=4.27:d=0.7,volume=0.06",
    "-vf", vf,
    "-map", "0:v", "-map", "1:a",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
    "-c:a", "aac", "-b:a", "128k",
    "-r", str(FPS), "-t", str(DUR),
    "-movflags", "+faststart",
    draft,
]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    print("FFMPEG FAILED")
    print(r.stderr[-3000:])
    raise SystemExit(1)

# verify
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries",
     "stream=codec_type,width,height:format=duration,size",
     "-of", "default=nw=1", draft],
    capture_output=True, text=True)
print("RENDERED:", os.path.abspath(draft))
print(probe.stdout)
