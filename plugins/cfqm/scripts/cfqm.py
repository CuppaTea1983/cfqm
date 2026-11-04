#!/usr/bin/env python3
"""cfqm: a session memory for Claude Code that survives compaction (the CFQM plugin's mechanical half).

CFQM.md, kept in the project, holds what a resumed or compacted session needs to pick the work back up: who you
work with and how, the rules not to relearn, what is happening NOW, the open threads, a dated LOG. Claude keeps it
true (the cfqm skill: judgment). This script does everything mechanical, run by Claude Code's hooks:

  restore      SessionStart       print CFQM's inline part, kept under Claude Code's 10,000-character limit for hook
                                  output (past it a session gets a 2 KB preview and a file path instead), with how
                                  fresh it is and where the rest is
  precompact   PreCompact         snapshot CFQM.md, stamp its fingerprint and print instructions: Claude Code adds a
                                  PreCompact hook's output to the compaction prompt, so the compaction itself, with
                                  the whole conversation in view, writes CFQM's NOW and LOG lines
  postcompact  PostCompact        file that block from the compaction's summary into CFQM.md (the NOW it replaces goes
                                  to the archive); the oldest LOG lines rotate to the archive past the body's budget
  nudge        UserPromptSubmit   one line, rarely: many file edits since NOW was last written

and by hand:   status | init | stamp [--check | --print] | rotate        [--project DIR]  (default: this directory)

Settings (optional): <project>/.claude/cfqm.json with any of the keys in DEFAULTS. Standard library only. A hook
never fails the session: an error is reported in one line and the hook exits 0.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

VERSION = "1.1.2"
BODY_START = "## RESTORE CORE"
BODY_END = "<!-- end restore body -->"
INLINE_END = "<!-- end inline"
MAX_HOOK_TEXT = 9500     # Claude Code saves hook output over 10,000 characters to a file (the session sees a 2 KB
                         # preview) and cuts PreCompact output at 10,000: everything printed stays under both
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
TAIL_SCAN = 32 << 20     # a transcript's first look reads its last 32 MB (a long session's file can pass 400 MB)
MAX_EVENTS = 20000
ONCE_WINDOW = 90.0       # the same hook for the same session again within this many seconds is a duplicate (the
                         # plugin AND a project's own hooks both installed): the second does nothing
HOOKS = ("restore", "precompact", "postcompact", "nudge")

DEFAULTS = {
    "file": "CFQM.md",                   # the memory, relative to the project
    "archive": "CFQM_archive.md",        # where rotated LOG lines and replaced NOWs go (never loaded: grep it)
    "backups": ".claude/cfqm/backups",   # a snapshot before every compaction ("" = none)
    "state": ".claude/cfqm/state.json",  # the hooks' own bookkeeping
    "inline_budget": 8500,               # characters printed into the session; the rest is read on demand
    "body_budget": 40000,                # the whole body; past it the oldest LOG lines rotate to the archive
    "now_budget": 3000,                  # the NOW the compaction is asked to write
    "log_lines": 8,                      # LOG lines the compaction may add each time
    "nudge_edits": 40,                   # a reminder after this many file edits since NOW was written (0 = never)
    "nudge_hours": 2.0,                  # ...and at least this long since
    "also_read": [],                     # files the restore names as depth, read on demand
    "keep_snapshots": 0,                 # 0 = keep every snapshot
    "windows_notes": True,               # on Windows the restore adds windows_notes.md (Git Bash, the console, CRLF)
}

TEMPLATE = Path(__file__).resolve().parent.parent / "skills" / "cfqm" / "template.md"
WINDOWS_NOTES = Path(__file__).resolve().parent / "windows_notes.md"
IS_WINDOWS = sys.platform in ("win32", "cygwin", "msys")


# ---------------------------------------------------------------------------------------------------------- small


def _local(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else "never"


def _age(t):
    if not t:
        return "never"
    h = max(0.0, time.time() - t) / 3600
    if h < 1:
        return f"{h * 60:.0f} min ago"
    return f"{h:.1f} h ago" if h < 48 else f"{h / 24:.0f} days ago"


def _same(a, b):
    try:
        return bool(a) and bool(b) and (os.path.normcase(os.path.abspath(str(a)))
                                        == os.path.normcase(os.path.abspath(str(b))))
    except Exception:
        return False


def _iso(ts):
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _cut(s, n):
    """s cut to at most n characters at a line end; (text, characters dropped)."""
    if len(s) <= n:
        return s, 0
    k = s.rfind("\n", 0, n)
    k = k if k > n * 0.6 else n
    return s[:k].rstrip(), len(s) - k


def _hash(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def _read(path):
    """(text, newline) of a file, or (None, None). The text has '\\n' line ends; newline is the file's own."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None, None
    text = raw.decode("utf-8", errors="replace")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), nl


