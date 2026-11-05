from __future__ import annotations

from datetime import datetime, timezone
import html as htmllib
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlparse
import httpx

from .indexer import get_lmstudio_home
from .models import DownloadJobInfo, HfQuantizationOption

_QUANT_RE = re.compile(
    r"(?:^|[-_.])("
    r"(?:IQ[1-4]_(?:XXS|XS|S|M|NL))|"
    r"(?:Q[2-8]_(?:K_(?:XL|L|M|S)|[01K]))|"
    r"(?:MXFP4|FP16|F16|BF16|F32|Q4_0|Q4_1|Q5_0|Q5_1|Q8_0)"
    r")(?:[-_.]|\.gguf$)",
    re.IGNORECASE,
)
_SHARD_RE = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.IGNORECASE)


def _ms_to_iso(ts_ms: int | float | None) -> str | None:
    if not ts_ms or ts_ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _is_model_job(job: dict[str, Any]) -> bool:
    if job.get("artifactType") == "model":
        return True
    job_id_str = str(job.get("jobIdentifier") or "")
    if job_id_str.startswith(("modelDownload:", "resolvedArtifactDownload:")):
        return True
    if job.get("fullIndexedModelIdentifier"):
        return True
    return False


def _infer_model_id_from_job(job: dict[str, Any]) -> str:
    full_id = job.get("fullIndexedModelIdentifier")
    if full_id and isinstance(full_id, str):
        return full_id
    add_ids = job.get("additionalIndexedModelIdentifiers")
    if isinstance(add_ids, list) and add_ids:
        return str(add_ids[0])
    job_ident = str(job.get("jobIdentifier") or "")
    # e.g. modelDownload:huggingface:owner/repo:owner/repo/file.gguf
    parts = job_ident.split(":")
    if len(parts) >= 3 and parts[2]:
        return parts[2]
    return job_ident or str(job.get("shortHashJobId") or "unknown")


