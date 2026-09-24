"""Object storage abstraction -- MinIO in production, filesystem in dev.

The spec's persistence layer is "PostgreSQL + MinIO".  Everything above this
module writes through ``StorageBackend``, so the pipeline, report builder and
route handlers are identical whether the bytes land in an S3 bucket or under
./storage.  Selected by STORAGE_BACKEND.
"""
from __future__ import annotations

import io
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings


class StorageBackend(ABC):
    """Contract every storage implementation honours.

    ``key`` is always a POSIX-style relative path such as
    ``uploads/2026/09/sess_ab12_FRONT.jpg`` -- it is a bucket key on MinIO and a
    path fragment under STORAGE_DIR locally.
    """

    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def url_for(self, key: str) -> str: ...

    @abstractmethod
    def local_path(self, key: str) -> Path:
        """A real filesystem path, materialising the object if necessary.

        OpenCV and the PDF builder need to touch actual files; this is the
        escape hatch that keeps them backend-agnostic.
        """


class LocalStorage(StorageBackend):
    """Filesystem backend -- the zero-install default."""

    def __init__(self, root: Path | None = None, public_prefix: str | None = None):
        self.root = Path(root or settings.STORAGE_DIR)
        self.public_prefix = (public_prefix or settings.PUBLIC_STORAGE_URL).rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Defend against traversal: the resolved path must stay under root.
        target = (self.root / key.lstrip("/")).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise ValueError(f"Refusing to access key outside storage root: {key!r}")
        return target

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> None:
        p = self._resolve(key)
        if p.exists():
            p.unlink()

    def url_for(self, key: str) -> str:
        return f"{self.public_prefix}/{key.lstrip('/')}"

    def local_path(self, key: str) -> Path:
        return self._resolve(key)


class MinioStorage(StorageBackend):
    """S3-compatible backend (MinIO) -- the production path from docker-compose."""

    def __init__(self) -> None:
        import boto3  # imported lazily so dev never needs the dependency
        from botocore.client import Config

        self.bucket = settings.MINIO_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
        )
        self._cache = Path(settings.STORAGE_DIR) / ".minio-cache"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=io.BytesIO(data), ContentType=content_type
        )
        return key

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def url_for(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600
        )

    def local_path(self, key: str) -> Path:
        target = self._cache / key
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.read(key))
        return target


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = MinioStorage() if settings.STORAGE_BACKEND == "minio" else LocalStorage()
    return _backend


# --------------------------------------------------------------------------
# Key helpers -- one place that decides the object layout
# --------------------------------------------------------------------------
def build_key(bucket: str, filename: str, when: datetime | None = None) -> str:
    """Date-partitioned key, e.g. ``uploads/2026/09/sess_ab12_FRONT.jpg``."""
    ts = when or datetime.now(timezone.utc)
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    return f"{bucket}/{ts:%Y/%m}/{safe}"


def copy_into_storage(src: Path, key: str) -> str:
    storage = get_storage()
    if isinstance(storage, LocalStorage):
        dst = storage.local_path(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return key
    return storage.save(key, Path(src).read_bytes())
