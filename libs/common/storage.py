from datetime import datetime, timedelta, timezone
import math
from urllib.parse import urlparse, urlunparse

import boto3
from botocore.client import Config

from libs.common.config import get_settings


class ObjectStorage:
    def __init__(self) -> None:
        s = get_settings()
        self.settings = s
        self.bucket = s.storage_bucket
        self.ttl_seconds = s.download_url_ttl_seconds
        common_config = Config(signature_version='s3v4', s3={'addressing_style': 'path'})

        # Used by backend services running in Docker network.
        self.upload_client = boto3.client(
            's3',
            endpoint_url=s.storage_endpoint,
            region_name=s.storage_region,
            aws_access_key_id=s.storage_access_key,
            aws_secret_access_key=s.storage_secret_key,
            use_ssl=s.storage_secure,
            config=common_config,
        )

        # Used for presigned URLs returned to browser clients.
        self.sign_client = boto3.client(
            's3',
            endpoint_url=self._sign_endpoint(),
            region_name=s.storage_region,
            aws_access_key_id=s.storage_access_key,
            aws_secret_access_key=s.storage_secret_key,
            use_ssl=s.storage_secure,
            config=common_config,
        )

    def ensure_bucket(self) -> None:
        buckets = [item['Name'] for item in self.upload_client.list_buckets().get('Buckets', [])]
        if self.bucket not in buckets:
            self.upload_client.create_bucket(Bucket=self.bucket)
        self._ensure_lifecycle_rule()

    def upload_file(self, local_path: str, key: str, content_type: str = 'audio/mpeg') -> None:
        self.upload_client.upload_file(local_path, self.bucket, key, ExtraArgs={'ContentType': content_type})

    def sign_download_url(self, key: str) -> tuple[str, datetime]:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        filename = key.rsplit('/', 1)[-1] or 'audio.mp3'
        content_type = self._guess_content_type(filename)
        url = self.sign_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': self.bucket,
                'Key': key,
                'ResponseContentDisposition': f'attachment; filename=\"{filename}\"',
                'ResponseContentType': content_type,
            },
            ExpiresIn=self.ttl_seconds,
        )
        return url, expires_at

    def _sign_endpoint(self) -> str:
        public_base = (self.settings.storage_public_endpoint or '').strip()
        if public_base:
            return public_base

        internal = urlparse(self.settings.storage_endpoint)
        if internal.hostname == 'minio':
            return urlunparse((
                internal.scheme or 'http',
                'localhost:9000',
                '',
                '',
                '',
                '',
            ))
        return self.settings.storage_endpoint

    def _ensure_lifecycle_rule(self) -> None:
        # S3 lifecycle expiration is day-based; 24h => 1 day.
        retention_hours = max(1, int(self.settings.object_retention_hours))
        retention_days = max(1, math.ceil(retention_hours / 24))
        rule_id = 'grab-auto-expire'

        lifecycle = {
            'Rules': [
                {
                    'ID': rule_id,
                    'Status': 'Enabled',
                    'Filter': {'Prefix': ''},
                    'Expiration': {'Days': retention_days},
                }
            ]
        }
        self.upload_client.put_bucket_lifecycle_configuration(
            Bucket=self.bucket,
            LifecycleConfiguration=lifecycle,
        )

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        lower = filename.lower()
        if lower.endswith('.wav'):
            return 'audio/wav'
        return 'audio/mpeg'
