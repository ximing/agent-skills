#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import posixpath
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse


VALID_TARGETS = {"public", "private"}
DEFAULT_PRIVATE_URL_EXPIRES = 259200
DEFAULT_PUBLIC_URL_EXPIRES = 3600
SKILL_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = SKILL_ROOT / ".venv"
AUTO_PACKAGES = ("boto3",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage S3 or S3-compatible object storage using AS_* environment variables."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure_runtime = subparsers.add_parser(
        "ensure-runtime",
        help="Install uv if needed, create the skill-local virtualenv, and install boto3.",
    )
    ensure_runtime.set_defaults(handler=handle_ensure_runtime)

    put_parser = subparsers.add_parser(
        "put",
        help="Upload a local file to object storage. Re-running with the same key overwrites the object.",
    )
    add_target_arg(put_parser)
    put_parser.add_argument("--file", required=True, help="Local file path to upload")
    put_parser.add_argument("--key", help="Destination object key. Defaults to the filename.")
    put_parser.add_argument("--content-type", help="Override detected content type")
    put_parser.add_argument("--cache-control", help="Optional Cache-Control header")
    put_parser.add_argument("--acl", help="Optional canned ACL override")
    put_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Metadata entry to attach. Can be passed multiple times.",
    )
    put_parser.set_defaults(handler=handle_put)

    list_parser = subparsers.add_parser(
        "list",
        help="List objects under a prefix and optionally include immediate child prefixes.",
    )
    add_target_arg(list_parser)
    list_parser.add_argument("--prefix", default="", help="Prefix to list from")
    list_parser.add_argument("--delimiter", default="", help="Delimiter, for example '/'")
    list_parser.add_argument("--limit", type=int, default=100, help="Maximum number of objects to return")
    list_parser.add_argument(
        "--include-urls",
        action="store_true",
        help="Include direct or presigned access URLs for listed objects.",
    )
    list_parser.set_defaults(handler=handle_list)

    stat_parser = subparsers.add_parser(
        "stat",
        help="Read object metadata, size, timestamps, and access links.",
    )
    add_target_arg(stat_parser)
    stat_parser.add_argument("--key", required=True, help="Object key to inspect")
    stat_parser.add_argument(
        "--expires-in",
        type=int,
        help="Optional access-link validity override in seconds for private targets.",
    )
    stat_parser.set_defaults(handler=handle_stat)

    url_parser = subparsers.add_parser(
        "url",
        help="Generate a preview or download link for an existing object.",
    )
    add_target_arg(url_parser)
    url_parser.add_argument("--key", required=True, help="Object key")
    url_parser.add_argument(
        "--expires-in",
        type=int,
        help="Optional access-link validity override in seconds for private targets.",
    )
    url_parser.add_argument(
        "--mode",
        choices=["preview", "download"],
        default="preview",
        help="Preview keeps the browser inline when possible; download suggests attachment.",
    )
    url_parser.add_argument("--filename", help="Optional filename hint for download or preview")
    url_parser.set_defaults(handler=handle_url)

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete one or more objects from a target bucket.",
    )
    add_target_arg(delete_parser)
    delete_parser.add_argument(
        "--key",
        action="append",
        required=True,
        help="Object key to delete. Pass multiple times to delete several objects.",
    )
    delete_parser.set_defaults(handler=handle_delete)

    download_parser = subparsers.add_parser(
        "download",
        help="Download an object to a local file path.",
    )
    add_target_arg(download_parser)
    download_parser.add_argument("--key", required=True, help="Object key to download")
    download_parser.add_argument("--output", required=True, help="Local path to write the file to")
    download_parser.set_defaults(handler=handle_download)

    copy_parser = subparsers.add_parser(
        "copy",
        help="Copy an object within the same target or across targets.",
    )
    add_source_dest_target_args(copy_parser)
    copy_parser.add_argument("--source-key", required=True, help="Source object key")
    copy_parser.add_argument("--dest-key", required=True, help="Destination object key")
    copy_parser.add_argument("--acl", help="Optional canned ACL override for the destination")
    copy_parser.set_defaults(handler=handle_copy)

    move_parser = subparsers.add_parser(
        "move",
        help="Move or rename an object by copying it and deleting the source.",
    )
    add_source_dest_target_args(move_parser)
    move_parser.add_argument("--source-key", required=True, help="Source object key")
    move_parser.add_argument("--dest-key", required=True, help="Destination object key")
    move_parser.add_argument("--acl", help="Optional canned ACL override for the destination")
    move_parser.set_defaults(handler=handle_move)

    metadata_parser = subparsers.add_parser(
        "set-metadata",
        help="Update object metadata by rewriting the object in place.",
    )
    add_target_arg(metadata_parser)
    metadata_parser.add_argument("--key", required=True, help="Object key to update")
    metadata_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Metadata entry to add or overwrite. Can be passed multiple times.",
    )
    metadata_parser.add_argument(
        "--clear-metadata",
        action="store_true",
        help="Clear existing metadata before applying new entries.",
    )
    metadata_parser.add_argument("--content-type", help="Optional content type override")
    metadata_parser.add_argument("--cache-control", help="Optional cache control override")
    metadata_parser.add_argument("--acl", help="Optional canned ACL override")
    metadata_parser.set_defaults(handler=handle_set_metadata)

    return parser.parse_args()


