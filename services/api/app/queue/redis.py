"""
Redis client for ingestion job queue.
Provides enqueue, status lookup, and connection lifecycle.
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import redis.asyncio as redis

logger = logging.getLogger(__name__)

INGESTION_QUEUE_KEY = "ingestion:queue"
INGESTION_JOB_PREFIX = "ingestion:job:"
JOB_TTL_SECONDS = 86400 * 7  # 7 days


def _get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379")


@asynccontextmanager
async def redis_connection():
    """Async context manager for Redis connection."""
    logger.debug("redis_connection started")
    client = redis.from_url(_get_redis_url(), decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
        logger.debug("redis_connection ended")


async def enqueue_ingestion_job(
    codebase_id: str,
    user_id: str,
    zip_storage_key: str,
    job_id: str | None = None,
) -> str:
    """
    Enqueue an ingestion job to Redis.
    Returns the job_id (UUID string).
    """
    logger.info(
        "enqueue_ingestion_job started codebase_id=%s user_id=%s zip_storage_key=%s",
        codebase_id, user_id, zip_storage_key,
    )

    if job_id is None:
        job_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "job_id": job_id,
        "codebase_id": codebase_id,
        "user_id": user_id,
        "zip_storage_key": zip_storage_key,
        "status": "queued",
        "created_at": now,
    }
    job_key = f"{INGESTION_JOB_PREFIX}{job_id}"

    logger.info("enqueue_ingestion_job storing job job_id=%s", job_id)
    async with redis_connection() as client:
        await client.hset(job_key, mapping=payload)
        await client.expire(job_key, JOB_TTL_SECONDS)
        await client.rpush(INGESTION_QUEUE_KEY, job_id)
    logger.info("enqueue_ingestion_job stored job_id=%s", job_id)

    logger.info("enqueue_ingestion_job ended job_id=%s", job_id)
    return job_id


async def get_job_status(job_id: str) -> dict | None:
    """
    Get job status from Redis.
    Returns a dict with job metadata, or None if not found.
    """
    logger.info("get_job_status started job_id=%s", job_id)

    job_key = f"{INGESTION_JOB_PREFIX}{job_id}"
    async with redis_connection() as client:
        data = await client.hgetall(job_key)
    result = data if data else None

    logger.info(
        "get_job_status ended job_id=%s found=%s",
        job_id, result is not None,
    )
    return result


async def dequeue_ingestion_job(timeout_sec: int = 30) -> dict | None:
    """
    Block until a job is available or timeout. Returns job payload or None.
    """
    logger.info("dequeue_ingestion_job started timeout_sec=%s", timeout_sec)

    async with redis_connection() as client:
        result = await client.blpop(INGESTION_QUEUE_KEY, timeout=timeout_sec)

    if result is None:
        logger.info("dequeue_ingestion_job ended timeout no job")
        return None

    _, job_id = result
    job_key = f"{INGESTION_JOB_PREFIX}{job_id}"
    async with redis_connection() as client:
        payload = await client.hgetall(job_key)

    logger.info("dequeue_ingestion_job ended job_id=%s found=%s", job_id, payload is not None)
    return payload if payload else None


async def update_job_status(
    job_id: str,
    status: str,
    message: str | None = None,
) -> None:
    """
    Update job status and optional message in Redis.
    """
    logger.info("update_job_status started job_id=%s status=%s", job_id, status)

    job_key = f"{INGESTION_JOB_PREFIX}{job_id}"
    async with redis_connection() as client:
        await client.hset(job_key, "status", status)
        if message is not None:
            await client.hset(job_key, "message", message)

    logger.info("update_job_status ended job_id=%s status=%s", job_id, status)
