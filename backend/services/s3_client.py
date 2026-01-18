"""S3 client for presigned URL generation and file operations."""

from functools import lru_cache

import boto3
from botocore.config import Config

from config import get_settings


@lru_cache
def get_s3_client():
    """Get S3 client singleton with optional transfer acceleration."""
    settings = get_settings()

    config_params = {"signature_version": "s3v4"}

    # Enable S3 Transfer Acceleration if configured
    if settings.s3_use_acceleration:
        config_params["s3"] = {"use_accelerate_endpoint": True}

    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
        config=Config(**config_params),
    )


def generate_presigned_upload_url(
    bucket: str,
    key: str,
    content_type: str,
    expires_in: int = 3600,
) -> str:
    """Generate a presigned URL for uploading to S3.

    Args:
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        content_type: MIME type of the file
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL for PUT upload
    """
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def generate_presigned_download_url(
    bucket: str,
    key: str,
    expires_in: int = 3600,
) -> str:
    """Generate a presigned URL for downloading from S3.

    Args:
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL for GET download
    """
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
        },
        ExpiresIn=expires_in,
    )


def download_file(bucket: str, key: str, local_path: str) -> None:
    """Download a file from S3 to local filesystem.

    Args:
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        local_path: Local file path to save to
    """
    s3 = get_s3_client()
    s3.download_file(bucket, key, local_path)


def upload_file(local_path: str, bucket: str, key: str, content_type: str = None) -> str:
    """Upload a file from local filesystem to S3.

    Args:
        local_path: Local file path to upload
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        content_type: Optional MIME type

    Returns:
        S3 URI of the uploaded file
    """
    s3 = get_s3_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    s3.upload_file(local_path, bucket, key, ExtraArgs=extra_args if extra_args else None)
    return f"s3://{bucket}/{key}"


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Parse an S3 URI into bucket and key.

    Args:
        s3_uri: S3 URI in format s3://bucket/key

    Returns:
        Tuple of (bucket, key)
    """
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")

    path = s3_uri[5:]  # Remove "s3://"
    parts = path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URI: {s3_uri}")

    return parts[0], parts[1]


# Multipart Upload Functions


def create_multipart_upload(bucket: str, key: str, content_type: str) -> str:
    """Initiate a multipart upload and return the upload ID.

    Args:
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        content_type: MIME type of the file

    Returns:
        Upload ID for the multipart upload
    """
    s3 = get_s3_client()
    response = s3.create_multipart_upload(
        Bucket=bucket, Key=key, ContentType=content_type
    )
    return response["UploadId"]


def generate_presigned_chunk_url(
    bucket: str,
    key: str,
    upload_id: str,
    part_number: int,
    expires_in: int = 3600,
) -> str:
    """Generate presigned URL for uploading a single chunk.

    Args:
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        upload_id: Multipart upload ID
        part_number: Part number (1-indexed, must be 1-10000)
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL for PUT upload of this part
    """
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": bucket,
            "Key": key,
            "UploadId": upload_id,
            "PartNumber": part_number,
        },
        ExpiresIn=expires_in,
    )


def complete_multipart_upload(
    bucket: str, key: str, upload_id: str, parts: list[dict]
) -> None:
    """Complete a multipart upload.

    Args:
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        upload_id: Multipart upload ID
        parts: List of completed parts with ETags
               Format: [{"PartNumber": 1, "ETag": "..."}, ...]
               Must be sorted by PartNumber in ascending order
    """
    s3 = get_s3_client()
    s3.complete_multipart_upload(
        Bucket=bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )


def abort_multipart_upload(bucket: str, key: str, upload_id: str) -> None:
    """Abort a multipart upload and clean up parts.

    Args:
        bucket: S3 bucket name
        key: Object key (path) in the bucket
        upload_id: Multipart upload ID
    """
    s3 = get_s3_client()
    s3.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
