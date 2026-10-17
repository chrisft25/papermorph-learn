# Delivery pass

Serve `site/` with `python3 SKILL/scripts/serve.py 8765 site` (no browser caching, so an engine edit is never hidden by a stale file). Use this pass once per chapter: watch, fix what you find, recheck those parts, then deliver for the user's judgement of aesthetics, pacing and teaching. Keep the evidence in `books/<book>/review/chNN/`.

## Watch it in motion

```sh
uv run --with playwright --with pillow SKILL/scripts/strip.py chNN OUT --url http://localhost:8765/<book>/ push/0.25 law3/0.5@w
```

A strip shows one beat at small steps; `@w` adds a motion WebP. Look at each action as a viewer would: do actors perform what the narration says, do props stay on the hands, does the camera move with purpose, does each frame still match the storyboard, do arrows, labels and readouts agree with the motion? Then watch a few beats live in Firefox with sound, which is how the user watches.

## Static checks first

`python3 SKILL/scripts/lint.py site/<book> chNN` takes a second and needs no browser: a global name that clashes with the engine or a library (which stops the page script), beats without timings or MP3, marks the code waits for that the narration lacks, narration edited since `tts.py` ran, and a malformed `style.json`. Run it after every edit, before the passes below.

## Frames and openings

```sh
uv run --with playwright --with pillow SKILL/scripts/shot.py chNN --url http://localhost:8765/<book>/ --out OUT
uv run --with playwright SKILL/scripts/check_blank.py site/<book> chNN --url http://localhost:8765/<book>/
uv run --with playwright SKILL/scripts/overlap.py chNN --url http://localhost:8765/<book>/
```

`shot.py` captures open/end frames of every beat as 4-up sheets and reports console errors. Look for an empty or unrelated opening, text over drawings or clipped at the edge, a card covering what it asks about, leftovers half faded, geometry contradicting its values, shapes inside circles or curves crossing the outline (check thin geometry on the full-size `chNN_bII_T.png`, not only the sheet), text too small at half size or too much at once, and the same idea in different colours. `check_blank.py` reports openings empty for more than a second after speech starts. `overlap.py` samples every beat and lists where an arrow runs through text or two texts collide, with times, so you can look at exactly those frames.

## Smoothness

`uv run --with playwright SKILL/scripts/perf.py chNN --url …` measures frame times in Firefox, which repaints SVG on the main thread and is the slowest common browser for these pages; headless Chromium hides paint cost. Look at the worst beats and transitions; the remedies are in [engine.md](engine.md#performance-firefox).

## Interaction tests

Adapt `assets/templates/e2e.py` into `tools/<book>/e2e_chNN.py`: it checks playback, that every beat replays the same frame when seeked, that quiz cards stay readable and on stage at two viewport sizes, and walks the answers, practice and finish card. Run it in Chromium and with `BROWSER=firefox`. Run existing tests of approved chapters after changing the book's engine or library.

After scoring changes, check a wrong first try stays recorded after revisiting and a restart clears it; after progress changes, check book isolation and missing or malformed stored data. Fix engine bugs at the engine source and copy them to the books with `scripts/engine.py`; book-specific settings stay in each book's `lib/book.css`.

Test details: keyboard first (Enter checks, Esc leaves a box, press Esc before S, R replays on the finish card); a page opened with `?beat=` is not started, so start it before pressing keys; `seek(i, false)` stops before the old panel's fade, so seek playing or evaluate past it; compare text in lower case (CSS uppercases kickers); avoid assertions on totals that grow with the book; Python's server lacks Range requests, so let audio play rather than setting `currentTime`.

## Leftovers (things still on the stage after they should be gone)

Required for every chapter, in both modes, both must exit 0 (run from the project root, dev server up):

```sh
uv run --with playwright SKILL/scripts/leftovers.py --book <book> --ch chNN             # scene changes: what survives a panel() change
uv run --with playwright SKILL/scripts/leftovers.py --book <book> --within --ch chNN    # inside a beat: hides ignored, forgotten, reappearing, strays
```

`--all` checks every chapter with a page; `--url` points at the dev server (default `http://localhost:8766/<book>/`). Reports and annotated
screenshots go to `books/<book>/review/chNN/leftovers*/`. The checker answers the chapter's questions from `tools/<book>/e2e_chNN.py` (keep its
`ANSWERS`/`R`/`L` tables complete), so an incomplete e2e hides later beats. Rules that prevent most findings: never let a `pop()`/`show()` end after
the `hide()` of the same element starts (hide at `>= t + .5` after `pop(x, t)`); hide every element of a loop; draw answer effects into the beat panel
or the question layer, never the persistent scene; mark intentional carries with `data-keep="why"`; two tweens on one property of one element must not
end in the wrong order (the root cause of "stuck" pieces). Look at the screenshots, not only the counts.