class StatelessDownloadReader:
    """Reads LM Studio's ~/.lmstudio/.internal/download-jobs-info.json and merges live REST status."""

    def __init__(self, lmstudio_home: str | Path | None = None) -> None:
        self.lmstudio_home = get_lmstudio_home(lmstudio_home)
        # In-process ephemeral cache only for jobs started moments before LM Studio flushes download-jobs-info.json
        self._ephemeral_jobs: dict[str, dict[str, Any]] = {}

    @property
    def download_jobs_path(self) -> Path:
        return self.lmstudio_home / ".internal" / "download-jobs-info.json"

    def register_ephemeral_job(
        self,
        job_id: str,
        model: str,
        quantization: str | None,
        resp_data: dict[str, Any],
    ) -> None:
        if not job_id:
            return
        label = f"{model} ({quantization})" if quantization else model
        self._ephemeral_jobs[job_id] = {
            "job_id": job_id,
            "model_id": label,
            "status": resp_data.get("status") or "downloading",
            "total_size_bytes": resp_data.get("total_size_bytes"),
            "downloaded_bytes": resp_data.get("downloaded_bytes") or 0,
            "started_at": resp_data.get("started_at"),
            "completed_at": resp_data.get("completed_at"),
        }

    def read_local_jobs(self) -> list[DownloadJobInfo]:
        jobs_list: list[DownloadJobInfo] = []
        seen_job_ids: set[str] = set()

        if self.download_jobs_path.is_file():
            try:
                raw = json.loads(self.download_jobs_path.read_text(encoding="utf-8"))
                raw_jobs = raw.get("jobs") if isinstance(raw, dict) else []
            except Exception:
                raw_jobs = []

            for j in reversed(raw_jobs or []):
                if not isinstance(j, dict) or not _is_model_job(j):
                    continue

                short_id = j.get("shortHashJobId")
                job_ident = j.get("jobIdentifier")
                job_id = str(short_id or job_ident or "")
                if not job_id or job_id in seen_job_ids:
                    continue
                seen_job_ids.add(job_id)

                job_state = j.get("jobState") or {}
                status = str(job_state.get("type") or "completed")
                started_at = _ms_to_iso(j.get("startedTimestamp"))
                completed_at = _ms_to_iso(job_state.get("completedTimestamp"))

                total_bytes = 0
                downloaded_bytes = 0
                speed_bps = 0.0
                target_path: str | None = j.get("fileSystemPath")
                error_msg: str | None = None

                for t in j.get("tasks") or []:
                    if not isinstance(t, dict):
                        continue
                    dl = t.get("download") or {}
                    req = t.get("request") or {}
                    t_total = int(dl.get("totalSizeBytes") or req.get("fileSizeBytes") or 0)
                    t_done = int(dl.get("downloadedSizeBytes") or 0)
                    total_bytes += t_total
                    downloaded_bytes += t_done
                    speed_bps += float(dl.get("speedBytesPerSecond") or 0.0)
                    if not target_path and dl.get("targetPath"):
                        target_path = str(dl["targetPath"])
                    if dl.get("errorMessage"):
                        error_msg = str(dl["errorMessage"])

                progress_pct = (
                    round(min(100.0, (downloaded_bytes / total_bytes) * 100.0), 1)
                    if total_bytes > 0
                    else (100.0 if status == "completed" else 0.0)
                )

                add_ids = [
                    str(x)
                    for x in (j.get("additionalIndexedModelIdentifiers") or [])
                    if x
                ]

                jobs_list.append(
                    DownloadJobInfo(
                        job_id=job_id,
                        job_identifier=str(job_ident) if job_ident else None,
                        model_id=_infer_model_id_from_job(j),
                        additional_identifiers=add_ids,
                        status=status,
                        total_size_bytes=total_bytes if total_bytes > 0 else None,
                        downloaded_bytes=downloaded_bytes if total_bytes > 0 else None,
                        bytes_per_second=speed_bps if speed_bps > 0 else None,
                        progress_pct=progress_pct,
                        started_at=started_at,
                        completed_at=completed_at,
                        target_path=target_path,
                        error_message=error_msg,
                    )
                )

        # Merge any newly triggered ephemeral jobs not yet flushed to download-jobs-info.json
        for ej_id, ej in list(self._ephemeral_jobs.items()):
            if ej_id in seen_job_ids:
                continue
            total = ej.get("total_size_bytes") or 0
            done = ej.get("downloaded_bytes") or 0
            pct = round(min(100.0, (done / total) * 100.0), 1) if total > 0 else 0.0
            jobs_list.insert(
                0,
                DownloadJobInfo(
                    job_id=ej_id,
                    model_id=ej["model_id"],
                    status=ej["status"],
                    total_size_bytes=total or None,
                    downloaded_bytes=done,
                    progress_pct=pct,
                    started_at=ej.get("started_at"),
                    completed_at=ej.get("completed_at"),
                ),
            )

        return jobs_list

    async def list_jobs_with_live_status(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
    ) -> list[DownloadJobInfo]:
        jobs = self.read_local_jobs()
        for job in jobs:
            # Query live status from REST API for active jobs (or recently triggered ephemeral jobs)
            if job.job_id.startswith("job_") and (
                job.status in ("downloading", "paused") or job.job_id in self._ephemeral_jobs
            ):
                try:
                    resp = await client.get(
                        f"/api/v1/models/download/status/{job.job_id}",
                        headers=headers,
                        timeout=3.0,
                    )
                    if resp.status_code == 200:
                        live = resp.json()
                        job.status = str(live.get("status") or job.status)
                        if live.get("total_size_bytes") is not None:
                            job.total_size_bytes = int(live["total_size_bytes"])
                        if live.get("downloaded_bytes") is not None:
                            job.downloaded_bytes = int(live["downloaded_bytes"])
                        if live.get("bytes_per_second") is not None:
                            job.bytes_per_second = float(live["bytes_per_second"])
                        if live.get("started_at"):
                            job.started_at = str(live["started_at"])
                        if live.get("completed_at"):
                            job.completed_at = str(live["completed_at"])
                        if live.get("estimated_completion"):
                            job.estimated_completion = str(live["estimated_completion"])
                        if job.total_size_bytes and job.total_size_bytes > 0 and job.downloaded_bytes is not None:
                            job.progress_pct = round(
                                min(100.0, (job.downloaded_bytes / job.total_size_bytes) * 100.0),
                                1,
                            )
                        elif job.status == "completed":
                            job.progress_pct = 100.0
                except Exception:
                    pass
        return jobs


