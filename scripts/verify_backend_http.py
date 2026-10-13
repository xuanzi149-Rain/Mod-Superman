"""Start a temporary local server, inspect HTTP routes, then stop it."""
import json
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from scripts.generate_mod import ROOT


def main():
    directory = ROOT / 'build/backend'
    directory.mkdir(parents=True, exist_ok=True)
    opener = build_opener(ProxyHandler({}))
    with (directory / 'http-smoke.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app:app',
                                    '--host', '127.0.0.1', '--port', '18083', '--workers', '1'],
                                   cwd=ROOT, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for attempt in range(50):
                if process.poll() is not None:
                    raise RuntimeError('Local server exited; see http-smoke.log')
                try:
                    with opener.open('http://127.0.0.1:18083/api/equipment?limit=1', timeout=1) as response:
                        result = json.load(response)
                    break
                except URLError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Local server did not become ready')
            assert result['total'] == 1872
            with opener.open('http://127.0.0.1:18083/openapi.json', timeout=2) as response:
                schema = json.load(response)
            assert '/api/previews' in schema['paths']
            assert not any('healing' in path for path in schema['paths'])
            report = {'http_catalog': 'passed', 'openapi': 'passed', 'items_count': result['total'],
                      'server': 'temporary 127.0.0.1:18083', 'public_deployment': 'not_performed'}
            (directory / 'http-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
