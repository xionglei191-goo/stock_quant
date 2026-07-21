#!/usr/bin/env python3
"""Generate a structured attestation for an isolated report-recovery clone.

The probe is read-only. It inspects the clone application container, reads its
health endpoint, runs bounded SELECT queries through the application's own
PostgreSQL DSN, and confirms that the primary application service is not
reachable from the isolated container network.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.recover_watchlist_research_reports import (
    RecoveryRefused,
    validate_clone_attestation_for_plan,
    validate_clone_attestation_static,
)


SAFE_DATABASE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
PROBE_PRODUCER = "scripts/probe_research_report_clone_runtime.py"
DATABASE_PROBE_CODE = r"""
import json
import os
import psycopg
from scripts.postgres_durable_backup import RESEARCH_STATE_SQL

with psycopg.connect(os.environ["AI_QUANT_POSTGRES_DSN"]) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        database_name = str(cursor.fetchone()[0])
        cursor.execute("SELECT oid::text FROM pg_database WHERE datname = current_database()")
        database_oid = str(cursor.fetchone()[0])
        cursor.execute("SELECT system_identifier::text FROM pg_control_system()")
        postgres_system_identifier = str(cursor.fetchone()[0])
        table_counts = {}
        for key, sql in {
            "records": "SELECT COUNT(*) FROM ai_quant.records",
            "audit_log": "SELECT COUNT(*) FROM ai_quant.audit_log",
            "market_data_bars": "SELECT COUNT(*) FROM ai_quant.market_data_bars",
        }.items():
            cursor.execute(sql)
            table_counts[key] = int(cursor.fetchone()[0])
        cursor.execute(RESEARCH_STATE_SQL)
        research_state = json.loads(str(cursor.fetchone()[0]))

print(json.dumps({
    "query_id": "select_current_database",
    "success": True,
    "current_database": database_name,
    "database_oid": database_oid,
    "postgres_system_identifier": postgres_system_identifier,
    "table_counts": table_counts,
    "collection_counts": research_state["counts"],
}, sort_keys=True))
"""
PRIMARY_SERVICE_PROBE_CODE = r"""
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

try:
    with urlopen(sys.argv[1], timeout=float(sys.argv[2])) as response:
        response.read(1)
except HTTPError:
    raise SystemExit(0)
except (URLError, OSError, TimeoutError):
    raise SystemExit(3)
raise SystemExit(0)
"""
HEALTH_PROBE_CODE = r"""
import json
import sys
from urllib.request import urlopen

