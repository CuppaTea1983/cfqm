<!-- CFQM: this project's session memory (the cfqm plugin). Everything above the "end inline" marker is printed
     into the session after a compaction, resume, clear or new start; the rest is read on demand. RESTORE CORE,
     HARD CONSTRAINTS, THREADS and POINTERS are kept true by hand (the cfqm skill says how); NOW and LOG are
     rewritten by every compaction. The fingerprint is stamped by the hooks: never edit it. -->

---
schema: cfqm-2
fingerprint: 0000000000000000
updated: 2026-01-01
---

## RESTORE CORE
- Who you're working with, and how they like to work: direct or formal, short or thorough, humour or none.
- What you are to each other on this project (collaborator, pair programmer, reviewer, ...).
- What they've told you about themselves that a fresh session would otherwise have to relearn.

## HARD CONSTRAINTS
- The rules not to relearn the hard way, one line each, with the reason in a few words.

## NOW
- Nothing yet: the first compaction writes this, or rewrite it at the next milestone.

<!-- end inline: everything above this line is printed into the session (keep it under about 8,500 characters);
     everything below is read on demand. -->

## THREADS
- Open and parked threads, each with the user's call on it; the project's map.

## LOG
<!-- newest first, one dated line per thing finished or decided; every compaction adds lines here and the oldest
     rotate to the archive. -->

## POINTERS
- Where the depth lives: docs, design notes, logs. The archive: CFQM_archive.md (grep it).

<!-- end restore body -->
