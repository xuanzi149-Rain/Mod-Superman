"""Online SQLite backup and cleanup limited to expired generated UUID artifacts."""
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta


def maintain(service):
    backup = service.root / 'backups'
    backup.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc)
    destination = backup / (stamp.strftime('%Y-%m-%d') + '.sqlite3')
    with service.store.connect() as source:
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
    with service.lock:
        with service.store.connect() as db:
            records = db.execute("SELECT id,payload FROM records WHERE kind='plans'").fetchall()
        import json
        for identifier, payload in records:
            plan = json.loads(payload)
            if not plan.get('generated_at') or datetime.fromisoformat(plan['generated_at']) >= stamp-timedelta(days=7):
                continue
            identifier = str(uuid.UUID(identifier))
            archive = service.root / 'downloads' / (identifier + '.zip')
            if archive.is_file():
                archive.unlink()
            package = plan.get('package_id')
            if package:
                directory = (service.root / 'packages' / str(uuid.UUID(package))).resolve()
                if directory.parent == (service.root / 'packages').resolve() and directory.is_dir():
                    shutil.rmtree(directory)
    for old in backup.glob('*.sqlite3'):
        if old.name < (stamp-timedelta(days=7)).strftime('%Y-%m-%d')+'.sqlite3':
            old.unlink()