def parse_hf_repo_id(repo_or_url: str) -> str | None:
    val = (repo_or_url or "").strip()
    if not val:
        return None
    if val.startswith(("http://", "https://")):
        parsed = urlparse(val)
        if "huggingface.co" not in parsed.netloc.lower():
            return None
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return None
    parts = [p for p in val.strip("/").split("/") if p]
    if len(parts) == 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def extract_quantizations_from_hf_siblings(
    siblings: list[dict[str, Any]],
) -> list[HfQuantizationOption]:
    quant_buckets: dict[str, dict[str, Any]] = {}
    for sib in siblings or []:
        if not isinstance(sib, dict):
            continue
        rfilename = str(sib.get("rfilename") or "")
        if not rfilename.lower().endswith(".gguf"):
            continue
        basename = rfilename.rsplit("/", 1)[-1]
        if basename.lower().startswith("mmproj"):
            continue

        m = _QUANT_RE.search(basename)
        if m:
            q_name = m.group(1).upper()
        else:
            stem = _SHARD_RE.sub("", basename)
            if stem.lower().endswith(".gguf"):
                stem = stem[:-5]
            parts = re.split(r"[-_.]", stem)
            q_name = parts[-1].upper() if parts else stem

        size = sib.get("size")
        size_int = int(size) if isinstance(size, (int, float)) else None

        bucket = quant_buckets.get(q_name)
        if bucket is None:
            quant_buckets[q_name] = {
                "quantization": q_name,
                "filename": basename,
                "size_bytes": size_int,
            }
        else:
            if size_int is not None:
                bucket["size_bytes"] = (bucket.get("size_bytes") or 0) + size_int

    options = [HfQuantizationOption(**v) for v in quant_buckets.values()]
    options.sort(key=lambda o: (o.size_bytes or 0, o.quantization))
    return options


async def fetch_hf_quantizations(repo_or_url: str) -> dict[str, Any]:
    repo_id = parse_hf_repo_id(repo_or_url)
    if not repo_id:
        return {"repo_id": None, "is_hf": False, "quantizations": []}

    url = f"https://huggingface.co/api/models/{repo_id}?blobs=true"
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return {
                "repo_id": repo_id,
                "is_hf": True,
                "quantizations": [],
                "error": f"Hugging Face API returned HTTP {resp.status_code}",
            }
        data = resp.json()

    siblings = data.get("siblings") or []
    quants = extract_quantizations_from_hf_siblings(siblings)
    has_safetensors = any(
        str(s.get("rfilename") or "").lower().endswith(".safetensors")
        for s in siblings
        if isinstance(s, dict)
    )
    return {
        "repo_id": repo_id,
        "url": f"https://huggingface.co/{repo_id}",
        "is_hf": True,
        "has_safetensors": has_safetensors,
        "quantizations": [q.model_dump() for q in quants],
    }


# --- Live LM Studio Catalog & Hugging Face Discovery ---

_CATALOG_CACHE: dict[str, Any] = {"ts": 0.0, "families": []}
_FAMILY_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}

