#!/usr/bin/env python3
import sys
from pathlib import Path
root = Path('/home/rick/Paradox/Documents/Europa Universalis V/mod/Imperator Universalis')
changed = []
for p in root.rglob('setup/start/*.txt'):
    try:
        data = p.read_bytes()
    except Exception as e:
        print(f"skip {p}: {e}")
        continue
    if data.startswith(b'\xef\xbb\xbf'):
        new = data[3:]
        p.write_bytes(new)
        changed.append(str(p.relative_to(root)))
        print(f"Stripped BOM: {p}")
print(f"Done. Files changed: {len(changed)}")
if len(changed) > 0:
    sys.exit(0)
else:
    sys.exit(0)
