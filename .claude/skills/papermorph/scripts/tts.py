"""Generate narration audio and word-mark timings with Edge TTS or Kokoro.

Usage (from the project root; SKILL is this skill's folder):
    uv run --with edge-tts $SKILL/scripts/tts.py content/ch01/narration.en.json site/ch01/audio/en
    uv run --python 3.12 --with kokoro $SKILL/scripts/tts.py ...      # narration with "engine": "kokoro"

The narration file names the engine ("edge", the default, or "kokoro"), the voice and the rate. Edge needs network
access. Kokoro (Apache 2.0) runs locally: its first run downloads the model (about 330 MB) and an English dictionary;
voices start with the accent's letter (am_michael, af_heart: American; bm_george, bf_emma: British) and its word
timings cover English. Both need ffmpeg/ffprobe.

Narration text may contain [[mark]] tags placed before a word. The output
timings.js records each clip's duration and the time (seconds) at which the
word after every mark starts, so page animations can wait for that word,
plus one caption cue per sentence. An optional "say" object maps shown words to the spelling the voice
should read ({"CNOT": "si-not"}); captions and marks keep the shown words. Only beats whose text or voice changed are
regenerated; spoken word times are cached, so caption and mark rules can change
without new audio.

Narration files are read as UTF-8 (a byte order mark is allowed) on every platform.
Keep beat ids and mark names ASCII: they become file names and JS keys, and are
printed to the console.

Edge sometimes answers a request with no audio (NoAudioReceived), more often for
some voices; such a beat is requested again up to MAX_ATTEMPTS times with growing
pauses. If it still gets none, a short test phrase in the same voice tells whether
the voice is unavailable or this beat's text is the problem, and the run stops.
"""

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


MARK = re.compile(r"\[\[(\w+)\]\]")
MAX_ATTEMPTS = 5          # requests per beat when Edge returns no audio
FIRST_RETRY_DELAY = 2     # seconds before the second request; doubles after each failure
PROBE_TEXT = "1, 2, 3."   # checks the voice after a beat fails; any voice reads digits in its own language


async def synth(text, voice, rate, mp3_path):
    import edge_tts
    words = []  # (seconds, word)
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append((chunk["offset"] / 1e7, chunk["text"]))
    return words


async def synth_with_retries(beat, text, voice, rate, mp3_path):
    """synth(), requested again after NoAudioReceived; each attempt rewrites mp3_path from the start."""
    from edge_tts.exceptions import NoAudioReceived
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await synth(text, voice, rate, mp3_path)
        except NoAudioReceived:
            if attempt == MAX_ATTEMPTS:
                raise
            delay = FIRST_RETRY_DELAY * 2 ** (attempt - 1)
            print(f"{beat}: Edge returned no audio, retrying in {delay} s (attempt {attempt + 1} of {MAX_ATTEMPTS})",
                  file=sys.stderr, flush=True)
            await asyncio.sleep(delay)


async def explain_no_audio(beat, voice, rate, out_dir):
    """The message for a beat that ran out of attempts: whether the voice or this beat's text failed."""
    from edge_tts.exceptions import NoAudioReceived
    with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".probe-", suffix=".mp3", delete=False) as f:
        probe_path = Path(f.name)
    try:
        await synth(PROBE_TEXT, voice, rate, probe_path)
        voice_works = True
    except NoAudioReceived:
        voice_works = False
    finally:
        probe_path.unlink(missing_ok=True)
    if voice_works:
        return (f"{beat}: the voice {voice} works, but Edge returned no audio for this beat's text "
                f"{MAX_ATTEMPTS} times. Look for unusual characters in it, or split the beat.")
    return (f"{beat}: the voice {voice} returned no audio {MAX_ATTEMPTS} times, and also for a short test phrase, "
            "so the voice is unavailable at Edge right now; the text is not the cause. Completed beats are saved. "
            "Rerun later, or choose another voice for the whole book (uv run --with edge-tts edge-tts --list-voices).")


