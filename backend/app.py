import json
import os
import secrets
import time
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from typing import Any
from typing import Literal
from threading import RLock

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from fastapi.staticfiles import StaticFiles

from backend.ai_service import AIService
from backend.jobs import Jobs
from backend.equipment_presentation import presentation
from backend.ai_protocol import StrictModel, parameter_message

from backend.service import EquipmentService, ServiceError
from scripts.generate_mod import ValidationError, no_duplicate_keys
from scripts.generate_mod import ROOT


class SessionCreate(StrictModel):
    object: str


class SessionRequest(StrictModel):
    version: int = Field(ge=0)
    request_id: str = Field(min_length=1, max_length=100)


class MessageRequest(SessionRequest):
    text: str = Field(min_length=1, max_length=4000, pattern=r'\S')


class DraftRequest(SessionRequest):
    changes: dict[str, Any]
    accept_supported_only: bool = False


class Modification(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    object: str
    changes: dict[str, Any]


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    confirmed: bool
    accept_experimental: bool = False


class Feedback(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)
    outcome: str = Field(pattern=r'^(success|problem)$')
    stage: str = Field(pattern=r'^(game_effect|installation|download|generation|packaging)$')
    game_version: str = Field(default='', max_length=100)
    detail: str = Field(default='', max_length=2000)


class CraftCreate(StrictModel):
    mode: Literal['modify_existing', 'create_new']
    base_equipment: str = Field(max_length=150)
    inheritance: Literal['retain_base', 'reconfigure'] | None = None
    acquisition: str | None = Field(default=None, max_length=150)
    goal: str = Field(default='装备定制', min_length=1, max_length=2000)


class CraftAction(StrictModel):
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=100)
    data: dict[str, Any] = Field(default_factory=dict)


