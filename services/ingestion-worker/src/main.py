"""
Ingestion worker entrypoint. Runs the worker loop.
"""
import logging
import sys

from dotenv import load_dotenv

# Load .env from project root or current dir
load_dotenv()

from .worker import dequeue_job, process_job

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure logging to stdout with timestamps."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


async def run_worker_loop() -> None:
    """Main worker loop: dequeue jobs, process each."""
    logger.info("run_worker_loop started")

    while True:
        try:
            payload = await dequeue_job()
            if payload:
                logger.info("run_worker_loop dequeued job_id=%s", payload.get("job_id"))
                await process_job(payload)
        except KeyboardInterrupt:
            logger.info("run_worker_loop interrupted")
            break
        except Exception as e:
            logger.exception("run_worker_loop error: %s", e)

    logger.info("run_worker_loop ended")


def main() -> None:
    configure_logging()
    logger.info("main started")
    try:
        import asyncio
        asyncio.run(run_worker_loop())
    except KeyboardInterrupt:
        pass
    logger.info("main ended")


if __name__ == "__main__":
    main()
