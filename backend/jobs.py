"""Bounded, single-worker packaging. Persist claims before dispatch."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from backend.service import ServiceError, read_record, write_json


class Jobs:
    def __init__(self, service):
        self.service = service
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mod-package')
        self.slots = BoundedSemaphore(3)
        self.active = set()
        # Only run with one application process. Recover records from its predecessor.
        for path in (service.root / 'plans').glob('*.json'):
            service.read(path.stem)  # Import legacy snapshots into SQLite if needed.
        with service.store.connect() as db:
            identifiers = [row[0] for row in db.execute("SELECT id FROM records WHERE kind='plans'")]
        for identifier in identifiers:
            plan = service.read(identifier)
            if plan['status'] in ('queued', 'generating'):
                plan.update(status='interrupted', failure_stage='service_restart')
                write_json(service.path(identifier), plan)

    def submit(self, identifier, confirmed, experimental):
        s = self.service
        with s.lock:
            plan = s.read(identifier)
            if confirmed is not True:
                raise ServiceError('confirmation_required', '请确认参数。')
            if plan['status'] in ('queued', 'generating', 'succeeded'):
                return {k: v for k, v in plan.items() if k != 'error'}
            if plan['status'] != 'preview':
                raise ServiceError('new_preview_required', '请重新预览并确认后重试。')
            if plan['versions'] != s.versions():
                raise ServiceError('stale_preview', '目录或模板已变化，请重新预览。')
            if plan['experimental'] and experimental is not True:
                raise ServiceError('experimental_confirmation_required', '请接受未验证方案的试验提示。')
            if plan.get('ai_session'):
                state = read_record(s.root / 'ai_sessions' / (plan['ai_session'] + '.json')) or {}
                if state.get('version') != plan['ai_version'] or state.get('inflight') or state.get('questions') or state.get('unsupported'):
                    raise ServiceError('stale_ai_preview', '草稿已变化或仍有问题，请重新预览。')
            if not self.slots.acquire(blocking=False):
                raise ServiceError('generation_capacity', '制作任务已满，请稍后重试。', 429)
            plan.update(status='queued', confirmed=True, accept_experimental=experimental)
            write_json(s.path(identifier), plan)
            self.active.add(identifier)
            try:
                self.executor.submit(self.run, identifier, experimental)
            except Exception:
                self.active.discard(identifier)
                self.slots.release()
                plan.update(status='interrupted', failure_stage='dispatch')
                write_json(s.path(identifier), plan)
                raise
            return plan

    def run(self, identifier, experimental):
        try:
            self.service.confirm_generate(identifier, True, experimental, queued=True)
        except Exception:
            with self.service.lock:
                plan = self.service.read(identifier)
                if plan['status'] in ('queued', 'generating'):
                    plan.update(status='failed', failure_stage='preparation')
                    write_json(self.service.path(identifier), plan)
        finally:
            self.active.discard(identifier)
            self.slots.release()

    def close(self):
        self.executor.shutdown(wait=True)
