import json
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from fastapi.staticfiles import StaticFiles

from backend.ai_service import AIService
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


def create_app(service=None, model=None):
    service = service or EquipmentService()
    app = FastAPI(title='Mod-Superman 装备制作 API', version='1.0.0')
    app.state.service = service
    ai = AIService(service, model)
    app.state.ai = ai

    @app.post('/api/ai/sessions', status_code=201)
    def create_session(body: SessionCreate):
        return ai.create(body.object)

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
    def ai_preview(session_id: str, body: SessionRequest):
        return ai.preview(session_id, body.model_dump())

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
                       offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
        catalog = service.catalog()
        items = [i for i in catalog['items'].values()
                 if (category is None or i['category'] == category) and
                 search.casefold() in (i['display_name'] + ' ' + i['record']).casefold()]
        return {'total': len(items), 'offset': offset, 'limit': limit, 'catalog_version': catalog['catalog_version'],
                'items': [{k: i[k] for k in ('object_id', 'display_name', 'category', 'capabilities', 'game_validation')}
                          for i in items[offset:offset + limit]]}

    @app.get('/api/equipment/{object_id}')
    def equipment_detail(object_id: str):
        return service.detail(object_id)

    @app.post('/api/previews', status_code=201)
    def preview(body: Modification):
        return service.preview(body.model_dump())

    @app.post('/api/plans/{plan_id}/generate')
    def generate(plan_id: str, body: Confirmation):
        return service.confirm_generate(plan_id, body.confirmed, body.accept_experimental)

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
    def demo():
        return FileResponse(ROOT / 'web/index.html')

    app.mount('/demo-assets', StaticFiles(directory=ROOT / 'web', check_dir=False), name='demo-assets')
    return app


app = create_app()
