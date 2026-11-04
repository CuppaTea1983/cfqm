# CFQM: a session memory for Claude Code that survives compaction

When Claude Code compacts a conversation, its summary keeps the recent work but drops the long view: who you are, how you like to work, the rules it learned the hard way, what's parked and why. CFQM keeps all of that in one plain-text file in your project, `CFQM.md`, and puts it back into the session after every compaction, resume, `/clear` and new start.

The compaction itself keeps the file current. Just before it summarises, the plugin asks it to write CFQM's **NOW** section (what's in flight and the next steps) and a few dated **LOG** lines. The compaction is the one moment where the whole conversation is in view, so these come from the source. Afterwards the plugin files them into `CFQM.md`. A forgotten "update the memory file" can't happen.

CFQM (Cloud Fractal Quantum Memory) began as CuppaTea1983's way of making a cloud session *reconstitute* instead of waking up cold.

## How it works

| Hook | What the plugin does |
|---|---|
| `SessionStart` (startup, resume, clear, compact) | Prints CFQM's inline part into the session, says how fresh NOW is, and says where the rest is. |
| `PreCompact` | Snapshots `CFQM.md`, stamps its fingerprint, and prints instructions. Claude Code adds a PreCompact hook's output to the compaction prompt, so the summary ends with a `<cfqm-refresh>` block holding a new NOW and LOG lines. |
| `PostCompact` | Reads that block out of the summary and files it. The NOW it replaces goes to `CFQM_archive.md`; the oldest LOG lines rotate there once the file passes its budget. |
| `UserPromptSubmit` | Rarely, one line: many file edits have built up since NOW was last written (counted from your session's transcript, locally). |

The restore stays under 9,500 characters. Claude Code saves any hook output over 10,000 characters to a file and shows the session only a 2 KB preview. A memory file that has grown past that size silently stops arriving, and this plugin was built after measuring exactly that.

### The file

| Section | Printed into the session | Kept by |
|---|---|---|
| `RESTORE CORE` | yes | you and Claude: who you are, how you like to work |
| `HARD CONSTRAINTS` | yes | you and Claude: rules not to relearn the hard way |
| `NOW` | yes | every compaction; Claude, at milestones |
| `THREADS` | on demand | open and parked threads, with your call on each |
| `LOG` | on demand | every compaction adds dated lines; the oldest rotate to the archive |
| `POINTERS` | on demand | where the depth lives |

Everything above the `<!-- end inline -->` marker is printed into the session; Claude reads the rest when it needs it. The included `cfqm` skill tells Claude how to keep each section true.

## Install

From GitHub: CuppaTea1983/cfqm

    /plugin install cfqm --marketplace CuppaTea1983/cfqm

That's one step on Claude Code 2.1.275 or later. On older versions, use two:

    /plugin marketplace add CuppaTea1983/cfqm
    /plugin install cfqm@cuppatea1983

From a local copy of this folder:

    /plugin marketplace add "/path/to/CFQM Plugin"
    /plugin install cfqm@cuppatea1983

Then, in a project, run `/cfqm init` (or ask Claude to set up CFQM) and fill in RESTORE CORE and HARD CONSTRAINTS together. NOW fills itself at the first compaction.

## Settings

All optional, in `<project>/.claude/cfqm.json`:

| Key | Default | Meaning |
|---|---|---|
| `file` | `CFQM.md` | the memory file |
| `archive` | `CFQM_archive.md` | where replaced NOWs and rotated LOG lines go (never loaded) |
| `backups` | `.claude/cfqm/backups` | a snapshot before every compaction (`""` = none) |
| `state` | `.claude/cfqm/state.json` | the hooks' bookkeeping |
| `inline_budget` | `8500` | characters printed into the session |
| `body_budget` | `40000` | past this, the oldest LOG lines rotate to the archive |
| `now_budget` | `3000` | the NOW the compaction is asked for |
| `log_lines` | `8` | LOG lines a compaction may add |
| `nudge_edits` | `40` | remind after this many file edits since NOW was written (`0` = never) |
| `nudge_hours` | `2.0` | ...and at least this long since |
| `also_read` | `[]` | files the restore names as further reading |
| `keep_snapshots` | `0` | `0` keeps every snapshot |
| `windows_notes` | `true` | on Windows, the restore adds the plugin's short Windows notes (`false` = off) |

By hand, from the project folder: `sh "<plugin folder>/scripts/cfqm.sh" status | init | stamp [--check] | rotate` (or add `--project DIR`).

## Requirements

- Python 3.8 or newer, standard library only. The launcher tries `$CFQM_PYTHON`, `python3`, `python` and `py -3`, and uses the first one that actually starts. On Windows a bare `python3` is often the Microsoft Store's stub.
- `sh`: built in on macOS and Linux. On Windows it comes with Git for Windows, which Claude Code uses anyway.

## Good to know

- Everything stays on your machine. `CFQM.md` is plain text that gets printed into your sessions, so never put secrets in it. If the repository is shared, add `CFQM.md`, `CFQM_archive.md` and `.claude/cfqm/` to `.gitignore`.
- If a compaction leaves the block out, NOW stays as it was and the next restore says it wasn't rewritten. That also happens with some compaction paths that hand PostCompact an empty summary.
- If the same hooks are also in a project's own settings, that's safe: a duplicate run within 90 seconds does nothing.
- In a project with no `CFQM.md` the hooks do nothing and leave no trace.
- **On Windows**, the restore also gives Claude a short block of Windows notes ([`windows_notes.md`](plugins/cfqm/scripts/windows_notes.md)). They're the traps that otherwise come back every session: Git Bash halving `\\` in commands, the cp1252 console crashing on `→` or emoji, CRLF line endings, `/arguments` rewritten into Windows paths, and `python3` being the Microsoft Store stub. Your own CFQM always comes first. If the notes would crowd it out, the restore prints one line saying where they are instead.

## Uninstall

    /plugin uninstall cfqm@cuppatea1983

Your `CFQM.md` and its archive stay where they are.

## Licence

MIT. See `LICENSE`.

- **Full licence:** https://spdx.org/licenses/MIT.html
- **Source and other releases:** https://github.com/CuppaTea1983
- **Huggingface:** https://huggingface.co/spaces/Omega-Dev/Leviathan
