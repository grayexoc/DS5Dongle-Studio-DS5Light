"""Reject compile databases from another checkout or a missing explicit build."""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from test_support import firmware_build

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary) / 'source'
    build = Path(temporary) / 'external-build'
    root.mkdir(); build.mkdir()
    database = build / 'compile_commands.json'
    database.write_text(json.dumps([{'file': str(root / 'src/audio.cpp')}]))
    with patch.dict(os.environ, DS5_FIRMWARE_BUILD=str(build)):
        assert firmware_build(root) == build
        database.write_text(json.dumps([{'file': str(root / 'other/audio.cpp')}]))
        try:
            firmware_build(root)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Another checkout was accepted')
        database.unlink()
        try:
            firmware_build(root)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Missing explicit build was silently replaced')
print('PASS: explicit external build selected; foreign and missing databases rejected')