_FALLBACK_CATALOG_FAMILIES: list[dict[str, Any]] = [
    {
        "slug": "gemma-4",
        "name": "Gemma 4",
        "params": ["5.1B", "7.9B", "12B", "26B", "31B"],
        "capabilities": ["Tool use", "Reasoning", "Vision"],
        "description": "Google's open multimodal & reasoning family built from Gemini 3 research.",
        "url": "https://lmstudio.ai/models/gemma-4",
        "variants": [
            {"model_id": "google/gemma-4-e2b", "size": "4.20 GB", "url": "https://lmstudio.ai/models/google/gemma-4-e2b"},
            {"model_id": "google/gemma-4-e4b", "size": "5.90 GB", "url": "https://lmstudio.ai/models/google/gemma-4-e4b"},
            {"model_id": "google/gemma-4-12b", "size": "7.40 GB", "url": "https://lmstudio.ai/models/google/gemma-4-12b"},
            {"model_id": "google/gemma-4-26b-a4b", "size": "15.60 GB", "url": "https://lmstudio.ai/models/google/gemma-4-26b-a4b"},
            {"model_id": "google/gemma-4-26b-a4b-qat", "size": "15.60 GB", "url": "https://lmstudio.ai/models/google/gemma-4-26b-a4b-qat"},
            {"model_id": "google/gemma-4-31b", "size": "19.00 GB", "url": "https://lmstudio.ai/models/google/gemma-4-31b"},
        ],
    },
    {
        "slug": "qwen3.8",
        "name": "Qwen3.8",
        "params": ["27B"],
        "capabilities": ["Tool use", "Reasoning", "Vision"],
        "description": "Dense 27B vision-language model for coding, research, and long-horizon agentic tasks.",
        "url": "https://lmstudio.ai/models/qwen3.8",
        "variants": [
            {"model_id": "qwen/qwen3.8-27b", "size": "16.20 GB", "url": "https://lmstudio.ai/models/qwen/qwen3.8-27b"},
        ],
    },
    {
        "slug": "qwen3.5",
        "name": "Qwen3.5",
        "params": ["2B", "4B", "9B", "27B", "35B"],
        "capabilities": ["Tool use", "Reasoning", "Vision"],
        "description": "Multimodal and reasoning family ranging from compact 2B/4B to 35B.",
        "url": "https://lmstudio.ai/models/qwen3.5",
        "variants": [
            {"model_id": "qwen/qwen3.5-4b", "size": "2.80 GB", "url": "https://lmstudio.ai/models/qwen/qwen3.5-4b"},
            {"model_id": "qwen/qwen3.5-9b", "size": "5.80 GB", "url": "https://lmstudio.ai/models/qwen/qwen3.5-9b"},
            {"model_id": "qwen/qwen3.5-27b", "size": "16.40 GB", "url": "https://lmstudio.ai/models/qwen/qwen3.5-27b"},
        ],
    },
    {
        "slug": "gpt-oss",
        "name": "gpt-oss",
        "params": ["20B", "120B"],
        "capabilities": ["Tool use", "Reasoning"],
        "description": "OpenAI's open-weight LLM with configurable reasoning effort and tool calling.",
        "url": "https://lmstudio.ai/models/gpt-oss",
        "variants": [
            {"model_id": "openai/gpt-oss-20b", "size": "12.50 GB", "url": "https://lmstudio.ai/models/openai/gpt-oss-20b"},
            {"model_id": "openai/gpt-oss-120b", "size": "68.00 GB", "url": "https://lmstudio.ai/models/openai/gpt-oss-120b"},
        ],
    },
    {
        "slug": "granite-4",
        "name": "Granite 4.0",
        "params": ["3B", "7B", "32B"],
        "capabilities": ["Tool use"],
        "description": "IBM's lightweight open models for RAG, tool use, coding, and structured JSON output.",
        "url": "https://lmstudio.ai/models/granite-4",
        "variants": [
            {"model_id": "ibm/granite-4-micro", "size": "2.10 GB", "url": "https://lmstudio.ai/models/ibm/granite-4-micro"},
        ],
    },
    {
        "slug": "deepseek-r1",
        "name": "deepseek-r1",
        "params": ["7B", "8B", "14B", "32B", "70B"],
        "capabilities": ["Tool use", "Reasoning"],
        "description": "DeepSeek R1 reasoning models and distilled Qwen/Llama checkpoints.",
        "url": "https://lmstudio.ai/models/deepseek-r1",
        "variants": [
            {"model_id": "deepseek/deepseek-r1-0528-qwen3-8b", "size": "5.20 GB", "url": "https://lmstudio.ai/models/deepseek/deepseek-r1-0528-qwen3-8b"},
        ],
    },
]