async def edge_beat(beat, text, voice, rate, mp3_path, out_dir):
    from edge_tts.exceptions import NoAudioReceived
    try:
        return await synth_with_retries(beat, text, voice, rate, mp3_path)
    except NoAudioReceived:
        raise SystemExit(await explain_no_audio(beat, voice, rate, out_dir)) from None


KOKORO = {}   # one pipeline per accent, loaded once per run


def kokoro_beat(text, voice, rate, mp3_path):
    """Synthesize locally with Kokoro; word start times come from its predicted durations."""
    import numpy as np
    from kokoro import KPipeline
    lang = voice[0]
    if lang not in KOKORO:
        KOKORO[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    speed = 1 + float(rate.rstrip("%")) / 100 if rate else 1
    words, chunks, offset = [], [], 0.0
    for r in KOKORO[lang](text, voice=voice, speed=speed):
        audio = np.asarray(r.audio, dtype=np.float32)
        for tk in r.tokens or []:
            if tk.start_ts is not None and any(c.isalnum() for c in tk.text):
                words.append((round(offset + tk.start_ts, 3), tk.text))
        chunks.append(audio)
        offset += len(audio) / 24000
    pcm = (np.clip(np.concatenate(chunks), -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "-",
                    "-b:a", "64k", str(mp3_path)], input=pcm, check=True)
    return words


def split_marks(raw):
    """Return clean text and {mark: char position in clean text}."""
    marks, clean, pos = {}, [], 0
    # MARK.split alternates text, name, text, name, ...
    for i, part in enumerate(MARK.split(raw)):
        if i % 2:
            if part in marks:
                raise ValueError(f"duplicate mark {part!r} in one beat")
            marks[part] = pos
        else:
            clean.append(part)
            pos += len(part)
    return "".join(clean), marks


def respell(clean, say):
    """Apply the narration's "say" lexicon (shown word -> spelling the voice reads) to whole words.

    Returns the spoken text and a function mapping a char position in it back to the clean text,
    so marks and captions keep the shown spelling while the voice hears the respelling."""
    if not say:
        return clean, lambda pos: pos
    pattern = re.compile("|".join(rf"(?<!\w){re.escape(k)}(?!\w)" for k in sorted(say, key=len, reverse=True)))
    spoken, segs, last = [], [], 0   # segs: (spoken start, spoken end, clean start, clean end) of each respelling
    for m in pattern.finditer(clean):
        spoken.append(clean[last:m.start()])
        start = sum(map(len, spoken))
        spoken.append(say[m.group(0)])
        segs.append((start, start + len(say[m.group(0)]), m.start(), m.end()))
        last = m.end()
    spoken.append(clean[last:])

    def to_clean(pos):
        shift = 0
        for s0, s1, c0, c1 in segs:
            if pos < s0:
                break
            if pos < s1:
                return c0
            shift = c1 - s1
        return pos + shift
    return "".join(spoken), to_clean


def time_at(clean, words, spoken=None, to_clean=lambda pos: pos):
    """Return f(pos): start time of the first spoken word at or after char pos of the clean text."""
    text = clean if spoken is None else spoken
    cursor, located = 0, []
    for t, w in words:
        i = text.find(w, cursor)
        if i < 0:
            continue
        located.append((to_clean(i), t))
        cursor = i + len(w)
    return lambda pos: next((round(t, 3) for i, t in located if i >= pos), None)


def mark_times(clean, marks, words, spoken=None, to_clean=lambda pos: pos):
    at, out = time_at(clean, words, spoken, to_clean), {}
    for name, pos in marks.items():
        out[name] = at(pos)
        if out[name] is None:
            raise SystemExit(f"mark {name!r} not matched to a spoken word")
    return out


def caption_cues(clean, words, spoken=None, to_clean=lambda pos: pos):
    """One cue per sentence: [start seconds, sentence]."""
    at, cues, start = time_at(clean, words, spoken, to_clean), [], 0
    for m in list(re.finditer(r"[.?!]\s+", clean)) + [None]:
        end = m.end() if m else len(clean)
        text = clean[start:end].strip()
        if text:
            cues.append([at(start) or 0, text])
        start = end
    return cues


def duration(mp3):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
        capture_output=True, text=True, check=True)
    return round(float(r.stdout), 3)


