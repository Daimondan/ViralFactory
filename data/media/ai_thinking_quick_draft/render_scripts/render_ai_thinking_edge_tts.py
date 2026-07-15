"""
Edge-TTS review draft: 'AI THINKS FIRST' IG Reel.
Natural neural voice (placeholder for cloned Chatterbox voice, swapped next).
Per-section VO -> real durations -> text timed to actual speech.
Fixed audio: no hot boost, alimiter + loudnorm, peaks kept below -1 dBFS.
Output: data/media/ai_thinking_quick_draft/ai_thinks_first_EDGE_TTS_REVIEW.mp4
"""
import asyncio
import os
import subprocess

import edge_tts

os.chdir("/home/daimon/ViralFactory")
OUT = "data/media/ai_thinking_quick_draft"
os.makedirs(OUT, exist_ok=True)

W, H, FPS = 1080, 1920, 30
VOICE = "en-US-ChristopherNeural"  # confident male creator tone
F_HEAD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_MONO = "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"
BG = "0x0B0E14"
WHITE, RED, BLUE, GREEN = "white", "0xE54B2C", "0x2E7DFF", "0x3DDC84"

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


async def synth(text, mp3_path):
    await edge_tts.Communicate(text, VOICE, rate="+6%").save(mp3_path)


# --- 1) Edge-TTS per section -> wav, measure real durations --------------
seg_paths, durs = [], []
for sid, line, _ in sections:
    mp3 = f"{OUT}/vo_edge_{sid}.mp3"
    wav = f"{OUT}/vo_edge_{sid}.wav"
    asyncio.run(synth(line, mp3))
    subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", "44100", "-ac", "1", wav],
                   check=True, capture_output=True)
    d = probe_dur(wav)
    seg_paths.append(wav)
    durs.append(d)
    print(f"  {sid:10s} {d:5.2f}s  {line[:50]}")

# concat with breath pad
PAD = 0.4
sil = f"{OUT}/_sil_edge.wav"
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", str(PAD), sil], check=True, capture_output=True)
with open(f"{OUT}/vo_edge_concat.txt", "w") as f:
    for p in seg_paths:
        f.write(f"file '{os.path.basename(p)}'\n")
        f.write(f"file '{os.path.basename(sil)}'\n")
subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", "vo_edge_concat.txt", "-ar", "44100", "-ac", "1", "vo_edge_full.wav"],
               check=True, capture_output=True, cwd=OUT)
vo_full = f"{OUT}/vo_edge_full.wav"
TOTAL = probe_dur(vo_full)
print(f"\nVO total (with breaths): {TOTAL:.2f}s")

# --- 2) Section windows --------------------------------------------------
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

# background tint per emotional beat (red = pain, green = solution)
tint_map = {"hook": None, "problem": RED, "reframe": BLUE, "transform": GREEN,
            "demo": None, "tension": RED, "payoff": GREEN, "cta": BLUE}
for (sid, _, cards), (t0, t1) in zip(sections, windows):
    tint = tint_map.get(sid)
    if tint:
        layers.append(
            f"drawbox=x=0:y=0:w=iw:h=ih:color={tint}@0.10:t=fill:"
            f"enable='between(t\\,{t0:.3f}\\,{t1:.3f})'")
    n = len(cards)
    span = (t1 - t0)
    for i, (text, font, size, color, y) in enumerate(cards):
        appear = t0 + (span * 0.30) * (i / max(n, 1))
        x = "120" if font == F_MONO else "(w-text_w)/2"
        layers.append(drawtext(text, font, size, color, y, appear, t1, x=x))

# pattern-interrupt white flashes (2 frames each) at key transitions
flash_times = [windows[2][0], windows[5][0], windows[7][0]]  # reframe, tension, cta
for ft in flash_times:
    layers.append(
        f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.7:t=fill:"
        f"enable='between(t\\,{ft:.3f}\\,{ft+0.13:.3f})'")

vf = ",".join(layers)

# --- 3) Render: clean VO mix, limiter + loudnorm, low music bed ----------
out = f"{OUT}/ai_thinks_first_EDGE_TTS_REVIEW.mp4"
cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:r={FPS}:d={TOTAL:.3f}",
    "-i", vo_full,
    "-f", "lavfi", "-i",
    f"sine=frequency=110:sample_rate=44100:duration={TOTAL:.3f},tremolo=f=4.27:d=0.5,volume=0.03",
    "-vf", vf,
    "-filter_complex",
    "[1:a]alimiter=limit=0.9[vo];"
    "[vo][2:a]amix=inputs=2:duration=first:normalize=0,"
    "loudnorm=I=-16:TP=-1.5:LRA=11[a]",
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
