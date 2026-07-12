"""Raw body 的本地 gzip Blob Store；数据库只保存返回的相对路径。"""
from __future__ import annotations

import gzip
import os
from pathlib import Path


class FileFetchBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, artifact_id: str, body: bytes) -> str:
        relative = Path(artifact_id[:2]) / f"{artifact_id}.gz"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        with gzip.open(temporary, "wb") as stream:
            stream.write(body)
        os.replace(temporary, target)
        return relative.as_posix()

    def get(self, blob_path: str) -> bytes:
        with gzip.open(self._resolve(blob_path), "rb") as stream:
            return stream.read()

    def delete(self, blob_path: str) -> bool:
        path = self._resolve(blob_path)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _resolve(self, blob_path: str) -> Path:
        path = (self.root / blob_path).resolve()
        if self.root not in path.parents:
            raise ValueError("blob path 不能越过配置的存储根目录")
        return path
