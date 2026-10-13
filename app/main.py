import base64
import binascii
import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .provider import Provider
from .importer import create_course
from .service import Problem, Service

ROOT=Path(__file__).resolve().parents[1]


def create_app(data_root=None,live_allowed=None):
    app=FastAPI(title="Course Maintenance",docs_url=None,redoc_url=None)
    service=Service(data_root or ROOT / ".local")
    provider=Provider(allowed=(os.environ.get("COURSE_ALLOW_LIVE_AI")=="1") if live_allowed is None else live_allowed)
    app.state.service,app.state.provider=service,provider

    @app.middleware("http")
    async def local_boundary(request:Request,call_next):
        # Local single-user app: reject browser cross-origin writes and DNS rebinding.
        host=request.headers.get("host","").split(":")[0]
        if host not in {"127.0.0.1","localhost","testserver"}:
            return JSONResponse({"error":"This application is local-only"},status_code=403)
        origin=request.headers.get("origin")
        if request.method not in {"GET","HEAD"} and origin and origin not in {"http://"+request.headers.get("host",""),"https://"+request.headers.get("host","")}:
            return JSONResponse({"error":"Cross-origin writes are not allowed"},status_code=403)
        if int(request.headers.get("content-length","0"))>30_000_000:
            return JSONResponse({"error":"Request exceeds 30 MB"},status_code=413)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Cache-Control"]="no-store"
        return response

    @app.exception_handler(Problem)
    async def problem(_,exc): return JSONResponse({"error":exc.message},status_code=exc.status)

    @app.exception_handler(ValidationError)
    async def validation(_,exc): return JSONResponse({"error":"Input does not match the supported course/proposal format","details":[{"location":list(e["loc"]),"message":e["msg"]} for e in exc.errors()]},status_code=422)

    @app.exception_handler(ValueError)
    async def value_error(_,exc): return JSONResponse({"error":str(exc)},status_code=422)

    @app.get("/api/status")
    def status(): return {"provider":provider.status(),"mode":"local_single_user","format_version":1}

    @app.get("/api/runs")
    def runs(): return service.list()

    @app.post("/api/course/build")
    async def build(request:Request):
        archive,course=create_course(await request.json())
        return {"course_base64":base64.b64encode(archive).decode(),"course":course}

    @app.post("/api/runs")
    async def create(request:Request):
        body=await request.json()
        try: archive=base64.b64decode(body["course_base64"],validate=True)
        except (KeyError,binascii.Error,TypeError): raise Problem("Choose a valid course ZIP",422)
        try: return service.create(archive,body["new_source"].encode())
        except (KeyError,TypeError,AttributeError): raise Problem("Choose a UTF-8 Markdown source",422)
        except __import__('zipfile').BadZipFile: raise Problem("The course file is not a readable ZIP",422)

    @app.get("/api/runs/{run_id}")
    def get(run_id:str): return service.get(run_id)

    @app.post("/api/runs/{run_id}/proposals")
    async def drafts(run_id:str,request:Request): return service.add_drafts(run_id,await request.json(),"manual")

    @app.post("/api/runs/{run_id}/demo-proposals")
    def demo(run_id:str):
        state=service.get(run_id)
        sample=json.loads((ROOT / "fixtures" / "human-authored-proposals.json").read_text())
        if state["current"]["id"]!="beacon-desk-training" or state["source"]!=(ROOT / "fixtures" / "new-product.md").read_text():
            raise Problem("Demonstration proposals only match the unchanged Beacon Desk sample. Use manual proposals or an authorized AI provider for other inputs.")
        return service.add_drafts(run_id,{"expected_revision":state["revision"],"source_hash":state["source_hash"],"proposals":sample["proposals"]},"human_authored_demo")

    @app.post("/api/runs/{run_id}/decisions/{pid}")
    async def decide(run_id:str,pid:str,request:Request):
        body=await request.json()
        return service.decide(run_id,pid,body.get("decision"),body.get("reason",""))

    @app.post("/api/runs/{run_id}/source")
    async def source(run_id:str,request:Request):
        body=await request.json()
        return service.update_source(run_id,body.get("text","").encode())

    @app.post("/api/runs/{run_id}/apply")
    def apply(run_id:str): return service.apply(run_id)

    @app.post("/api/runs/{run_id}/rollback")
    def rollback(run_id:str): return service.rollback(run_id)

    @app.get("/api/runs/{run_id}/export")
    def export(run_id:str):
        data,fingerprint=service.export(run_id)
        return Response(data,media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="beacon-maintained-{fingerprint[:8]}.course.zip"'})

    @app.post("/api/provider/session")
    async def config(request:Request):
        if not provider.allowed: raise Problem("Live AI is disabled; no credential is accepted or saved",403)
        body=await request.json()
        provider.configure(body.get("endpoint",""),body.get("model",""),body.get("key",""))
        return provider.status()

    @app.delete("/api/provider/session")
    def clear(): provider.clear();return provider.status()

    @app.post("/api/runs/{run_id}/analyze")
    async def analyze(run_id:str):
        state=service.get(run_id)
        payload=await provider.propose(state)
        return service.add_drafts(run_id,payload,"ai_provider_unverified")

    @app.get("/samples/{name}")
    def sample(name:str):
        if name not in {"beacon-old.course.zip","new-product.md","human-authored-proposals.json"}: raise Problem("Sample not found",404)
        return FileResponse(ROOT / "fixtures" / name,filename=name)

    @app.get("/")
    def index(): return FileResponse(ROOT / "web" / "index.html")

    app.mount("/static",StaticFiles(directory=ROOT / "web"),name="static")
    return app


app=create_app()
