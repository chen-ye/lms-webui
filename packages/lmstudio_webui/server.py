from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel

from .downloads import (
    StatelessDownloadReader,
    fetch_hf_quantizations,
    fetch_lmstudio_catalog,
    fetch_lmstudio_catalog_family,
    search_huggingface_models,
)
from .indexer import HostModelIndex, get_lmstudio_home
from .models import (
    DeleteModelRequest,
    DownloadModelRequest,
    LoadModelRequest,
    UnloadModelRequest,
)
from .service import control_service, get_service_status, install_service, uninstall_service

_REPO_WEB_DIR = Path(__file__).resolve().parents[2] / "web"
_PKG_WEB_DIR = Path(__file__).resolve().parent / "web"
WEB_DIR = _REPO_WEB_DIR if _REPO_WEB_DIR.is_dir() else _PKG_WEB_DIR


class ServerConfig:
    def __init__(self) -> None:
        self._download_reader: StatelessDownloadReader | None = None
        self._last_home: Path | None = None

    @property
    def lmstudio_url(self) -> str:
        return os.environ.get("LMSTUDIO_URL", "http://localhost:1234").rstrip("/")

    @property
    def lmstudio_home(self) -> Path:
        return get_lmstudio_home()

    @property
    def api_token(self) -> str | None:
        tok = os.environ.get("LM_API_TOKEN", "").strip()
        return tok or None

    @property
    def port(self) -> int:
        try:
            return int(os.environ.get("LMS_WEBUI_PORT", "8420"))
        except ValueError:
            return 8420

    @property
    def host(self) -> str:
        return os.environ.get("LMS_WEBUI_HOST", "0.0.0.0")

    def get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def get_indexer(self) -> HostModelIndex:
        return HostModelIndex(self.lmstudio_home)

    def get_download_reader(self) -> StatelessDownloadReader:
        home = self.lmstudio_home
        if self._download_reader is None or self._last_home != home:
            self._download_reader = StatelessDownloadReader(home)
            self._last_home = home
        return self._download_reader


config = ServerConfig()

app = FastAPI(
    title="LM Studio Model Management WebUI API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_upstream_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            if isinstance(err, str):
                return err
            if data.get("message"):
                return str(data["message"])
            if data.get("detail"):
                return str(data["detail"])
    except Exception:
        pass
    return resp.text.strip() or f"Upstream HTTP {resp.status_code}"


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    indexer = config.get_indexer()
    svc_status = get_service_status(
        default_port=config.port,
        default_host=config.host,
        default_lmstudio_url=config.lmstudio_url,
    )
    connected = False
    model_count = 0
    loaded_count = 0
    error_msg: str | None = None

    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=4.0) as client:
        try:
            resp = await client.get("/api/v1/models", headers=config.get_headers())
            if resp.status_code == 200:
                connected = True
                raw_models = resp.json().get("models") or []
                model_count = len(raw_models)
                loaded_count = sum(len(m.get("loaded_instances") or []) for m in raw_models)
            else:
                error_msg = _extract_upstream_error(resp)
        except httpx.RequestError as exc:
            error_msg = f"Cannot reach LM Studio server at {config.lmstudio_url}: {exc}"

    return {
        "connected": connected,
        "lmstudio_url": config.lmstudio_url,
        "lmstudio_home": str(config.lmstudio_home),
        "downloads_folder": str(indexer.get_downloads_folder()),
        "default_context_length": indexer.get_default_context_length(),
        "auth_configured": config.api_token is not None,
        "model_count": model_count,
        "loaded_instance_count": loaded_count,
        "service": svc_status.model_dump(),
        "error": error_msg,
    }


