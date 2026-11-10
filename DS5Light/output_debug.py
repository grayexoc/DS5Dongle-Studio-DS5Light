"""Temporary output identification diagnostics, with bounded disk usage."""
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from threading import RLock

_lock = RLock()
_logger = None
_last = {}

def _token(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:16] if value else None

def _row(row):
    fields = ('name', 'index', 'hostApi', 'maxOutputChannels', 'maxInputChannels',
              'isLoopbackDevice', 'defaultSampleRate')
    result = {key: row[key] for key in fields if key in row}
    for key in ('id', 'endpoint_id', 'container_id', 'hid_path', 'serial'):
        if key in row:result[key] = _token(row[key])
    return result

def record(event, rows=(), binding=None, requested=None, endpoints=None, error=None):
    global _logger
    try:
        data = dict(event=event, requested=requested, devices=[_row(row) for row in rows])
        if binding is not None:
            from dataclasses import asdict
            data['binding'] = _row(asdict(binding.snapshot()))
        if endpoints is not None:data['windows_endpoints'] = [_row(row) for row in endpoints]
        if error is not None:data['error'] = str(error)
        message = json.dumps(data, ensure_ascii=False, sort_keys=True)
        with _lock:
            if _last.get(event) == message:return
            if _logger is None:
                base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
                directory = base / 'logs'
                directory.mkdir(exist_ok=True)
                handler = RotatingFileHandler(directory / 'output-debug.log', maxBytes=1_000_000,
                                             backupCount=2, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
                _logger = logging.getLogger('ds5light.output-debug')
                _logger.setLevel(logging.INFO)
                _logger.propagate = False
                _logger.addHandler(handler)
            _logger.info(message)
            _last[event] = message
    except Exception:
        # A read-only installation must still be able to start audio.
        pass