def parse_lmstudio_catalog_html(raw_html: str) -> list[dict[str, Any]]:
    families: list[dict[str, Any]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<a\s+[^>]*data-model-page-has-downloads="true"[^>]*href="/models/([a-zA-Z0-9._-]+)"[^>]*>(.*?)</a>',
        re.S,
    )
    for m in pattern.finditer(raw_html):
        slug, body = m.group(1), m.group(2)
        if slug in seen:
            continue
        seen.add(slug)
        title_m = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.S)
        name = (
            htmllib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1)).strip())
            if title_m
            else slug
        )
        params_block = re.search(r'aria-label="Parameter sizes"[^>]*>(.*?)</div>', body, re.S)
        params = (
            re.findall(r">(\d+(?:\.\d+)?[BM])</span>", params_block.group(1))
            if params_block
            else []
        )
        caps = re.findall(r'<span title="(Tool use|Reasoning|Vision)">', body)
        desc_m = re.search(r"<p(?:\s[^>]*)?>(.*?)</p>", body, re.S)
        desc = (
            htmllib.unescape(re.sub(r"<[^>]+>", "", desc_m.group(1)).strip())
            if desc_m
            else ""
        )
        families.append(
            {
                "slug": slug,
                "name": name,
                "params": params,
                "capabilities": caps,
                "description": desc,
                "url": f"https://lmstudio.ai/models/{slug}",
            }
        )
    return families


def parse_lmstudio_family_variants_html(raw_html: str) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'href="/models/([a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)"[^>]*>\1</a>(.*?)(?=href="/models/|</section>|</div></div></div>|$)',
        re.S,
    )
    for m in pattern.finditer(raw_html):
        model_id = m.group(1)
        if model_id in seen:
            continue
        seen.add(model_id)
        tail = m.group(2)
        sz_m = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", tail)
        variants.append(
            {
                "model_id": model_id,
                "size": sz_m.group(1) if sz_m else None,
                "url": f"https://lmstudio.ai/models/{model_id}",
            }
        )
    return variants


async def fetch_lmstudio_catalog(query: str = "") -> dict[str, Any]:
    now = time.time()
    families: list[dict[str, Any]] = _CATALOG_CACHE.get("families") or []
    if not families or (now - float(_CATALOG_CACHE.get("ts") or 0.0)) > 600:
        try:
            async with httpx.AsyncClient(
                timeout=6.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"},
            ) as client:
                resp = await client.get("https://lmstudio.ai/models")
                if resp.status_code == 200:
                    parsed = parse_lmstudio_catalog_html(resp.text)
                    if parsed:
                        families = parsed
                        _CATALOG_CACHE["families"] = families
                        _CATALOG_CACHE["ts"] = now
        except Exception:
            pass

    if not families:
        families = _FALLBACK_CATALOG_FAMILIES

    q = (query or "").strip().lower()
    if q:
        filtered = [
            f
            for f in families
            if q in f["slug"].lower()
            or q in f["name"].lower()
            or q in (f.get("description") or "").lower()
            or any(q in p.lower() for p in (f.get("params") or []))
        ]
    else:
        filtered = families

    return {
        "catalog_url": "https://lmstudio.ai/models",
        "families": filtered,
    }