def add_target_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target",
        default="auto",
        choices=["public", "private", "auto"],
        help="Bucket target. `auto` uses AS_DEFAULT_TARGET.",
    )


def add_source_dest_target_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-target",
        default="auto",
        choices=["public", "private", "auto"],
        help="Source target. `auto` uses AS_DEFAULT_TARGET.",
    )
    parser.add_argument(
        "--dest-target",
        choices=["public", "private", "auto"],
        help="Destination target. Defaults to the resolved source target.",
    )


def normalize_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise SystemExit(f"Invalid integer value: {value}") from exc
    if parsed <= 0:
        raise SystemExit(f"Expected a positive integer, got: {value}")
    return parsed


def normalize_endpoint(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    return raw.rstrip("/")


def venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def build_bootstrap_env() -> dict[str, str]:
    env = os.environ.copy()
    extra_paths = [str(Path.home() / ".local" / "bin"), str(Path.home() / ".cargo" / "bin")]
    current_path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(extra_paths + ([current_path] if current_path else []))
    return env


def ensure_uv_available() -> tuple[str, dict[str, str]]:
    env = build_bootstrap_env()
    uv_path = shutil.which("uv", path=env.get("PATH"))
    if uv_path:
        return uv_path, env

    if os.name == "nt":
        raise SystemExit("uv is required but was not found. Please install uv before running this script on Windows.")

    curl_path = shutil.which("curl", path=env.get("PATH"))
    if not curl_path:
        raise SystemExit("Automatic uv installation requires `curl`, but it was not found on PATH.")

    try:
        subprocess.run(
            ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
            check=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Failed to install uv automatically: {exc}") from exc

    uv_path = shutil.which("uv", path=env.get("PATH"))
    if not uv_path:
        raise SystemExit(
            "uv was installed but could not be found afterwards. Ensure ~/.local/bin is available on PATH."
        )
    return uv_path, env


def ensure_runtime_packages(packages: tuple[str, ...] = AUTO_PACKAGES) -> Path:
    uv_path, env = ensure_uv_available()
    python_path = venv_python_path()

    try:
        if not python_path.exists():
            subprocess.run([uv_path, "venv", str(VENV_DIR)], check=True, env=env)
        subprocess.run(
            [uv_path, "pip", "install", "--python", str(python_path), *packages],
            check=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Failed to prepare the uv-managed runtime: {exc}") from exc

    return python_path


def pick_target(requested: str) -> str:
    if requested in VALID_TARGETS:
        return requested

    default_target = os.getenv("AS_DEFAULT_TARGET", "").strip().lower()
    if default_target in VALID_TARGETS:
        return default_target

    raise SystemExit(
        "Could not determine target. Pass an explicit target or set AS_DEFAULT_TARGET to public/private."
    )


def normalize_key(value: str, prefix: str | None = None) -> str:
    normalized = value.strip().lstrip("/")
    normalized_prefix = (prefix or "").strip().strip("/")
    if not normalized_prefix:
        if not normalized:
            raise SystemExit("Object key or prefix is empty.")
        return normalized
    if not normalized:
        return normalized_prefix
    if normalized == normalized_prefix or normalized.startswith(normalized_prefix + "/"):
        return normalized
    return posixpath.join(normalized_prefix, normalized)


def parse_key_values(items: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"Invalid KEY=VALUE entry `{item}`.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"Invalid KEY=VALUE entry `{item}`. Key is empty.")
        parsed[key] = value
    return parsed


def load_target_config(target: str) -> dict[str, Any]:
    prefix = f"AS_{target.upper()}_"
    endpoint = normalize_endpoint(
        os.getenv(prefix + "ENDPOINT_URL") or os.getenv(prefix + "HOST")
    )
    config = {
        "env_prefix": prefix,
        "target": target,
        "bucket": os.getenv(prefix + "BUCKET", "").strip(),
        "access_key_id": os.getenv(prefix + "ACCESS_KEY_ID", "").strip(),
        "secret_access_key": os.getenv(prefix + "SECRET_ACCESS_KEY", "").strip(),
        "session_token": os.getenv(prefix + "SESSION_TOKEN", "").strip() or None,
        "region": os.getenv(prefix + "REGION", "").strip() or "us-east-1",
        "endpoint_url": endpoint,
        "prefix": os.getenv(prefix + "PREFIX", "").strip().strip("/"),
        "base_url": normalize_endpoint(os.getenv(prefix + "BASE_URL")),
        "acl": os.getenv(prefix + "ACL", "").strip() or None,
        "force_path_style": normalize_bool(os.getenv(prefix + "FORCE_PATH_STYLE")),
        "signed_url_expires": normalize_int(
            os.getenv(prefix + "SIGNED_URL_EXPIRES"),
            DEFAULT_PRIVATE_URL_EXPIRES if target == "private" else DEFAULT_PUBLIC_URL_EXPIRES,
        ),
    }

    missing = [
        name
        for name, value in (
            (prefix + "BUCKET", config["bucket"]),
            (prefix + "ACCESS_KEY_ID", config["access_key_id"]),
            (prefix + "SECRET_ACCESS_KEY", config["secret_access_key"]),
        )
        if not value
    ]
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))
    return config


def build_client(config: dict[str, Any]):
    try:
        import boto3
        from botocore.config import Config
    except ModuleNotFoundError:
        runtime_python = ensure_runtime_packages()
        if Path(sys.executable).resolve() != runtime_python.resolve():
            os.execv(str(runtime_python), [str(runtime_python), str(Path(__file__).resolve()), *sys.argv[1:]])
        import boto3
        from botocore.config import Config

    s3_config = Config(
        signature_version="s3v4",
        s3={
            "addressing_style": "path" if config["force_path_style"] else "virtual",
        },
    )
    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=config["region"],
        endpoint_url=config["endpoint_url"],
        aws_access_key_id=config["access_key_id"],
        aws_secret_access_key=config["secret_access_key"],
        aws_session_token=config["session_token"],
        config=s3_config,
    )


def build_extra_args(
    config: dict[str, Any],
    *,
    acl: str | None = None,
    content_type: str | None = None,
    cache_control: str | None = None,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    extra_args: dict[str, Any] = {}
    resolved_acl = acl or config["acl"]
    if resolved_acl:
        extra_args["ACL"] = resolved_acl
    if content_type:
        extra_args["ContentType"] = content_type
    if cache_control:
        extra_args["CacheControl"] = cache_control
    if metadata:
        extra_args["Metadata"] = metadata
    return extra_args


def build_object_url(config: dict[str, Any], key: str) -> str:
    escaped_key = quote(key, safe="/")
    bucket = config["bucket"]

    if config["base_url"]:
        return f"{config['base_url']}/{escaped_key}"

    if config["endpoint_url"]:
        parsed = urlparse(config["endpoint_url"])
        if config["force_path_style"]:
            return f"{config['endpoint_url']}/{bucket}/{escaped_key}"
        return f"{parsed.scheme}://{bucket}.{parsed.netloc}/{escaped_key}"

    if config["region"] == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{escaped_key}"
    return f"https://{bucket}.s3.{config['region']}.amazonaws.com/{escaped_key}"


def build_content_disposition(mode: str, filename: str | None) -> str | None:
    if mode == "preview" and not filename:
        return None
    if filename:
        safe_filename = filename.replace('"', "")
        if mode == "download":
            return f'attachment; filename="{safe_filename}"'
        return f'inline; filename="{safe_filename}"'
    if mode == "download":
        return "attachment"
    return None


def build_access_descriptor(
    client,
    config: dict[str, Any],
    key: str,
    *,
    expires_in: int | None = None,
    mode: str = "preview",
    filename: str | None = None,
) -> dict[str, Any]:
    object_url = build_object_url(config, key)
    if config["target"] == "public":
        return {
            "url": object_url,
            "access_url": object_url,
            "object_url": object_url,
            "access_url_type": "direct",
            "expires_in_seconds": None,
        }

    params: dict[str, Any] = {"Bucket": config["bucket"], "Key": key}
    disposition = build_content_disposition(mode, filename)
    if disposition:
        params["ResponseContentDisposition"] = disposition
    ttl = expires_in or config["signed_url_expires"]
    access_url = client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=ttl,
    )
    return {
        "url": access_url,
        "access_url": access_url,
        "object_url": object_url,
        "access_url_type": "presigned",
        "expires_in_seconds": ttl,
    }


def build_object_descriptor(
    client,
    config: dict[str, Any],
    key: str,
    *,
    expires_in: int | None = None,
    mode: str = "preview",
    filename: str | None = None,
) -> dict[str, Any]:
    access = build_access_descriptor(
        client,
        config,
        key,
        expires_in=expires_in,
        mode=mode,
        filename=filename,
    )
    return {
        "key": key,
        "s3_uri": f"s3://{config['bucket']}/{key}",
        **access,
    }


def resolve_object_key(config: dict[str, Any], raw_key: str | None, *, allow_empty: bool = False) -> str:
    if raw_key is None:
        if allow_empty and config["prefix"]:
            return config["prefix"]
        raise SystemExit("A key or prefix value is required.")
    if not raw_key.strip():
        if allow_empty and config["prefix"]:
            return config["prefix"]
        if allow_empty:
            return ""
        raise SystemExit("A key or prefix value is required.")
    return normalize_key(raw_key, config["prefix"])


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def emit_result(result: dict[str, Any]) -> int:
    print(json.dumps(result, ensure_ascii=True, indent=2, default=serialize_value))
    return 0


def head_object(client, config: dict[str, Any], key: str) -> dict[str, Any]:
    return client.head_object(Bucket=config["bucket"], Key=key)


def handle_ensure_runtime(_: argparse.Namespace) -> int:
    python_path = ensure_runtime_packages()
    return emit_result(
        {
            "status": "ok",
            "operation": "ensure-runtime",
            "venv": str(VENV_DIR),
            "python": str(python_path),
            "packages": list(AUTO_PACKAGES),
        }
    )


def handle_put(args: argparse.Namespace) -> int:
    target = pick_target(args.target)
    config = load_target_config(target)
    client = build_client(config)

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.is_file():
        raise SystemExit(f"File not found: {file_path}")

    object_key = resolve_object_key(config, args.key or file_path.name)
    metadata = parse_key_values(args.metadata)
    content_type = args.content_type or mimetypes.guess_type(str(file_path))[0]
    extra_args = build_extra_args(
        config,
        acl=args.acl,
        content_type=content_type,
        cache_control=args.cache_control,
        metadata=metadata,
    )

    client.upload_file(
        str(file_path),
        config["bucket"],
        object_key,
        ExtraArgs=extra_args or None,
    )

    descriptor = build_object_descriptor(client, config, object_key)
    return emit_result(
        {
            "status": "ok",
            "operation": "put",
            "target": target,
            "bucket": config["bucket"],
            "local_file": str(file_path),
            **descriptor,
            "content_type": content_type,
            "cache_control": args.cache_control,
            "acl": extra_args.get("ACL"),
            "metadata": metadata,
            "endpoint_url": config["endpoint_url"],
            "used_env_prefix": config["env_prefix"],
        }
    )


def handle_list(args: argparse.Namespace) -> int:
    target = pick_target(args.target)
    config = load_target_config(target)
    client = build_client(config)

    prefix = resolve_object_key(config, args.prefix, allow_empty=True)
    paginator = client.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(
        Bucket=config["bucket"],
        Prefix=prefix,
        Delimiter=args.delimiter or "",
        PaginationConfig={"PageSize": min(max(args.limit, 1), 1000)},
    )

    objects: list[dict[str, Any]] = []
    prefixes: list[str] = []
    for page in page_iterator:
        prefixes.extend(item["Prefix"] for item in page.get("CommonPrefixes", []))
        for entry in page.get("Contents", []):
            key = entry["Key"]
            item = {
                "key": key,
                "s3_uri": f"s3://{config['bucket']}/{key}",
                "size": entry.get("Size"),
                "etag": entry.get("ETag", "").strip('"'),
                "last_modified": entry.get("LastModified"),
                "storage_class": entry.get("StorageClass"),
            }
            if args.include_urls:
                item.update(build_access_descriptor(client, config, key))
            objects.append(item)
            if len(objects) >= args.limit:
                break
        if len(objects) >= args.limit:
            break

    return emit_result(
        {
            "status": "ok",
            "operation": "list",
            "target": target,
            "bucket": config["bucket"],
            "prefix": prefix,
            "delimiter": args.delimiter or None,
            "count": len(objects),
            "objects": objects,
            "common_prefixes": prefixes,
            "used_env_prefix": config["env_prefix"],
        }
    )


def handle_stat(args: argparse.Namespace) -> int:
    target = pick_target(args.target)
    config = load_target_config(target)
    client = build_client(config)
    key = resolve_object_key(config, args.key)

    response = head_object(client, config, key)
    descriptor = build_object_descriptor(client, config, key, expires_in=args.expires_in)
    return emit_result(
        {
            "status": "ok",
            "operation": "stat",
            "target": target,
            "bucket": config["bucket"],
            **descriptor,
            "size": response.get("ContentLength"),
            "etag": response.get("ETag", "").strip('"'),
            "last_modified": response.get("LastModified"),
            "content_type": response.get("ContentType"),
            "cache_control": response.get("CacheControl"),
            "metadata": response.get("Metadata", {}),
            "version_id": response.get("VersionId"),
            "used_env_prefix": config["env_prefix"],
        }
    )


def handle_url(args: argparse.Namespace) -> int:
    target = pick_target(args.target)
    config = load_target_config(target)
    client = build_client(config)
    key = resolve_object_key(config, args.key)

    descriptor = build_object_descriptor(
        client,
        config,
        key,
        expires_in=args.expires_in,
        mode=args.mode,
        filename=args.filename,
    )
    return emit_result(
        {
            "status": "ok",
            "operation": "url",
            "target": target,
            "bucket": config["bucket"],
            **descriptor,
            "mode": args.mode,
            "filename": args.filename,
            "used_env_prefix": config["env_prefix"],
        }
    )


def handle_delete(args: argparse.Namespace) -> int:
    target = pick_target(args.target)
    config = load_target_config(target)
    client = build_client(config)
    keys = [resolve_object_key(config, raw_key) for raw_key in args.key]

    delete_response = client.delete_objects(
        Bucket=config["bucket"],
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": False},
    )
    deleted = [item.get("Key") for item in delete_response.get("Deleted", [])]
    errors = delete_response.get("Errors", [])

    return emit_result(
        {
            "status": "ok" if not errors else "partial",
            "operation": "delete",
            "target": target,
            "bucket": config["bucket"],
            "requested_keys": keys,
            "deleted_keys": deleted,
            "errors": errors,
            "used_env_prefix": config["env_prefix"],
        }
    )


def handle_download(args: argparse.Namespace) -> int:
    target = pick_target(args.target)
    config = load_target_config(target)
    client = build_client(config)
    key = resolve_object_key(config, args.key)
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client.download_file(config["bucket"], key, str(output_path))
    descriptor = build_object_descriptor(client, config, key)
    return emit_result(
        {
            "status": "ok",
            "operation": "download",
            "target": target,
            "bucket": config["bucket"],
            **descriptor,
            "output_file": str(output_path),
            "used_env_prefix": config["env_prefix"],
        }
    )


def resolve_copy_targets(args: argparse.Namespace) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    source_target = pick_target(args.source_target)
    dest_target = pick_target(args.dest_target or source_target)
    source_config = load_target_config(source_target)
    dest_config = load_target_config(dest_target)
    return source_target, dest_target, source_config, dest_config


def execute_copy_like_operation(args: argparse.Namespace, *, delete_source: bool) -> int:
    source_target, dest_target, source_config, dest_config = resolve_copy_targets(args)
    source_client = build_client(source_config)
    dest_client = build_client(dest_config)
    source_key = resolve_object_key(source_config, args.source_key)
    dest_key = resolve_object_key(dest_config, args.dest_key)

    extra_args = build_extra_args(dest_config, acl=args.acl)
    dest_client.copy(
        {"Bucket": source_config["bucket"], "Key": source_key},
        dest_config["bucket"],
        dest_key,
        ExtraArgs=extra_args or None,
        SourceClient=source_client,
    )

    if delete_source:
        source_client.delete_object(Bucket=source_config["bucket"], Key=source_key)

    descriptor = build_object_descriptor(dest_client, dest_config, dest_key)
    return emit_result(
        {
            "status": "ok",
            "operation": "move" if delete_source else "copy",
            "source_target": source_target,
            "source_bucket": source_config["bucket"],
            "source_key": source_key,
            "source_s3_uri": f"s3://{source_config['bucket']}/{source_key}",
            "dest_target": dest_target,
            "dest_bucket": dest_config["bucket"],
            **descriptor,
            "deleted_source": delete_source,
            "acl": extra_args.get("ACL"),
            "source_env_prefix": source_config["env_prefix"],
            "dest_env_prefix": dest_config["env_prefix"],
        }
    )


def handle_copy(args: argparse.Namespace) -> int:
    return execute_copy_like_operation(args, delete_source=False)


def handle_move(args: argparse.Namespace) -> int:
    return execute_copy_like_operation(args, delete_source=True)


def handle_set_metadata(args: argparse.Namespace) -> int:
    target = pick_target(args.target)
    config = load_target_config(target)
    client = build_client(config)
    key = resolve_object_key(config, args.key)

    existing = head_object(client, config, key)
    metadata = {} if args.clear_metadata else dict(existing.get("Metadata", {}))
    metadata.update(parse_key_values(args.metadata))
    content_type = args.content_type or existing.get("ContentType")
    cache_control = args.cache_control if args.cache_control is not None else existing.get("CacheControl")
    extra_args = build_extra_args(
        config,
        acl=args.acl,
        content_type=content_type,
        cache_control=cache_control,
        metadata=metadata,
    )
    extra_args["MetadataDirective"] = "REPLACE"

    client.copy(
        {"Bucket": config["bucket"], "Key": key},
        config["bucket"],
        key,
        ExtraArgs=extra_args,
    )

    descriptor = build_object_descriptor(client, config, key)
    return emit_result(
        {
            "status": "ok",
            "operation": "set-metadata",
            "target": target,
            "bucket": config["bucket"],
            **descriptor,
            "metadata": metadata,
            "content_type": content_type,
            "cache_control": cache_control,
            "acl": extra_args.get("ACL"),
            "used_env_prefix": config["env_prefix"],
        }
    )


def main() -> int:
    args = parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
