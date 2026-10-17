#!/usr/bin/env bash
# Commit one finished, registered chapter (no deploy). Run from the project root.
# Usage: SKILL/scripts/commit_chapter.sh <book> chNN "Chapter title" [--push]
# Stages only the chapter's own files plus the shared book files the chapter loop owns. Platform files (tools/tutor,
# lib/tutor.js, lib/learn.js, lib/lang.js, lib/draw.js...) are committed separately by whoever owns them.
# Extra paths (e.g. the book's element library after "// chNN additions"): EXTRA_PATHS="site/<book>/lib/mybook.js ..."
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
book="$1"; ch="$2"; title="$3"; push="${4:-}"
paths=(
  "site/$book/$ch"
  "content/$book/$ch"
  "books/$book/chapters/$ch.md"
  "books/$book/chapters.md"
  "site/$book/lib/contents.js"
  "site/$book/index.html"
  "books/$book/curriculum.md"
  "books/$book/sources"
)
for p in "${paths[@]}" ${EXTRA_PATHS:-}; do [ -e "$p" ] && git add -- "$p"; done
if git diff --cached --quiet; then echo "nothing to commit for $ch"; exit 0; fi
git commit -q -m "Add $ch: $title

Lesson page, narration, audio, chapter notes and registration.

Co-Authored-By: Claude <noreply@anthropic.com>"
git log --oneline -1
if [ "$push" = "--push" ]; then git push -q origin HEAD && echo pushed; fi
