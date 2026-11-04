#!/bin/sh
# cfqm's launcher: runs cfqm.py with the first Python 3.8+ that actually starts ($CFQM_PYTHON, python3, python,
# py -3). A bare `python3` isn't enough: on Windows it is often the Microsoft Store's stub ("Python was not found").
# The plugin's folder comes from $CLAUDE_PLUGIN_ROOT (Claude Code sets it for plugin hooks); a backslashed Windows
# path in $0 has no '/' for dirname to split on.
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "$CLAUDE_PLUGIN_ROOT/scripts/cfqm.py" ]; then
  script="$CLAUDE_PLUGIN_ROOT/scripts/cfqm.py"
else
  script="$(dirname -- "$0")/cfqm.py"
fi
for py in "${CFQM_PYTHON:-}" python3 python "py -3"; do
  [ -n "$py" ] || continue
  if $py -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    exec $py "$script" "$@"
  fi
done
echo "cfqm: no Python 3.8+ found (set CFQM_PYTHON to one)" >&2
exit 0
