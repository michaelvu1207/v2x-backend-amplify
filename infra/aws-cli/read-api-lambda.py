import base64
import json
import math
import mimetypes
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]
GSI_NAME = os.environ.get("GSI_NAME", "gsi_geohash_time")
MAX_LIMIT = int(os.environ.get("MAX_LIMIT", "200"))
SITE_GEOHASH = os.environ["SITE_GEOHASH"]
STATE_BUCKET = os.environ["STATE_BUCKET"]
SNAPSHOT_URL_EXPIRES_SECONDS = int(os.environ["SNAPSHOT_URL_EXPIRES_SECONDS"])
DEMO_VIDEOS_PREFIX = os.environ["DEMO_VIDEOS_PREFIX"]
DEMO_VIDEO_URL_EXPIRES_SECONDS = int(os.environ["DEMO_VIDEO_URL_EXPIRES_SECONDS"])

ddb = boto3.resource("dynamodb")
table = ddb.Table(TABLE_NAME)
s3_client = boto3.client("s3")

ALLOWED_DEMO_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}


def _jsonable(value):
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value

def _strip_api_fields(item):
    # Keep storage as-is, but remove fleet identifiers from the public read API.
    if not isinstance(item, dict):
        return item
    item = dict(item)
    item.pop("fleet_id", None)
    return item

def _b64(obj):
    if obj is None:
        return None
    return base64.urlsafe_b64encode(json.dumps(obj).encode("utf-8")).decode("utf-8")

def _unb64(s):
    if not s:
        return None
    return json.loads(base64.urlsafe_b64decode(s.encode("utf-8")).decode("utf-8"))

def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
        },
        "body": json.dumps(body),
    }


def _api_base_url(event):
    headers = event.get("headers") or {}
    request_context = event.get("requestContext") or {}
    proto = headers.get("x-forwarded-proto", "https")
    domain_name = request_context.get("domainName") or headers.get("host", "")
    stage = request_context.get("stage") or ""

    if stage and stage != ("$" + "default"):
        return f"{proto}://{domain_name}/{stage}"
    return f"{proto}://{domain_name}"

def _get_s3_json(key):
    try:
        response = s3_client.get_object(Bucket=STATE_BUCKET, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "ClientError")
        status = 404 if error_code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"} else 502
        return None, _resp(status, {"error": "state_asset_unavailable", "detail": error_code, "key": key})

    body = response["Body"].read().decode("utf-8")
    try:
        return json.loads(body), None
    except json.JSONDecodeError:
        return None, _resp(502, {"error": "state_asset_invalid_json", "key": key})

def _snapshot_api_url(event, object_id, snapshot_timestamp):
    base_url = _api_base_url(event)
    encoded_object_id = quote(str(object_id), safe="")
    if snapshot_timestamp:
        encoded_version = quote(str(snapshot_timestamp), safe="")
        return f"{base_url}/snapshots/{encoded_object_id}/latest?v={encoded_version}"
    return f"{base_url}/snapshots/{encoded_object_id}/latest"

def _get_state(event):
    payload, error = _get_s3_json("api/state.json")
    if error:
        return error

    objects = []
    for item in payload.get("objects", []) or []:
        obj = dict(item)
        if obj.get("snapshot_url") and obj.get("object_id"):
            obj["snapshot_url"] = _snapshot_api_url(
                event,
                obj["object_id"],
                obj.get("snapshot_timestamp"),
            )
        objects.append(obj)
    payload["objects"] = objects
    return _resp(200, payload)

def _get_map_data():
    payload, error = _get_s3_json("api/map-data.json")
    if error:
        return error
    return _resp(200, payload)


def _get_snapshot(object_id):
    key = f"snapshots/{object_id}/latest.jpg"
    try:
        s3_client.head_object(Bucket=STATE_BUCKET, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "ClientError")
        status = 404 if error_code in {"NoSuchKey", "404", "NotFound"} else 502
        return _resp(
            status,
            {
                "error": "snapshot_unavailable",
                "objectId": object_id,
                "detail": error_code,
            },
        )

    signed_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": STATE_BUCKET, "Key": key},
        ExpiresIn=SNAPSHOT_URL_EXPIRES_SECONDS,
    )
    return {
        "statusCode": 307,
        "headers": {
            "location": signed_url,
            "cache-control": "no-store",
            "access-control-allow-origin": "*",
        },
        "body": "",
    }

def _demo_video_title(filename):
    stem, _sep, _ext = filename.rpartition(".")
    source = stem or filename
    parts = source.replace("_", " ").replace("-", " ").split()
    return " ".join(parts) if parts else filename

