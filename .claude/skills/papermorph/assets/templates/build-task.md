# Build task — one chapter page

You build the lesson page for chapter NN of the Papermorph book <book>. Read `books/<book>/worker-brief.md` first and follow it; then `style.json`, the Skill references you need (diagrams.md, engine.md, authoring.md for questions, review.md for the delivery pass), the approved reference `site/<book>/<chNN>/index.html` and the book library `site/<book>/lib/` (read its header comments).

Content is done: do not change narration or audio: `books/<book>/chapters/chNN.md` (beats, trigger words, checks with answers, build exercise, practice, storyboard plan, errata) and `content/<book>/chNN/narration.<lang>.json` with audio and timings in `site/<book>/chNN/audio/<lang>/`.

Steps:
1. **Layout first**: key frames at real size, then the storyboard sheet `books/<book>/review/chNN/storyboard.jpg` with `strip.py` (one line per frame appended to `chNN.md`). Use your own scratch dir, not shared helper files.
2. **Motion**, camera, checks, the build exercise, practice; marks closer than ~1.3 s get quick pops.
3. New general elements go into the library strictly additively in one block `// chNN additions` ... `// end chNN additions` at the end (another builder may add its own block at the same time: never edit existing code or other blocks; if in doubt keep it chapter-local).
4. Wire the platform: `uv run tools/tutor/wire_chapter.py <book> chNN`. Set `CHAPTER.next` to the next chapter.
5. `tools/<book>/e2e_chNN.py`: muted Chromium and Firefox, replay determinism, every check with a wrong pick first, the build with a wrong attempt, practice, finish card. Keep the answers tables complete (the leftover finder reads them).
6. Delivery pass per `review.md` in both browsers (lint, check_blank, overlap, perf); fix what you find.
7. **Leftovers (required):** `uv run --with playwright SKILL/scripts/leftovers.py --book <book> --ch chNN` and the same with `--within` must both exit 0. Look at the screenshots. Dev server for all checks: `python3 SKILL/scripts/serve.py 8766 site`.

Browsers MUTED always. Do not edit the contents, `chapters.md`, other chapters, the engine, `book.css` or platform files. Reply in at most 8 lines: done or not, sheet path, library additions, test and perf results, unresolved issues.
