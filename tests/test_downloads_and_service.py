from __future__ import annotations

import json
from pathlib import Path
import plistlib

from lmstudio_webui.downloads import (
    StatelessDownloadReader,
    extract_quantizations_from_hf_siblings,
    parse_hf_repo_id,
    parse_lmstudio_catalog_html,
    parse_lmstudio_family_variants_html,
)
from lmstudio_webui.service import (
    control_service,
    get_service_status,
    install_service,
    uninstall_service,
)


def test_stateless_download_reader_filters_model_jobs(tmp_path: Path) -> None:
    home = tmp_path / ".lmstudio"
    internal = home / ".internal"
    internal.mkdir(parents=True)

    jobs_payload = {
        "jobs": [
            {
                "jobIdentifier": "backendDownload:llama.cpp-mac-arm64:1.104.2",
                "shortHashJobId": "job_backend1",
                "jobState": {"type": "completed", "completedTimestamp": 1778232114047},
                "tasks": [],
            },
            {
                "jobIdentifier": "resolvedArtifactDownload:google:gemma-4-26b-a4b-qat:2:abc",
                "shortHashJobId": "job_691a27300d",
                "jobState": {"type": "completed", "completedTimestamp": 1781443313001},
                "startedTimestamp": 1781441516038,
                "fullIndexedModelIdentifier": "google/gemma-4-26b-a4b-qat",
                "additionalIndexedModelIdentifiers": [
                    "lmstudio-community/gemma-4-26B-A4B-it-QAT-MLX-4bit"
                ],
                "fileSystemPath": str(home / "hub" / "models" / "google" / "gemma-4-26b-a4b-qat"),
                "artifactType": "model",
                "tasks": [
                    {
                        "download": {
                            "totalSizeBytes": 1000,
                            "downloadedSizeBytes": 1000,
                            "speedBytesPerSecond": 0,
                            "status": "completed",
                        }
                    }
                ],
            },
        ]
    }
    (internal / "download-jobs-info.json").write_text(json.dumps(jobs_payload), encoding="utf-8")

    reader = StatelessDownloadReader(home)
    jobs = reader.read_local_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_id == "job_691a27300d"
    assert jobs[0].model_id == "google/gemma-4-26b-a4b-qat"
    assert jobs[0].progress_pct == 100.0
    assert jobs[0].total_size_bytes == 1000


def test_hf_repo_parsing_and_quantization_extraction() -> None:
    assert parse_hf_repo_id("https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF") == "Qwen/Qwen2.5-7B-Instruct-GGUF"
    assert parse_hf_repo_id("lmstudio-community/gemma-4-GGUF") == "lmstudio-community/gemma-4-GGUF"
    assert parse_hf_repo_id("single-token") is None

    siblings = [
        {"rfilename": "README.md", "size": 1200},
        {"rfilename": "mmproj-model-f16.gguf", "size": 500_000},
        {"rfilename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf", "size": 4_683_073_216},
        {"rfilename": "Qwen2.5-7B-Instruct-Q8_0-00001-of-00002.gguf", "size": 4_000_000_000},
        {"rfilename": "Qwen2.5-7B-Instruct-Q8_0-00002-of-00002.gguf", "size": 4_100_000_000},
    ]
    quants = extract_quantizations_from_hf_siblings(siblings)
    assert len(quants) == 2
    assert quants[0].quantization == "Q4_K_M"
    assert quants[0].size_bytes == 4_683_073_216
    assert quants[1].quantization == "Q8_0"
    assert quants[1].size_bytes == 8_100_000_000


def test_macos_launchd_service_registration(tmp_path: Path) -> None:
    res = install_service(
        port=8425,
        host="127.0.0.1",
        lmstudio_url="http://localhost:1234",
        platform_override="macos",
        unit_dir=tmp_path,
    )
    assert res["platform"] == "macos"
    assert res["service_manager"] == "launchd"
    unit_file = Path(res["unit_path"])
    assert unit_file.is_file()

    plist_data = plistlib.loads(unit_file.read_bytes())
    assert plist_data["Label"] == "ai.lmstudio.webui"
    assert plist_data["RunAtLoad"] is True
    assert plist_data["KeepAlive"] is True
    assert plist_data["EnvironmentVariables"]["LMS_WEBUI_PORT"] == "8425"

    st = get_service_status(platform_override="macos", unit_dir=tmp_path)
    assert st.installed is True
    assert st.port == 8425
    assert st.host == "127.0.0.1"

    un_res = uninstall_service(platform_override="macos", unit_dir=tmp_path)
    assert un_res["removed"] is True
    assert not unit_file.exists()


