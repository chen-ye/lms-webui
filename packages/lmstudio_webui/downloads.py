from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
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
