"""One explicit, minimal API call; no project context and no automatic retries."""
import argparse
import json
import queue
import threading
import time
from pathlib import Path

import httpx
from backend.model_client import settings
from scripts.generate_mod import ROOT


def diagnose(route='direct', stream=True, timeout=75, model=None):
    config = settings()
    if model:
        config['DEEPSEEK_MODEL']=model
    started = time.monotonic()
    report = dict(route=route, stream=stream, thinking='disabled', model=config['DEEPSEEK_MODEL'],
                  payload='fixed_minimal_json', stages=[], result='pending', usage=None)
    lock = threading.Lock()
    done = queue.Queue()
    def record(stage, **values):
        with lock:
            report['stages'].append(dict(stage=stage, elapsed_ms=round((time.monotonic()-started)*1000), **values))
    def call():
        try:
            with httpx.Client(trust_env=route=='system', timeout=httpx.Timeout(65, connect=10)) as client:
                with client.stream('POST', 'https://api.deepseek.com/chat/completions',
                    headers={'Authorization':'Bearer '+config['DEEPSEEK_API_KEY']},
                    json={'model':config['DEEPSEEK_MODEL'],'thinking':{'type':'disabled'},'stream':stream,
                          'max_tokens':64,'response_format':{'type':'json_object'},
                          'messages':[{'role':'user','content':'Return exactly this JSON object: {"ok":true}'}]}) as response:
                    record('headers', status=response.status_code)
                    if response.status_code != 200:
                        report.update(result='failed', error='http_error')
                        try:
                            error=response.read().decode('utf-8')[:1500]
                            report['upstream_error']=error.replace(config['DEEPSEEK_API_KEY'],'[redacted]')
                        except Exception:
                            pass
                        return
                    content=[]
                    if stream:
                        first=True
                        for line in response.iter_lines():
                            if time.monotonic()-started>timeout:
                                raise TimeoutError()
                            if not line or line.startswith(':'):
                                continue
                            if not line.startswith('data:'):
                                raise ValueError('invalid_sse')
                            raw=line[5:].strip()
                            if raw=='[DONE]':
                                record('done');break
                            data=json.loads(raw)
                            if data.get('error'):
                                report.update(result='failed', error='upstream_error');return
                            if data.get('usage'):
                                report['usage']=data['usage']
                            for choice in data.get('choices',[]):
                                text=choice.get('delta',{}).get('content')
                                if text:
                                    if first:record('first_content');first=False
                                    content.append(text)
                                if choice.get('finish_reason'):
                                    report['finish_reason']=choice['finish_reason']
                    else:
                        raw=response.read()
                        record('body_complete', byte_count=len(raw))
                        data=json.loads(raw)
                        content=[data['choices'][0]['message']['content']]
                        report['usage']=data.get('usage')
                        report['finish_reason']=data['choices'][0]['finish_reason']
                    report['result']='passed' if json.loads(''.join(content))=={'ok':True} and report.get('finish_reason')=='stop' else 'invalid_output'
        except Exception as exc:
            report.update(result='failed', error=type(exc).__name__)
        finally:
            record('finished');done.put(True)
    threading.Thread(target=call,daemon=True).start()
    try:done.get(timeout=timeout)
    except queue.Empty:
        with lock:report.update(result='failed',error='total_timeout')
    with lock:
        report=json.loads(json.dumps(report))
    directory=ROOT/'build/backend/model-diagnostics'
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/(time.strftime('%Y%m%d-%H%M%S')+'-'+config['DEEPSEEK_MODEL']+'-'+route+('-sse' if stream else '-json')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(path),**report},ensure_ascii=True,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--route',choices=['direct','system'],default='direct')
    parser.add_argument('--nonstream',action='store_true')
    parser.add_argument('--model',choices=['deepseek-flash','deepseek-v4-pro'])
    args=parser.parse_args();diagnose(args.route,not args.nonstream,model=args.model)