def write_atomic(path, text):
    """Replace output only after its complete contents have been written."""
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}-", delete=False) as f:
        tmp = Path(f.name)
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


async def main(src, out_dir):
    spec = json.loads(Path(src).read_text(encoding="utf-8-sig"))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path(src).with_suffix(".timings.json")  # build cache, kept out of the site
    cache = json.loads(cache_path.read_text(encoding="utf-8-sig")) if cache_path.exists() else {}
    voice, rate, engine = spec["voice"], spec["rate"], spec.get("engine", "edge")
    if engine not in ("edge", "kokoro"):
        raise SystemExit(f"unknown engine {engine!r}: use edge or kokoro")
    result = {}
    public = lambda v: {k: v[k] for k in ("dur", "marks", "cues")}
    live = {b: public(v) for b, v in cache.items()
            if {"dur", "marks", "cues"} <= v.keys() and (out_dir / f"{b}.mp3").exists()}
    timings_path = out_dir / "timings.js"
    for beat, raw in spec["beats"].items():
        mp3 = out_dir / f"{beat}.mp3"
        old = cache.get(beat)
        clean, marks = split_marks(raw)
        spoken, to_clean = respell(clean, spec.get("say"))
        tag = "" if engine == "edge" else f"{engine}|"   # Edge keys stay as they were, so its audio is kept
        key = hashlib.sha1(f"{tag}{voice}|{rate}|{spoken}".encode()).hexdigest()
        # Existing caches included [[marks]] in the key; reuse an unchanged old beat once,
        # then save its spoken-text key so future mark edits do not regenerate audio.
        legacy_key = hashlib.sha1(f"{voice}|{rate}|{raw}".encode()).hexdigest()
        reusable = old and old.get("key") in (key, legacy_key if engine == "edge" else key) and "words" in old and mp3.exists() and mp3.stat().st_size > 0
        tmp = None
        if reusable:
            words = old["words"]
            clip = mp3
        else:
            with tempfile.NamedTemporaryFile(dir=out_dir, prefix=f".{beat}-", suffix=".mp3", delete=False) as f:
                tmp = Path(f.name)
            clip = tmp
        try:
            if not reusable:
                words = (kokoro_beat(spoken, voice, rate, clip) if engine == "kokoro"
                         else await edge_beat(beat, spoken, voice, rate, clip, out_dir))
            entry = {"key": key, "dur": duration(clip), "words": words,
                     "marks": mark_times(clean, marks, words, spoken, to_clean),
                     "cues": caption_cues(clean, words, spoken, to_clean)}
            if tmp:
                tmp.replace(mp3)
                print(f"{beat}: synthesized")
            result[beat] = entry
            cache[beat] = entry
            # A later failed beat must not discard the successful beats' cache.
            write_atomic(cache_path, json.dumps(cache, indent=1))
            # Keep the successful MP3's timings consistent even if a later beat fails.
            live[beat] = public(entry)
            write_atomic(timings_path, "window.TIMINGS = " + json.dumps(live, indent=1) + ";\n")
        finally:
            if tmp:
                tmp.unlink(missing_ok=True)
    write_atomic(cache_path, json.dumps(result, indent=1))
    js = {b: public(v) for b, v in result.items()}
    write_atomic(timings_path, "window.TIMINGS = " + json.dumps(js, indent=1) + ";\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(0 if sys.argv[1:] in (["-h"], ["--help"]) else 2)
    asyncio.run(main(*sys.argv[1:3]))
