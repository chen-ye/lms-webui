from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


ModelOrigin = Literal["local", "hub", "bundled", "remote"]


class DiskPathsInfo(BaseModel):
    concrete_dir: str | None = None
    hub_manifest_dir: str | None = None
    self_files: list[str] = Field(default_factory=list)
    shared_concrete_dir: bool = False
    delete_targets: list[str] = Field(default_factory=list)


class EnrichedModel(BaseModel):
    uid: str
    type: str
    publisher: str
    key: str
    display_name: str
    architecture: str | None = None
    quantization: dict[str, Any] | None = None
    size_bytes: int = 0
    params_string: str | None = None
    loaded_instances: list[dict[str, Any]] = Field(default_factory=list)
    max_context_length: int | None = None
    format: str | None = None
    capabilities: dict[str, Any] | None = None
    description: str | None = None
    variants: list[str] | None = None
    selected_variant: str | None = None
    decision_type: str | None = None
    has_vision_adapter: bool | None = None

    # Host-enriched metadata
    origin: ModelOrigin = "remote"
    device_identifier: str | None = None
    device_name: str | None = None
    indexed_model_identifier: str | None = None
    disk_paths: DiskPathsInfo = Field(default_factory=DiskPathsInfo)
    deletable: bool = False
    is_loaded: bool = False
    catalog_url: str | None = None
    hf_url: str | None = None


class LoadModelRequest(BaseModel):
    model: str
    context_length: int | None = None
    eval_batch_size: int | None = None
    flash_attention: bool | None = None
    num_experts: int | None = None
    offload_kv_cache_to_gpu: bool | None = None
    echo_load_config: bool = True


class UnloadModelRequest(BaseModel):
    instance_id: str


class DeleteModelRequest(BaseModel):
    uid: str | None = None
    key: str
    selected_variant: str | None = None
    format: str | None = None
    size_bytes: int | None = None


class DownloadModelRequest(BaseModel):
    model: str
    quantization: str | None = None


class DownloadJobInfo(BaseModel):
    job_id: str
    job_identifier: str | None = None
    model_id: str
    additional_identifiers: list[str] = Field(default_factory=list)
    status: str
    total_size_bytes: int | None = None
    downloaded_bytes: int | None = None
    bytes_per_second: float | None = None
    progress_pct: float = 0.0
    started_at: str | None = None
    completed_at: str | None = None
    estimated_completion: str | None = None
    target_path: str | None = None
    error_message: str | None = None


class HfQuantizationOption(BaseModel):
    quantization: str
    filename: str
    size_bytes: int | None = None


class ServiceStatusInfo(BaseModel):
    platform: str
    service_manager: str
    service_name: str
    unit_path: str
    installed: bool
    running: bool
    exec_start: str
    working_directory: str
    port: int
    host: str
    lmstudio_url: str
