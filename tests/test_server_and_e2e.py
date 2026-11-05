from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import uvicorn

from lmstudio_webui.server import app as webui_app


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict[str, Any]) -> dict[str, Any]:
    cache_root = Path.home() / "Library" / "Caches" / "ms-playwright"
    if cache_root.is_dir():
        shells = sorted(
            cache_root.glob("chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell"),
            reverse=True,
        )
        if shells:
            return {**browser_type_launch_args, "executable_path": str(shells[0])}
    return browser_type_launch_args


def create_mock_lmstudio_app(state: dict[str, Any]) -> FastAPI:
    mock_api = FastAPI()

    @mock_api.get("/api/v1/models")
    async def list_models() -> dict[str, Any]:
        return {"models": state["models"]}

    @mock_api.post("/api/v1/models/load")
    async def load_model(body: dict[str, Any]) -> dict[str, Any]:
        model_id = body["model"]
        ctx = body.get("context_length", 8192)
        for m in state["models"]:
            if m["key"] == model_id or m.get("selected_variant") == model_id or model_id in (m.get("variants") or []):
                m.setdefault("loaded_instances", []).append(
                    {
                        "id": model_id,
                        "config": {
                            "context_length": ctx,
                            "eval_batch_size": body.get("eval_batch_size", 512),
                            "flash_attention": body.get("flash_attention", True),
                            "offload_kv_cache_to_gpu": body.get("offload_kv_cache_to_gpu", True),
                        },
                        "remaining_ttl_seconds": 3600,
                    }
                )
        state["load_calls"].append(body)
        return {
            "type": "llm",
            "instance_id": model_id,
            "load_time_seconds": 1.23,
            "status": "loaded",
            "load_config": {"context_length": ctx},
        }

    @mock_api.post("/api/v1/models/unload")
    async def unload_model(body: dict[str, Any]) -> dict[str, Any]:
        inst_id = body["instance_id"]
        for m in state["models"]:
            m["loaded_instances"] = [
                i for i in (m.get("loaded_instances") or []) if i.get("id") != inst_id
            ]
        state["unload_calls"].append(inst_id)
        return {"instance_id": inst_id}

    @mock_api.post("/api/v1/models/download")
    async def download_model(body: dict[str, Any]) -> dict[str, Any]:
        state["download_calls"].append(body)
        job_id = "job_mock_999"
        state["download_jobs"][job_id] = {
            "job_id": job_id,
            "status": "downloading",
            "total_size_bytes": 2_000_000_000,
            "downloaded_bytes": 500_000_000,
            "bytes_per_second": 52_428_800,
            "started_at": "2026-11-04T12:00:00Z",
        }
        return state["download_jobs"][job_id]

    @mock_api.get("/api/v1/models/download/status/{job_id}")
    async def download_status(job_id: str) -> dict[str, Any]:
        return state["download_jobs"].get(
            job_id,
            {
                "job_id": job_id,
                "status": "completed",
                "total_size_bytes": 2_000_000_000,
                "downloaded_bytes": 2_000_000_000,
            },
        )

    return mock_api