async def fetch_lmstudio_catalog_family(slug: str) -> dict[str, Any]:
    clean_slug = re.sub(r"[^a-zA-Z0-9._-]", "", slug or "")
    now = time.time()
    cached = _FAMILY_CACHE.get(clean_slug)
    if cached and (now - cached[0]) < 600:
        return {
            "slug": clean_slug,
            "url": f"https://lmstudio.ai/models/{clean_slug}",
            "variants": cached[1],
        }

    variants: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(
            timeout=6.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"},
        ) as client:
            resp = await client.get(f"https://lmstudio.ai/models/{clean_slug}")
            if resp.status_code == 200:
                variants = parse_lmstudio_family_variants_html(resp.text)
                if variants:
                    _FAMILY_CACHE[clean_slug] = (now, variants)
    except Exception:
        pass

    if not variants:
        for fb in _FALLBACK_CATALOG_FAMILIES:
            if fb["slug"] == clean_slug and fb.get("variants"):
                variants = fb["variants"]
                break

    return {
        "slug": clean_slug,
        "url": f"https://lmstudio.ai/models/{clean_slug}",
        "variants": variants,
    }


async def search_huggingface_models(
    query: str = "",
    fmt: str = "all",
    limit: int = 20,
) -> dict[str, Any]:
    q = (query or "").strip()
    fmt_low = (fmt or "all").strip().lower()

    params_list: list[dict[str, Any]] = []
    if q:
        if fmt_low in ("gguf", "mlx"):
            params_list.append(
                {"search": q, "filter": fmt_low, "sort": "downloads", "direction": "-1", "limit": str(limit)}
            )
        else:
            params_list.append(
                {"search": q, "filter": "gguf", "sort": "downloads", "direction": "-1", "limit": str(limit // 2 + 4)}
            )
            params_list.append(
                {"search": q, "filter": "mlx", "sort": "downloads", "direction": "-1", "limit": str(limit // 2 + 4)}
            )
    else:
        if fmt_low == "gguf":
            params_list.append(
                {"author": "lmstudio-community", "filter": "gguf", "sort": "downloads", "direction": "-1", "limit": str(limit)}
            )
        elif fmt_low == "mlx":
            params_list.append(
                {"author": "mlx-community", "sort": "downloads", "direction": "-1", "limit": str(limit)}
            )
        else:
            params_list.append(
                {"author": "lmstudio-community", "sort": "downloads", "direction": "-1", "limit": str(limit // 2 + 4)}
            )
            params_list.append(
                {"author": "mlx-community", "sort": "downloads", "direction": "-1", "limit": str(limit // 2 + 4)}
            )

    raw_items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for p in params_list:
            try:
                resp = await client.get("https://huggingface.co/api/models", params=p)
                if resp.status_code == 200 and isinstance(resp.json(), list):
                    raw_items.extend(resp.json())
            except Exception:
                pass

    seen_ids: set[str] = set()
    models: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("id") or item.get("modelId") or "")
        if not repo_id or repo_id in seen_ids:
            continue
        seen_ids.add(repo_id)
        tags = [str(t).lower() for t in (item.get("tags") or [])]
        is_mlx = "mlx" in tags or "mlx" in repo_id.lower()
        is_gguf = "gguf" in tags or "gguf" in repo_id.lower()
        detected_fmt = "mlx" if is_mlx and not is_gguf else ("gguf" if is_gguf else "safetensors")
        models.append(
            {
                "id": repo_id,
                "url": f"https://huggingface.co/{repo_id}",
                "downloads": int(item.get("downloads") or 0),
                "likes": int(item.get("likes") or 0),
                "format": detected_fmt,
                "pipeline_tag": item.get("pipeline_tag"),
                "vision": "image-text-to-text" in tags or "vision" in tags,
            }
        )

    models.sort(key=lambda x: x["downloads"], reverse=True)
    return {
        "hf_search_url": f"https://huggingface.co/models?search={q}" if q else "https://huggingface.co/models?other=lmstudio",
        "models": models[:limit],
    }
