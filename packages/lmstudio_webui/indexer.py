from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .models import DeleteModelRequest, DiskPathsInfo, EnrichedModel


def get_lmstudio_home(explicit_home: str | Path | None = None) -> Path:
    if explicit_home:
        return Path(explicit_home).expanduser().resolve()
    env_home = os.environ.get("LMSTUDIO_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".lmstudio").resolve()


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_format(fmt: str | None) -> str:
    if not fmt:
        return ""
    low = fmt.strip().lower()
    if low in ("mlx", "safetensors"):
        return "mlx"
    return low


class HostModelIndex:
    """Stateless reader and filesystem resolver for LM Studio's host model index."""

    def __init__(self, lmstudio_home: str | Path | None = None) -> None:
        self.lmstudio_home = get_lmstudio_home(lmstudio_home)

    @property
    def settings_path(self) -> Path:
        return self.lmstudio_home / "settings.json"

    @property
    def index_cache_path(self) -> Path:
        return self.lmstudio_home / ".internal" / "model-index-cache.json"

    @property
    def lm_link_cache_path(self) -> Path:
        return self.lmstudio_home / ".internal" / "lm-link-resume-cache.json"

    @property
    def model_data_path(self) -> Path:
        return self.lmstudio_home / ".internal" / "model-data.json"

    @property
    def hub_models_dir(self) -> Path:
        return (self.lmstudio_home / "hub" / "models").resolve()

    def load_model_sources(self) -> dict[str, dict[str, Any]]:
        """Read ~/.lmstudio/.internal/model-data.json map of modelId -> source metadata."""
        raw = _read_json_file(self.model_data_path)
        entries = raw.get("json")
        out: dict[str, dict[str, Any]] = {}
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, list) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], dict):
                    src = item[1].get("source")
                    if isinstance(src, dict):
                        out[item[0]] = src
        return out

    def _resolve_external_links(
        self,
        key: str,
        origin: str,
        matched_idx: dict[str, Any] | None,
        model_sources: dict[str, dict[str, Any]],
    ) -> tuple[str | None, str | None]:
        catalog_url: str | None = None
        hf_url: str | None = None

        src = model_sources.get(key)
        if src:
            if src.get("type") == "hub" and src.get("url"):
                catalog_url = str(src["url"])
            elif src.get("type") == "huggingface" and src.get("owner") and src.get("repo"):
                hf_url = f"https://huggingface.co/{src['owner']}/{src['repo']}"

        if matched_idx is not None:
            idx_id = str(matched_idx.get("indexedModelIdentifier") or "")
            if not src and idx_id in model_sources:
                s2 = model_sources[idx_id]
                if s2.get("type") == "hub" and s2.get("url"):
                    catalog_url = str(s2["url"])
                elif s2.get("type") == "huggingface" and s2.get("owner") and s2.get("repo"):
                    hf_url = f"https://huggingface.co/{s2['owner']}/{s2['repo']}"

            virtual = matched_idx.get("virtual") or {}
            concrete_id = str(virtual.get("concreteModelIndexedModelIdentifier") or "")
            if concrete_id and "/" in concrete_id and not hf_url:
                parts = concrete_id.split("/")
                hf_url = f"https://huggingface.co/{parts[0]}/{parts[1]}"

            subpath = str(matched_idx.get("containingDirSubpath") or "")
            if not hf_url and origin in ("local", "bundled") and "/" in subpath:
                parts = subpath.split("/")
                hf_url = f"https://huggingface.co/{parts[0]}/{parts[1]}"

        if not catalog_url and origin in ("hub", "remote") and "/" in key:
            catalog_url = f"https://lmstudio.ai/models/{key}"

        return catalog_url, hf_url

    def get_settings(self) -> dict[str, Any]:
        return _read_json_file(self.settings_path)

    def get_downloads_folder(self) -> Path:
        settings = self.get_settings()
        raw = settings.get("downloadsFolder")
        if raw and isinstance(raw, str):
            return Path(raw).expanduser().resolve()
        return (self.lmstudio_home / "models").resolve()

    def get_default_context_length(self) -> int:
        settings = self.get_settings()
        dcl = settings.get("defaultContextLength")
        if isinstance(dcl, dict) and isinstance(dcl.get("value"), int):
            return dcl["value"]
        return 8192

    def get_peer_device_map(self) -> dict[str, str]:
        """Map LM Link deviceIdentifier -> human-readable deviceName."""
        data = _read_json_file(self.lm_link_cache_path)
        peers_map: dict[str, str] = {}
        for net in data.get("networks") or []:
            info = net.get("info") or {}
            for peer in info.get("peers") or []:
                dev_id = peer.get("deviceIdentifier")
                dev_name = peer.get("deviceName") or peer.get("hostname")
                if dev_id and dev_name:
                    peers_map[str(dev_id)] = str(dev_name)
        return peers_map

    def _query_lms_ls_remote_devices(self) -> list[dict[str, Any]]:
        """Optionally query `lms ls --json` if `lms` binary exists to disambiguate multiple remote peers."""
        lms_bin = self.lmstudio_home / "bin" / "lms"
        if not lms_bin.is_file():
            found = shutil.which("lms")
            if not found:
                return []
            lms_bin = Path(found)
        try:
            res = subprocess.run(
                [str(lms_bin), "ls", "--json"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                parsed = json.loads(res.stdout)
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass
        return []

    def load_index_models(self) -> list[dict[str, Any]]:
        data = _read_json_file(self.index_cache_path)
        models = data.get("models")
        return models if isinstance(models, list) else []

    def _match_index_entry(
        self,
        api_model: dict[str, Any],
        index_models: list[dict[str, Any]],
        consumed_concrete_dirs: set[str],
    ) -> dict[str, Any] | None:
        key = str(api_model.get("key") or "").strip().lower()
        selected_variant = str(api_model.get("selected_variant") or "").strip().lower()
        api_fmt = _normalize_format(api_model.get("format"))
        api_size = int(api_model.get("size_bytes") or 0)

        target_ids = {k for k in (selected_variant, key) if k}
        for v in api_model.get("variants") or []:
            if v:
                target_ids.add(str(v).strip().lower())

        candidates: list[tuple[int, dict[str, Any]]] = []
        for idx in index_models:
            # Skip remote entries if any ever appear in index cache
            if idx.get("deviceIdentifier") is not None:
                continue

            idx_fmt = _normalize_format(idx.get("format"))
            if api_fmt and idx_fmt and api_fmt != idx_fmt:
                continue

            concrete_dir = str(idx.get("concreteModelDirAbsolutePath") or "")
            containing_dir = str(idx.get("containingDirAbsolutePath") or "")
            consume_token = f"{idx.get('sourceDirectoryType')}:{concrete_dir}:{idx.get('entryPoint', {}).get('absPath', '')}"
            if consume_token in consumed_concrete_dirs:
                continue

            idx_ids: set[str] = set()
            for field in ("defaultIdentifier", "indexedModelIdentifier", "originalIndexedModelIdentifier"):
                val = idx.get(field)
                if val:
                    idx_ids.add(str(val).strip().lower())
            for auto_id in idx.get("autoIdentifiers") or []:
                if auto_id:
                    idx_ids.add(str(auto_id).strip().lower())

            if not (target_ids & idx_ids):
                continue

            idx_size = int(idx.get("sizeBytes") or 0)
            # Compute priority score:
            # Prefer exact size match, then prefer 'hub' (when key matches a hub virtual model) or 'user', and prefer non-isAlt or exact selected_variant match
            score = 0
            if api_size > 0 and idx_size == api_size:
                score += 100
            elif api_size > 0 and abs(idx_size - api_size) < 1_000_000:
                score += 50
            else:
                # If size differs by more than 1MB, it's a different quantization/remote peer model!
                continue

            if selected_variant and selected_variant == str(idx.get("defaultIdentifier") or "").strip().lower():
                score += 20
            if key and key == str(idx.get("defaultIdentifier") or "").strip().lower():
                score += 15
            if idx.get("sourceDirectoryType") == "hub" and "/" in key:
                score += 10
            if containing_dir:
                score += 1

            candidates.append((score, idx))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best = candidates[0][1]
        concrete_dir = str(best.get("concreteModelDirAbsolutePath") or "")
        consume_token = f"{best.get('sourceDirectoryType')}:{concrete_dir}:{best.get('entryPoint', {}).get('absPath', '')}"
        consumed_concrete_dirs.add(consume_token)
        # Also mark underlying user concrete dir consumed if this was a hub model
        if best.get("sourceDirectoryType") == "hub":
            consumed_concrete_dirs.add(f"user:{concrete_dir}:")
        return best

    def _compute_disk_paths(
        self,
        matched_idx: dict[str, Any],
        index_models: list[dict[str, Any]],
    ) -> tuple[str, DiskPathsInfo, bool]:
        src_type = str(matched_idx.get("sourceDirectoryType") or "user")
        concrete_dir = matched_idx.get("concreteModelDirAbsolutePath")
        containing_dir = matched_idx.get("containingDirAbsolutePath")

        if src_type == "bundled":
            return (
                "bundled",
                DiskPathsInfo(
                    concrete_dir=concrete_dir,
                    hub_manifest_dir=None,
                    self_files=[
                        str(f["absPath"])
                        for f in (matched_idx.get("selfFiles") or [])
                        if isinstance(f, dict) and f.get("absPath")
                    ],
                    shared_concrete_dir=False,
                    delete_targets=[],
                ),
                False,
            )

        # Find all distinct 'user' entries sharing this concreteModelDirAbsolutePath
        user_entries_in_dir = [
            m
            for m in index_models
            if m.get("sourceDirectoryType") == "user"
            and m.get("concreteModelDirAbsolutePath") == concrete_dir
        ]
        distinct_user_ids = {
            str(m.get("indexedModelIdentifier") or "")
            for m in user_entries_in_dir
            if m.get("indexedModelIdentifier")
        }
        shared_concrete = len(distinct_user_ids) > 1

        if src_type == "hub":
            virtual = matched_idx.get("virtual") or {}
            concrete_id = virtual.get("concreteModelIndexedModelIdentifier")
            concrete_entry = next(
                (
                    m
                    for m in user_entries_in_dir
                    if m.get("indexedModelIdentifier") == concrete_id
                ),
                user_entries_in_dir[0] if user_entries_in_dir else None,
            )
            concrete_self_files = [
                str(f["absPath"])
                for f in ((concrete_entry or {}).get("selfFiles") or [])
                if isinstance(f, dict) and f.get("absPath")
            ]

            delete_targets: list[str] = []
            if shared_concrete and concrete_self_files:
                delete_targets.extend(concrete_self_files)
            elif concrete_dir:
                delete_targets.append(str(concrete_dir))

            # Check if any other concrete variants for this same hub manifest dir exist
            other_hub_variants = [
                m
                for m in index_models
                if m.get("sourceDirectoryType") == "hub"
                and m.get("containingDirAbsolutePath") == containing_dir
                and m.get("concreteModelDirAbsolutePath") != concrete_dir
            ]
            if containing_dir and not other_hub_variants:
                delete_targets.append(str(containing_dir))

            return (
                "hub",
                DiskPathsInfo(
                    concrete_dir=concrete_dir,
                    hub_manifest_dir=containing_dir,
                    self_files=concrete_self_files,
                    shared_concrete_dir=shared_concrete,
                    delete_targets=delete_targets,
                ),
                bool(delete_targets),
            )

        # Default: 'user' model
        self_files = [
            str(f["absPath"])
            for f in (matched_idx.get("selfFiles") or [])
            if isinstance(f, dict) and f.get("absPath")
        ]
        delete_targets = []
        if shared_concrete and self_files:
            delete_targets.extend(self_files)
        elif concrete_dir:
            delete_targets.append(str(concrete_dir))

        return (
            "local",
            DiskPathsInfo(
                concrete_dir=concrete_dir,
                hub_manifest_dir=None,
                self_files=self_files,
                shared_concrete_dir=shared_concrete,
                delete_targets=delete_targets,
            ),
            bool(delete_targets),
        )

    def enrich_models(
        self,
        api_models: list[dict[str, Any]],
        use_lms_cli_for_peers: bool = True,
    ) -> list[EnrichedModel]:
        index_models = self.load_index_models()
        peer_map = self.get_peer_device_map()
        model_sources = self.load_model_sources()
        lms_cli_models = self._query_lms_ls_remote_devices() if use_lms_cli_for_peers else []

        # Queue of remote CLI models by (modelKey_lower, format_norm, sizeBytes)
        remote_cli_buckets: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        for cm in lms_cli_models:
            dev_id = cm.get("deviceIdentifier")
            if not dev_id:
                continue
            k = str(cm.get("modelKey") or "").strip().lower()
            fmt = _normalize_format(cm.get("format"))
            sz = int(cm.get("sizeBytes") or 0)
            remote_cli_buckets.setdefault((k, fmt, sz), []).append(cm)

        consumed_concrete_dirs: set[str] = set()
        enriched: list[EnrichedModel] = []

        for i, m in enumerate(api_models):
            matched = self._match_index_entry(m, index_models, consumed_concrete_dirs)
            key = str(m.get("key") or "")
            selected_variant = m.get("selected_variant")
            fmt = m.get("format")
            size_bytes = int(m.get("size_bytes") or 0)
            loaded_instances = m.get("loaded_instances") or []

            if matched is not None:
                origin, disk_paths, deletable = self._compute_disk_paths(matched, index_models)
                indexed_id = matched.get("indexedModelIdentifier")
                catalog_url, hf_url = self._resolve_external_links(key, origin, matched, model_sources)
                uid = f"{origin}:{indexed_id or key}:{fmt}:{size_bytes}:{i}"
                enriched.append(
                    EnrichedModel(
                        uid=uid,
                        type=str(m.get("type") or "llm"),
                        publisher=str(m.get("publisher") or ""),
                        key=key,
                        display_name=str(m.get("display_name") or key),
                        architecture=m.get("architecture"),
                        quantization=m.get("quantization"),
                        size_bytes=size_bytes,
                        params_string=m.get("params_string"),
                        loaded_instances=loaded_instances,
                        max_context_length=m.get("max_context_length"),
                        format=fmt,
                        capabilities=m.get("capabilities"),
                        description=m.get("description"),
                        variants=m.get("variants"),
                        selected_variant=selected_variant,
                        decision_type=m.get("decision_type"),
                        has_vision_adapter=m.get("has_vision_adapter"),
                        origin=origin,  # type: ignore[arg-type]
                        device_identifier=None,
                        device_name=None,
                        indexed_model_identifier=indexed_id,
                        disk_paths=disk_paths,
                        deletable=deletable,
                        is_loaded=len(loaded_instances) > 0,
                        catalog_url=catalog_url,
                        hf_url=hf_url,
                    )
                )
            else:
                bucket_key = (key.strip().lower(), _normalize_format(fmt), size_bytes)
                cli_list = remote_cli_buckets.get(bucket_key) or []
                cli_entry = cli_list.pop(0) if cli_list else None
                dev_id = str(cli_entry.get("deviceIdentifier")) if cli_entry and cli_entry.get("deviceIdentifier") else None
                if not dev_id and len(peer_map) == 1:
                    dev_id = next(iter(peer_map.keys()))
                dev_name = peer_map.get(dev_id) if dev_id else None
                catalog_url, hf_url = self._resolve_external_links(key, "remote", None, model_sources)
                uid = f"remote:{dev_id or 'peer'}:{selected_variant or key}:{fmt}:{size_bytes}:{i}"
                enriched.append(
                    EnrichedModel(
                        uid=uid,
                        type=str(m.get("type") or "llm"),
                        publisher=str(m.get("publisher") or ""),
                        key=key,
                        display_name=str(m.get("display_name") or key),
                        architecture=m.get("architecture"),
                        quantization=m.get("quantization"),
                        size_bytes=size_bytes,
                        params_string=m.get("params_string"),
                        loaded_instances=loaded_instances,
                        max_context_length=m.get("max_context_length"),
                        format=fmt,
                        capabilities=m.get("capabilities"),
                        description=m.get("description"),
                        variants=m.get("variants"),
                        selected_variant=selected_variant,
                        decision_type=m.get("decision_type"),
                        has_vision_adapter=m.get("has_vision_adapter"),
                        origin="remote",
                        device_identifier=dev_id,
                        device_name=dev_name,
                        indexed_model_identifier=cli_entry.get("indexedModelIdentifier") if cli_entry else None,
                        disk_paths=DiskPathsInfo(),
                        deletable=False,
                        is_loaded=len(loaded_instances) > 0,
                        catalog_url=catalog_url,
                        hf_url=hf_url,
                    )
                )

        return enriched

    def _is_safe_delete_path(self, target_path: Path) -> bool:
        """Verify target_path is strictly inside downloadsFolder or ~/.lmstudio/hub/models."""
        try:
            resolved = target_path.resolve()
        except Exception:
            return False

        allowed_roots = [self.get_downloads_folder(), self.hub_models_dir]
        for root in allowed_roots:
            try:
                root_resolved = root.resolve()
                if resolved != root_resolved and resolved.is_relative_to(root_resolved):
                    return True
            except Exception:
                continue
        return False

    def _prune_empty_parents(self, deleted_path: Path) -> None:
        """Remove empty <publisher> parent directories up to (but never including) allowed roots."""
        allowed_roots = {self.get_downloads_folder().resolve(), self.hub_models_dir.resolve()}
        parent = deleted_path.parent
        while parent and parent.exists():
            try:
                parent_resolved = parent.resolve()
            except Exception:
                break
            if parent_resolved in allowed_roots:
                break
            if not any(parent_resolved.is_relative_to(r) for r in allowed_roots):
                break
            entries = [p for p in parent.iterdir() if p.name != ".DS_Store"]
            if entries:
                break
            ds_store = parent / ".DS_Store"
            if ds_store.is_file():
                try:
                    ds_store.unlink()
                except Exception:
                    pass
            try:
                parent.rmdir()
            except Exception:
                break
            parent = parent.parent

    def resolve_model_for_deletion(
        self,
        req: DeleteModelRequest,
        enriched_models: list[EnrichedModel],
    ) -> EnrichedModel:
        if req.uid:
            for em in enriched_models:
                if em.uid == req.uid:
                    return em

        for em in enriched_models:
            if em.key != req.key:
                continue
            if req.selected_variant and em.selected_variant != req.selected_variant:
                continue
            if req.format and _normalize_format(em.format) != _normalize_format(req.format):
                continue
            if req.size_bytes is not None and em.size_bytes != req.size_bytes:
                continue
            if em.deletable:
                return em

        # Fallback if only key matches a single deletable model
        matches = [em for em in enriched_models if em.key == req.key and em.deletable]
        if len(matches) == 1:
            return matches[0]

        raise ValueError(f"Could not uniquely resolve a deletable local model for '{req.key}'.")

    def delete_model_files(self, model: EnrichedModel) -> dict[str, Any]:
        if not model.deletable or model.origin not in ("local", "hub"):
            raise PermissionError(
                f"Model '{model.key}' (origin={model.origin}) is not deletable on this host."
            )

        targets = model.disk_paths.delete_targets
        if not targets:
            raise ValueError(f"No resolved disk paths found for model '{model.key}'.")

        validated_paths: list[Path] = []
        for raw_target in targets:
            p = Path(raw_target)
            if not self._is_safe_delete_path(p):
                raise PermissionError(
                    f"Refusing to delete path outside LM Studio model directories: {raw_target}"
                )
            validated_paths.append(p)

        removed_paths: list[str] = []
        for p in validated_paths:
            if not p.exists():
                continue
            if p.is_dir():
                shutil.rmtree(p)
                removed_paths.append(str(p))
                self._prune_empty_parents(p)
            elif p.is_file():
                p.unlink()
                removed_paths.append(str(p))
                self._prune_empty_parents(p)

        return {
            "key": model.key,
            "selected_variant": model.selected_variant,
            "origin": model.origin,
            "removed_paths": removed_paths,
            "freed_bytes": model.size_bytes if removed_paths else 0,
        }