def setup_mock_home_and_state(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    home = tmp_path / ".lmstudio"
    models_dir = home / "models"
    hub_dir = home / "hub" / "models"
    internal_dir = home / ".internal"
    models_dir.mkdir(parents=True, exist_ok=True)
    hub_dir.mkdir(parents=True, exist_ok=True)
    internal_dir.mkdir(parents=True, exist_ok=True)

    user_model_dir = models_dir / "torchcast-ai" / "torchcast-decision-4b-mlx"
    user_model_dir.mkdir(parents=True, exist_ok=True)
    (user_model_dir / "weights.safetensors").write_bytes(b"w" * 1024)

    (home / "settings.json").write_text(
        json.dumps(
            {
                "downloadsFolder": str(models_dir),
                "defaultContextLength": {"type": "custom", "value": 8192},
            }
        ),
        encoding="utf-8",
    )

    (internal_dir / "model-index-cache.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "domain": "llm",
                        "indexedModelIdentifier": "torchcast-ai/torchcast-decision-4b-mlx",
                        "defaultIdentifier": "torchcast-decision-4b-mlx",
                        "autoIdentifiers": ["torchcast-decision-4b-mlx"],
                        "containingDirAbsolutePath": str(user_model_dir),
                        "concreteModelDirAbsolutePath": str(user_model_dir),
                        "sourceDirectoryType": "user",
                        "format": "safetensors",
                        "sizeBytes": 5835186530,
                        "selfFiles": [
                            {
                                "filename": "weights.safetensors",
                                "absPath": str(user_model_dir / "weights.safetensors"),
                                "sizeBytes": 5835186530,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (internal_dir / "download-jobs-info.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "jobIdentifier": "resolvedArtifactDownload:google:gemma-4-26b-a4b-qat:2:xyz",
                        "shortHashJobId": "job_hist_001",
                        "jobState": {"type": "completed", "completedTimestamp": 1781443313001},
                        "startedTimestamp": 1781441516038,
                        "fullIndexedModelIdentifier": "google/gemma-4-26b-a4b-qat",
                        "artifactType": "model",
                        "tasks": [
                            {
                                "download": {
                                    "totalSizeBytes": 15641323739,
                                    "downloadedSizeBytes": 15641323739,
                                    "status": "completed",
                                }
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    state: dict[str, Any] = {
        "load_calls": [],
        "unload_calls": [],
        "download_calls": [],
        "download_jobs": {},
        "models": [
            {
                "type": "llm",
                "publisher": "torchcast-ai",
                "key": "torchcast-decision-4b-mlx",
                "display_name": "Torchcast Decision 4B",
                "architecture": "qwen3_5",
                "quantization": {"name": "8bit", "bits_per_weight": 8},
                "size_bytes": 5835186530,
                "params_string": "4B",
                "loaded_instances": [
                    {
                        "id": "torchcast-decision-4b-mlx",
                        "config": {"context_length": 8192, "parallel": 4},
                        "remaining_ttl_seconds": 1800,
                    }
                ],
                "max_context_length": 262144,
                "format": "mlx",
                "capabilities": {"vision": True, "trained_for_tool_use": True},
            },
            {
                "type": "llm",
                "publisher": "google",
                "key": "google/gemma-4-12b",
                "display_name": "Gemma 4 12B (Remote)",
                "architecture": "gemma4",
                "quantization": {"name": "Q8_0", "bits_per_weight": 8},
                "size_bytes": 12844836457,
                "params_string": "12B",
                "loaded_instances": [],
                "max_context_length": 262144,
                "format": "gguf",
                "capabilities": {"vision": True, "trained_for_tool_use": True},
                "variants": ["google/gemma-4-12b@q8_0"],
                "selected_variant": "google/gemma-4-12b@q8_0",
            },
        ],
    }
    return home, state


def test_playwright_e2e_webui(tmp_path: Path, page: Any) -> None:
    home, _ = setup_mock_home_and_state(tmp_path)
    mock_port = _get_free_port()
    webui_port = _get_free_port()

    # Write a small helper script to run mock LM Studio server
    mock_script = tmp_path / "run_mock_lms.py"
    mock_script.write_text(
        f"""
import json
from pathlib import Path
from fastapi import FastAPI
import uvicorn
from tests.test_server_and_e2e import create_mock_lmstudio_app, setup_mock_home_and_state

_, state = setup_mock_home_and_state(Path({str(tmp_path)!r}))
app = create_mock_lmstudio_app(state)
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port={mock_port}, log_level="warning")
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{Path(__file__).resolve().parents[1]}:{Path(__file__).resolve().parents[1] / 'packages'}"
    env["LMSTUDIO_URL"] = f"http://127.0.0.1:{mock_port}"
    env["LMSTUDIO_HOME"] = str(home)
    env["LMS_WEBUI_PORT"] = str(webui_port)

    mock_proc = subprocess.Popen([sys.executable, str(mock_script)], env=env)
    webui_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "lmstudio_webui.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(webui_port),
            "--log-level",
            "warning",
        ],
        env=env,
    )

    try:
        # Wait for both mock LM Studio server and WebUI server to start
        for target_port in (mock_port, webui_port):
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1", target_port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)

        page.goto(f"http://127.0.0.1:{webui_port}/", wait_until="networkidle")

        # 1. Verify header and model cards render
        page.wait_for_selector(".model-card")
        cards = page.locator(".model-card")
        assert cards.count() == 2
        assert "Torchcast Decision 4B" in page.content()
        assert "Gemma 4 12B (Remote)" in page.content()

        # 2. Open Load Dialog on Gemma 4 12B and load with custom context length
        gemma_card = page.locator('.model-card[data-model-key="google/gemma-4-12b"]')
        gemma_card.locator('[data-action="open-load"]').click()
        page.wait_for_selector("dialog#load-model-dialog[open]")
        page.fill("#load-context-length-input", "16384")
        page.click("#confirm-load-model-btn")
        page.wait_for_selector("dialog#load-model-dialog:not([open])", state="attached")

        # Verify Gemma is now shown as loaded
        page.wait_for_selector('.model-card[data-model-key="google/gemma-4-12b"].is-loaded')

        # 3. Switch to Downloads view and trigger a model download
        page.click("#pull-model-header-btn")
        page.wait_for_selector("#download-model-input")
        page.fill("#download-model-input", "ibm/granite-4-micro")
        page.click("#start-download-btn")
        page.wait_for_selector('[data-job-id="job_mock_999"]')
        assert "job_hist_001" in page.content()

        # 4. Switch back to Inventory and delete local Torchcast model via confirm-dialog
        page.locator("#view-switcher-control").locator("button").first.click()
        page.wait_for_selector('.model-card[data-model-key="torchcast-decision-4b-mlx"]')
        torch_card = page.locator('.model-card[data-model-key="torchcast-decision-4b-mlx"]')
        torch_card.locator('[data-action="delete-model"]').click()

        confirm_btn = page.locator("confirm-dialog#delete-model-dialog").locator('[data-role="confirm"]')
        confirm_btn.click()

        # Verify the local directory was deleted on disk (and its active instance was unloaded first!)
        for _ in range(20):
            if not (home / "models" / "torchcast-ai" / "torchcast-decision-4b-mlx").exists():
                break
            time.sleep(0.1)
        assert not (home / "models" / "torchcast-ai" / "torchcast-decision-4b-mlx").exists()

    finally:
        webui_proc.terminate()
        mock_proc.terminate()
        webui_proc.wait(timeout=5)
        mock_proc.wait(timeout=5)
