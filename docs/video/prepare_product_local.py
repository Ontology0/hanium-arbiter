"""Download the public source package and start an isolated first-run workspace.

Run only after the parent confirms the final deployed build is ready to capture.
All files, logs, and the database stay under docs/video/work/product/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
WORK = HERE / 'work' / 'product'
PUBLIC = 'https://culture-fit-demo-production.up.railway.app'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8896)
    args = parser.parse_args()
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', args.port)) == 0:
            raise RuntimeError(f'Port {args.port} already in use; do not replace another server')
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / 'source-first-run'
    if target.exists():
        raise RuntimeError('First-run extraction already exists. Preserve it and choose a new capture run.')
    packages = {}
    for name in ('source', 'skill'):
        url = f'{PUBLIC}/static/downloads/culture-fit-{name}.zip'
        path = WORK / f'culture-fit-{name}.zip'
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
        packages[name] = {'url': url, 'file': str(path.relative_to(HERE)),
                          'bytes': path.stat().st_size,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    with zipfile.ZipFile(WORK / 'culture-fit-source.zip') as archive:
        for entry in archive.infolist():
            resolved = (target / entry.filename).resolve()
            if not resolved.is_relative_to(target.resolve()):
                raise RuntimeError('Archive path escapes the video-owned directory')
        archive.extractall(target)
    projects = list(target.rglob('pyproject.toml'))
    if len(projects) != 1:
        raise RuntimeError(f'Expected one extracted project, found {len(projects)}')
    project = projects[0].parent
    database = WORK / 'first-run.sqlite3'
    if database.exists():
        raise RuntimeError('First-run database already exists')
    env = dict(os.environ, ARBITER_PORT=str(args.port), ARBITER_DB=str(database))
    logfile = WORK / 'first-run-server.log'
    with logfile.open('wb') as output:
        process = subprocess.Popen(['bash', './start-macos.sh'], cwd=project,
                                   env=env, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    receipt = {'source': packages, 'platform': 'macOS', 'command': ['bash', './start-macos.sh'],
               'cwd': str(project.relative_to(HERE)), 'port': args.port, 'pid': process.pid,
               'database': str(database.relative_to(HERE)), 'log': str(logfile.relative_to(HERE)),
               'local_url': f'http://127.0.0.1:{args.port}',
               'windows_execution': 'not performed; instructions are shown only', 'ready': False}
    receipt_path = WORK / 'first-run-receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    for _ in range(240):
        if process.poll() is not None:
            raise RuntimeError(f'Launch exited {process.returncode}; inspect {logfile}')
        try:
            with urllib.request.urlopen(receipt['local_url'] + '/api/health', timeout=1) as response:
                receipt['health_status'] = response.status
            with urllib.request.urlopen(receipt['local_url'] + '/api/sessions', timeout=2) as response:
                receipt['initial_sessions'] = json.load(response)
            receipt['ready'] = True
            receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
            print(json.dumps(receipt, indent=2), flush=True)
            return
        except OSError:
            time.sleep(.5)
    raise RuntimeError('Local source launch did not become ready in 120 seconds')


if __name__ == '__main__':
    main()
