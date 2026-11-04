# cfqm

A session memory for Claude Code that survives compaction. `CFQM.md` in your project holds who you are, how you like to work, the rules not to relearn, what's happening NOW, open threads and a dated log. This plugin puts it back into the session after every compaction, resume, `/clear` and new start, staying under the 10,000-character limit beyond which Claude Code shows hook output as a 2 KB preview.

The compaction keeps it current: the PreCompact hook asks the compaction to write NOW and LOG lines into its summary, and the PostCompact hook files them into `CFQM.md`. Old detail rotates to `CFQM_archive.md`.

Install it with `/plugin install cfqm --marketplace CuppaTea1983/cfqm` (Claude Code 2.1.275 or later), then start with `/cfqm init` in a project. Requirements: Python 3.8+ (standard library only) and `sh` (on Windows, Git for Windows). Settings, the file's sections and how the hooks work are in the repository's main README.
