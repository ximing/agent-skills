---
name: s3-manager
description: Manage S3 or S3-compatible object storage through environment variables that start with AS_. Use this skill whenever the user wants to upload, download, inspect, list, delete, copy, move, rename, or update metadata for objects in S3, MinIO, or other compatible storage, or when they need preview links, download links, or presigned URLs. This skill supports both public and private bucket configurations at the same time through AS_PUBLIC_* and AS_PRIVATE_* variables, and should be preferred whenever the task is broader than a one-off upload.
---

# S3 Manager Guide

## What this skill is for

Use this skill when the user wants an agent to manage objects in S3 or any S3-compatible object storage.

This skill supports a full object-management workflow:
- upload or overwrite objects
- list objects and prefixes
- inspect metadata and object size
- generate direct, preview, download, or presigned access links
- download objects to local files
- delete objects
- copy objects
- move or rename objects
- update object metadata in place

The skill is designed around two independent configurations that can exist at the same time:
- `public` target for shareable objects and direct-access assets
- `private` target for internal or access-controlled objects

All configuration comes from environment variables that start with `AS_`, so secrets stay out of source code.

## Dependencies

Prefer using `python3` plus the bundled `scripts/s3_manager.py` helper.
The script is designed to be usable out of the box:
- if `uv` is missing, it installs `uv` automatically in user scope
- if the skill-local `.venv` is missing, it creates one with `uv venv`
- if `boto3` is missing, it installs `boto3` into that uv-managed environment automatically

This keeps the runtime isolated under `skills/s3-manager/.venv` and avoids requiring a manual preinstall step.

## Choose the right target

Choose `public` when:
- the user explicitly wants a public URL
- the object is a web asset, downloadable file, image, or build artifact meant for sharing
- the result needs to be opened directly without additional authentication

Choose `private` when:
- the object contains internal, sensitive, or user-specific content
- the user says the file should stay private or internal
- the user needs controlled access, preview links, or time-limited downloads

If the user already specifies the bucket type, follow that instruction.
If the request is ambiguous, prefer `private` for anything sensitive.

## Required environment variables

All environment variables must start with `AS_`.

The two target configs mirror each other:
- `AS_PUBLIC_*` configures the public bucket
- `AS_PRIVATE_*` configures the private bucket

### Core variables per target

For either target, replace `<TARGET>` with `PUBLIC` or `PRIVATE`.

- `AS_<TARGET>_BUCKET` - bucket name
- `AS_<TARGET>_ACCESS_KEY_ID` - access key ID
- `AS_<TARGET>_SECRET_ACCESS_KEY` - secret access key
- `AS_<TARGET>_REGION` - optional, defaults to `us-east-1`
- `AS_<TARGET>_HOST` - optional custom S3 host such as `https://s3.example.com`
- `AS_<TARGET>_ENDPOINT_URL` - optional alias for `HOST`
- `AS_<TARGET>_SESSION_TOKEN` - optional temporary credential token
- `AS_<TARGET>_PREFIX` - optional logical prefix prepended to object keys
- `AS_<TARGET>_BASE_URL` - optional external URL base used when building returned direct URLs
- `AS_<TARGET>_ACL` - optional canned ACL override
- `AS_<TARGET>_FORCE_PATH_STYLE` - optional `true`/`false`, useful for MinIO or path-style endpoints
- `AS_<TARGET>_SIGNED_URL_EXPIRES` - optional signed URL validity in seconds; private defaults to `259200` (3 days)

### Shared optional variables

- `AS_DEFAULT_TARGET` - optional fallback target when a command uses `auto`

## Preferred workflow

1. Decide whether the task belongs in the `public` or `private` target.
2. Resolve the object key or prefix.
   - Preserve file extensions.
   - Use stable, readable paths.
   - If the user gives an exact object path, use it.
3. Use the bundled `scripts/s3_manager.py` helper rather than writing ad-hoc boto3 snippets.
4. Return structured results that mention the action taken, target, bucket, object key, and access link when relevant.
5. Never print secrets or echo credential values back to the user.

## Supported commands

If this skill is installed in the current project, use the bundled script:

```bash
python3 skills/s3-manager/scripts/s3_manager.py <command> [...flags]
```

### Runtime bootstrap

