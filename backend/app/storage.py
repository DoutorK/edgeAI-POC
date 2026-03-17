import logging

import boto3
from botocore.exceptions import ClientError

from .config import settings

logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.s3_region,
    endpoint_url=settings.s3_endpoint_url,
)


def ensure_bucket_exists() -> None:
    try:
        s3_client.head_bucket(Bucket=settings.s3_bucket_name)
    except ClientError:
        logger.info("Bucket inexistente; criando bucket %s", settings.s3_bucket_name)
        s3_client.create_bucket(Bucket=settings.s3_bucket_name)


def upload_structured_json(key: str, content: str) -> str:
    s3_client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="application/json",
    )
    return key
