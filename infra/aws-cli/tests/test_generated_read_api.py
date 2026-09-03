import base64
import io
import json
import os
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class Condition:
    def __init__(self, expression):
        self.expression = expression

    def __and__(self, other):
        return Condition(("and", self.expression, other.expression))


class Key:
    def __init__(self, name):
        self.name = name

    def eq(self, value):
        return Condition(("eq", self.name, value))

    def between(self, start, end):
        return Condition(("between", self.name, start, end))


class Attr(Key):
    pass


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.put_calls = []
        self.delete_calls = []

    def put_object(self, **kwargs):
        body = kwargs["Body"]
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.objects[kwargs["Key"]] = bytes(body)
        self.put_calls.append(kwargs)
        return {}

    def get_object(self, **kwargs):
        try:
            body = self.objects[kwargs["Key"]]
        except KeyError as exc:
            raise FakeClientError("NoSuchKey") from exc
        return {"Body": io.BytesIO(body)}

    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)
        self.delete_calls.append(kwargs)
        return {}


class FakeTable:
    def __init__(self):
        self.query_calls = []
        self.items = [
            {
                "object_id": "newest",
                "timestamp_utc": "2026-07-10T05:30:00.000Z",
                "fleet_id": "private",
            },
            {
                "object_id": "older",
                "timestamp_utc": "2026-07-10T05:29:00.000Z",
            },
        ]
        self.last_evaluated_key = {
            "object_id": "older",
            "ts_event": "2026-07-10T05:29:00.000Z#event",
        }

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "Items": self.items,
            "LastEvaluatedKey": self.last_evaluated_key,
        }

    def scan(self, **_kwargs):
        raise AssertionError("recent detections must not use DynamoDB Scan")


def generated_lambda_source():
    root = Path(__file__).resolve().parents[1]
    source_path = root / "read-api-lambda.py"
    script = (root / "provision-read-api.sh").read_text(encoding="utf-8")
    expected_install = 'install -m 0600 "${HERE}/read-api-lambda.py" "${WORKDIR}/index.py"'
    if script.count(expected_install) != 1:
        raise AssertionError("deployment does not package the tested Lambda source")
    source = source_path.read_text(encoding="utf-8")
    if "${" in source:
        raise AssertionError("shell interpolation is forbidden in Lambda source")
    compile(source, str(source_path), "exec")
    return source


class DeploymentArtifactContractTest(unittest.TestCase):
    def test_exact_source_is_compiled_before_packaging_and_iam(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "provision-read-api.sh").read_text(encoding="utf-8")
        install_at = script.index(
            'install -m 0600 "${HERE}/read-api-lambda.py" "${WORKDIR}/index.py"'
        )
        compile_at = script.index('python3 -m py_compile "${WORKDIR}/index.py"')
        zip_at = script.index('zip -Xq function.zip index.py')
        lambda_apply_at = min(
            value
            for value in (
                script.find("aws lambda update-function-code", zip_at),
                script.find("aws lambda create-function", zip_at),
            )
            if value >= 0
        )
        iam_apply_at = script.index("aws iam put-role-policy", lambda_apply_at)
        self.assertLess(install_at, compile_at)
        self.assertLess(compile_at, zip_at)
        self.assertLess(zip_at, lambda_apply_at)
        self.assertLess(lambda_apply_at, iam_apply_at)
        self.assertNotIn("<<PY", script)

    def test_existing_lambda_configuration_is_reconciled_before_new_code(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "provision-read-api.sh").read_text(encoding="utf-8")
        existing_at = script.index('if [[ "${READ_LAMBDA_EXISTS}" == "true" ]]')
        configuration_at = script.index(
            "aws lambda update-function-configuration", existing_at
        )
        code_at = script.index("aws lambda update-function-code", existing_at)
        self.assertLess(configuration_at, code_at)

    def test_retired_video_routes_and_kinesis_permissions_are_removed(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "provision-read-api.sh").read_text(encoding="utf-8")
        source = (root / "read-api-lambda.py").read_text(encoding="utf-8")
        self.assertNotIn("kinesisvideo:", script)
        self.assertNotIn('boto3.client("kinesisvideo"', source)
        self.assertNotIn("kinesis-video-archived-media", source)
        for route in (
            "GET /video/session/{camera_id}",
            "GET /video/browser-session/{camera_id}",
            "GET /video/proxy/{token}/{resource_id}",
            "GET /video/coverage/{camera_id}",
        ):
            self.assertIn(route, script)
        self.assertIn("aws apigatewayv2 delete-route", script)


