# Final pass — items collected during production

Add one line per deferred item as you find it (chapter, what, why it waits). Work through the list once the chapters are done, then re-run every e2e test and both leftover modes.

- <chNN>: <what to fix later, and what to re-run afterwards>
- ENGINE FIX candidates go here with their root cause (fix at the engine's source, then sync with `engine.py`).
- LEFTOVERS: after all chapters are done, run `leftovers.py --all` in both modes and fix every finding.