def _write(path, text, newline="\n"):
    """Write atomically (a temporary file beside it, then a rename), with the file's own line ends."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".cfqm-tmp")
    # errors="replace": a stray lone surrogate (from anywhere) costs one character, never the whole write
    with open(tmp, "w", encoding="utf-8", errors="replace", newline=newline) as fh:
        fh.write(text)
    os.replace(tmp, path)


def _hook_input():
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        # The BYTES, decoded as UTF-8: Claude Code sends its JSON as raw UTF-8 (nothing escaped), while Python's own
        # text stdin on Windows is the ANSI code page (cp1252 + surrogateescape on a pipe). That turned an em dash
        # into mojibake and the 0x8F byte inside an emoji into a lone surrogate no file write accepts (1.1.2: a
        # compaction's NOW was lost to "UnicodeEncodeError ... '\udc8f'").
        buf = getattr(sys.stdin, "buffer", None)
        raw = buf.read().decode("utf-8", errors="replace") if buf is not None else sys.stdin.read()
        d = json.loads(raw) if raw.strip() else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


@contextlib.contextmanager
def _locked(path):
    """One cfqm at a time per project (a duplicate hook waits, then sees the first one's record and stands down).
    Never hangs a hook: after 5 s it goes ahead unlocked; a lock older than 30 s is a crashed run's, removed."""
    lock = str(path) + ".lock"
    os.makedirs(os.path.dirname(lock) or ".", exist_ok=True)
    fd, deadline = None, time.time() + 5
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > 30:
                    os.remove(lock)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                break
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                os.remove(lock)
            except OSError:
                pass


# ------------------------------------------------------------------------------------------------- the document


# Markers count only at the start of a line: a header note that MENTIONS "## RESTORE CORE" isn't where the body starts
# (his own CFQM's note did, so its body - and fingerprint - began at the note line until 11-04).
_START_RE = re.compile(r"(?m)^" + re.escape(BODY_START))
_END_RE = re.compile(r"(?m)^" + re.escape(BODY_END))
_INLINE_RE = re.compile(r"(?m)^" + re.escape(INLINE_END))


def body_span(text):
    m = _START_RE.search(text)
    if not m:
        return None
    e = _END_RE.search(text, m.start())
    return (m.start(), e.start()) if e else None


def fingerprint(text):
    """sha256[:16] of the body: from the '## RESTORE CORE' heading up to the end-of-body marker, rstripped."""
    sp = body_span(text)
    return None if not sp else _hash(text[sp[0]:sp[1]].rstrip())


def stamped(text):
    m = re.search(r"(?m)^fingerprint:[ \t]*(\S+)[ \t]*$", text)
    return m.group(1) if m else None


def stamp(text, today=None):
    """(text with `fingerprint:` and `updated:` stamped to the body, changed?)."""
    fp = fingerprint(text)
    if fp is None or stamped(text) in (None, fp):
        return text, False
    today = today or _dt.date.today().isoformat()
    new = re.sub(r"(?m)^fingerprint:[ \t]*\S+[ \t]*$", f"fingerprint: {fp}", text, count=1)
    new = re.sub(r"(?m)^updated:[ \t]*\S+[ \t]*$", f"updated: {today}", new, count=1)
    return new, new != text


_STOP = re.compile(r"(?m)^(## |<!-- end inline|<!-- end restore body -->)")


def section(text, name):
    """(heading start, content start, end) of the body's '## <name>' section, else None. Its content runs to the
    next '## ' heading, the end-of-inline marker or the end of the body."""
    sp = body_span(text)
    if not sp:
        return None
    m = re.compile(rf"(?mi)^## {re.escape(name)}\b[^\n]*\n?").search(text, sp[0], sp[1])
    if not m:
        return None
    n = _STOP.search(text, m.end(), sp[1])
    return m.start(), m.end(), (n.start() if n else sp[1])


def section_text(text, name):
    s = section(text, name)
    return text[s[1]:s[2]].strip() if s else None


def inline_part(text):
    """(the body up to the end-of-inline marker, the body after it). No marker: all of it is inline."""
    sp = body_span(text)
    if not sp:
        return "", ""
    m = _INLINE_RE.search(text, sp[0], sp[1])
    if not m:
        return text[sp[0]:sp[1]].rstrip(), ""
    mk = m.start()
    close = text.find("-->", mk, sp[1])
    rest = text[close + 3:sp[1]] if close >= 0 else ""
    return text[sp[0]:mk].rstrip(), rest.strip()


def _headings(s):
    out = []
    for h in re.findall(r"(?m)^## ([^\n]+)", s or ""):
        h = re.split(r" \(| — | - |:", h, maxsplit=1)[0].strip()
        out.append(h[:40])
    return out


def _log_items(content):
    """(lines before the first item, [items]): an item is a line starting '- ' or '* ' plus the lines under it."""
    pre, items, cur = [], [], None
    for line in content.split("\n"):
        if re.match(r"^[-*] ", line):
            if cur is not None:
                items.append("\n".join(cur).rstrip())
            cur = [line]
        elif cur is not None:
            cur.append(line)
        else:
            pre.append(line)
    if cur is not None:
        items.append("\n".join(cur).rstrip())
    return [p for p in pre if p.strip()], [i for i in items if i.strip()]


# ------------------------------------------------------------------------------------------------------ context


class Ctx:
    def __init__(self, project, hook=None):
        self.project = Path(project).resolve()
        self.hook = hook or {}
        self.cfg, self.config_error = dict(DEFAULTS), None
        p = self.project / ".claude" / "cfqm.json"
        if p.is_file():
            try:
                user = json.loads(p.read_text(encoding="utf-8"))
                self.cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
            except Exception as e:
                self.config_error = f"{p}: {e}"
        self.file = self._p(self.cfg["file"])
        self.archive = self._p(self.cfg["archive"])
        self.backups = self._p(self.cfg["backups"]) if self.cfg["backups"] else None
        self.state_path = self._p(self.cfg["state"])
        self.state = {}

    def _p(self, rel):
        q = Path(str(rel))
        return q if q.is_absolute() else self.project / q

    def load_state(self):
        try:
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            self.state = {}
        return self.state

    def save_state(self):
        try:
            _write(self.state_path, json.dumps(self.state, indent=1))
        except Exception:
            pass

    def once(self, event, ident):
        """False when this event already ran for this ident moments ago (a duplicate hook)."""
        ran = self.state.setdefault("ran", {})
        prev, t = ran.get(event), time.time()
        if isinstance(prev, list) and len(prev) == 2 and prev[0] == ident and t - prev[1] < ONCE_WINDOW:
            return False
        ran[event] = [ident, t]
        return True

    def transcript(self):
        """The session's transcript: the hook's, else the last one seen, else this project's newest."""
        tp = self.hook.get("transcript_path")
        if tp and os.path.isfile(tp):
            return tp
        tp = (self.state.get("scan") or {}).get("path")
        if tp and os.path.isfile(tp):
            return tp
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.project)).lower()
        root = Path.home() / ".claude" / "projects"
        try:
            for d in root.iterdir():
                if d.is_dir() and d.name.lower() == slug:
                    files = sorted(d.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
                    return str(files[-1]) if files else None
        except OSError:
            pass
        return None


def track(ctx, text):
    """Notice what changed in the file since the last look: NOW's content (staleness counts from its last change)."""
    st = ctx.state
    nh = _hash(section_text(text, "NOW") or "")
    if st.get("now_hash") != nh:
        try:
            mt = os.path.getmtime(ctx.file)
        except OSError:
            mt = time.time()
        st["now_by"] = "hand" if st.get("now_hash") else "file"
        st["now_at"] = mt
        st["now_hash"] = nh
    st["body"] = fingerprint(text)


def scan(ctx, since):
    """File edits / shell commands Claude made after `since` (epoch seconds), read from the session's transcript:
    only what was added since the last look (the first look reads the last TAIL_SCAN bytes)."""
    st = ctx.state.setdefault("scan", {})
    tp = ctx.transcript()
    events = st.get("events") or []
    if tp and os.path.isfile(tp):
        size = os.path.getsize(tp)
        if not _same(st.get("path"), tp) or int(st.get("offset") or 0) > size:
            # a new transcript (a new session): its events join the ones kept (they carry their times)
            st["path"], start, first = str(tp), max(0, size - TAIL_SCAN), True
        else:
            start, first = int(st.get("offset") or 0), False
        with open(tp, "rb") as fh:
            fh.seek(start)
            data = fh.read(max(0, size - start))
        pos = 0
        if first and start > 0:                     # the tail starts mid-line: skip to the next whole one
            nl = data.find(b"\n")
            pos = nl + 1 if nl >= 0 else len(data)
        last = data.rfind(b"\n")
        end = last + 1 if last >= pos else pos      # a line still being written is read next time
        for line in data[pos:end].split(b"\n"):
            if b'"tool_use"' not in line or b'"assistant"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            msg = d.get("message")
            # only the assistant's own turns: Claude Code also logs "api-request-blob" lines (a request's payload,
            # the old assistant turns inside, no timestamp) that would count every past edit again as "now"
            if d.get("type") != "assistant" or not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            t = _iso(d.get("timestamp"))
            if t is None:
                continue
            for b in msg.get("content") or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                name = b.get("name") or ""
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                if name in EDIT_TOOLS:
                    f = str(inp.get("file_path") or inp.get("notebook_path") or "")
                    if not _same(f, ctx.file):
                        events.append([t, "edit", f])
                elif name == "Bash":
                    events.append([t, "bash", ""])
        st["offset"] = start + end
    keep = ctx.state.get("now_at") or 0
    seen, uniq = set(), []
    for e in events:                                # a forked / resumed transcript repeats the old lines
        k = (round(e[0], 3), e[1], e[2])
        if k not in seen and e[0] >= keep - 1:
            seen.add(k)
            uniq.append(e)
    st["events"] = uniq[-MAX_EVENTS:]
    ev = [e for e in st["events"] if e[0] >= (since or 0)]
    edits = [e for e in ev if e[1] == "edit"]
    per = {}
    for e in edits:
        k = os.path.basename(e[2]) or "?"
        per[k] = per.get(k, 0) + 1
    top = sorted(per.items(), key=lambda kv: -kv[1])[:5]
    return {"edits": len(edits), "files": len({os.path.normcase(e[2]) for e in edits}),
            "bash": sum(1 for e in ev if e[1] == "bash"),
            "top": ", ".join(f"{k} x{v}" for k, v in top)}


# --------------------------------------------------------------------------------------------- the archive


def archive_append(ctx, title, content):
    content = (content or "").strip()
    if not content:
        return
    text, nl = _read(ctx.archive)
    if text is None:
        text, nl = ("# CFQM archive\n\nWhat rotated out of CFQM.md, oldest first. The cfqm plugin appends here; "
                    "nothing in it is loaded into a session: grep it.\n"), "\n"
    _write(ctx.archive, text.rstrip("\n") + f"\n\n## {title}\n\n{content}\n", nl)


def rotate(ctx, text):
    """The oldest LOG items moved to the archive until the body is under its budget (to 90 % of it, so it doesn't
    rotate a line at every compaction). (text, items moved)."""
    budget = int(ctx.cfg["body_budget"])
    sp = body_span(text)
    if not sp or sp[1] - sp[0] <= budget:
        return text, 0
    s = section(text, "LOG")
    if not s:
        return text, 0
    pre, items = _log_items(text[s[1]:s[2]])
    over = (sp[1] - sp[0]) - int(budget * 0.9)
    moved = []
    while items and over > 0:
        it = items.pop()
        moved.insert(0, it)
        over -= len(it) + 1
    if not moved:
        return text, 0
    archive_append(ctx, f"LOG, rotated out {_local(time.time())}", "\n".join(moved))
    body = "\n".join(pre + items)
    return text[:s[1]] + (body + "\n\n" if body else "\n") + text[s[2]:], len(moved)


# ------------------------------------------------------------------------------------------------------ hooks


def cmd_restore(ctx, argv):
    text, nl = _read(ctx.file)
    if text is None or not body_span(text):
        return ""
    src = ctx.hook.get("source") or "start"
    if not ctx.once("restore", f"{ctx.hook.get('session_id')}|{src}"):
        return ""
    new, changed = stamp(text)
    if changed:
        _write(ctx.file, new, nl)
        text = new
    track(ctx, text)
    st = ctx.state
    lc = st.get("last_compaction") or {}
    fresh = lc.get("at") and time.time() - lc["at"] < 600
    if src == "compact" and fresh and lc.get("refreshed") is None:
        how = "being rewritten from this compaction's summary"
    elif src == "compact" and fresh and lc.get("refreshed") is False:
        how = (f"NOT rewritten by this compaction ({lc.get('why', '?')}): it dates from {_local(st.get('now_at'))}"
               f", {lc.get('edits', 0)} file edits before this compaction. Rewrite it from the summary above "
               f"(the cfqm skill)")
    elif st.get("now_by") == "compaction":
        how = f"written by the compaction of {_local(st.get('now_at'))}"
    else:
        how = f"last changed {_local(st.get('now_at'))} ({_age(st.get('now_at'))})"
    head = [f"=== CFQM: this project's session memory ({ctx.file}) ===",
            f"fingerprint {fingerprint(text)} | NOW {how}."]
    if src == "compact":
        head.append("The summary above is the newer account of the latest work: where it and NOW differ, trust it.")
    elif src in ("resume", "clear", "startup", "start"):
        c = scan(ctx, st.get("now_at"))
        if c["edits"] >= max(1, int(ctx.cfg["nudge_edits"] or 40)):
            head.append(f"NOW may be behind: {c['edits']} file edits since it was written ({c['top']}).")
    if ctx.config_error:
        head.append(f"(cfqm settings unreadable, defaults used: {ctx.config_error})")
    inline, rest = inline_part(text)
    hs = _headings(rest)
    tail = ["", "--- on demand ---"]
    if rest:
        tail.append(f"The rest of CFQM ({', '.join(hs) or 'more'}; {len(rest) / 1024:.0f} KB): Read {ctx.file}"
                    + (f' from "## {hs[0]}"' if hs else "") + ".")
    if ctx.archive.exists():
        tail.append(f"Older history: grep {ctx.archive} (never loaded).")
    also = [str(ctx._p(a)) for a in ctx.cfg["also_read"] or [] if ctx._p(a).exists()]
    if also:
        tail.append("Depth, read when the work needs it: " + "; ".join(also) + ".")
    sp = body_span(text)
    if sp[1] - sp[0] > int(ctx.cfg["body_budget"]):
        tail.append(f"(CFQM's body is {sp[1] - sp[0]:,} characters, over its {int(ctx.cfg['body_budget']):,} "
                    f"budget: trim THREADS, or `cfqm.py rotate` moves the oldest LOG lines out.)")
    ib = int(ctx.cfg["inline_budget"])
    tail = place_notes(head, tail, inline, ib, windows_notes(ctx))
    limit = min(ib, _room(head, tail))
    if len(inline) <= limit:
        shown = inline
    else:
        shown, dropped = _cut(inline, max(500, limit - 300))
        shown += (f"\n\n[... {len(inline) - len(shown):,} more characters of CFQM's inline part are not shown: "
                  f"it is over the {limit:,} characters this restore has room for. Read the file for them, then "
                  f"trim it (the cfqm skill).]")
    return "\n".join(head) + "\n\n" + shown + "\n" + "\n".join(tail)


def _room(head, tail):
    """Characters left for CFQM's inline part once the restore's own lines are counted."""
    return MAX_HOOK_TEXT - len("\n".join(head)) - len("\n".join(tail)) - 10


def windows_notes(ctx):
    """The plugin's Windows notes (Git Bash's halved backslashes, the cp1252 console, CRLF...), on Windows only."""
    if not IS_WINDOWS or not ctx.cfg.get("windows_notes", True):
        return ""
    t, _ = _read(WINDOWS_NOTES)
    return _cut((t or "").strip(), 1800)[0]


def place_notes(head, tail, inline, inline_budget, notes):
    """The user's own memory comes first: the notes go in whole only while the inline part still fits whole beside
    them; otherwise one line says where they are."""
    if not notes:
        return tail
    full = tail + ["", notes]
    if len(inline) <= min(inline_budget, _room(head, full)):
        return full
    return tail + ["", f"Windows notes (Git Bash's halved backslashes, the cp1252 console, CRLF): Read {WINDOWS_NOTES}"
                       " before running shell commands."]


def _snapshot(ctx):
    if not ctx.backups:
        return None
    ctx.backups.mkdir(parents=True, exist_ok=True)
    stem = Path(ctx.cfg["file"]).stem
    dst = ctx.backups / f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}.md"
    dst.write_bytes(ctx.file.read_bytes())
    keep = int(ctx.cfg["keep_snapshots"] or 0)
    if keep > 0:
        snaps = sorted(ctx.backups.glob(f"{stem}_????????_??????.md"))
        for old in snaps[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass
    return dst


def instructions(ctx, text):
    now = section_text(text, "NOW")
    if now is None:
        now = "(the file has no NOW section yet: yours starts it)"
    now = re.sub(r"(?m)^<!-- written by the compaction[^\n]*-->\n?", "", now).strip() or "(empty)"
    nb, nl = int(ctx.cfg["now_budget"]), int(ctx.cfg["log_lines"])
    head = (
        f"CFQM, this project's session memory ({ctx.file}), is restored into the next session from what you write "
        f"here. End your summary with this block, filled in from the conversation:\n\n"
        f"<cfqm-refresh>\n## NOW\n- ...\n## LOG\n- {_dt.date.today().isoformat()}: ...\n</cfqm-refresh>\n\n"
        f"NOW = the state as of this compaction, for whoever picks the work up next: what is in flight (files, "
        f"functions, what is left), the next steps in order, and any decision or rule the user set that must "
        f"outlast this conversation. Plain bullets, at most {nb:,} characters, no history.\n"
        f"LOG = one dated line per thing finished or decided since the last compaction, newest first, at most "
        f"{nl} lines.\n"
        f"Start from the NOW the file holds (below): keep what is still true, drop what is done, add what is new.\n\n"
        f"<current-now>\n")
    room = MAX_HOOK_TEXT - len(head) - 40
    now, dropped = _cut(now, room)
    if dropped:
        now += f"\n[... {dropped:,} more characters]"
    return head + now + "\n</current-now>"


def cmd_precompact(ctx, argv):
    text, nl = _read(ctx.file)
    if text is None or not body_span(text):
        return ""
    if not ctx.once("precompact", str(ctx.hook.get("session_id"))):
        return ""
    _snapshot(ctx)
    new, changed = stamp(text)
    if changed:
        _write(ctx.file, new, nl)
        text = new
    track(ctx, text)
    c = scan(ctx, ctx.state.get("now_at"))
    ctx.state["last_compaction"] = {"at": time.time(), "session": ctx.hook.get("session_id"),
                                    "trigger": ctx.hook.get("trigger"), "refreshed": None,
                                    "edits": c["edits"], "files": c["files"]}
    return instructions(ctx, text)


_BLOCK = re.compile(r"<cfqm-refresh>(.*?)</cfqm-refresh>", re.S | re.I)


def extract(ctx, summary):
    """(NOW, [LOG lines]) from the last <cfqm-refresh> block of a compaction's summary, else None."""
    blocks = _BLOCK.findall(summary or "")
    if not blocks:
        return None
    b = re.sub(r"(?m)^[ \t]*```[A-Za-z]*[ \t]*$", "", blocks[-1])
    m_log = re.search(r"(?mi)^[ \t]*#{1,6}[ \t]*LOG\b[^\n]*$", b)
    m_now = re.search(r"(?mi)^[ \t]*#{1,6}[ \t]*NOW\b[^\n]*$", b)
    if m_now and (not m_log or m_now.start() < m_log.start()):
        now = b[m_now.end():m_log.start() if m_log else len(b)]
    else:
        now = b[:m_log.start()] if m_log else b
    now = now.strip()
    if not re.sub(r"[-*.\s…]", "", now):        # only the form's own "- ..." copied back: nothing written
        now = ""
    log = []
    today = _dt.date.today().isoformat()
    for line in (b[m_log.end():] if m_log else "").splitlines():
        s = line.strip()
        if not s.startswith(("- ", "* ")) or len(s) < 4:
            continue
        s = s[2:].strip()
        if not re.sub(r"[-*.:\s…\d]", "", s):    # "2026-11-04: ..." = the form, not a line
            continue
        if not re.match(r"^(\*\*)?\d{4}-\d{2}-\d{2}", s):
            s = f"{today}: {s}"
        log.append("- " + _cut(s, 400)[0])
    now, dropped = _cut(now, int(int(ctx.cfg["now_budget"]) * 1.2))   # bounded: NOW is printed in every restore
    if dropped:
        now += f"\n- [... {dropped:,} more characters dropped: over the NOW budget]"
    return now, log[:2 * int(ctx.cfg["log_lines"])]


def apply_refresh(ctx, text, now_new, log_new):
    stampline = f"<!-- written by the compaction of {_local(time.time())} -->"
    s = section(text, "NOW")
    if s:
        old = text[s[1]:s[2]].strip()
        text = text[:s[1]] + now_new.strip() + "\n" + stampline + "\n\n" + text[s[2]:]
    else:
        old = ""
        sp = body_span(text)
        mk = _INLINE_RE.search(text, sp[0], sp[1])
        at = mk.start() if mk else sp[1]
        text = text[:at] + "## NOW\n" + now_new.strip() + "\n" + stampline + "\n\n" + text[at:]
    if log_new:
        s = section(text, "LOG")
        if s:
            pre, items = _log_items(text[s[1]:s[2]])
            body = "\n".join(pre + log_new + items)
            text = text[:s[1]] + body + "\n\n" + text[s[2]:]
        else:
            sp = body_span(text)
            text = text[:sp[1]] + "## LOG\n" + "\n".join(log_new) + "\n\n" + text[sp[1]:]
    if old and _hash(old) != _hash(now_new.strip()):
        archive_append(ctx, f"NOW as of {_local(ctx.state.get('now_at'))}, replaced by the compaction of "
                            f"{_local(time.time())}", old)
    return text


def cmd_postcompact(ctx, argv):
    text, nl = _read(ctx.file)
    if text is None or not body_span(text):
        return ""
    summary = ctx.hook.get("compact_summary") or ""
    if not ctx.once("postcompact", f"{ctx.hook.get('session_id')}|{_hash(summary)}"):
        return ""
    lc = ctx.state.setdefault("last_compaction", {})
    lc.setdefault("at", time.time())
    got = extract(ctx, summary)
    why = None
    if got is None:
        why = "the summary was empty" if not summary.strip() else "no <cfqm-refresh> block in its summary"
    elif not got[0]:
        why = "the block's NOW was empty"
    if why:
        lc["refreshed"], lc["why"] = False, why
        return f"cfqm: NOW not rewritten ({why}); the restore says so."
    now_new, log_new = got
    text = apply_refresh(ctx, text, now_new, log_new)
    text, moved = rotate(ctx, text)
    text, _ = stamp(text)
    _write(ctx.file, text, nl)
    ctx.state["now_hash"] = _hash(section_text(text, "NOW") or "")
    ctx.state["now_at"] = time.time()
    ctx.state["now_by"] = "compaction"
    ctx.state["body"] = fingerprint(text)
    lc["refreshed"], lc["why"] = True, None
    ctx.state.get("nudged", {}).clear()
    return (f"cfqm: NOW rewritten by the compaction ({len(now_new):,} characters), {len(log_new)} LOG line(s) "
            f"added" + (f", {moved} old LOG item(s) rotated to {ctx.archive.name}" if moved else "")
            + f"; fingerprint {fingerprint(text)}.")


def cmd_nudge(ctx, argv):
    n = int(ctx.cfg["nudge_edits"] or 0)
    if n <= 0:
        return ""
    text, nl = _read(ctx.file)
    if text is None or not body_span(text):
        return ""
    track(ctx, text)
    since = ctx.state.get("now_at") or 0
    c = scan(ctx, since)
    level = c["edits"] // n
    hours = (time.time() - since) / 3600 if since else 0.0
    key = f"{ctx.hook.get('session_id')}|{ctx.state.get('now_hash')}"
    done = ctx.state.setdefault("nudged", {})
    if level < 1 or hours < float(ctx.cfg["nudge_hours"]) or int(done.get(key, 0)) >= level:
        return ""
    done.clear()
    done[key] = level
    return (f"[cfqm] {c['edits']} file edits ({c['files']} files) since CFQM's NOW was written ({_age(since)}). At "
            f"the next natural milestone, rewrite NOW in {ctx.file} to the state as it is now (the cfqm skill); "
            f"every compaction rewrites it too.")


# ---------------------------------------------------------------------------------------------------- by hand


def cmd_status(ctx, argv):
    text, _ = _read(ctx.file)
    if text is None:
        return f"cfqm: no {ctx.file} (`cfqm.py init` makes one from the template)."
    if not body_span(text):
        return f"cfqm: {ctx.file} has no body markers ({BODY_START!r} ... {BODY_END!r})."
    track(ctx, text)
    fp, stp = fingerprint(text), stamped(text)
    inline, rest = inline_part(text)
    sp = body_span(text)
    ib, bb = int(ctx.cfg["inline_budget"]), int(ctx.cfg["body_budget"])
    st = ctx.state
    c = scan(ctx, st.get("now_at"))
    lc = st.get("last_compaction") or {}
    lines = [f"CFQM: {ctx.file}",
             f"  fingerprint {fp}" + ("" if stp == fp else f"  (stamped {stp}: stale, `cfqm.py stamp` fixes it)"),
             f"  inline part {len(inline):,} / {ib:,} characters" + ("  OVER" if len(inline) > ib else "")
             + f"; body {sp[1] - sp[0]:,} / {bb:,}" + ("  OVER" if sp[1] - sp[0] > bb else ""),
             f"  NOW: by {st.get('now_by', '?')}, {_local(st.get('now_at'))} ({_age(st.get('now_at'))}); since then "
             f"{c['edits']} file edits ({c['files']} files){': ' + c['top'] if c['top'] else ''}, {c['bash']} "
             f"shell commands"]
    if lc:
        r = {True: "NOW rewritten", False: f"NOW not rewritten ({lc.get('why')})", None: "pending"}
        lines.append(f"  last compaction: {_local(lc.get('at'))} ({lc.get('trigger') or '?'}): "
                     f"{r.get(lc.get('refreshed'), '?')}")
    if ctx.archive.exists():
        lines.append(f"  archive: {ctx.archive} ({ctx.archive.stat().st_size / 1024:.0f} KB)")
    if ctx.backups and ctx.backups.exists():
        lines.append(f"  snapshots: {len(list(ctx.backups.glob('*.md')))} in {ctx.backups}")
    if ctx.config_error:
        lines.append(f"  settings unreadable, defaults used: {ctx.config_error}")
    return "\n".join(lines)


def cmd_init(ctx, argv):
    if ctx.file.exists():
        return f"cfqm: {ctx.file} already exists; left as it is."
    t, _ = _read(TEMPLATE)
    if t is None:
        return f"cfqm: the template is missing ({TEMPLATE})."
    t, _ = stamp(t)
    _write(ctx.file, t)
    return f"cfqm: made {ctx.file} from the template. Fill in RESTORE CORE and HARD CONSTRAINTS; NOW fills itself."


def cmd_stamp(ctx, argv):
    text, nl = _read(ctx.file)
    if text is None or not body_span(text):
        return f"cfqm: no CFQM body at {ctx.file}"
    if "--print" in argv:
        return fingerprint(text)
    new, changed = stamp(text)
    if "--check" in argv:
        ctx.exit_code = 1 if changed else 0
        return f"CFQM fingerprint {'STALE' if changed else 'ok'} (body={fingerprint(text)}, stamped={stamped(text)})"
    if changed:
        _write(ctx.file, new, nl)
        return f"CFQM fingerprint stamped {stamped(text)} -> {fingerprint(new)}"
    return f"CFQM fingerprint ok ({fingerprint(text)}) - no change"


def cmd_rotate(ctx, argv):
    text, nl = _read(ctx.file)
    if text is None or not body_span(text):
        return f"cfqm: no CFQM body at {ctx.file}"
    text, moved = rotate(ctx, text)
    if not moved:
        return "cfqm: nothing to rotate (the body is within its budget, or LOG is empty)."
    text, _ = stamp(text)
    _write(ctx.file, text, nl)
    return f"cfqm: {moved} LOG item(s) moved to {ctx.archive}."


HANDLERS = {"restore": cmd_restore, "precompact": cmd_precompact, "postcompact": cmd_postcompact,
            "nudge": cmd_nudge, "status": cmd_status, "init": cmd_init, "stamp": cmd_stamp, "rotate": cmd_rotate}


def _project(argv, hook):
    if "--project" in argv:
        i = argv.index("--project")
        if i + 1 < len(argv):
            return argv[i + 1]
    return os.environ.get("CLAUDE_PROJECT_DIR") or hook.get("cwd") or os.getcwd()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--version" in argv:
        print(f"cfqm {VERSION}")
        return 0
    cmd = argv[0] if argv and argv[0] in HANDLERS else "status"
    hook = _hook_input() if cmd in HOOKS else {}
    try:
        ctx = Ctx(_project(argv, hook), hook)
        ctx.exit_code = 0
        if not ctx.file.is_file():              # no CFQM here: the hooks leave no trace (no state, no lock)
            out = "" if cmd in HOOKS else HANDLERS[cmd](ctx, argv)
            if out:
                print(out)
            return ctx.exit_code
        with _locked(ctx.state_path):
            ctx.load_state()
            out = HANDLERS[cmd](ctx, argv)
            ctx.save_state()
        if out:
            print(out)
        return ctx.exit_code
    except Exception as e:                      # a hook never breaks the session
        msg = f"cfqm {cmd}: skipped ({type(e).__name__}: {e})"
        if cmd == "restore":
            print(f"[{msg}. Read CFQM.md yourself.]")
        elif cmd == "postcompact" or cmd not in HOOKS:
            print(msg)
        else:
            print(msg, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
