#!/usr/bin/env python3
"""Merge a chapter's narration "say" respellings into style.json (the book's lexicon). Run from the project root.

    python3 SKILL/scripts/merge_say.py <book> chNN

Only for books whose narration language needs respellings (e.g. Spanish narration full of English terms); the lexicon is
optional and empty for other languages (see references/authoring.md, "say"). Language comes from style.json book.language.
"""
import json, sys
if len(sys.argv) != 3:
    sys.exit(__doc__)
book, ch = sys.argv[1], sys.argv[2]
p = f'books/{book}/style.json'; s = json.load(open(p))
lang = s.get('book', {}).get('language', 'en')
n = json.load(open(f'content/{book}/{ch}/narration.{lang}.json')).get('say', {})
voice = s.setdefault('voice', {}); lex = voice.setdefault('say', {})
new = {k: v for k, v in n.items() if k not in lex}
lex.update(new); json.dump(s, open(p, 'w'), ensure_ascii=False, indent=2)
print(len(new), 'added:', ', '.join(new) or '-')