with urlopen(f"{sys.argv[1].rstrip('/')}/api/health", timeout=float(sys.argv[2])) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), sort_keys=True))
"""


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return payload


def _run(command: list[str], *, timeout: float, allowed_returncodes: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    allowed = allowed_returncodes or {0}
    if result.returncode not in allowed:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(f"{command[0]} probe failed: {detail[:500]}")
    return result


def _docker_inspect(target: str, *, timeout: float) -> dict[str, Any]:
    result = _run(["docker", "inspect", target], timeout=timeout)
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise RuntimeError(f"docker inspect returned an unexpected payload for {target}")
    return payload[0]


def _container_health(app_container: str, base_url: str, *, timeout: float) -> dict[str, Any]:
    try:
        result = _run(
            [
                "docker",
                "exec",
                app_container,
                "python",
                "-c",
                HEALTH_PROBE_CODE,
                base_url,
                str(min(timeout, 10.0)),
            ],
            timeout=timeout,
        )
        payload = json.loads(result.stdout)
    except (RuntimeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"clone health probe failed: {type(exc).__name__}") from exc
    if not isinstance(payload, Mapping) or payload.get("success") is not True or not isinstance(payload.get("data"), Mapping):
        raise RuntimeError("clone health probe did not return a successful structured response")
    return dict(payload["data"])


def _environment_map(container: Mapping[str, Any]) -> dict[str, str]:
    config = container.get("Config") if isinstance(container.get("Config"), Mapping) else {}
    values = config.get("Env") if isinstance(config.get("Env"), list) else []
    result: dict[str, str] = {}
    for item in values:
        key, separator, value = str(item).partition("=")
        if separator:
            result[key] = value
    return result


def _database_name_from_dsn(dsn: str) -> str:
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgresql", "postgres"}:
        return ""
    return unquote(parsed.path.lstrip("/")).strip().lower()


def _container_id(container: Mapping[str, Any]) -> str:
    return str(container.get("Id") or "")


def _mount_read_only(container: Mapping[str, Any], target: str) -> bool:
    mounts = container.get("Mounts") if isinstance(container.get("Mounts"), list) else []
    matches = [item for item in mounts if isinstance(item, Mapping) and item.get("Destination") == target]
    return len(matches) == 1 and matches[0].get("RW") is False


def build_attestation(
    *,
    app_container: str,
    postgres_container: str,
    isolated_network: str,
    database_name: str,
    base_url: str,
    primary_service_url: str,
    raw_mount_target: str,
    backup_manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
    timeout: float,
) -> dict[str, Any]:
    database_name = database_name.strip().lower()
    if not SAFE_DATABASE_NAME.fullmatch(database_name) or database_name == "ai_quant":
        raise RuntimeError("database_name must be a safe non-primary PostgreSQL identifier")
    if not re.search(r"(?:clone|pilot|restore|test)", database_name):
        raise RuntimeError("database_name must identify a clone, pilot, restore, or test database")
    parsed_base_url = urlsplit(base_url.rstrip("/"))
    if str(parsed_base_url.hostname or "").lower() not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("base_url must use clone-container loopback (127.0.0.1 or localhost)")
    if (parsed_base_url.port or 80) == 8000:
        raise RuntimeError("base_url must not use the live/default port 8000")

    app_inspect = _docker_inspect(app_container, timeout=timeout)
    postgres_inspect = _docker_inspect(postgres_container, timeout=timeout)
    network_inspect = _docker_inspect(isolated_network, timeout=timeout)
    app_environment = _environment_map(app_inspect)
    runtime_database_name = _database_name_from_dsn(app_environment.get("AI_QUANT_POSTGRES_DSN", ""))
    app_container_id = _container_id(app_inspect)
    app_container_hostname = str(
        (app_inspect.get("Config") if isinstance(app_inspect.get("Config"), Mapping) else {}).get("Hostname") or ""
    )
    app_image_id = str(app_inspect.get("Image") or "")
    postgres_container_id = _container_id(postgres_inspect)
    postgres_image_id = str(postgres_inspect.get("Image") or "")
    isolated_network_id = str(network_inspect.get("Id") or "")

    network_settings = (
        app_inspect.get("NetworkSettings") if isinstance(app_inspect.get("NetworkSettings"), Mapping) else {}
    )
    app_networks = network_settings.get("Networks") if isinstance(network_settings.get("Networks"), Mapping) else {}
    network_names = sorted(str(name) for name in app_networks)
    network_members = network_inspect.get("Containers") if isinstance(network_inspect.get("Containers"), Mapping) else {}
    expected_member_ids = {_container_id(app_inspect), _container_id(postgres_inspect)}
    actual_member_ids = {str(item) for item in network_members}
    network_members_limited = bool(all(expected_member_ids)) and actual_member_ids == expected_member_ids
    network_internal = network_inspect.get("Internal") is True
    network_isolation = network_names == [isolated_network] and network_internal and network_members_limited

    host_config = app_inspect.get("HostConfig") if isinstance(app_inspect.get("HostConfig"), Mapping) else {}
    root_filesystem_read_only = host_config.get("ReadonlyRootfs") is True
    raw_mount_read_only = _mount_read_only(app_inspect, raw_mount_target)
    object_store_backend = app_environment.get("AI_QUANT_OBJECT_STORE_BACKEND", "").strip().lower()
    search_backend = app_environment.get("AI_QUANT_SEARCH_BACKEND", "").strip().lower()

    health = _container_health(app_container, base_url, timeout=timeout)
    health_object_store = health.get("object_store") if isinstance(health.get("object_store"), Mapping) else {}
    health_search = health.get("search_index") if isinstance(health.get("search_index"), Mapping) else {}
    health_probe = {
        "status": str(health.get("status") or ""),
        "store": str(health.get("store") or ""),
        "object_store_backend": str(health_object_store.get("backend") or ""),
        "search_backend": str(health_search.get("backend") or ""),
        "transport": "docker_exec_loopback",
    }

    database_result = _run(
        ["docker", "exec", app_container, "python", "-c", DATABASE_PROBE_CODE],
        timeout=timeout,
    )
    database_probe = json.loads(database_result.stdout)
    if not isinstance(database_probe, dict):
        raise RuntimeError("database probe returned an unexpected payload")

    primary_result = _run(
        [
            "docker",
            "exec",
            app_container,
            "python",
            "-c",
            PRIMARY_SERVICE_PROBE_CODE,
            primary_service_url,
            str(min(timeout, 10.0)),
        ],
        timeout=timeout,
        allowed_returncodes={0, 3},
    )
    primary_service_reachable = primary_result.returncode == 0

    source_counts = backup_manifest.get("source_counts") if isinstance(backup_manifest.get("source_counts"), Mapping) else {}
    collection_counts = (
        backup_manifest.get("collection_counts")
        if isinstance(backup_manifest.get("collection_counts"), Mapping)
        else {}
    )
    restored_counts = database_probe.get("table_counts") if isinstance(database_probe.get("table_counts"), Mapping) else {}
    restored_collection_counts = (
        database_probe.get("collection_counts")
        if isinstance(database_probe.get("collection_counts"), Mapping)
        else {}
    )
    database_oid = str(database_probe.get("database_oid") or "")
    postgres_system_identifier = str(database_probe.get("postgres_system_identifier") or "")
    restore_verified = bool(source_counts) and dict(source_counts) == dict(restored_counts)
    restore_verified = restore_verified and bool(collection_counts) and dict(collection_counts) == dict(restored_collection_counts)

    safety_checks = {
        "runtime_database_matches": runtime_database_name == database_name,
        "database_query_matches": str(database_probe.get("current_database") or "").strip().lower() == database_name,
        "database_query_succeeded": database_probe.get("success") is True,
        "object_store_local": object_store_backend == "local" and health_probe["object_store_backend"] == "local",
        "search_backend_local": search_backend == "local" and health_probe["search_backend"] == "local",
        "health_ok": health_probe["status"] == "ok" and health_probe["store"] == "PostgreSQLStore",
        "network_isolation": network_isolation,
        "raw_mount_read_only": raw_mount_read_only,
        "root_filesystem_read_only": root_filesystem_read_only,
        "primary_service_unreachable": not primary_service_reachable,
        "restore_counts_match": restore_verified,
        "app_container_identity": bool(app_container_id)
        and bool(app_container_hostname)
        and app_container_id.startswith(app_container_hostname),
        "app_image_identity": bool(app_image_id),
        "postgres_container_identity": bool(postgres_container_id) and bool(postgres_image_id),
        "network_identity": bool(isolated_network_id),
        "database_identity": database_oid.isdigit()
        and int(database_oid) > 0
        and postgres_system_identifier.isdigit()
        and int(postgres_system_identifier) > 0,
    }
    failed = [check_id for check_id, passed in safety_checks.items() if not passed]
    if failed:
        raise RuntimeError(f"clone runtime probe failed: {','.join(failed)}")

    generated_at = datetime.now(timezone.utc).isoformat()
    runtime_identity = {
        "app_container_id": app_container_id,
        "app_container_hostname": app_container_hostname,
        "app_image_id": app_image_id,
        "postgres_container_id": postgres_container_id,
        "postgres_image_id": postgres_image_id,
        "isolated_network_id": isolated_network_id,
        "database_oid": database_oid,
        "postgres_system_identifier": postgres_system_identifier,
    }
    runtime_proof: dict[str, Any] = {
        "schema_version": "research-report-clone-runtime-proof-v1",
        "producer": PROBE_PRODUCER,
        "generated_at": generated_at,
        "base_url": base_url.rstrip("/"),
        "execution_scope": "inside_clone_app_container",
        "health_probe": health_probe,
        "database_probe": {
            "query_id": "select_current_database",
            "success": True,
            "current_database": database_name,
            "database_oid": database_oid,
            "postgres_system_identifier": postgres_system_identifier,
            "table_counts": dict(restored_counts),
            "collection_counts": dict(restored_collection_counts),
        },
        "environment_summary": {
            "runtime_database_name": runtime_database_name,
            "object_store_backend": object_store_backend,
            "search_backend": search_backend,
            "network_isolation": network_isolation,
            "isolated_network_name": isolated_network,
            "network_names": network_names,
            "network_internal": network_internal,
            "network_members_limited_to_app_and_postgres": network_members_limited,
            "raw_mount_read_only": raw_mount_read_only,
            "root_filesystem_read_only": root_filesystem_read_only,
            "primary_service_reachable": primary_service_reachable,
            "execution_scope": "inside_clone_app_container",
        },
        "runtime_identity": runtime_identity,
    }
    evidence = plan.get("input_evidence") if isinstance(plan.get("input_evidence"), Mapping) else {}
    attestation: dict[str, Any] = {
        "schema_version": "research-report-clone-attestation-v1",
        "status": "passed",
        "generated_at": generated_at,
        "environment": "cloned_database_pilot",
        "base_url": base_url.rstrip("/"),
        "execution_scope": "inside_clone_app_container",
        "database_name": database_name,
        "runtime_database_name": runtime_database_name,
        "object_store_backend": object_store_backend,
        "search_backend": search_backend,
        "network_isolation": network_isolation,
        "raw_mount_read_only": raw_mount_read_only,
        "primary_service_reachable": primary_service_reachable,
        "restore_verified": restore_verified,
        "source_backup_dump_sha256": str(backup_manifest.get("dump_sha256") or ""),
        "plan_sha256": str(plan.get("plan_sha256") or ""),
        "source_counts": dict(source_counts),
        "restored_counts": dict(restored_counts),
        "collection_counts": dict(collection_counts),
        "restored_collection_counts": dict(restored_collection_counts),
        "runtime_identity": runtime_identity,
        "runtime_proof": runtime_proof,
        "runtime_proof_sha256": _canonical_sha256(runtime_proof),
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
    }
    if str(evidence.get("backup_dump_sha256") or "") != attestation["source_backup_dump_sha256"]:
        raise RuntimeError("plan and backup manifest reference different dump SHA-256 values")
    try:
        validate_clone_attestation_static(attestation, base_url=base_url)
        validate_clone_attestation_for_plan(attestation, base_url=base_url, plan=plan)
    except RecoveryRefused as exc:
        raise RuntimeError(f"generated clone attestation was rejected: {exc}") from exc
    return attestation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-container", required=True)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--isolated-network", required=True)
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--primary-service-url", default="http://ai-quant-org:8000/api/health")
    parser.add_argument("--raw-mount-target", default="/data/local/research_reports")
    parser.add_argument("--backup-manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    attestation = build_attestation(
        app_container=args.app_container,
        postgres_container=args.postgres_container,
        isolated_network=args.isolated_network,
        database_name=args.database_name,
        base_url=args.base_url,
        primary_service_url=args.primary_service_url,
        raw_mount_target=args.raw_mount_target,
        backup_manifest=_load_json(args.backup_manifest),
        plan=_load_json(args.plan),
        timeout=max(1.0, args.timeout),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