def _get_demo_videos():
    paginator = s3_client.get_paginator("list_objects_v2")
    items = []

    for page in paginator.paginate(Bucket=STATE_BUCKET, Prefix=DEMO_VIDEOS_PREFIX):
        for obj in page.get("Contents", []) or []:
            key = obj.get("Key", "")
            if not key or key.endswith("/"):
                continue

            filename = key.rsplit("/", 1)[-1]
            lower_name = filename.lower()
            if not any(lower_name.endswith(ext) for ext in ALLOWED_DEMO_VIDEO_EXTENSIONS):
                continue

            signed_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": STATE_BUCKET, "Key": key},
                ExpiresIn=DEMO_VIDEO_URL_EXPIRES_SECONDS,
            )
            content_type = mimetypes.guess_type(filename)[0] or "video/mp4"
            last_modified = obj.get("LastModified")
            items.append(
                {
                    "key": key,
                    "fileName": filename,
                    "title": _demo_video_title(filename),
                    "url": signed_url,
                    "sizeBytes": obj.get("Size", 0),
                    "lastModified": last_modified.isoformat() if last_modified else None,
                    "contentType": content_type,
                }
            )

    items.sort(key=lambda item: item.get("lastModified") or "", reverse=True)
    return _resp(200, {"items": items})


