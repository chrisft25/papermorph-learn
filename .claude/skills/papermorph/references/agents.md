# Producing many chapters with agents

This is the workflow that produced a 30+ chapter book. It needs no special tooling beyond this Skill: briefs are Markdown files, state is files, and a coordinator hands one chapter at a time to workers.

## Roles (model per role)

| Role | Model | Owns |
|---|---|---|
| **Coordinator / main** | the strongest available (e.g. Opus) | intake, `style.json`, the curriculum, briefs, **registration** (contents, `chapters.md`, tutor pack), commits, decisions that change the book's direction |
| **Content worker** | the strongest (e.g. Opus) | `chapters/chNN.md` (beats, trigger words, checks with verified answers, glossary, notes for the tutor, storyboard plan), `narration.<lang>.json`, the audio |
| **Build worker** | a strong coding model (e.g. Sonnet) | `chNN/index.html`: layout first, storyboard sheet, motion, camera, questions, the chapter's `e2e_chNN.py`, delivery pass, leftover finder; additive library blocks |
| **Check worker** | a small fast model (e.g. Haiku) | mechanical work: `lint.py`, `check_blank.py`, `overlap.py`, `perf.py`, strips, `leftovers.py` runs (both modes), tutor pack, `register.py`, report in a few lines |

At most **two chapters in flight**; the same file never has two writers. Workers get a brief and return files plus a reply of at most ~8 lines (done or not, paths, new elements and respellings, test results, unresolved issues).
Resume a rate-limited worker with a message instead of restarting it. Decide small questions yourself and record them under "Errata / notes" in `chNN.md`; escalate only what changes the book's direction.

## The loop for one chapter

1. **Content** (content worker, from `assets/templates/content-task.md`): reads the curriculum row, the neighbouring chapters' notes and the sources; writes `chNN.md` and the narration, runs `tts.py`.
2. **Build** (build worker, `build-task.md`): layout first (key frames at real size, storyboard sheet, one line per frame), then motion and questions, then the e2e test and the delivery pass in Chromium and Firefox.
3. **Checks** (check worker): lint, blank openings, overlap, perf, **leftovers in both modes** ([review.md](review.md#leftovers-things-still-on-the-stage-after-they-should-be-gone)); everything must exit 0.
4. **Register** (coordinator): `python3 SKILL/scripts/register.py <book> chNN "Title" minutes "Part"`, `merge_say.py` if the book uses respellings, set `CHAPTER.next`, update `style.json`.
5. **Commit** (coordinator): `SKILL/scripts/commit_chapter.sh <book> chNN "Title" [--push]` stages only the chapter's files and the shared files the loop owns.

Keep a `final-pass.md` (deferred fixes found during production, such as an engine fix to apply once) and an `open-questions.md` (evidence log: observed vs expected, evidence, how to reproduce, plus "questions for colleagues"). Templates in `assets/templates/`.

## Multi-source books (intake pattern)

When a book is built from several sources rather than one PDF: write `books/<book>/curriculum.md` (teaching approach + a chapter table with "can do / sources" columns), extract each source to text with `=== [pN] ===` page markers into
`books/<book>/sources/`, add short digests for sources that are not books (docs, code, papers), and make the content task quote the curriculum row. A research worker can fetch missing sources. The same files feed the tutor's source search.

## Rules that already cost a revision

- Browsers are **muted** in every Playwright run (`--mute-audio`; Firefox `media.volume_scale=0.0`): audio must never reach the user's speakers.
- The coordinator owns registration, contents, `chapters.md` and `style.json`; workers never edit other chapters, the engine, `book.css` or platform files; they report needs instead.
- New library elements go in as additive blocks at the end of the book's library (`// chNN additions` ... `// end chNN additions`); never edit earlier blocks (wrap them instead). If in doubt keep it chapter-local.
- Beat ids are stable, ASCII, meaningful (the tutor, mastery map, quizzes and scene links key on them).
- Draw answer effects into the beat panel or the question layer, never the persistent scene; `data-keep="why"` for intentional carries; both leftover modes must pass.
- Never let a `pop`/`show` end after the same element's `hide` starts (hide at `>= t + .5` after `pop(x, t)`); hide every element of a loop.
- Fixed sample data for anything random (replay determinism); verify every number and answer by computation; "illustrative / made up" stamps on invented data; "observed vs inferred" labels.
- Version-flag facts about software and papers (a paper is a published method, not current behaviour); keep private or internal information out of book files unless the user allows it.
- Layout first, storyboard sheet before motion: builders tend to skip it; enforce it if it matters.

## Pitfalls

`pickEls` wrong-answer messages must be a function `i => ...`, not an array. The `blanks` parser rejects "64 %", ".48" and leading zeros. Shift keys are reserved by the player during questions (use PageUp/PageDown). The question band covers the bottom
of the stage (y >= ~686): build layouts above it. e2e start-up wait >= 1500 ms once `tutor.js` loads. `overlap.py` lists harmless transients (cross-fades, flights): read them. The leftover finder needs complete e2e answers. Firefox may show an
occasional single frame of ~200 ms at beat starts; measure with `perf.py` with and without the platform before blaming either. `engine.py` refuses an existing empty `lib/` folder. `serve.py` must support Range requests for seeking in audio.