@app.get("/api/models")
async def list_models(
    use_cli_peers: bool = Query(True, description="Resolve remote LM Link peer names via lms ls"),
) -> dict[str, Any]:
    indexer = config.get_indexer()
    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=10.0) as client:
        try:
            resp = await client.get("/api/v1/models", headers=config.get_headers())
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach LM Studio server at {config.lmstudio_url}: {exc}",
            )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=_extract_upstream_error(resp))

    raw_models = resp.json().get("models") or []
    enriched = indexer.enrich_models(raw_models, use_lms_cli_for_peers=use_cli_peers)
    return {
        "models": [m.model_dump() for m in enriched],
        "default_context_length": indexer.get_default_context_length(),
        "downloads_folder": str(indexer.get_downloads_folder()),
    }


@app.post("/api/models/load")
async def load_model(req: LoadModelRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": req.model,
        "echo_load_config": req.echo_load_config,
    }
    if req.context_length is not None:
        payload["context_length"] = req.context_length
    if req.eval_batch_size is not None:
        payload["eval_batch_size"] = req.eval_batch_size
    if req.flash_attention is not None:
        payload["flash_attention"] = req.flash_attention
    if req.num_experts is not None:
        payload["num_experts"] = req.num_experts
    if req.offload_kv_cache_to_gpu is not None:
        payload["offload_kv_cache_to_gpu"] = req.offload_kv_cache_to_gpu

    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=120.0) as client:
        try:
            resp = await client.post(
                "/api/v1/models/load",
                headers=config.get_headers(),
                json=payload,
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach LM Studio server at {config.lmstudio_url}: {exc}",
            )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=_extract_upstream_error(resp))
    return resp.json()


@app.post("/api/models/unload")
async def unload_model(req: UnloadModelRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=30.0) as client:
        try:
            resp = await client.post(
                "/api/v1/models/unload",
                headers=config.get_headers(),
                json={"instance_id": req.instance_id},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach LM Studio server at {config.lmstudio_url}: {exc}",
            )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=_extract_upstream_error(resp))
    return resp.json()


@app.post("/api/models/unload-all")
async def unload_all_models() -> dict[str, Any]:
    unloaded: list[str] = []
    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=30.0) as client:
        try:
            resp = await client.get("/api/v1/models", headers=config.get_headers())
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach LM Studio server at {config.lmstudio_url}: {exc}",
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=_extract_upstream_error(resp))

        raw_models = resp.json().get("models") or []
        for m in raw_models:
            for inst in m.get("loaded_instances") or []:
                inst_id = inst.get("id")
                if not inst_id:
                    continue
                u_resp = await client.post(
                    "/api/v1/models/unload",
                    headers=config.get_headers(),
                    json={"instance_id": inst_id},
                )
                if u_resp.status_code == 200:
                    unloaded.append(str(inst_id))

    return {"unloaded": unloaded, "count": len(unloaded)}


@app.delete("/api/models")
async def delete_model(req: DeleteModelRequest) -> dict[str, Any]:
    indexer = config.get_indexer()
    unloaded_instances: list[str] = []

    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=30.0) as client:
        try:
            resp = await client.get("/api/v1/models", headers=config.get_headers())
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach LM Studio server at {config.lmstudio_url}: {exc}",
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=_extract_upstream_error(resp))

        raw_models = resp.json().get("models") or []
        enriched = indexer.enrich_models(raw_models, use_lms_cli_for_peers=False)

        try:
            target_model = indexer.resolve_model_for_deletion(req, enriched)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        if not target_model.deletable:
            raise HTTPException(
                status_code=403,
                detail=f"Model '{target_model.key}' (origin={target_model.origin}) cannot be deleted on this host.",
            )

        # Unload any running instances before deleting files from disk
        for inst in target_model.loaded_instances:
            inst_id = inst.get("id")
            if inst_id:
                u_resp = await client.post(
                    "/api/v1/models/unload",
                    headers=config.get_headers(),
                    json={"instance_id": inst_id},
                )
                if u_resp.status_code == 200:
                    unloaded_instances.append(str(inst_id))

    try:
        del_res = indexer.delete_model_files(target_model)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "status": "deleted",
        "unloaded_instances": unloaded_instances,
        **del_res,
    }


