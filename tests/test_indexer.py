from __future__ import annotations

import json
from pathlib import Path
import pytest

from lmstudio_webui.indexer import HostModelIndex
from lmstudio_webui.models import DeleteModelRequest, DiskPathsInfo, EnrichedModel


@pytest.fixture()
def fake_lms_home(tmp_path: Path) -> Path:
    home = tmp_path / ".lmstudio"
    models_dir = home / "models"
    hub_dir = home / "hub" / "models"
    bundled_dir = home / ".internal" / "bundled-models"
    internal_dir = home / ".internal"

    models_dir.mkdir(parents=True, exist_ok=True)
    hub_dir.mkdir(parents=True, exist_ok=True)
    bundled_dir.mkdir(parents=True, exist_ok=True)
    internal_dir.mkdir(parents=True, exist_ok=True)

    # 1. Direct user model
    user_model_dir = models_dir / "torchcast-ai" / "torchcast-decision-4b-mlx"
    user_model_dir.mkdir(parents=True)
    (user_model_dir / "model.safetensors").write_bytes(b"x" * 1024)

    # 2. Hub virtual catalog model (manifest in hub/models + weights in models/)
    hub_manifest_dir = hub_dir / "google" / "gemma-4-26b-a4b-qat"
    hub_manifest_dir.mkdir(parents=True)
    (hub_manifest_dir / "model.yaml").write_text("model: google/gemma-4-26b-a4b-qat\n", encoding="utf-8")

    hub_concrete_dir = models_dir / "lmstudio-community" / "gemma-4-26B-A4B-it-QAT-MLX-4bit"
    hub_concrete_dir.mkdir(parents=True)
    (hub_concrete_dir / "model-00001.safetensors").write_bytes(b"y" * 2048)

    # 3. Shared multi-variant GGUF folder
    shared_gguf_dir = models_dir / "Qwen" / "Qwen2.5-7B-Instruct-GGUF"
    shared_gguf_dir.mkdir(parents=True)
    q4_file = shared_gguf_dir / "qwen2.5-7b-instruct-q4_k_m.gguf"
    q8_file = shared_gguf_dir / "qwen2.5-7b-instruct-q8_0.gguf"
    q4_file.write_bytes(b"4" * 512)
    q8_file.write_bytes(b"8" * 1024)

    # 4. Bundled model
    bundled_model_dir = bundled_dir / "nomic-ai" / "nomic-embed-text-v1.5-GGUF"
    bundled_model_dir.mkdir(parents=True)
    bundled_file = bundled_model_dir / "nomic-embed-text-v1.5.Q4_K_M.gguf"
    bundled_file.write_bytes(b"b" * 256)

    (home / "settings.json").write_text(
        json.dumps(
            {
                "downloadsFolder": str(models_dir),
                "defaultContextLength": {"type": "custom", "value": 16384},
            }
        ),
        encoding="utf-8",
    )

    (internal_dir / "lm-link-resume-cache.json").write_text(
        json.dumps(
            {
                "networks": [
                    {
                        "info": {
                            "peers": [
                                {
                                    "deviceIdentifier": "peer_vishnu_123",
                                    "deviceName": "Vishnu",
                                }
                            ]
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    index_cache = {
        "models": [
            {
                "domain": "llm",
                "indexedModelIdentifier": "torchcast-ai/torchcast-decision-4b-mlx",
                "defaultIdentifier": "torchcast-decision-4b-mlx",
                "autoIdentifiers": ["torchcast-decision-4b-mlx", "torchcast-ai/torchcast-decision-4b-mlx"],
                "containingDirAbsolutePath": str(user_model_dir),
                "concreteModelDirAbsolutePath": str(user_model_dir),
                "sourceDirectoryType": "user",
                "format": "safetensors",
                "sizeBytes": 5835186530,
                "selfFiles": [
                    {
                        "filename": "model.safetensors",
                        "absPath": str(user_model_dir / "model.safetensors"),
                        "sizeBytes": 5835186530,
                    }
                ],
            },
            {
                "domain": "llm",
                "indexedModelIdentifier": "google/gemma-4-26b-a4b-qat",
                "defaultIdentifier": "google/gemma-4-26b-a4b-qat",
                "autoIdentifiers": ["google/gemma-4-26b-a4b-qat", "google/gemma-4-26b-a4b-qat@4bit"],
                "containingDirAbsolutePath": str(hub_manifest_dir),
                "concreteModelDirAbsolutePath": str(hub_concrete_dir),
                "sourceDirectoryType": "hub",
                "format": "safetensors",
                "sizeBytes": 15641332573,
                "virtual": {
                    "isAlt": False,
                    "concreteModelIndexedModelIdentifier": "lmstudio-community/gemma-4-26B-A4B-it-QAT-MLX-4bit",
                },
                "selfFiles": [
                    {
                        "filename": "model.yaml",
                        "absPath": str(hub_manifest_dir / "model.yaml"),
                        "sizeBytes": 1551,
                    }
                ],
            },
            {
                "domain": "llm",
                "indexedModelIdentifier": "lmstudio-community/gemma-4-26B-A4B-it-QAT-MLX-4bit",
                "defaultIdentifier": "gemma-4-26b-a4b-it-qat-mlx",
                "autoIdentifiers": ["gemma-4-26b-a4b-it-qat-mlx"],
                "containingDirAbsolutePath": str(hub_concrete_dir),
                "concreteModelDirAbsolutePath": str(hub_concrete_dir),
                "sourceDirectoryType": "user",
                "format": "safetensors",
                "sizeBytes": 15641259285,
                "selfFiles": [
                    {
                        "filename": "model-00001.safetensors",
                        "absPath": str(hub_concrete_dir / "model-00001.safetensors"),
                        "sizeBytes": 15641259285,
                    }
                ],
            },
            {
                "domain": "llm",
                "indexedModelIdentifier": "Qwen/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_k_m.gguf",
                "defaultIdentifier": "qwen2.5-7b-instruct@q4_k_m",
                "autoIdentifiers": ["qwen2.5-7b-instruct", "qwen2.5-7b-instruct@q4_k_m"],
                "containingDirAbsolutePath": str(shared_gguf_dir),
                "concreteModelDirAbsolutePath": str(shared_gguf_dir),
                "sourceDirectoryType": "user",
                "format": "gguf",
                "sizeBytes": 4683073216,
                "entryPoint": {"absPath": str(q4_file)},
                "selfFiles": [{"filename": q4_file.name, "absPath": str(q4_file), "sizeBytes": 4683073216}],
            },
            {
                "domain": "llm",
                "indexedModelIdentifier": "Qwen/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q8_0.gguf",
                "defaultIdentifier": "qwen2.5-7b-instruct@q8_0",
                "autoIdentifiers": ["qwen2.5-7b-instruct", "qwen2.5-7b-instruct@q8_0"],
                "containingDirAbsolutePath": str(shared_gguf_dir),
                "concreteModelDirAbsolutePath": str(shared_gguf_dir),
                "sourceDirectoryType": "user",
                "format": "gguf",
                "sizeBytes": 8098123456,
                "entryPoint": {"absPath": str(q8_file)},
                "selfFiles": [{"filename": q8_file.name, "absPath": str(q8_file), "sizeBytes": 8098123456}],
            },
            {
                "domain": "embedding",
                "indexedModelIdentifier": "nomic-ai/nomic-embed-text-v1.5-GGUF/nomic-embed-text-v1.5.Q4_K_M.gguf",
                "defaultIdentifier": "text-embedding-nomic-embed-text-v1.5",
                "autoIdentifiers": ["text-embedding-nomic-embed-text-v1.5"],
                "containingDirAbsolutePath": str(bundled_model_dir),
                "concreteModelDirAbsolutePath": str(bundled_model_dir),
                "sourceDirectoryType": "bundled",
                "format": "gguf",
                "sizeBytes": 84106624,
                "selfFiles": [{"filename": bundled_file.name, "absPath": str(bundled_file), "sizeBytes": 84106624}],
            },
        ]
    }
    (internal_dir / "model-index-cache.json").write_text(json.dumps(index_cache), encoding="utf-8")
    return home


def test_enrich_and_resolve_all_model_origins(fake_lms_home: Path) -> None:
    indexer = HostModelIndex(fake_lms_home)
    assert indexer.get_default_context_length() == 16384

    api_models = [
        {
            "type": "llm",
            "publisher": "torchcast-ai",
            "key": "torchcast-decision-4b-mlx",
            "display_name": "Torchcast Decision 4B",
            "size_bytes": 5835186530,
            "format": "mlx",
            "loaded_instances": [],
        },
        {
            "type": "llm",
            "publisher": "google",
            "key": "google/gemma-4-26b-a4b-qat",
            "display_name": "Gemma 4 26B A4B QAT",
            "size_bytes": 15641332573,
            "format": "mlx",
            "variants": ["google/gemma-4-26b-a4b-qat@4bit"],
            "selected_variant": "google/gemma-4-26b-a4b-qat@4bit",
            "loaded_instances": [],
        },
        {
            # Same key as above, but GGUF on remote LM Link peer!
            "type": "llm",
            "publisher": "google",
            "key": "google/gemma-4-26b-a4b-qat",
            "display_name": "Gemma 4 26B A4B QAT",
            "size_bytes": 15634264392,
            "format": "gguf",
            "variants": ["google/gemma-4-26b-a4b-qat@q4_0"],
            "selected_variant": "google/gemma-4-26b-a4b-qat@q4_0",
            "loaded_instances": [],
        },
        {
            "type": "llm",
            "publisher": "Qwen",
            "key": "qwen2.5-7b-instruct",
            "display_name": "Qwen 2.5 7B Instruct",
            "size_bytes": 4683073216,
            "format": "gguf",
            "variants": ["qwen2.5-7b-instruct@q4_k_m", "qwen2.5-7b-instruct@q8_0"],
            "selected_variant": "qwen2.5-7b-instruct@q4_k_m",
            "loaded_instances": [],
        },
        {
            "type": "embedding",
            "publisher": "nomic-ai",
            "key": "text-embedding-nomic-embed-text-v1.5",
            "display_name": "Nomic Embed Text v1.5",
            "size_bytes": 84106624,
            "format": "gguf",
            "loaded_instances": [],
        },
    ]

    enriched = indexer.enrich_models(api_models, use_lms_cli_for_peers=False)
    assert len(enriched) == 5

    # 0: Direct local user model
    m0 = enriched[0]
    assert m0.origin == "local"
    assert m0.deletable is True
    assert m0.disk_paths.shared_concrete_dir is False
    assert m0.disk_paths.delete_targets == [
        str(fake_lms_home / "models" / "torchcast-ai" / "torchcast-decision-4b-mlx")
    ]

    # 1: Hub virtual catalog model (both concrete weights dir and hub manifest dir)
    m1 = enriched[1]
    assert m1.origin == "hub"
    assert m1.deletable is True
    assert m1.disk_paths.shared_concrete_dir is False
    assert set(m1.disk_paths.delete_targets) == {
        str(fake_lms_home / "models" / "lmstudio-community" / "gemma-4-26B-A4B-it-QAT-MLX-4bit"),
        str(fake_lms_home / "hub" / "models" / "google" / "gemma-4-26b-a4b-qat"),
    }

    # 2: Remote LM Link peer model with same key as m1
    m2 = enriched[2]
    assert m2.origin == "remote"
    assert m2.deletable is False
    assert m2.device_name == "Vishnu"
    assert m2.disk_paths.delete_targets == []

    # 3: Shared multi-variant GGUF folder -> only deletes Q4_K_M self_file
    m3 = enriched[3]
    assert m3.origin == "local"
    assert m3.deletable is True
    assert m3.disk_paths.shared_concrete_dir is True
    assert m3.disk_paths.delete_targets == [
        str(
            fake_lms_home
            / "models"
            / "Qwen"
            / "Qwen2.5-7B-Instruct-GGUF"
            / "qwen2.5-7b-instruct-q4_k_m.gguf"
        )
    ]

    # 4: Bundled model -> protected
    m4 = enriched[4]
    assert m4.origin == "bundled"
    assert m4.deletable is False
    assert m4.disk_paths.delete_targets == []


def test_delete_hub_and_shared_variant_models_safely(fake_lms_home: Path) -> None:
    indexer = HostModelIndex(fake_lms_home)
    api_models = [
        {
            "type": "llm",
            "publisher": "google",
            "key": "google/gemma-4-26b-a4b-qat",
            "display_name": "Gemma 4 26B A4B QAT",
            "size_bytes": 15641332573,
            "format": "mlx",
            "selected_variant": "google/gemma-4-26b-a4b-qat@4bit",
        },
        {
            "type": "llm",
            "publisher": "Qwen",
            "key": "qwen2.5-7b-instruct",
            "display_name": "Qwen 2.5 7B Instruct",
            "size_bytes": 4683073216,
            "format": "gguf",
            "selected_variant": "qwen2.5-7b-instruct@q4_k_m",
        },
    ]
    enriched = indexer.enrich_models(api_models, use_lms_cli_for_peers=False)

    # Delete Hub model: should remove both concrete weights dir & hub manifest dir + prune empty publisher dirs
    hub_model = indexer.resolve_model_for_deletion(
        DeleteModelRequest(key="google/gemma-4-26b-a4b-qat", format="mlx"),
        enriched,
    )
    res_hub = indexer.delete_model_files(hub_model)
    assert len(res_hub["removed_paths"]) == 2
    assert not (fake_lms_home / "models" / "lmstudio-community").exists()
    assert not (fake_lms_home / "hub" / "models" / "google").exists()
    # Root directories remain intact
    assert (fake_lms_home / "models").is_dir()
    assert (fake_lms_home / "hub" / "models").is_dir()

    # Delete Q4_K_M variant in shared GGUF folder: should remove only Q4_K_M and keep Q8_0
    qwen_model = indexer.resolve_model_for_deletion(
        DeleteModelRequest(
            key="qwen2.5-7b-instruct",
            selected_variant="qwen2.5-7b-instruct@q4_k_m",
        ),
        enriched,
    )
    res_qwen = indexer.delete_model_files(qwen_model)
    assert len(res_qwen["removed_paths"]) == 1
    shared_dir = fake_lms_home / "models" / "Qwen" / "Qwen2.5-7B-Instruct-GGUF"
    assert not (shared_dir / "qwen2.5-7b-instruct-q4_k_m.gguf").exists()
    assert (shared_dir / "qwen2.5-7b-instruct-q8_0.gguf").is_file()


def test_path_traversal_guard_blocks_outside_deletion(fake_lms_home: Path, tmp_path: Path) -> None:
    indexer = HostModelIndex(fake_lms_home)
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("do not delete", encoding="utf-8")

    malicious_model = EnrichedModel(
        uid="local:evil:gguf:100:0",
        type="llm",
        publisher="evil",
        key="evil/model",
        display_name="Evil",
        origin="local",
        deletable=True,
        disk_paths=DiskPathsInfo(
            concrete_dir=str(outside_file),
            delete_targets=[str(outside_file)],
        ),
    )
    with pytest.raises(PermissionError):
        indexer.delete_model_files(malicious_model)
    assert outside_file.is_file()
