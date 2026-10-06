"""System health response models."""

from typing import Literal

from pydantic import Field, BaseModel


Health = Literal["normal", "warning", "critical"]


class Thresholds(BaseModel):
    """Usage fractions at which a resource turns warning / critical."""

    warning: float
    critical: float


class ResourceOut(BaseModel):
    """One server resource (disk, memory, CPU)."""

    key: Literal["disk", "memory", "cpu"]
    label: str
    detail: str = Field(description="What is measured, e.g. the partition path")
    fraction: float = Field(description="Used fraction (0–1)")
    used: str
    capacity: str
    free: str
    status: Health
    thresholds: Thresholds


class ServiceItem(BaseModel):
    """A labelled value shown in a service's details."""

    label: str
    value: str


class ServiceOut(BaseModel):
    """An application service and its health."""

    key: str
    name: str
    version: str | None = None
    status: Health
    response_ms: float | None = Field(None, description="Time of one light probe")
    details: list[ServiceItem] = Field(default_factory=list)
    note: str | None = None


class StorageItem(BaseModel):
    """A category of data on disk."""

    key: str
    label: str
    description: str
    files: int
    bytes: int
    size: str
    regenerable: bool = Field(description="Can be deleted and rebuilt on demand")


class SystemOut(BaseModel):
    """System health snapshot."""

    condition: Health
    measured_at: str = Field(description="ISO-8601 UTC time of the reading")
    cache_seconds: int = Field(description="Readings are reused for this long")
    host: str
    os: str
    environment: str = Field(
        description="How the app is served (production build or API only)"
    )
    python: str
    titan3d: str
    commit: str
    data_dir: str
    server_uptime_s: float
    app_uptime_s: float
    resources: list[ResourceOut]
    services: list[ServiceOut]
    storage: list[StorageItem]
    notes: list[str]


class CacheClearOut(BaseModel):
    """Result of clearing regenerable caches."""

    files: int
    bytes: int
    size: str
