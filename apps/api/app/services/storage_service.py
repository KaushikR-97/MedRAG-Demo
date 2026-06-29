import hashlib
from dataclasses import dataclass

import boto3
from botocore.client import Config
from fastapi import UploadFile

from app.core.config import settings


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    key: str
    uri: str
    sha256: str
    size_bytes: int


class ObjectStorageService:
    def __init__(self) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )

    async def put_upload(self, *, file: UploadFile, key: str) -> StoredObject:
        content = await file.read()
        content_type = file.content_type or "application/octet-stream"
        return self.put_bytes(content=content, key=key, content_type=content_type)

    def put_bytes(self, *, content: bytes, key: str, content_type: str = "application/octet-stream") -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        self.ensure_bucket()
        self.client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return StoredObject(
            bucket=settings.s3_bucket,
            key=key,
            uri=f"s3://{settings.s3_bucket}/{key}",
            sha256=digest,
            size_bytes=len(content),
        )

    def get_bytes(self, *, bucket: str, key: str) -> bytes:
        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def ensure_bucket(self) -> None:
        existing = [bucket["Name"] for bucket in self.client.list_buckets().get("Buckets", [])]
        if settings.s3_bucket not in existing:
            self.client.create_bucket(Bucket=settings.s3_bucket)