```bash
python3 skills/s3-manager/scripts/s3_manager.py ensure-runtime
```

Prepares the uv-managed runtime, installs `boto3`, and returns the resolved `.venv` details.

### Upload or overwrite an object

```bash
python3 skills/s3-manager/scripts/s3_manager.py put --target public --file "/absolute/path/to/file" --key "assets/report.pdf"
```

Useful flags:
- `--content-type image/png`
- `--cache-control "public, max-age=31536000, immutable"`
- `--acl public-read`
- `--metadata source=agent`

### List objects under a prefix

```bash
python3 skills/s3-manager/scripts/s3_manager.py list --target private --prefix "reports/" --delimiter "/" --limit 100
```

Useful flags:
- `--include-urls` to attach direct or presigned URLs to each listed object

### Inspect object metadata

```bash
python3 skills/s3-manager/scripts/s3_manager.py stat --target private --key "reports/q1.pdf"
```

### Generate a preview or download link

```bash
python3 skills/s3-manager/scripts/s3_manager.py url --target private --key "reports/q1.pdf" --mode preview
python3 skills/s3-manager/scripts/s3_manager.py url --target private --key "reports/q1.pdf" --mode download --filename "Q1-report.pdf"
```

### Download an object

```bash
python3 skills/s3-manager/scripts/s3_manager.py download --target private --key "reports/q1.pdf" --output "/tmp/q1.pdf"
```

### Delete one or more objects

```bash
python3 skills/s3-manager/scripts/s3_manager.py delete --target public --key "old/a.js" --key "old/b.js"
```

### Copy an object

```bash
python3 skills/s3-manager/scripts/s3_manager.py copy --source-target private --source-key "reports/q1.pdf" --dest-target public --dest-key "shared/q1.pdf"
```

### Move or rename an object

```bash
python3 skills/s3-manager/scripts/s3_manager.py move --source-target public --source-key "drafts/a.png" --dest-key "published/a.png"
```

If `--dest-target` is omitted, the move stays in the resolved source target.

### Update metadata

```bash
python3 skills/s3-manager/scripts/s3_manager.py set-metadata --target public --key "assets/app.js" --metadata release=2026-05 --cache-control "public, max-age=86400"
```

Useful flags:
- `--clear-metadata` to replace existing metadata instead of merging
- `--content-type` to set or override the stored content type
- `--acl` to update destination ACL while rewriting metadata

## Link behavior

The script prints JSON so it is easy to parse or summarize.

- for `public` targets, `url` is a direct object URL
- for `private` targets, `url` is a presigned access link
- private links default to 3 days unless `AS_PRIVATE_SIGNED_URL_EXPIRES` or `--expires-in` overrides them
- `url --mode preview` is the preferred choice when the user wants a preview link
- `url --mode download` adds a download-oriented content disposition when supported

## Output expectations

After a successful operation, respond with a short status update that includes:
- what action you took
- which target you chose and why, if the choice was not explicit
- the bucket and object key or prefix involved
- the final access link when relevant
- for private links, the expiration time if a presigned URL was generated
- the `s3://` URI for traceability when the operation targets a single object

## Troubleshooting

If an operation fails:
- check that the target-specific `AS_<TARGET>_*` variables are present
- verify the local file path exists for uploads and downloads
- for S3-compatible platforms, make sure `HOST` or `ENDPOINT_URL` is correct
- if the endpoint requires path-style addressing, set `AS_<TARGET>_FORCE_PATH_STYLE=true`
- if automatic dependency bootstrap fails, verify that outbound network access and `curl` are available, or preinstall `uv`
- when troubleshooting configuration, mention only missing variable names, never the secret values

## Examples

**Example 1: upload and return a public URL**
- Task: upload a generated PNG so teammates can open it directly
- Command: `put`
- Target: `public`
- Result: return the direct public URL plus the `s3://` URI

**Example 2: generate a private preview link**
- Task: share an internal PDF temporarily
- Command: `url --mode preview`
- Target: `private`
- Result: return a presigned preview link that defaults to 3 days plus the `s3://` URI

**Example 3: rename an object in place**
- Task: move `drafts/logo.svg` to `published/logo.svg`
- Command: `move`
- Target: same source and destination target unless the user says otherwise
- Result: return the new object location and whether the source was deleted
