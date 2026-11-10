"""Find compile settings belonging to this checkout; never use another source tree."""
from pathlib import Path
import json

def firmware_build(root):
    root = root.resolve()
    candidates = sorted((root / 'build').glob('*/compile_commands.json'),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        rows = json.loads(path.read_text(encoding='utf-8'))
        if any(Path(row['file']).resolve() == root / 'src/audio.cpp' for row in rows):
            return path.parent
    raise RuntimeError('Configure this checkout with CMAKE_EXPORT_COMPILE_COMMANDS=ON before ARM syntax tests')
