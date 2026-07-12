"""
Quick TTS draft v2: 'AI THINKS FIRST' IG Reel.
Per-section flite VO -> real durations -> text timed to actual speech.
Placeholder robot voice (flite slt) for STRUCTURE ONLY. Swap Chatterbox next.
Output: data/media/ai_thinking_quick_draft/ai_thinks_first_QUICK_TTS.mp4
"""
import os
import subprocess

os.chdir("/home/daimon/ViralFactory")
OUT = "data/media/ai_thinking_quick_draft"
os.makedirs(OUT, exist_ok=True)

W, H, FPS = 1080, 1920, 30
F_HEAD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_MONO = "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"
BG = "0x0B0E14"
WHITE, RED, BLUE, GREEN = "white", "0xE54B2C", "0x2E7DFF", "0x3DDC84"

# --- Sections: (id, VO line, [text cards]) -------------------------------
# Each card: (text, font, size, color, y_expr)
sections = [
    ("hook", "Your brain was never meant to start from zero.", [
        ("STOP", F_HEAD, 150, WHITE, "H/2-320"),
        ("THINKING FROM", F_HEAD, 92, WHITE, "H/2-120"),
        ("SCRATCH", F_HEAD, 130, RED, "H/2+40"),
    ]),
    ("problem", "Every day you make a hundred tiny decisions before the real work even starts.", [
        ("100 tabs.", F_HEAD, 90, WHITE, "H/2-220"),
        ("12 tasks.", F_HEAD, 90, WHITE, "H/2-40"),
        ("0 clarity.", F_HEAD, 100, RED, "H/2+150"),
    ]),
    ("reframe", "That is where AI changes everything.", [
        ("NEW RULE", F_HEAD, 80, WHITE, "H/2-160"),
        ("AI THINKS FIRST", F_HEAD, 104, BLUE, "H/2"),
    ]),
    ("transform", "Not because it replaces your brain. Because it gives you mental leverage.", [
        ("NOT replacement", F_HEAD, 84, RED, "H/2-120"),
        ("Mental LEVERAGE", F_HEAD, 88, GREEN, "H/2+60"),
    ]),
    ("demo", "It turns fog into options, a plan, and your next move.", [
        ("FOG", F_HEAD, 80, WHITE, "H/2-300"),
        ("OPTIONS", F_HEAD, 80, WHITE, "H/2-120"),
        ("PLAN", F_HEAD, 80, WHITE, "H/2+60"),
        ("ACTION", F_HEAD, 96, GREEN, "H/2+240"),
    ]),
    ("tension", "Because the blank page is the enemy.", [
        ("THE BLANK PAGE", F_HEAD, 92, WHITE, "H/2-100"),
        ("IS THE ENEMY", F_HEAD, 100, RED, "H/2+70"),
    ]),
    ("payoff", "Use this prompt. Act as my strategist. Ask what matters. Give me three options. Then recommend the next move.", [
        ("COPY THIS PROMPT", F_HEAD, 66, GREEN, "H/2-420"),
        ("Act as my strategist.", F_MONO, 50, WHITE, "H/2-220"),
        ("Ask what matters.", F_MONO, 50, WHITE, "H/2-120"),
        ("Give me 3 options.", F_MONO, 50, WHITE, "H/2-20"),
        ("Recommend the next step.", F_MONO, 50, GREEN, "H/2+80"),
    ]),
    ("cta", "You still decide. AI organizes. Save this before your next blank page.", [
        ("YOU DECIDE.", F_HEAD, 96, WHITE, "H/2-200"),
        ("AI ORGANIZES.", F_HEAD, 96, BLUE, "H/2-40"),
        ("Save this before", F_HEAD, 66, WHITE, "H/2+140"),
        ("your next blank page.", F_HEAD, 66, GREEN, "H/2+240"),
    ]),
]


def probe_dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


# --- 1) Generate per-section VO, measure real durations ------------------
seg_paths, durs = [], []
for sid, line, _ in sections:
    p = f"{OUT}/vo_{sid}.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"flite=text='{line}':voice=slt", p],
                   check=True, capture_output=True)
    d = probe_dur(p)
    seg_paths.append(p)
    durs.append(d)
    print(f"  {sid:10s} {d:5.2f}s  {line[:50]}")

# concat VO (pad each section with 0.35s breath)
PAD = 0.35
concat_list = f"{OUT}/vo_concat.txt"
sil = f"{OUT}/_sil.wav"
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                f"anullsrc=r=44100:cl=mono", "-t", str(PAD), sil],
               check=True, capture_output=True)
with open(concat_list, "w") as f:
    for p in seg_paths:
        f.write(f"file '{os.path.basename(p)}'\n")
        f.write(f"file '{os.path.basename(sil)}'\n")
vo_full = f"{OUT}/vo_full.wav"
# concat file uses basenames -> run from OUT dir
subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", "vo_concat.txt", "-ar", "44100", "-ac", "1", "vo_full.wav"],
               check=True, capture_output=True, cwd=OUT)
TOTAL = probe_dur(vo_full)
print(f"\nVO total (with breaths): {TOTAL:.2f}s")

# --- 2) Compute each section's window on the timeline --------------------
windows, t = [], 0.0
for d in durs:
    windows.append((t, t + d + PAD))
    t += d + PAD


def esc(x):
    return (x.replace("\\", "\\\\").replace(":", "\\:")
             .replace("'", "\u2019").replace(",", "\\,"))


def drawtext(text, font, size, color, y, t0, t1, x="(w-text_w)/2"):
    en = f"between(t\\,{t0:.3f}\\,{t1:.3f})"
    return ("drawtext=" + ":".join([
        f"fontfile={font}", f"text='{esc(text)}'", f"fontsize={size}",
        f"fontcolor={color}", f"x={x}", f"y={y}",
        "borderw=6", "bordercolor=black", f"enable='{en}'",
    ]))


layers = [f"drawbox=x=0:y=0:w='iw*t/{TOTAL:.3f}':h=12:color={BLUE}@0.9:t=fill"]
for (sid, _, cards), (t0, t1) in zip(sections, windows):
    n = len(cards)
    span = (t1 - t0)
    for i, (text, font, size, color, y) in enumerate(cards):
        # stagger card appearance within the section window
        appear = t0 + (span * 0.35) * (i / max(n, 1))
        x = "140" if font == F_MONO else "(w-text_w)/2"
        layers.append(drawtext(text, font, size, color, y, appear, t1, x=x))
vf = ",".join(layers)

# --- 3) Render: VO + low pulse bed, text over dark bg --------------------
out = f"{OUT}/ai_thinks_first_QUICK_TTS.mp4"
cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:r={FPS}:d={TOTAL:.3f}",
    "-i", vo_full,
    "-f", "lavfi", "-i",
    f"sine=frequency=110:sample_rate=44100:duration={TOTAL:.3f},tremolo=f=4.27:d=0.6,volume=0.04",
    "-vf", vf,
    "-filter_complex", "[1:a]volume=2.2[vo];[vo][2:a]amix=inputs=2:duration=first:normalize=0[a]",
    "-map", "0:v", "-map", "[a]",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
    "-c:a", "aac", "-b:a", "160k", "-r", str(FPS), "-t", f"{TOTAL:.3f}",
    "-movflags", "+faststart", out,
]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    print("FFMPEG FAILED\n", r.stderr[-2500:])
    raise SystemExit(1)

print("\nRENDERED:", os.path.abspath(out))
subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height:format=duration,size",
                "-of", "default=nw=1", out])
