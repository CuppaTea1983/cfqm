---
name: cfqm
description: Keeps this project's CFQM.md true. CFQM.md is the session memory that the cfqm hooks print back into the session after every compaction, resume and clear. Use when a "[cfqm]" nudge appears, when the restore says NOW was not rewritten, at a milestone (something finished, a decision made, the plan changed), when the user says something about themselves or how to work that should outlast this session, before a long session ends, or when the user runs /cfqm.
argument-hint: "[status | init | refresh | rotate]"
---

# CFQM: the session memory that survives compaction

`CFQM.md` sits in the project root, unless `.claude/cfqm.json` names another file. It is what a compacted, resumed or cleared session wakes up with.

The cfqm hooks do the mechanical half:
- They print its inline part into the session after a compaction, resume, clear or new start.
- Before a compaction they snapshot it and stamp its fingerprint. They also ask the compaction for a fresh NOW and new LOG lines, and file them in afterwards.
- Old LOG lines, and every NOW that gets replaced, move to `CFQM_archive.md`.

Your half is judgment: keeping what it says true.

## What goes where

| Section | Printed into the session | Kept by |
|---|---|---|
| RESTORE CORE | yes | You. Who the user is, how they like to work, what you are to each other on this project. Rarely changes. |
| HARD CONSTRAINTS | yes | You. Rules not to relearn the hard way: one line each, with the reason in a few words. |
| NOW | yes | The compaction, every time; you, at milestones. |
| THREADS | on demand | You. Open and parked threads, each with the user's call on it; the project's map. |
| LOG | on demand | Every compaction adds dated lines; the oldest rotate to the archive. |
| POINTERS | on demand | You. Where the depth lives. |

Keep everything above the `<!-- end inline ... -->` marker under about 8,500 characters, because it is printed into every session. Claude Code turns hook output over 10,000 characters into a 2 KB preview, so an oversized core goes unread. Keep the whole body under about 40,000 characters.

## Refreshing NOW

Rewrite NOW; don't append to it. It is the state as it is right now, for whoever picks the work up next:
- What is in flight: the files, functions or documents, and what is left to do on each.
- The next steps, in order.
- Any decision or rule the user set that has to outlast this conversation.

Keep it within about 3,000 characters.

History goes in LOG instead: one dated line per thing finished or decided (`- 2026-11-04: ...`), newest first.

Use the Edit tool. Never compute the fingerprint yourself: the hooks stamp it.

## When the user tells you something lasting

A preference, a correction, or a fact about them or the way they work goes in RESTORE CORE or HARD CONSTRAINTS, in their terms and briefly. If a line already covers it, update that line instead of adding a second one. Anything only this task needs goes in NOW or THREADS.

## Commands

Run them through the launcher, which finds a working Python:

    sh "${CLAUDE_PLUGIN_ROOT}/scripts/cfqm.sh" <command>

- `status`: sizes against their budgets, the fingerprint, when NOW was written, file edits since then, and the last compaction.
- `init`: makes CFQM.md from the template and never overwrites an existing file. Then fill in RESTORE CORE and HARD CONSTRAINTS with the user. If the repository is shared, offer to add `CFQM.md`, `CFQM_archive.md` and `.claude/cfqm/` to `.gitignore`, because CFQM is personal.
- `rotate`: moves the oldest LOG lines to the archive now.
- `stamp --check`: says whether the fingerprint is current.

`/cfqm refresh` means: rewrite NOW (and add LOG lines) as above, then run `status`.

Invoked as: /cfqm $ARGUMENTS

## Rules

- Never put secrets (keys, passwords, tokens) in CFQM: it is printed into every session.
- Never delete from the archive. It is the record, and none of it is loaded.
- When the restore says NOW was not rewritten by a compaction, rewrite it from the summary before anything else.
