# CFQM privacy policy

CFQM is a Claude Code plugin that keeps a session memory file, `CFQM.md`, in your project and gives it back to Claude after a compaction, resume, `/clear` or new start. This page says exactly what it reads, writes and sends. It applies to every version from 1.0.0 on.

## In short

Everything CFQM keeps stays in your own project on your own machine. The plugin makes no network connections, has no telemetry or analytics, and needs no account. The author receives nothing.

## What it reads

- **`CFQM.md`**, the memory file you and Claude write, plus its settings (`.claude/cfqm.json`) and its own bookkeeping (`.claude/cfqm/state.json`).
- **Your Claude Code session's transcript**, read only. CFQM counts the file edits and shell commands Claude has made since `CFQM.md` was last updated, and keeps only each one's time, kind and file path. It does not keep the text of your conversation.
- **The compaction's summary**, when Claude Code compacts a conversation. CFQM takes out the `<cfqm-refresh>` block it asked for (the new NOW and LOG lines) and ignores the rest.

## What it writes

- **`CFQM.md`:** the NOW section and dated LOG lines, after each compaction.
- **`CFQM_archive.md`:** each NOW that gets replaced, and the oldest LOG lines once the file passes its size budget.
- **`.claude/cfqm/state.json`:** times, session ids, the transcript's location, recent file paths and counts.
- **`.claude/cfqm/backups/`:** a copy of `CFQM.md` before each compaction.

## Personal data

`CFQM.md` holds whatever you and Claude put in it. Its first section is meant to describe you and how you like to work, so it can contain your name or other personal details, and file paths can include your username. All of it stays in your project.

- Don't put secrets (passwords, keys, tokens) in it.
- If the repository is shared, add `CFQM.md`, `CFQM_archive.md` and `.claude/cfqm/` to `.gitignore`.

## What leaves your machine

Only text that CFQM hands to Claude inside your own session:
- the restored part of `CFQM.md`;
- before a compaction, the current NOW and a short instruction.

That text reaches Anthropic in the same way as the rest of your conversation, under your agreement with Anthropic. CFQM itself sends nothing anywhere.

## How long it's kept

Until you delete it. CFQM keeps every snapshot unless you set `keep_snapshots` in `.claude/cfqm.json`. Uninstalling the plugin leaves your files in place: delete `CFQM.md`, `CFQM_archive.md` and `.claude/cfqm/` to remove everything.

## Contact

Questions or concerns: open an issue at https://github.com/CuppaTea1983/cfqm/issues