def _parse_ts(value):
    """Parse an ISO-8601 timestamp (with optional trailing Z) to aware UTC."""
    if not value:
        return None
    v = str(value).strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _parse_trusted_ts(value):
    """Parse only explicit timezone-bearing timestamps for trust decisions."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)

def _exact_schema_version(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer():
        return None
    return int(numeric)

def _trusted_media_time(item):
    """Apply the persisted schema-v2 HLS media-time acceptance contract."""
    if item.get("media_time_trusted") is not True:
        return False
    if _exact_schema_version(item.get("timestamp_schema_version")) != 2:
        return False

    timestamp_raw = item.get("timestamp_utc")
    media_timestamp_raw = item.get("media_timestamp_utc")
    if (
        not isinstance(timestamp_raw, str)
        or not timestamp_raw.strip()
        or not isinstance(media_timestamp_raw, str)
        or not media_timestamp_raw.strip()
        or timestamp_raw.strip() != media_timestamp_raw.strip()
    ):
        return False
    media_timestamp = _parse_trusted_ts(media_timestamp_raw)
    if media_timestamp is None:
        return False

    media_clock = item.get("media_clock")
    if not isinstance(media_clock, dict):
        return False
    if media_clock.get("source") != "hls_ext_x_program_date_time":
        return False
    if _exact_schema_version(media_clock.get("schema_version")) != 1:
        return False
    anchor = _parse_trusted_ts(media_clock.get("anchor_program_date_time_utc"))
    position = media_clock.get("position_milliseconds")
    if (
        anchor is None
        or isinstance(position, bool)
        or not isinstance(position, (int, float, Decimal))
    ):
        return False
    try:
        position_ms = float(position)
    except (TypeError, ValueError, OverflowError):
        return False
    if not math.isfinite(position_ms) or position_ms < 0:
        return False
    reconstructed = anchor + timedelta(milliseconds=position_ms)
    return abs((reconstructed - media_timestamp).total_seconds()) * 1000.0 <= 5.0

def _iso_millis(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def _ts_event_bounds(start_dt, end_dt):
    # ts_event is "{timestamp_utc}#{event_id}" with millisecond timestamps.
    # Normalising both bounds to millisecond precision keeps the lexicographic
    # BETWEEN correct; "~" sorts after both "Z" and "#".
    return _iso_millis(start_dt), _iso_millis(end_dt) + "~"

def _resolve_window(qs, default_hours=24, max_hours=48):
    start_dt = _parse_ts(qs.get("start"))
    end_dt = _parse_ts(qs.get("end"))
    if end_dt is None:
        end_dt = datetime.now(timezone.utc)
    if start_dt is None:
        start_dt = end_dt - timedelta(hours=default_hours)
    if start_dt >= end_dt:
        return None, None, _resp(400, {"error": "invalid_range", "detail": "start must be before end"})
    if end_dt - start_dt > timedelta(hours=max_hours):
        start_dt = end_dt - timedelta(hours=max_hours)
    return start_dt, end_dt, None


def _range_filter_expression(qs):
    filters = []
    device_id = (qs.get("device_id") or "").strip()
    object_type = (qs.get("object_type") or "").strip()
    if device_id:
        filters.append(Attr("device_id").eq(device_id))
    if object_type:
        filters.append(Attr("object_type").eq(object_type))
    if not filters:
        return None
    condition = filters[0]
    for extra in filters[1:]:
        condition = condition & extra
    return condition

def _get_detections_range(qs, limit, exclusive_start_key):
    # All detections at the site share one precision-5 geohash, so the
    # geohash+ts_event GSI doubles as a time index.
    start_dt, end_dt, err = _resolve_window(qs)
    if err:
        return err

    start_key, end_key = _ts_event_bounds(start_dt, end_dt)
    kwargs = {
        "IndexName": GSI_NAME,
        "KeyConditionExpression": Key("geohash").eq(SITE_GEOHASH)
        & Key("ts_event").between(start_key, end_key),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    condition = _range_filter_expression(qs)
    if condition is not None:
        kwargs["FilterExpression"] = condition
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key
    resp = table.query(**kwargs)
    items = [_strip_api_fields(x) for x in (resp.get("Items", []) or [])]
    return _resp(
        200,
        {
            "items": _jsonable(items),
            "next": _b64(resp.get("LastEvaluatedKey")),
            "start": _iso_millis(start_dt),
            "end": _iso_millis(end_dt),
        },
    )

def _get_detections_recent(limit, exclusive_start_key):
    """Return the site's newest detections from the geohash/time index.

    DynamoDB Scan order isn't chronological, and its Limit is applied before
    any client-side sort. Querying the site's shared geohash partition keeps
    pagination stable and guarantees newest-first results without reading old
    table pages first.
    """
    kwargs = {
        "IndexName": GSI_NAME,
        "KeyConditionExpression": Key("geohash").eq(SITE_GEOHASH),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key
    resp = table.query(**kwargs)
    items = [_strip_api_fields(x) for x in (resp.get("Items", []) or [])]
    return _resp(
        200,
        {
            "items": _jsonable(items),
            "next": _b64(resp.get("LastEvaluatedKey")),
        },
    )

TIMELINE_MAX_PAGES = int(os.environ.get("TIMELINE_MAX_PAGES", "40"))

def _get_detections_timeline(qs):
    """Aggregate a time window into track events + a per-bucket histogram.

    Grouping happens here so the browser never has to page through tens of
    thousands of raw detection rows to draw timeline markers.
    """
    start_dt, end_dt, err = _resolve_window(qs)
    if err:
        return err

    try:
        bucket_seconds = int(qs.get("bucket") or "60")
    except ValueError:
        bucket_seconds = 60
    bucket_seconds = max(10, min(3600, bucket_seconds))

    start_key, end_key = _ts_event_bounds(start_dt, end_dt)
    base_kwargs = {
        "IndexName": GSI_NAME,
        "KeyConditionExpression": Key("geohash").eq(SITE_GEOHASH)
        & Key("ts_event").between(start_key, end_key),
        "ScanIndexForward": True,
        "ProjectionExpression": (
            "event_id, object_id, object_type, timestamp_utc, "
            "media_timestamp_utc, timestamp_schema_version, media_time_trusted, "
            "media_clock, device_id, confidence_score"
        ),
    }
    condition = _range_filter_expression(qs)
    if condition is not None:
        base_kwargs["FilterExpression"] = condition

    tracks = {}
    buckets = {}
    total = 0
    truncated = False
    exclusive_start_key = None
    for _ in range(TIMELINE_MAX_PAGES):
        kwargs = dict(base_kwargs)
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        resp = table.query(**kwargs)
        for item in resp.get("Items", []) or []:
            ts = _parse_ts(item.get("timestamp_utc"))
            if ts is None:
                continue
            total += 1
            object_id = str(item.get("object_id") or "unknown")
            object_type = str(item.get("object_type") or "unknown")
            confidence = item.get("confidence_score")
            confidence = float(confidence) if isinstance(confidence, (int, float, Decimal)) else 0.0
            schema_raw = item.get("timestamp_schema_version")
            timestamp_schema_version = _exact_schema_version(schema_raw)
            media_time_trusted = _trusted_media_time(item)
            event_id = str(item.get("event_id") or "")
            media_timestamp = str(item.get("media_timestamp_utc") or "")

            track = tracks.get(object_id)
            if track is None:
                tracks[object_id] = {
                    "object_id": object_id,
                    "object_type": object_type,
                    "device_id": str(item.get("device_id") or ""),
                    "first_seen": ts,
                    "last_seen": ts,
                    "count": 1,
                    "max_confidence": confidence,
                    "media_time_trusted": media_time_trusted,
                    "timestamp_schema_version": timestamp_schema_version,
                    "first_event_id": event_id,
                    "last_event_id": event_id,
                    "first_media_timestamp_utc": media_timestamp,
                    "last_media_timestamp_utc": media_timestamp,
                }
            else:
                track["count"] += 1
                track["media_time_trusted"] = (
                    track["media_time_trusted"] and media_time_trusted
                )
                if ts < track["first_seen"]:
                    track["first_seen"] = ts
                    track["first_event_id"] = event_id
                    track["first_media_timestamp_utc"] = media_timestamp
                if ts > track["last_seen"]:
                    track["last_seen"] = ts
                    track["last_event_id"] = event_id
                    track["last_media_timestamp_utc"] = media_timestamp
                if confidence > track["max_confidence"]:
                    track["max_confidence"] = confidence

            bucket_idx = int((ts - start_dt).total_seconds() // bucket_seconds)
            counts = buckets.setdefault(bucket_idx, {})
            counts[object_type] = counts.get(object_type, 0) + 1

        exclusive_start_key = resp.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break
    else:
        truncated = True

    events = sorted(tracks.values(), key=lambda t: t["first_seen"])
    return _resp(
        200,
        {
            "start": _iso_millis(start_dt),
            "end": _iso_millis(end_dt),
            "bucketSeconds": bucket_seconds,
            "totalDetections": total,
            "truncated": truncated,
            "events": [
                {
                    "object_id": t["object_id"],
                    "object_type": t["object_type"],
                    "device_id": t["device_id"],
                    "first_seen": _iso_millis(t["first_seen"]),
                    "last_seen": _iso_millis(t["last_seen"]),
                    "count": t["count"],
                    "max_confidence": round(t["max_confidence"], 4),
                    "media_time_trusted": t["media_time_trusted"],
                    "timestamp_schema_version": t["timestamp_schema_version"],
                    "first_event_id": t["first_event_id"],
                    "last_event_id": t["last_event_id"],
                    "first_media_timestamp_utc": t["first_media_timestamp_utc"],
                    "last_media_timestamp_utc": t["last_media_timestamp_utc"],
                }
                for t in events
            ],
            "histogram": [
                {
                    "bucket_start": _iso_millis(start_dt + timedelta(seconds=idx * bucket_seconds)),
                    "counts": buckets[idx],
                }
                for idx in sorted(buckets)
            ],
        },
    )

def handler(event, context):
    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
    qs = event.get("queryStringParameters") or {}
    path_params = event.get("pathParameters") or {}

    try:
        limit = int(qs.get("limit") or "50")
    except ValueError:
        limit = 50
    limit = max(1, min(MAX_LIMIT, limit))

    next_token = qs.get("next")
    exclusive_start_key = _unb64(next_token)


    if path == "/detections/timeline":
        return _get_detections_timeline(qs)

    if path == "/demo-videos":
        return _get_demo_videos()

    if path == "/state":
        return _get_state(event)

    if path == "/map-data":
        return _get_map_data()


    if path.startswith("/snapshots/") and path.endswith("/latest"):
        object_id = path_params.get("object_id") or path.split("/snapshots/", 1)[1].rsplit("/latest", 1)[0]
        return _get_snapshot(object_id)

    if path.startswith("/detections/object/"):
        object_id = path_params.get("object_id") or path.split("/detections/object/", 1)[1]
        kwargs = {
            "KeyConditionExpression": Key("object_id").eq(object_id),
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        resp = table.query(**kwargs)
        items = [_strip_api_fields(x) for x in (resp.get("Items", []) or [])]
        return _resp(
            200,
            {
                "items": _jsonable(items),
                "next": _b64(resp.get("LastEvaluatedKey")),
            },
        )

    if path.startswith("/detections/geohash/"):
        geohash = path_params.get("geohash") or path.split("/detections/geohash/", 1)[1]
        kwargs = {
            "IndexName": GSI_NAME,
            "KeyConditionExpression": Key("geohash").eq(geohash),
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        resp = table.query(**kwargs)
        items = [_strip_api_fields(x) for x in (resp.get("Items", []) or [])]
        return _resp(
            200,
            {
                "items": _jsonable(items),
                "next": _b64(resp.get("LastEvaluatedKey")),
            },
        )

    if path == "/detections/range":
        return _get_detections_range(qs, limit, exclusive_start_key)

    if path == "/detections/recent":
        return _get_detections_recent(limit, exclusive_start_key)

    if path in ("", "/"):
        return _resp(
            200,
            {
                "ok": True,
                "routes": [
                    "/demo-videos",
                    "/state",
                    "/map-data",
                    "/snapshots/{object_id}/latest",
                    "/detections/range",
                    "/detections/recent",
                    "/detections/timeline",
                    "/detections/object/{object_id}",
                    "/detections/geohash/{geohash}",
                ],
            },
        )

    return _resp(404, {"error": "not_found", "path": path})
