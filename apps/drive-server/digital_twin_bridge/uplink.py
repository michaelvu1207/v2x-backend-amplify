"""
AWS uplink -- uploads camera snapshots and state.json to S3.

The frontend polls state.json for near-real-time updates.  No AppSync,
Lambda, or DynamoDB required.
"""

import json
import os
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from digital_twin_bridge.config import Config

logger = logging.getLogger(__name__)


class Uplink:
    """Manages snapshot upload to S3 and state.json publishing."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._s3_client: Optional[Any] = None
        self._session: Optional[boto3.Session] = None
        self._s3_base_url = (
            config.S3_PUBLIC_BASE_URL
            or f"https://{config.S3_BUCKET}.s3.{config.S3_REGION}.amazonaws.com"
        )

        os.makedirs(self._config.LOCAL_SNAPSHOT_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # AWS initialisation
    # ------------------------------------------------------------------

    def _init_aws(self) -> None:
        if self._s3_client is not None:
            return
        try:
            self._session = boto3.Session(
                profile_name=self._config.AWS_PROFILE,
                region_name=self._config.S3_REGION,
            )
            self._s3_client = self._session.client("s3")
            logger.info(
                "AWS session initialised (profile=%s, region=%s).",
                self._config.AWS_PROFILE,
                self._config.S3_REGION,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Failed to initialise AWS session: %s", exc)
            raise

    # ------------------------------------------------------------------
    # S3 upload
    # ------------------------------------------------------------------

    def upload_snapshot(
        self,
        object_id: str,
        jpeg_bytes: bytes,
        metadata: Dict[str, str],
    ) -> str:
        """Upload a JPEG snapshot to S3.

        Returns the canonical object URL stored in state.json.
        """
        self._init_aws()
        assert self._s3_client is not None

        s3_key = f"snapshots/{object_id}/latest.jpg"

        safe_meta = {k: str(v) for k, v in metadata.items()}

        try:
            self._s3_client.put_object(
                Bucket=self._config.S3_BUCKET,
                Key=s3_key,
                Body=jpeg_bytes,
                ContentType="image/jpeg",
                Metadata=safe_meta,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("S3 upload failed for %s: %s", s3_key, exc)
            raise

        public_url = f"{self._s3_base_url}/{s3_key}"
        logger.debug("Uploaded snapshot: %s (%d bytes).", public_url, len(jpeg_bytes))
        return public_url

    # ------------------------------------------------------------------
    # state.json -- polled by the frontend
    # ------------------------------------------------------------------

    def publish_state(
        self,
        objects: List[Dict[str, Any]],
        bridge_status: Dict[str, Any],
    ) -> None:
        """Write state.json to S3 for the frontend to poll.

        Args:
            objects: List of object dicts with snapshot URLs.
            bridge_status: Current bridge health metrics.
        """
        self._init_aws()
        assert self._s3_client is not None

        state = {
            "objects": objects,
            "bridge_status": bridge_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._s3_client.put_object(
                Bucket=self._config.S3_BUCKET,
                Key="api/state.json",
                Body=json.dumps(state),
                ContentType="application/json",
                CacheControl="max-age=2",
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Failed to publish state.json: %s", exc)

    def upload_map_data(self, map_data: Dict[str, Any]) -> None:
        """Upload map data JSON to S3 at api/map-data.json."""
        self._init_aws()
        assert self._s3_client is not None

        try:
            self._s3_client.put_object(
                Bucket=self._config.S3_BUCKET,
                Key="api/map-data.json",
                Body=json.dumps(map_data),
                ContentType="application/json",
                CacheControl="max-age=3600",
            )
            logger.info("Uploaded map data to S3.")
        except (BotoCoreError, ClientError) as exc:
            logger.error("Failed to upload map data: %s", exc)

    # ------------------------------------------------------------------
    # Local storage (testing fallback)
    # ------------------------------------------------------------------

    def save_local(self, object_id: str, jpeg_bytes: bytes) -> str:
        now = datetime.now(timezone.utc)
        obj_dir = os.path.join(self._config.LOCAL_SNAPSHOT_DIR, object_id)
        os.makedirs(obj_dir, exist_ok=True)

        filename = now.strftime("%H%M%S_%f") + ".jpg"
        filepath = os.path.join(obj_dir, filename)

        with open(filepath, "wb") as f:
            f.write(jpeg_bytes)

        logger.debug("Saved local snapshot: %s (%d bytes).", filepath, len(jpeg_bytes))
        return os.path.abspath(filepath)
