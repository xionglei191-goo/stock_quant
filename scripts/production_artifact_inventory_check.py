from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.readiness_artifacts import is_production_artifact_uri


SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
RELEASE_ENVIRONMENTS = {"production", "prod", "staging", "preprod", "pre-production", "uat"}
NON_RELEASE_ENVIRONMENT_TOKENS = {"local", "demo", "sample", "test", "dev", "sandbox"}
PLACEHOLDER_URI_TOKENS = ("<", ">", "{release-id}", "{", "}", "example")
PLACEHOLDER_METADATA_TOKENS = ("<", ">", "{", "}")
URI_VALUE_KEYS = {
    "artifact_uri",
    "evidence_uri",
    "governance_artifact_uri",
    "validation_artifact_uri",
    "tos_review_artifact_uri",
    "robots_review_artifact_uri",
}
URI_CONTAINER_KEYS = {
    "artifact_uris",
    "artifact_uri_template",
    "component_evidence_uris",
}


def load_json_object(path: str | Path, *, label: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{label} must be a JSON object")
    return data


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _is_artifact_uri_key(key: str) -> bool:
    return key in URI_VALUE_KEYS or key.endswith("_artifact_uri") or key.endswith("_evidence_uri")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _collect_required_artifact_uris(value: Any, *, path: str, inside_uri_container: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if key in URI_CONTAINER_KEYS:
                rows.extend(_collect_required_artifact_uris(raw_item, path=child_path, inside_uri_container=True))
                continue
            if isinstance(raw_item, str) and (inside_uri_container or _is_artifact_uri_key(key)):
                rows.append({"uri": raw_item, "path": child_path})
                continue
            rows.extend(_collect_required_artifact_uris(raw_item, path=child_path, inside_uri_container=False))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            rows.extend(_collect_required_artifact_uris(item, path=f"{path}[{idx}]", inside_uri_container=inside_uri_container))
    return rows


def collect_required_artifact_uris(*contexts: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for idx, context in enumerate(contexts):
        if not isinstance(context, Mapping):
            continue
        for row in _collect_required_artifact_uris(context, path=f"context[{idx}]", inside_uri_container=False):
            key = (row["uri"], row["path"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def build_artifact_inventory_template(
    *contexts: Mapping[str, Any],
    inventory_id: str = "production_artifact_inventory_template",
    environment: str = "staging",
    storage_backend: str = "s3",
    generated_at: str = "<generated_at>",
) -> dict[str, Any]:
    rows = collect_required_artifact_uris(*contexts)
    source_paths_by_uri: dict[str, set[str]] = {}
    for row in rows:
        uri = row["uri"]
        source_paths_by_uri.setdefault(uri, set()).add(row["path"])
    artifacts = [
        {
            "uri": uri,
            "bundle_path": _default_bundle_path_for_uri(uri),
            "sha256": "<sha256>",
            "size_bytes": 0,
            "environment": environment,
            "storage_backend": storage_backend,
            "created_at": "<created_at>",
            "producer": "<producer>",
            "owner_role": "<owner_role>",
            "content_type": "application/json",
            "retention_policy": "<retention_policy>",
            "immutable": False,
            "source_paths": sorted(source_paths),
        }
        for uri, source_paths in sorted(source_paths_by_uri.items())
    ]
    return {
        "inventory_id": inventory_id,
        "environment": environment,
        "storage_backend": storage_backend,
        "generated_at": generated_at,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "production_boundary": "template only; replace sha256, size, timestamps, producer, owner, retention, and immutable/object lock before release",
    }


def build_artifact_inventory_from_bundle(
    *contexts: Mapping[str, Any],
    bundle_root: str | Path,
    inventory_id: str = "production_artifact_inventory",
    environment: str = "staging",
    storage_backend: str = "s3",
    generated_at: str | None = None,
    producer: str = "production_evidence_export",
    owner_role: str = "平台负责人",
    content_type: str = "application/json",
    retention_policy: str = "retain_release_evidence_7y",
    immutable: bool = True,
) -> dict[str, Any]:
    bundle_root_path = Path(bundle_root).resolve()
    generated_at_value = generated_at or _utc_now_iso()
    template = build_artifact_inventory_template(
        *contexts,
        inventory_id=inventory_id,
        environment=environment,
        storage_backend=storage_backend,
        generated_at=generated_at_value,
    )
    artifacts: list[dict[str, Any]] = []
    missing_files: list[dict[str, str]] = []
    for row in template["artifacts"]:
        uri = str(row["uri"])
        bundle_path = str(row.get("bundle_path") or _default_bundle_path_for_uri(uri))
        try:
            target = _safe_bundle_path(bundle_root_path, bundle_path)
        except ValueError as exc:
            missing_files.append({"uri": uri, "bundle_path": bundle_path, "error": str(exc)})
            continue
        if not target.exists() or not target.is_file():
            missing_files.append({"uri": uri, "bundle_path": bundle_path, "error": "artifact bundle file is missing"})
            continue
        artifacts.append(
            {
                **row,
                "bundle_path": bundle_path,
                "sha256": _sha256_file(target),
                "size_bytes": target.stat().st_size,
                "environment": environment,
                "storage_backend": storage_backend,
                "created_at": generated_at_value,
                "producer": producer,
                "owner_role": owner_role,
                "content_type": content_type,
                "retention_policy": retention_policy,
                "immutable": immutable,
            }
        )
    return {
        **template,
        "inventory_id": inventory_id,
        "environment": environment,
        "storage_backend": storage_backend,
        "generated_at": generated_at_value,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "bundle_root": str(bundle_root_path),
        "missing_bundle_file_count": len(missing_files),
        "missing_bundle_files": missing_files,
        "production_boundary": "generated from an exported evidence bundle; run validation with --bundle-root before release sign-off",
    }


def _default_bundle_path_for_uri(uri: str) -> str:
    parsed = urlparse(str(uri or "").strip())
    name = (parsed.netloc + parsed.path).strip("/")
    if not name:
        return "missing-uri"
    sanitized = re.sub(r"[^A-Za-z0-9._/\-]+", "_", name)
    return sanitized.strip("/") or "artifact"


def _safe_bundle_path(bundle_root: Path, raw_path: str) -> Path:
    relative = Path(raw_path)
    if relative.is_absolute():
        raise ValueError("bundle_path must be relative to bundle_root")
    target = (bundle_root / relative).resolve()
    root = bundle_root.resolve()
    if root != target and root not in target.parents:
        raise ValueError("bundle_path escapes bundle_root")
    return target


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_rows(inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = inventory.get("artifacts", inventory.get("items", inventory.get("rows", [])))
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _uri_for_artifact(row: Mapping[str, Any]) -> str:
    return str(row.get("uri", row.get("artifact_uri", row.get("evidence_uri", "")))).strip()


def _has_placeholder_uri_token(value: str) -> bool:
    normalized = value.strip().lower()
    return any(token in normalized for token in PLACEHOLDER_URI_TOKENS)


def _is_filled_metadata(value: str) -> bool:
    normalized = value.strip()
    return bool(normalized) and not any(token in normalized for token in PLACEHOLDER_METADATA_TOKENS)


def _environment_ok(value: str) -> bool:
    normalized = value.strip().lower().replace("_", "-")
    if not normalized:
        return False
    if normalized in RELEASE_ENVIRONMENTS:
        return True
    return not any(token in normalized for token in NON_RELEASE_ENVIRONMENT_TOKENS)


def _has_immutability(row: Mapping[str, Any]) -> bool:
    return bool(row.get("immutable") is True or row.get("object_lock") is True or row.get("write_once") is True)


def validate_artifact_inventory(
    inventory: Mapping[str, Any],
    *,
    required_contexts: list[Mapping[str, Any]] | None = None,
    bundle_root: str | Path | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    inventory_id = str(inventory.get("inventory_id", "")).strip()
    expect(bool(inventory_id), "inventory_id", "artifact inventory must have an inventory_id")
    top_environment = str(inventory.get("environment", "")).strip()
    expect(_environment_ok(top_environment), "inventory_environment", "inventory environment must be production/staging-like, not local/demo/test", value=top_environment)
    top_storage_backend = str(inventory.get("storage_backend", "")).strip()
    expect(bool(top_storage_backend), "inventory_storage_backend", "inventory storage_backend is required")
    generated_at = str(inventory.get("generated_at", "")).strip()
    expect(_is_filled_metadata(generated_at), "inventory_generated_at", "inventory generated_at is required and must not be a template placeholder", value=generated_at)

    artifacts = _artifact_rows(inventory)
    expect(bool(artifacts), "inventory_artifacts", "inventory must contain a non-empty artifacts list")
    if "artifact_count" in inventory:
        try:
            artifact_count = int(inventory.get("artifact_count", -1))
        except (TypeError, ValueError):
            artifact_count = -1
        expect(artifact_count == len(artifacts), "artifact_count", "artifact_count must match artifacts length", value=inventory.get("artifact_count"), actual=len(artifacts))

    inventory_uris: dict[str, dict[str, Any]] = {}
    duplicate_uris: set[str] = set()
    bundle_checks: list[dict[str, Any]] = []
    bundle_root_path = Path(bundle_root).resolve() if bundle_root else None
    for idx, row in enumerate(artifacts):
        uri = _uri_for_artifact(row)
        if uri in inventory_uris:
            duplicate_uris.add(uri)
        if uri:
            inventory_uris[uri] = row
        expect(is_production_artifact_uri(uri), "inventory_artifact_uri", "artifact row URI must be a concrete production/staging archive URI", row=idx, value=uri)
        expect(not _has_placeholder_uri_token(uri), "inventory_artifact_uri_filled", "artifact row URI must not contain template placeholder tokens", row=idx, value=uri)
        sha256 = str(row.get("sha256", row.get("checksum_sha256", ""))).strip()
        expect(bool(SHA256_RE.match(sha256)), "inventory_sha256", "artifact row must include a 64-hex sha256", row=idx, uri=uri, value=sha256)
        try:
            size_bytes = int(row.get("size_bytes", 0) or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        expect(size_bytes > 0, "inventory_size_bytes", "artifact row size_bytes must be > 0", row=idx, uri=uri, value=row.get("size_bytes"))
        row_environment = str(row.get("environment", top_environment)).strip()
        expect(_environment_ok(row_environment), "inventory_row_environment", "artifact row environment must be production/staging-like", row=idx, uri=uri, value=row_environment)
        storage_backend = str(row.get("storage_backend", top_storage_backend)).strip()
        expect(bool(storage_backend), "inventory_row_storage_backend", "artifact row storage_backend is required", row=idx, uri=uri)
        created_at = str(row.get("created_at", row.get("generated_at", ""))).strip()
        producer = str(row.get("producer", row.get("generated_by", ""))).strip()
        owner_role = str(row.get("owner_role", "")).strip()
        content_type = str(row.get("content_type", "")).strip()
        retention = str(row.get("retention_until", row.get("retention_policy", ""))).strip()
        expect(_is_filled_metadata(created_at), "inventory_created_at", "artifact row created_at/generated_at is required and must not be a template placeholder", row=idx, uri=uri, value=created_at)
        expect(_is_filled_metadata(producer), "inventory_producer", "artifact row producer/generated_by is required and must not be a template placeholder", row=idx, uri=uri, value=producer)
        expect(_is_filled_metadata(owner_role), "inventory_owner_role", "artifact row owner_role is required and must not be a template placeholder", row=idx, uri=uri, value=owner_role)
        expect(_is_filled_metadata(content_type), "inventory_content_type", "artifact row content_type is required and must not be a template placeholder", row=idx, uri=uri, value=content_type)
        expect(_is_filled_metadata(retention), "inventory_retention", "artifact row retention_until or retention_policy is required and must not be a template placeholder", row=idx, uri=uri, value=retention)
        expect(_has_immutability(row), "inventory_immutability", "artifact row must mark immutable/object_lock/write_once=true", row=idx, uri=uri)
        if bundle_root_path is not None:
            raw_bundle_path = str(row.get("bundle_path", row.get("local_path", _default_bundle_path_for_uri(uri)))).strip()
            try:
                bundle_path = _safe_bundle_path(bundle_root_path, raw_bundle_path)
            except ValueError as exc:
                failures.append({"check": "bundle_path", "row": idx, "uri": uri, "error": str(exc), "value": raw_bundle_path})
                continue
            if not bundle_path.exists() or not bundle_path.is_file():
                failures.append({"check": "bundle_file_exists", "row": idx, "uri": uri, "error": "artifact bundle file is missing", "bundle_path": str(bundle_path)})
                continue
            actual_size = bundle_path.stat().st_size
            actual_sha256 = _sha256_file(bundle_path)
            bundle_checks.append({"uri": uri, "bundle_path": str(bundle_path), "size_bytes": actual_size, "sha256": actual_sha256})
            if actual_size != size_bytes:
                failures.append(
                    {
                        "check": "bundle_size_bytes",
                        "row": idx,
                        "uri": uri,
                        "error": "bundle file size must match inventory size_bytes",
                        "expected": size_bytes,
                        "actual": actual_size,
                    }
                )
            if actual_sha256.lower() != sha256.lower():
                failures.append(
                    {
                        "check": "bundle_sha256",
                        "row": idx,
                        "uri": uri,
                        "error": "bundle file sha256 must match inventory sha256",
                        "expected": sha256,
                        "actual": actual_sha256,
                    }
                )

    expect(not duplicate_uris, "inventory_duplicate_uri", "artifact inventory must not contain duplicate URIs", duplicates=sorted(duplicate_uris))

    required_rows = collect_required_artifact_uris(*(required_contexts or []))
    required_uris = sorted({row["uri"] for row in required_rows if row["uri"]})
    invalid_required_uris = sorted(uri for uri in required_uris if not is_production_artifact_uri(uri))
    expect(not invalid_required_uris, "required_artifact_uri", "required artifact URI must be a production/staging archive URI", values=invalid_required_uris)
    placeholder_required_uris = sorted(uri for uri in required_uris if _has_placeholder_uri_token(uri))
    expect(not placeholder_required_uris, "required_artifact_uri_filled", "required artifact URI must not contain template placeholder tokens", values=placeholder_required_uris)
    missing_uris = sorted(uri for uri in required_uris if uri not in inventory_uris)
    expect(not missing_uris, "required_artifact_inventory_coverage", "every required artifact URI must have an inventory row", missing=missing_uris)

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "inventory_id": inventory_id,
        "artifact_count": len(artifacts),
        "required_uri_count": len(required_uris),
        "missing_uri_count": len(missing_uris),
        "invalid_required_uri_count": len(invalid_required_uris),
        "placeholder_required_uri_count": len(placeholder_required_uris),
        "bundle_root": str(bundle_root_path) if bundle_root_path else "",
        "bundle_check_count": len(bundle_checks),
        "failure_count": len(failures),
        "failures": failures,
    }


def load_and_validate_artifact_inventory(
    inventory_path: str | Path,
    *,
    plan_path: str | Path | None = None,
    evidence_package_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    bundle_root: str | Path | None = None,
) -> dict[str, Any]:
    inventory = load_json_object(inventory_path, label="artifact inventory")
    contexts: list[Mapping[str, Any]] = []
    if plan_path:
        contexts.append(load_json_object(plan_path, label="evidence plan"))
    if evidence_package_path:
        contexts.append(load_json_object(evidence_package_path, label="readiness evidence package"))
    if manifest_path:
        contexts.append(load_json_object(manifest_path, label="production closure manifest"))
    return validate_artifact_inventory(inventory, required_contexts=contexts, bundle_root=bundle_root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a production artifact inventory against release evidence contexts.")
    parser.add_argument("inventory_json", nargs="?")
    parser.add_argument("--plan", default="", help="Optional evidence collection plan JSON whose artifact URIs must be inventoried.")
    parser.add_argument("--evidence-package", default="", help="Optional readiness evidence package JSON whose evidence URIs must be inventoried.")
    parser.add_argument("--manifest", default="", help="Optional production closure manifest JSON whose artifact URIs must be inventoried.")
    parser.add_argument("--bundle-root", default="", help="Optional local exported artifact bundle root used to verify file size and sha256.")
    parser.add_argument("--from-bundle-root", default="", help="Generate a filled artifact inventory from files under this exported artifact bundle root.")
    parser.add_argument("--inventory-id", default="production_artifact_inventory", help="Inventory id used with --from-bundle-root.")
    parser.add_argument("--environment", default="staging", help="Inventory environment used when generating a bundle inventory.")
    parser.add_argument("--storage-backend", default="s3", help="Inventory storage backend used when generating a bundle inventory.")
    parser.add_argument("--generated-at", default="", help="Inventory timestamp used when generating a bundle inventory; defaults to current UTC time.")
    parser.add_argument("--producer", default="production_evidence_export", help="Producer used when generating a bundle inventory.")
    parser.add_argument("--owner-role", default="平台负责人", help="Owner role used when generating a bundle inventory.")
    parser.add_argument("--content-type", default="application/json", help="Content type used when generating a bundle inventory.")
    parser.add_argument("--retention-policy", default="retain_release_evidence_7y", help="Retention policy used when generating a bundle inventory.")
    parser.add_argument("--output-template", default="", help="Write an artifact inventory template covering the supplied contexts instead of validating an inventory.")
    parser.add_argument("--output", default="", help="Optional output path for generated inventory or validation result JSON.")
    args = parser.parse_args()
    contexts: list[Mapping[str, Any]] = []
    if args.plan:
        contexts.append(load_json_object(args.plan, label="evidence plan"))
    if args.evidence_package:
        contexts.append(load_json_object(args.evidence_package, label="readiness evidence package"))
    if args.manifest:
        contexts.append(load_json_object(args.manifest, label="production closure manifest"))
    if args.output_template:
        template = build_artifact_inventory_template(*contexts)
        rendered = json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True)
        _atomic_write_text(args.output_template, rendered + "\n")
        print(rendered)
        return
    if args.from_bundle_root:
        inventory = build_artifact_inventory_from_bundle(
            *contexts,
            bundle_root=args.from_bundle_root,
            inventory_id=args.inventory_id,
            environment=args.environment,
            storage_backend=args.storage_backend,
            generated_at=args.generated_at or None,
            producer=args.producer,
            owner_role=args.owner_role,
            content_type=args.content_type,
            retention_policy=args.retention_policy,
        )
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            _atomic_write_text(args.output, rendered + "\n")
        print(rendered)
        if inventory["missing_bundle_file_count"]:
            raise SystemExit(1)
        return
    if not args.inventory_json:
        parser.error("inventory_json is required unless --output-template is used")
    validation = load_and_validate_artifact_inventory(
        args.inventory_json,
        plan_path=args.plan or None,
        evidence_package_path=args.evidence_package or None,
        manifest_path=args.manifest or None,
        bundle_root=args.bundle_root or None,
    )
    rendered = json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