TEST_ENVIRONMENT = {
    "TABLE_NAME": "test-detections",
    "SITE_GEOHASH": "9q9p8",
    "STATE_BUCKET": "test-state",
    "SNAPSHOT_URL_EXPIRES_SECONDS": "300",
    "DEMO_VIDEOS_PREFIX": "demo-videos/",
    "DEMO_VIDEO_URL_EXPIRES_SECONDS": "3600",
}


def load_generated_lambda(fake_table, fake_s3=None, environment=None):
    fake_s3 = fake_s3 or FakeS3()
    boto3 = types.ModuleType("boto3")
    boto3.resource = lambda _service: types.SimpleNamespace(
        Table=lambda _name: fake_table
    )
    boto3.client = lambda service, *_args, **_kwargs: (
        fake_s3 if service == "s3" else types.SimpleNamespace()
    )

    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Attr = Attr
    conditions.Key = Key

    botocore_exceptions = types.ModuleType("botocore.exceptions")
    botocore_exceptions.ClientError = FakeClientError

    previous = {
        name: sys.modules.get(name)
        for name in (
            "boto3",
            "boto3.dynamodb",
            "boto3.dynamodb.conditions",
            "botocore",
            "botocore.exceptions",
        )
    }
    sys.modules["boto3"] = boto3
    sys.modules["boto3.dynamodb"] = types.ModuleType("boto3.dynamodb")
    sys.modules["boto3.dynamodb.conditions"] = conditions
    sys.modules["botocore"] = types.ModuleType("botocore")
    sys.modules["botocore.exceptions"] = botocore_exceptions
    try:
        namespace = {"__name__": "generated_read_api"}
        with patch.dict(
            os.environ,
            TEST_ENVIRONMENT if environment is None else environment,
            clear=True,
        ):
            exec(compile(generated_lambda_source(), "generated-index.py", "exec"), namespace)
        return namespace
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module



class RecentDetectionsTest(unittest.TestCase):
    def setUp(self):
        self.table = FakeTable()
        self.module = load_generated_lambda(self.table)

    def invoke(self, next_token=None):
        query = {"limit": "2"}
        if next_token:
            query["next"] = next_token
        response = self.module["handler"](
            {
                "rawPath": "/detections/recent",
                "queryStringParameters": query,
            },
            None,
        )
        self.assertEqual(response["statusCode"], 200)
        return json.loads(response["body"])

    def test_recent_queries_site_time_index_newest_first(self):
        body = self.invoke()
        call = self.table.query_calls[-1]
        self.assertEqual(call["IndexName"], "gsi_geohash_time")
        self.assertEqual(call["Limit"], 2)
        self.assertIs(call["ScanIndexForward"], False)
        self.assertEqual(
            call["KeyConditionExpression"].expression,
            ("eq", "geohash", "9q9p8"),
        )
        self.assertEqual([item["object_id"] for item in body["items"]], ["newest", "older"])
        self.assertNotIn("fleet_id", body["items"][0])

    def test_recent_pagination_round_trips_last_evaluated_key(self):
        first = self.invoke()
        decoded = json.loads(base64.urlsafe_b64decode(first["next"]).decode("utf-8"))
        self.assertEqual(decoded, self.table.last_evaluated_key)

        self.invoke(first["next"])
        self.assertEqual(
            self.table.query_calls[-1]["ExclusiveStartKey"],
            self.table.last_evaluated_key,
        )