def create_app(service=None, model=None, craft_model=None):
    service = service or EquipmentService()
    jobs = Jobs(service)
    async def maintenance():
        from backend.maintenance import maintain
        while True:
            await asyncio.sleep(86400)
            try:
                await asyncio.to_thread(maintain, service)
            except Exception:
                logging.exception('Maintenance failed')
    @asynccontextmanager
    async def lifespan(app):
        from backend.maintenance import maintain
        await asyncio.to_thread(maintain, service)
        task = asyncio.create_task(maintenance())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await asyncio.to_thread(jobs.close)
    app = FastAPI(title='Mod-Superman 装备制作 API', version='1.1.0', lifespan=lifespan)
    app.state.jobs = jobs
    limits = defaultdict(deque)
    public = os.environ.get('MOD_PUBLIC', '0') == '1'
    app.state.service = service
    ai = AIService(service, model)
    app.state.ai = ai
    craft_lock = RLock()
    app.state.craft = None

    def craft():
        with craft_lock:
            if app.state.craft is None:
                from backend.workflow_v11 import CraftService
                app.state.craft = CraftService(service, jobs, craft_model)
            return app.state.craft

    @app.get('/api/v11/catalog')
    def craft_catalog(kind: str = 'equipment', search: str = '', offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), mode: Literal['modify_existing', 'create_new'] | None = None):
        return craft().candidates(kind, search, offset, limit, mode=mode)

    @app.get('/api/v11/schema')
    def craft_schema():
        from backend.crafting_v11 import Plan
        from backend.task8_protocol import schema
        return {'plan': Plan.model_json_schema(), 'operations': schema('parse')}

    @app.get('/api/v11/history')
    def craft_history(request: Request):
        return craft().history(request.state.visitor)

    @app.post('/api/v11/sessions', status_code=201)
    def craft_create(body: CraftCreate, request: Request):
        return craft().create(body.model_dump(), request.state.visitor)

    @app.get('/api/v11/sessions/{identifier}')
    def craft_read(identifier: str):
        return craft().view(identifier)

    @app.post('/api/v11/sessions/{identifier}/{action}')
    def craft_action(identifier: str, action: str, body: CraftAction, request: Request):
        return craft().action(identifier, action, body.model_dump(), request.state.visitor)

    @app.get('/api/v11/tasks/{identifier}')
    def craft_task(identifier: str):
        return craft().task(identifier)

    @app.get('/api/v11/tasks/{identifier}/download')
    def craft_download(identifier: str):
        path = craft().download(identifier)
        return FileResponse(path, media_type='application/zip', filename=path.name)

    @app.post('/api/v11/tasks/{identifier}/feedback')
    def craft_feedback(identifier: str, body: Feedback):
        task = craft().task(identifier)
        if body.outcome == 'success' and task['status'] != 'succeeded':
            raise ServiceError('feedback_not_ready', '制作尚未成功，不能报告成功使用。', 409)
        if body.outcome == 'problem' and not body.detail.strip():
            raise ServiceError('feedback_detail_required', '请描述遇到的问题。', 422)
        if not service.store.feedback(identifier, body.model_dump()):
            raise ServiceError('feedback_conflict', '同一反馈编号不能提交不同内容。', 409)
        return {'status':'recorded','evidence':'user_report','game_validation':'not_performed'}

    @app.post('/api/ai/sessions', status_code=201)
    def create_session(body: SessionCreate, request: Request):
        state = ai.create(body.object)
        service.store.claim('ai_sessions', state['session_id'], request.state.visitor)
        return state

    @app.get('/api/ai/sessions/{session_id}')
    def read_session(session_id: str):
        return ai.get(session_id)

    @app.post('/api/ai/sessions/{session_id}/messages')
    def message(session_id: str, body: MessageRequest):
        return ai.message(session_id, body.model_dump())

    @app.post('/api/ai/sessions/{session_id}/draft')
    def draft(session_id: str, body: DraftRequest):
        return ai.manual(session_id, body.model_dump())

    @app.post('/api/ai/sessions/{session_id}/preview')
    def ai_preview(session_id: str, body: SessionRequest, request: Request):
        state = ai.preview(session_id, body.model_dump())
        service.store.claim('plans', state['preview']['plan_id'], request.state.visitor)
        return state

    @app.middleware('http')
    async def access(request: Request, call_next):
        token = request.cookies.get('mod_visitor', '')
        if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
            token = secrets.token_hex(32)
        request.state.visitor = token
        path = request.url.path
        def denied(status, code, message):
            return JSONResponse(status_code=status, content={'detail': {'code': code, 'message': message}})
        if path.startswith('/api/'):
            parts = path.strip('/').split('/')
            kind, identifier = None, None
            if len(parts) >= 4 and parts[1:3] == ['ai', 'sessions']:
                kind, identifier = 'ai_sessions', parts[3]
            elif len(parts) >= 3 and parts[1] == 'plans':
                kind, identifier = 'plans', parts[2]
            elif len(parts) >= 4 and parts[1] == 'v11' and parts[2] in ('sessions', 'tasks'):
                kind, identifier = 'v11_' + parts[2], parts[3]
            if kind and not service.store.allowed(kind, identifier, token):
                return denied(404, 'record_unavailable', '记录不存在或不属于当前浏览器。')
            if request.method == 'POST':
                origin = request.headers.get('origin')
                if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                    return denied(403, 'origin_rejected', '请从本站页面提交。')
                payload = await request.body()
                if len(payload) > (64000 if path.startswith('/api/v11/') else 24000):
                    return denied(413, 'body_too_large', '请求内容过长。')
                # IP limits prevent rotating cookies from bypassing model/cost limits.
                identity = request.client.host if request.client else 'unknown'
                bucket = 'model' if path.endswith(('/messages', '/message', '/review')) else 'write'
                key = (identity, bucket)
                stamp = time.monotonic()
                queue = limits[key]
                while queue and queue[0] <= stamp - 60:
                    queue.popleft()
                if len(queue) >= (10 if bucket == 'model' else 60):
                    return denied(429, 'request_limit', '请求过于频繁，请一分钟后重试。')
                queue.append(stamp)
                if len(limits) > 5000:
                    for old in list(limits):
                        if not limits[old] or limits[old][-1] < stamp - 60:
                            del limits[old]
        response = await call_next(request)
        response.set_cookie('mod_visitor', token, httponly=True, secure=public, samesite='lax', max_age=30*86400)
        if path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
            if response.status_code >= 400 or path.endswith('/download'):
                service.store.event(str(uuid.uuid4()), None, identifier if kind == 'plans' else None,
                                    'download_request' if path.endswith('/download') else 'http_error',
                                    str(response.status_code), {'path': path})
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @app.get('/health')
    def health():
        return {'status': 'ok', 'packager_available': service.packager.is_file()}

    @app.middleware('http')
    async def strict_json(request: Request, call_next):
        if request.method == 'POST':
            try:
                body = await request.body()
                json.loads(body, object_pairs_hook=no_duplicate_keys,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
            except (ValueError, UnicodeDecodeError):
                return JSONResponse(status_code=422, content={'detail': {'code': 'invalid_json',
                                    'message': 'JSON 格式无效，禁止重复键及非有限数。'}})
        return await call_next(request)

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(status_code=exc.status, content={'detail': {'code': exc.code, 'message': exc.message}})

    @app.exception_handler(ValidationError)
    async def invalid_parameters(request, exc):
        return JSONResponse(status_code=422, content={'detail': {'code': 'invalid_parameters', 'message': parameter_message(exc)}})

    @app.get('/api/equipment')
    def list_equipment(search: str = '', category: str | None = None,
                       player_available_only: bool = False,
                       offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
        catalog = service.catalog()
        items = [i for i in catalog['items'].values()
                 if (category is None or i['category'] == category) and
                 search.casefold() in (i['display_name'] + ' ' + i['record']).casefold()]
        if player_available_only:
            items = [i for i in items if presentation(i)['availability'] == 'verified']
        return {'total': len(items), 'offset': offset, 'limit': limit, 'catalog_version': catalog['catalog_version'],
                'items': [{**{k: i[k] for k in ('object_id', 'display_name', 'category', 'capabilities', 'game_validation')},
                           'presentation': presentation(i)}
                          for i in items[offset:offset + limit]]}

    @app.get('/api/equipment/{object_id}')
    def equipment_detail(object_id: str):
        return service.detail(object_id)

    @app.post('/api/previews', status_code=201)
    def preview(body: Modification, request: Request):
        plan = service.preview(body.model_dump())
        service.store.claim('plans', plan['plan_id'], request.state.visitor)
        return plan

    @app.post('/api/plans/{plan_id}/generate')
    def generate(plan_id: str, body: Confirmation):
        if public:
            raise ServiceError('use_task_endpoint', '请使用后台制作接口。', 409)
        return service.confirm_generate(plan_id, body.confirmed, body.accept_experimental)

    @app.post('/api/plans/{plan_id}/tasks', status_code=202)
    def generate_task(plan_id: str, body: Confirmation):
        return jobs.submit(plan_id, body.confirmed, body.accept_experimental)

    @app.post('/api/plans/{plan_id}/feedback')
    def feedback(plan_id: str, body: Feedback):
        plan = service.read(plan_id)
        if body.outcome == 'success' and plan['status'] != 'succeeded':
            raise ServiceError('feedback_not_ready', '本次制作尚未成功，不能报告成功使用。', 409)
        if body.outcome == 'problem' and not body.detail.strip():
            raise ServiceError('feedback_detail_required', '请描述遇到的问题。', 422)
        if not service.store.feedback(plan_id, body.model_dump()):
            raise ServiceError('feedback_conflict', '同一反馈编号不能提交不同内容。')
        return {'status': 'recorded', 'request_id': body.request_id,
                'evidence': 'user_report', 'game_validation': 'not_performed'}

    @app.get('/api/plans/{plan_id}/instructions')
    def instructions(plan_id: str):
        archive = service.download(plan_id)
        import zipfile
        with zipfile.ZipFile(archive) as package:
            return {'text': package.read('使用说明.txt').decode('utf-8')}

    @app.get('/api/plans/{plan_id}')
    def status(plan_id: str):
        plan = service.read(plan_id)
        # Raw tool output and filesystem paths remain in the local diagnostic record.
        return {k: v for k, v in plan.items() if k != 'error'}

    @app.get('/api/plans/{plan_id}/download')
    def download(plan_id: str):
        path = service.download(plan_id)
        return FileResponse(path, media_type='application/zip', filename=path.name)

    @app.get('/')
    def frontend():
        return RedirectResponse('/frontend/index.html', status_code=307)

    @app.get('/lab')
    def demo():
        if public:
            return JSONResponse(status_code=404, content={'detail': 'Not found'})
        return FileResponse(ROOT / 'web/lab/index.html')

    app.mount('/frontend', StaticFiles(directory=ROOT / 'web', check_dir=False), name='frontend')
    app.mount('/demo-assets', StaticFiles(directory=ROOT / 'web', check_dir=False), name='demo-assets')
    return app


app = create_app()