@app.post("/api/models/download")
async def download_model(req: DownloadModelRequest) -> dict[str, Any]:
    model_str = req.model.strip()
    if not model_str:
        raise HTTPException(status_code=400, detail="Model identifier or Hugging Face URL is required.")

    payload: dict[str, Any] = {"model": model_str}
    if req.quantization and req.quantization.strip():
        payload["quantization"] = req.quantization.strip()

    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=30.0) as client:
        try:
            resp = await client.post(
                "/api/v1/models/download",
                headers=config.get_headers(),
                json=payload,
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach LM Studio server at {config.lmstudio_url}: {exc}",
            )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=_extract_upstream_error(resp))

    data = resp.json()
    job_id = data.get("job_id")
    if job_id:
        config.get_download_reader().register_ephemeral_job(
            job_id=str(job_id),
            model=model_str,
            quantization=req.quantization,
            resp_data=data,
        )
    return data


@app.get("/api/models/downloads")
async def list_downloads() -> dict[str, Any]:
    reader = config.get_download_reader()
    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=5.0) as client:
        jobs = await reader.list_jobs_with_live_status(client, config.get_headers())
    return {"jobs": [j.model_dump() for j in jobs]}


@app.get("/api/models/download/status/{job_id}")
async def get_download_status(job_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=config.lmstudio_url, timeout=5.0) as client:
        try:
            resp = await client.get(
                f"/api/v1/models/download/status/{job_id}",
                headers=config.get_headers(),
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach LM Studio server at {config.lmstudio_url}: {exc}",
            )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=_extract_upstream_error(resp))
    return resp.json()


@app.get("/api/hf/quantizations")
async def get_hf_quantizations(repo: str = Query(..., description="Hugging Face repo ID or URL")) -> dict[str, Any]:
    return await fetch_hf_quantizations(repo)


@app.get("/api/catalog")
async def get_catalog(q: str = Query("", description="Filter LM Studio catalog families")) -> dict[str, Any]:
    return await fetch_lmstudio_catalog(q)


@app.get("/api/catalog/{slug}")
async def get_catalog_family(slug: str) -> dict[str, Any]:
    return await fetch_lmstudio_catalog_family(slug)


@app.get("/api/hf/search")
async def get_hf_search(
    q: str = Query("", description="Search query for Hugging Face GGUF/MLX models"),
    format: str = Query("all", description="Format filter: all, gguf, or mlx"),
) -> dict[str, Any]:
    return await search_huggingface_models(query=q, fmt=format)


class ServiceActionRequest(BaseModel):
    port: int | None = None
    host: str | None = None
    lmstudio_url: str | None = None
    dry_run: bool = False


@app.get("/api/service/status")
async def api_service_status() -> dict[str, Any]:
    st = get_service_status(
        default_port=config.port,
        default_host=config.host,
        default_lmstudio_url=config.lmstudio_url,
    )
    return st.model_dump()


@app.post("/api/service/install")
async def api_service_install(req: ServiceActionRequest) -> dict[str, Any]:
    try:
        res = install_service(
            port=req.port or config.port,
            host=req.host or config.host,
            lmstudio_url=req.lmstudio_url or config.lmstudio_url,
            lmstudio_home=config.lmstudio_home,
            api_token=config.api_token,
            dry_run=req.dry_run,
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Service installation failed: {exc}")


@app.post("/api/service/uninstall")
async def api_service_uninstall(req: ServiceActionRequest) -> dict[str, Any]:
    try:
        return uninstall_service(dry_run=req.dry_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Service uninstall failed: {exc}")


@app.post("/api/service/restart")
async def api_service_restart(req: ServiceActionRequest) -> dict[str, Any]:
    try:
        return control_service("restart", dry_run=req.dry_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Service restart failed: {exc}")


if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")
