#!/usr/bin/env python3
"""Register a finished chapter: contents entry, chapters.md row, tutor pack. Run from the project root.

    python3 SKILL/scripts/register.py <book> chNN "Chapter title" minutes "Part label"

Contents: inserts into the unit (in `Contents.book` of site/<book>/index.html) whose first chapter <= NN, numbering
explicitly across gaps. Inserted chapters with ids like ch24b are not handled here: add them to the contents by hand.
The coordinator owns this step (workers never edit the contents, chapters.md or other chapters).
"""
import re, subprocess, sys
if len(sys.argv) != 6:
    sys.exit(__doc__)
book, ch, title, mins, part = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
n = int(ch[2:])
p = f'site/{book}/index.html'; s = open(p).read()
# a unit is  [title, [[chapter title, minutes, number?], ...], { unit: U, chapter: C }]  (title: 'text' or UILang.t('es', 'en'))
ENTRY = re.compile(r"\[((?:UILang\.t\((?:[^()]|\([^)]*\))*\))|(?:'(?:[^'\\]|\\.)*')), \[(.*?)\], \{ unit: (\d+), chapter: (\d+) \}\]", re.S)
ITEM = re.compile(r"\['((?:[^'\\]|\\.)*)', (\d+)(?:, (\d+))?\]")
entries = list(ENTRY.finditer(s))
if not entries:
    sys.exit(f'no units found in {p}: expected [title, [[chapter, minutes]...], {{ unit: U, chapter: C }}] entries inside Contents.book')
host = max((m for m in entries if int(m.group(4)) <= n), key=lambda m: int(m.group(4)))
first = int(host.group(4)); items, k = [], first - 1
for t, mi, num in ITEM.findall(host.group(2)):
    k = int(num) if num else k + 1; items.append((k, t, int(mi)))
items = sorted({i[0]: i for i in items + [(n, title.replace("'", "\\'"), mins)]}.values())
out, k = [], first - 1
for num, t, mi in items:
    out.append(f"['{t}', {mi}]" if num == k + 1 else f"['{t}', {mi}, {num}]"); k = num
s = s[:host.start()] + f"[{host.group(1)}, [{', '.join(out)}], {{ unit: {host.group(3)}, chapter: {first} }}]" + s[host.end():]
open(p, 'w').write(s); print('contents: unit', host.group(3), '->', [i[0] for i in items])
q = f'books/{book}/chapters.md'
try:
    t = open(q).read()
except FileNotFoundError:
    t = "# Chapters\n\n| # | Part | Title | Status | Min | Files |\n|---|---|---|---|---|---|\n"
row = f"| {n} | {part} | {title} | ready | {mins} | chapters/{ch}.md; e2e tools/{book}/e2e_{ch}.py |"
lines = t.split('\n'); idx = [i for i, l in enumerate(lines) if re.match(r'\| \d+ \|', l)]
pos = next((i for i in idx if int(lines[i].split('|')[1]) > n), (idx[-1] + 1) if idx else len(lines))
if not any(l.startswith(f'| {n} |') for l in lines):
    lines.insert(pos, row)
else:
    lines = [row if l.startswith(f'| {n} |') else l for l in lines]
open(q, 'w').write('\n'.join(lines)); print('chapters.md: row', n)
print(subprocess.run(['uv', 'run', 'tools/tutor/packs.py', book, ch], capture_output=True, text=True).stdout.strip() or 'tutor pack: install the platform first (scripts/platform_install.py) to build packs')
