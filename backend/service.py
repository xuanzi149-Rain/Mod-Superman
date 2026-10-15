"""Persist previews and generate only their confirmed immutable parameters.

Local single-process service: a lock serializes state transitions and packaging.
"""
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from backend.storage import Store, now
from backend.instructions import delivery_instructions
from backend.equipment_presentation import presentation

from scripts.equipment_catalog import CATALOG_PATH, load_catalog
from scripts.generate_equipment import FIELDS, RULES, generate, validate_request
from scripts.generate_mod import DIVINE, ROOT


class ServiceError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    if path.parent.name in ('plans', 'ai_sessions'):
        Store(path.parent.parent).snapshot(path.parent.name, path.stem, value)


def read_record(path):
    store = Store(path.parent.parent)
    value = store.get(path.parent.name, path.stem)
    if value is None and path.exists():
        value = json.loads(path.read_text(encoding='utf-8'))
        store.snapshot(path.parent.name, path.stem, value)
    return value


class EquipmentService:
    def __init__(self, root=None, catalog_path=CATALOG_PATH, packager=None):
        root = root or os.environ.get('MOD_DATA_DIR', ROOT / 'build/backend')
        packager = packager or os.environ.get('MOD_PACKAGER', DIVINE)
        self.root, self.catalog_path, self.packager = Path(root), Path(catalog_path), Path(packager)
        self.lock = RLock()
        self.store = Store(self.root)

    def versions(self):
        paths = [ROOT / 'templates/module.lsx', ROOT / 'scripts/generate_equipment.py',
                 ROOT / 'scripts/generate_mod.py', ROOT / 'backend/service.py', ROOT / 'backend/instructions.py']
        return {'catalog_sha256': digest(self.catalog_path),
                'generator_sha256': hashlib.sha256(''.join(digest(p) for p in paths).encode()).hexdigest()}

    def catalog(self):
        return load_catalog(self.catalog_path)

    def detail(self, object_id):
        item = self.catalog()['items'].get(object_id)
        if item is None:
            raise ServiceError('unknown_object', '请选择目录中的装备对象。', 404)
        return {**item, 'presentation': presentation(item), 'field_rules': {k: RULES[k] for k in item['capabilities']},
                'validation_note': '目录对象是候选；历史用户报告不代表本次生成包已游戏验证。'}

    def path(self, plan_id):
        try:
            identifier = str(uuid.UUID(plan_id))
        except (ValueError, AttributeError):
            raise ServiceError('unknown_plan', '制作方案不存在。', 404)
        return self.root / 'plans' / (identifier + '.json')

    def read(self, plan_id):
        path = self.path(plan_id)
        value = read_record(path)
        if value is None:
            raise ServiceError('unknown_plan', '制作方案不存在。', 404)
        return value

    def preview(self, request):
        with self.lock:
            catalog = self.catalog()
            clean, warnings = validate_request(request, catalog=catalog, allow_unverified=True)
            item = catalog['items'][clean['object']]
            changes = []
            for field, value in clean['changes'].items():
                original = item['display_name'] if field == 'name' else item['original'].get(FIELDS[field])
                changes.append({'field': field, 'original': original, 'new': value, 'rule': RULES[field]})
            plan = {'plan_id': str(uuid.uuid4()), 'status': 'preview', 'created_at': now(), 'request': clean,
                    'versions': self.versions(), 'catalog_version': catalog['catalog_version'],
                    'changes': changes, 'experimental': bool(warnings), 'warnings': warnings,
                    'scope': item['scope'], 'shared_record_templates': item['shared_record_templates'],
                    'potential_descendant_records': item['descendant_records'],
                    'historical_game_validation': item['game_validation'], 'game_validation': 'not_performed'}
            write_json(self.path(plan['plan_id']), plan)
            return plan

    def confirm_generate(self, plan_id, confirmed, accept_experimental, *, queued=False):
        with self.lock:
            plan = self.read(plan_id)
            plan_id = plan['plan_id']
            if plan.get('ai_session') and plan['status'] != 'succeeded':
                session_path = self.root / 'ai_sessions' / (str(uuid.UUID(plan['ai_session'])) + '.json')
                session = read_record(session_path) or {}
                if session.get('version') != plan['ai_version'] or session.get('inflight') or session.get('questions') or session.get('unsupported'):
                    raise ServiceError('stale_ai_preview', 'AI 草稿已变化或正在处理，请重新预览并确认。')
            if confirmed is not True:
                raise ServiceError('confirmation_required', '请确认预览中的参数。')
            if plan['versions'] != self.versions():
                raise ServiceError('stale_preview', '目录或模板已变化，请重新预览并确认。')
            if plan['experimental'] and accept_experimental is not True:
                raise ServiceError('experimental_confirmation_required', '本方案尚待游戏验证，请明确接受试验提示。')
            if plan['status'] == 'succeeded':
                return plan
            if plan['status'] != ('queued' if queued else 'preview'):
                raise ServiceError('new_preview_required', '生成未完成或失败，请创建新预览后重试。')
            validate_request(plan['request'], catalog=self.catalog(), allow_unverified=accept_experimental)
            plan.update(status='generating', confirmed=True, accept_experimental=accept_experimental)
            write_json(self.path(plan_id), plan)
        stage = 'generation_and_pak_check'
        try:
            pak = generate(plan['request'], self.root / 'packages', confirmed=True,
                           allow_unverified=accept_experimental, packager=self.packager,
                           catalog_path=self.catalog_path)
            result = json.loads((pak.parent / 'result.json').read_text(encoding='utf-8'))
            stage = 'zip_delivery'
            result.update(plan_id=plan_id, versions=plan['versions'], confirmed_request=plan['request'])
            write_json(pak.parent / 'result.json', result)
            instruction = pak.parent / '使用说明.txt'
            catalog = self.catalog()
            instruction.write_text(delivery_instructions(plan, catalog['items'][plan['request']['object']],
                                   pak.name, catalog['game_version_context']), encoding='utf-8')
            archive = self.root / 'downloads' / (plan_id + '.zip')
            archive.parent.mkdir(parents=True, exist_ok=True)
            payload = {pak.name: pak.read_bytes(), '修改清单.json': (pak.parent / 'result.json').read_bytes(),
                       '使用说明.txt': instruction.read_bytes()}
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
                for name, content in payload.items():
                    output.writestr(name, content)
            with zipfile.ZipFile(archive) as output:
                if output.testzip() or {n: output.read(n) for n in output.namelist()} != payload:
                    raise RuntimeError('ZIP content check failed')
            plan.update(status='succeeded', stages={k: result[k] for k in
                        ('source_generation', 'pak_creation', 'package_check', 'game_validation')},
                        zip_check='passed', zip_sha256=digest(archive),
                        generated_at=now(), package_id=pak.parent.name,
                        download_url='/api/plans/' + plan_id + '/download')
        except Exception as exc:
            plan.update(status='failed', failure_stage=stage, error=str(exc))
            write_json(self.path(plan_id), plan)
            raise ServiceError('generation_failed', '生成或打包检查失败；请创建新预览重试。制作编号：' + plan_id, 500) from exc
        write_json(self.path(plan_id), plan)
        return plan

    def download(self, plan_id):
        plan = self.read(plan_id)
        if plan.get('generated_at') and datetime.fromisoformat(plan['generated_at']) < datetime.now(timezone.utc) - timedelta(days=7):
            raise ServiceError('download_expired', '下载已超过7天有效期，请重新制作。', 410)
        if plan['status'] != 'succeeded':
            raise ServiceError('download_not_ready', '本次制作没有通过检查的下载文件。')
        archive = self.root / 'downloads' / (str(uuid.UUID(plan_id)) + '.zip')
        if not archive.is_file() or digest(archive) != plan['zip_sha256']:
            raise ServiceError('download_corrupted', '下载文件缺失或已变化，请重新制作。', 500)
        return archive