def test_linux_systemd_service_registration(tmp_path: Path) -> None:
    res = install_service(
        port=8430,
        host="0.0.0.0",
        lmstudio_url="http://10.0.0.5:1234",
        platform_override="linux",
        unit_dir=tmp_path,
    )
    assert res["platform"] == "linux"
    assert res["service_manager"] == "systemd"
    unit_file = Path(res["unit_path"])
    assert unit_file.is_file()
    content = unit_file.read_text(encoding="utf-8")
    assert "[Unit]" in content
    assert "Restart=always" in content
    assert 'Environment="LMS_WEBUI_PORT=8430"' in content
    assert 'Environment="LMSTUDIO_URL=http://10.0.0.5:1234"' in content

    st = get_service_status(platform_override="linux", unit_dir=tmp_path)
    assert st.installed is True
    assert st.port == 8430
    assert st.lmstudio_url == "http://10.0.0.5:1234"

    un_res = uninstall_service(platform_override="linux", unit_dir=tmp_path)
    assert un_res["removed"] is True
    assert not unit_file.exists()


def test_windows_hkcu_run_service_registration(tmp_path: Path) -> None:
    res = install_service(
        port=8440,
        host="127.0.0.1",
        lmstudio_url="http://localhost:1234",
        platform_override="windows",
        unit_dir=tmp_path,
    )
    assert res["platform"] == "windows"
    assert res["service_manager"] == "hkcu-run"
    assert res["service_name"] == "LMStudioWebUI"
    assert "pythonw.exe" in res["exec_start"]
    assert any("HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" in c for c in res["commands"])

    state_file = Path(res["unit_path"])
    assert state_file.is_file()
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["registry_key"] == r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run\LMStudioWebUI"
    assert payload["port"] == 8440

    st = get_service_status(platform_override="windows", unit_dir=tmp_path)
    assert st.installed is True
    assert st.service_manager == "hkcu-run"
    assert st.port == 8440
    assert st.host == "127.0.0.1"

    ctrl = control_service("restart", platform_override="windows", unit_dir=tmp_path, dry_run=True)
    assert ctrl["platform"] == "windows"
    assert "pythonw.exe" in ctrl["command"]

    un_res = uninstall_service(platform_override="windows", unit_dir=tmp_path)
    assert un_res["removed"] is True
    assert not state_file.exists()


def test_parse_lmstudio_catalog_and_family_variants() -> None:
    sample_catalog_html = '''
    <a data-model-page-has-downloads="true" href="/models/gemma-4">
      <h2>Gemma 4</h2>
      <div aria-label="Parameter sizes"><span>12B</span><span>26B</span></div>
      <span title="Tool use"></span><span title="Vision"></span>
      <p>Google&#x27;s open multimodal family.</p>
    </a>
    '''
    fams = parse_lmstudio_catalog_html(sample_catalog_html)
    assert len(fams) == 1
    assert fams[0]["slug"] == "gemma-4"
    assert fams[0]["name"] == "Gemma 4"
    assert fams[0]["params"] == ["12B", "26B"]
    assert fams[0]["capabilities"] == ["Tool use", "Vision"]
    assert fams[0]["url"] == "https://lmstudio.ai/models/gemma-4"

    sample_family_html = '''
    <div>
      <a href="/models/google/gemma-4-12b">google/gemma-4-12b</a><span>7.40 GB</span>
      <a href="/models/google/gemma-4-26b-a4b-qat">google/gemma-4-26b-a4b-qat</a><span>15.60 GB</span>
    </div>
    '''
    variants = parse_lmstudio_family_variants_html(sample_family_html)
    assert len(variants) == 2
    assert variants[0]["model_id"] == "google/gemma-4-12b"
    assert variants[0]["size"] == "7.40 GB"
    assert variants[1]["model_id"] == "google/gemma-4-26b-a4b-qat"
    assert variants[1]["size"] == "15.60 GB"
