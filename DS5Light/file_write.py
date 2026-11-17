"""Replace a text file only after its complete contents have been written."""
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def replace_text(path, payload):
    path = Path(path)
    name = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
            name = file.name
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        if name:
            Path(name).unlink(missing_ok=True)