class DetectionTimelineTrustTest(unittest.TestCase):
    def setUp(self):
        self.table = FakeTable()
        self.table.last_evaluated_key = None
        self.table.items = [
            {
                "event_id": "trusted-event",
                "object_id": "global_car_run_1",
                "object_type": "car",
                "timestamp_utc": "2026-07-10T05:30:00.000Z",
                "media_timestamp_utc": "2026-07-10T05:30:00.000Z",
                "timestamp_schema_version": 2,
                "media_time_trusted": True,
                "media_clock": {
                    "source": "hls_ext_x_program_date_time",
                    "schema_version": 1,
                    "anchor_program_date_time_utc": "2026-07-10T05:29:59.000Z",
                    "position_milliseconds": 1000.0,
                },
                "device_id": "ch1",
                "confidence_score": 0.9,
            },
            {
                "event_id": "legacy-event",
                "object_id": "global_car_legacy_1",
                "object_type": "car",
                "timestamp_utc": "2026-07-10T05:31:00.000Z",
                "device_id": "ch4",
                "confidence_score": 0.8,
            },
            {
                "event_id": "mismatched-event",
                "object_id": "global_car_timestamp_mismatch_1",
                "object_type": "car",
                "timestamp_utc": "2026-07-10T05:32:00.000Z",
                "media_timestamp_utc": "2026-07-10T04:32:00.000Z",
                "timestamp_schema_version": 2,
                "media_time_trusted": True,
                "media_clock": {
                    "source": "hls_ext_x_program_date_time",
                    "schema_version": 1,
                    "anchor_program_date_time_utc": "2026-07-10T04:31:59.000Z",
                    "position_milliseconds": 1000.0,
                },
                "device_id": "ch1",
                "confidence_score": 0.7,
            },
            {
                "event_id": "boolean-schema-event",
                "object_id": "global_car_boolean_schema_1",
                "object_type": "car",
                "timestamp_utc": "2026-07-10T05:33:00.000Z",
                "media_timestamp_utc": "2026-07-10T05:33:00.000Z",
                "timestamp_schema_version": 2,
                "media_time_trusted": True,
                "media_clock": {
                    "source": "hls_ext_x_program_date_time",
                    "schema_version": True,
                    "anchor_program_date_time_utc": "2026-07-10T05:32:59.000Z",
                    "position_milliseconds": 1000.0,
                },
                "device_id": "ch1",
                "confidence_score": 0.7,
            },
            {
                "event_id": "spoofed-event",
                "object_id": "global_car_schema_spoof_1",
                "object_type": "car",
                "timestamp_utc": "2026-07-10T05:34:00.000Z",
                "media_timestamp_utc": "2026-07-10T05:34:00.000Z",
                "timestamp_schema_version": 2,
                "media_time_trusted": True,
                "media_clock": {
                    "source": "hls_ext_x_program_date_time",
                    "schema_version": 1,
                },
                "device_id": "ch1",
                "confidence_score": 0.7,
            },
        ]
        self.module = load_generated_lambda(self.table)

    def test_timeline_labels_only_strict_schema_v2_media_events_trusted(self):
        response = self.module["handler"](
            {
                "rawPath": "/detections/timeline",
                "queryStringParameters": {
                    "start": "2026-07-10T05:00:00.000Z",
                    "end": "2026-07-10T06:00:00.000Z",
                },
            },
            None,
        )
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        events = {event["object_id"]: event for event in body["events"]}
        self.assertIs(events["global_car_run_1"]["media_time_trusted"], True)
        self.assertEqual(
            events["global_car_run_1"]["timestamp_schema_version"], 2
        )
        self.assertEqual(
            events["global_car_run_1"]["first_event_id"], "trusted-event"
        )
        self.assertIs(events["global_car_legacy_1"]["media_time_trusted"], False)
        self.assertIs(
            events["global_car_timestamp_mismatch_1"]["media_time_trusted"],
            False,
        )
        self.assertIs(
            events["global_car_boolean_schema_1"]["media_time_trusted"],
            False,
        )
        self.assertIs(
            events["global_car_schema_spoof_1"]["media_time_trusted"],
            False,
        )
        projection = self.table.query_calls[-1]["ProjectionExpression"]
        self.assertIn("media_clock", projection)
        self.assertIn("media_time_trusted", projection)


if __name__ == "__main__":
    unittest.main()
