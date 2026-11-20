**## What's new in V1.1.3:**



**\*\*A warning the moment CFQM outgrows what a restore can print.\*\***



**After every compaction or resume, cfqm prints the inline part of your CFQM.md (RESTORE CORE, HARD CONSTRAINTS and NOW) back into the session. That part has a budget, 8,500 characters by default (`inline\_budget` in `.claude/cfqm.json`), because Claude Code cuts any hook output over 10,000 characters down to a short preview.**



**Until now nothing warned when NOW grew past that budget during a session. You found out only when a restore came back cut short. In real use, a day of hand edits took one CFQM from about 8,000 to 11,100 characters without a word.**



**Now the `nudge` hook, which already runs on every prompt, also checks the inline part's size. When it's over budget, Claude is told once to rewrite NOW tighter and to archive the old NOW whole (never cut). It warns again only if NOW changes while still over, and stays quiet when everything fits.**



**## Upgrading**



**Nothing to change: existing setups pick it up on the next prompt.**



**Changed: `scripts/cfqm.py` (`cmd\_nudge`), version 1.1.3 in `plugin.json` and `marketplace.json`.**



**Found and fixed with Claude (Opus 5.5).**



