#!/usr/bin/env python3
"""Audit and sync the progressive-disclosure layout.

Facts about loaders live in references/loaders.md. File shapes live in
references/layout.md. This script only checks those rules and rewrites the
generated mirrors.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
    ".cache",
    "vendor",
}

STUB_PREFIX = "<!-- progressive-disclosure: stub for "
SKILL_MIRROR_PREFIX = "<!-- progressive-disclosure: claude-skill-mirror of "
MIRROR_PREFIX = "<!-- progressive-disclosure: generated from "
GROK_ALIASES = {"Agents.md", "Claude.md", "AGENT.md", "Agent.md"}
SKILL_BODY_BYTES = 100_000
# Warning thresholds taken from references/loaders.md. 40 lines is this
# script's cutoff for a Claude rule that Grok will also load at startup.
CODEX_CHAIN_BYTES = 32 * 1024
ANTIGRAVITY_FILE_BYTES = 24_000
AGENTS_LINE_BUDGET = 200
CLAUDE_RULE_LINE_BUDGET = 40
DESCRIPTION_BUDGET = 500
TRIGGERS = {"always_on", "model_decision", "glob", "manual"}


@dataclass
class Finding:
    severity: str
    code: str
    path: str
    message: str


def skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.endswith(".egg-info")


def walk_files(root: Path):
    for dirpath, dirnames, filenames in os_walk(root):
        dirnames[:] = [name for name in dirnames if not skip_dir(name)]
        for name in filenames:
            yield Path(dirpath) / name


def os_walk(root: Path):
    import os

    return os.walk(root, followlinks=False)


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            if body.startswith("\n"):
                body = body[1:]
            elif body.startswith("\r\n"):
                body = body[2:]
            return frontmatter, body
    return None, text


def frontmatter_blocks(frontmatter: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in frontmatter.splitlines():
        if line.startswith((" ", "\t")) or (current and not line.strip()):
            buf.append(line)
            continue
        if ":" in line and not line.startswith("-"):
            if current is not None:
                blocks[current] = "\n".join(buf).strip()
            key, value = line.split(":", 1)
            current = key.strip()
            buf = [value.strip()]
            continue
        buf.append(line)
    if current is not None:
        blocks[current] = "\n".join(buf).strip()
    return blocks


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(value) >= 2 and value[0] == value[-1] and value[0] == "'":
        return value[1:-1]
    return value


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def first_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def marker_line(prefix: str, target: str) -> str:
    return f"{prefix}{target} -->"


def strip_marker(body: str, prefix: str) -> tuple[str | None, str]:
    lines = body.splitlines()
    if not lines:
        return None, body
    first = lines[0].strip()
    if not first.startswith(prefix) or not first.endswith("-->"):
        return None, body
    target = first[len(prefix) : -len(" -->")]
    rest = "\n".join(lines[1:])
    if rest.startswith("\n"):
        rest = rest[1:]
    return target, rest


def agents_files(root: Path) -> list[Path]:
    found = []
    for path in walk_files(root):
        if path.name != "AGENTS.md":
            continue
        if path.parent.name in {".claude", ".agents"}:
            continue
        found.append(path)
    return sorted(found)


def slug_for(root: Path, agents: Path) -> str:
    directory = agents.parent.relative_to(root).as_posix()
    return directory.replace("/", "__")


def skill_files(root: Path) -> list[Path]:
    base = root / ".agents" / "skills"
    if not base.is_dir():
        return []
    found = []
    for child in sorted(base.iterdir()):
        skill = child / "SKILL.md"
        if child.is_dir() and not skip_dir(child.name) and skill.is_file():
            found.append(skill)
    return found


def render_skill_mirror(
    name: str, description: str, target: str, paths_block: str | None, body: str
) -> str:
    lines = ["---", f"name: {name}", f"description: {yaml_quote(description)}"]
    if paths_block:
        lines.append(paths_block.rstrip())
    lines.extend(["---", "", marker_line(SKILL_MIRROR_PREFIX, target), ""])
    if body and not body.endswith("\n"):
        body += "\n"
    return "\n".join(lines) + body


def render_mirror(source_rel: str, description: str, source_text: str) -> str:
    body = source_text
    if not body.endswith("\n"):
        body += "\n"
    return "\n".join(
        [
            "---",
            "trigger: model_decision",
            f"description: {yaml_quote(description)}",
            "---",
            "",
            marker_line(MIRROR_PREFIX, source_rel),
            "",
            body,
        ]
    )


def existing_paths_block(text: str) -> str | None:
    frontmatter, _body = split_frontmatter(text)
    if frontmatter is None or "paths" not in frontmatter_blocks(frontmatter):
        return None
    lines = frontmatter.splitlines()
    kept: list[str] = []
    capturing = False
    for line in lines:
        if not line.startswith((" ", "\t")) and ":" in line:
            key = line.split(":", 1)[0].strip()
            capturing = key == "paths"
        if capturing:
            kept.append(line)
    return "\n".join(kept) if kept else None


def skill_meta(path: Path) -> tuple[str, str]:
    frontmatter, _body = split_frontmatter(read_text(path))
    blocks = frontmatter_blocks(frontmatter or "")
    name = unquote(blocks.get("name", "")) or path.parent.name
    description = unquote(blocks.get("description", ""))
    return name, description


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def rule_body(path: Path) -> str:
    _frontmatter, body = split_frontmatter(read_text(path))
    return normalized(body)


def add(findings: list[Finding], severity: str, code: str, path: Path, root: Path, message: str) -> None:
    findings.append(Finding(severity, code, rel(root, path), message))


def audit(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    agents = agents_files(root)

    for path in agents:
        text = read_text(path)
        if text.startswith("---"):
            add(
                findings,
                "error",
                "agents-frontmatter",
                path,
                root,
                "AGENTS.md stays plain markdown. Frontmatter is not a trigger, and Antigravity treats the whole file as always-on text.",
            )
        line_count = len(text.splitlines())
        if line_count > AGENTS_LINE_BUDGET:
            add(
                findings,
                "warning",
                "agents-long",
                path,
                root,
                f"{line_count} lines. Keep standing instructions under {AGENTS_LINE_BUDGET} lines; move procedures into a skill.",
            )
        size = len(text.encode("utf-8"))
        if size > ANTIGRAVITY_FILE_BYTES:
            add(
                findings,
                "warning",
                "antigravity-file-size",
                path,
                root,
                f"{size} bytes. Antigravity truncates a rule file past {ANTIGRAVITY_FILE_BYTES} bytes.",
            )
        chain = chain_bytes(root, path)
        if chain > CODEX_CHAIN_BYTES:
            add(
                findings,
                "warning",
                "codex-chain-size",
                path,
                root,
                f"AGENTS.md files from the repo root through here total {chain} bytes. The Codex AGENTS.md page stops the combined chain at {CODEX_CHAIN_BYTES} bytes.",
            )
        if path.parent != root:
            mirror = root / ".agents" / "rules" / f"{slug_for(root, path)}.md"
            if not mirror.is_file():
                add(
                    findings,
                    "error",
                    "mirror-missing",
                    path,
                    root,
                    "Antigravity opened at the repo root does not load this nested AGENTS.md. Run sync to write the model_decision mirror.",
                )
            else:
                _mirror_fm, mirror_body = split_frontmatter(read_text(mirror))
                if strip_marker(mirror_body, MIRROR_PREFIX)[0] is None:
                    add(
                        findings,
                        "error",
                        "mirror-blocked",
                        mirror,
                        root,
                        "A hand-written rule occupies the generated mirror name. Rename it so sync can write the directory mirror.",
                    )

    for path in walk_files(root):
        name = path.name
        if name in {"CLAUDE.md", "CLAUDE.local.md"}:
            add(
                findings,
                "error",
                "parallel-instruction",
                path,
                root,
                "Remove this file after merging unique lines into AGENTS.md. Grok loads it in addition to AGENTS.md, and any CLAUDE.md on the ancestor chain stops Claude from reading every AGENTS.md, including nested ones.",
            )
        if name == "GEMINI.md":
            add(
                findings,
                "error",
                "gemini-stack",
                path,
                root,
                "Antigravity loads GEMINI.md together with AGENTS.md. Merge it into AGENTS.md and delete this file. Grok's filename list does not include GEMINI.md.",
            )
        if name in GROK_ALIASES:
            add(
                findings,
                "error",
                "grok-alias",
                path,
                root,
                "Grok loads this alias in addition to AGENTS.md. Codex, Claude, and Antigravity do not treat it as the shared instruction file.",
            )
        if name == "AGENTS.md" and path.parent.name == ".claude":
            add(
                findings,
                "error",
                "claude-hidden-agents",
                path,
                root,
                "Claude loads .claude/AGENTS.md with the other AGENTS.md files. Codex does not. Keep the shared file at <dir>/AGENTS.md.",
            )
        if name == "AGENTS.override.md":
            add(
                findings,
                "error",
                "agents-override",
                path,
                root,
                "Codex uses AGENTS.override.md instead of AGENTS.md in this directory. Claude, Grok, and Antigravity do not read the override.",
            )
        if name == "AGENTS.md" and path.parent.name == ".agents":
            add(
                findings,
                "error",
                "agents-hidden-copy",
                path,
                root,
                "Antigravity loads .agents/AGENTS.md as well as a directory AGENTS.md. Codex, Claude, and Grok do not treat this path as the shared file.",
            )

    for path in walk_files(root):
        if not is_rule_file(path, ".claude"):
            continue
        frontmatter, _body = split_frontmatter(read_text(path))
        blocks = frontmatter_blocks(frontmatter or "")
        if "paths" not in blocks or not blocks["paths"]:
            add(
                findings,
                "error",
                "claude-rule-eager",
                path,
                root,
                "A Claude rule without paths loads at session start. Grok also loads every file in .claude/rules at session start.",
            )
        else:
            line_count = len(read_text(path).splitlines())
            if line_count > CLAUDE_RULE_LINE_BUDGET:
                add(
                    findings,
                    "warning",
                    "grok-eager-claude-rule",
                    path,
                    root,
                    f"{line_count} lines. Grok loads this whole file when the session starts. Keep the Claude half to a short constraint.",
                )
        if path.parent.name != "rules":
            add(
                findings,
                "warning",
                "rule-nested",
                path,
                root,
                "Put the rule directly in .claude/rules/. Nested files are unreliable for Grok and invisible to Antigravity.",
            )

    for path in walk_files(root):
        if not is_rule_file(path, ".agents"):
            continue
        text = read_text(path)
        frontmatter, body = split_frontmatter(text)
        blocks = frontmatter_blocks(frontmatter or "")
        trigger = unquote(blocks.get("trigger", ""))
        if trigger not in TRIGGERS:
            add(
                findings,
                "error",
                "antigravity-trigger",
                path,
                root,
                "Antigravity drops a rule whose trigger is missing or not one of always_on, model_decision, glob, manual.",
            )
        if trigger == "model_decision" and not unquote(blocks.get("description", "")):
            add(
                findings,
                "error",
                "antigravity-description",
                path,
                root,
                "model_decision requires description. Antigravity shows that text before it reads the file.",
            )
        if trigger == "glob" and not (blocks.get("globs") or blocks.get("glob")):
            add(
                findings,
                "error",
                "antigravity-globs",
                path,
                root,
                "A glob rule needs globs (or glob). Quote patterns that start with *.",
            )
        if path.parent.name != "rules":
            add(
                findings,
                "error",
                "antigravity-rule-nested",
                path,
                root,
                "Antigravity only reads markdown files directly inside .agents/rules/.",
            )
        target, payload = strip_marker(body, MIRROR_PREFIX)
        if target is not None:
            source = root / target
            if not source.is_file():
                add(
                    findings,
                    "error",
                    "mirror-orphan",
                    path,
                    root,
                    f"Generated mirror points at missing {target}. Run sync to delete it.",
                )
            elif normalized(payload) != normalized(read_text(source)):
                add(
                    findings,
                    "error",
                    "mirror-drift",
                    path,
                    root,
                    f"Body differs from {target}. Edit the AGENTS.md source and run sync.",
                )

    claude_rules = {
        path.stem: path
        for path in walk_files(root)
        if is_rule_file(path, ".claude") and path.parent.name == "rules"
    }
    handwritten_agents_rules: dict[str, Path] = {}
    generated_mirrors: set[str] = set()
    for path in walk_files(root):
        if not is_rule_file(path, ".agents") or path.parent.name != "rules":
            continue
        text = read_text(path)
        _frontmatter, body = split_frontmatter(text)
        if strip_marker(body, MIRROR_PREFIX)[0] is not None:
            generated_mirrors.add(path.stem)
            continue
        handwritten_agents_rules[path.stem] = path
        pair = claude_rules.get(path.stem)
        if pair is None:
            add(
                findings,
                "warning",
                "glob-pair-missing",
                path,
                root,
                "This Antigravity rule has no Claude twin at .claude/rules/"
                + path.name
                + ". Claude does not read .agents/rules/.",
            )
            continue
        if rule_body(pair) != rule_body(path):
            add(
                findings,
                "error",
                "glob-pair-mismatch",
                path,
                root,
                f"Body differs from {rel(root, pair)}. Keep the two halves identical below their frontmatter.",
            )
    for stem, path in claude_rules.items():
        pair_frontmatter, _pair_body = split_frontmatter(read_text(path))
        pair_blocks = frontmatter_blocks(pair_frontmatter or "")
        if "paths" not in pair_blocks or not pair_blocks["paths"]:
            continue
        if stem in generated_mirrors:
            add(
                findings,
                "error",
                "rule-name-collision",
                path,
                root,
                "This name belongs to a generated directory mirror. Rename the glob rule so it does not contain the mirror slug.",
            )
        elif stem not in handwritten_agents_rules:
            add(
                findings,
                "warning",
                "glob-pair-missing",
                path,
                root,
                "This Claude rule has no Antigravity twin at .agents/rules/"
                + path.name
                + ". Antigravity does not read .claude/rules/.",
            )

    for path in skill_files(root):
        frontmatter, _body = split_frontmatter(read_text(path))
        blocks = frontmatter_blocks(frontmatter or "")
        name = unquote(blocks.get("name", ""))
        description = blocks.get("description", "")
        description_text = unquote(description)
        if (
            not name
            or not description_text
            or "\n" in description
            or "\n" in description_text
            or len(description_text) > DESCRIPTION_BUDGET
        ):
            add(
                findings,
                "error",
                "skill-description",
                path,
                root,
                f"Canonical skills need a single-line name and a single-line description of at most {DESCRIPTION_BUDGET} characters.",
            )
        body_bytes = len(split_frontmatter(read_text(path))[1].encode("utf-8"))
        if body_bytes > SKILL_BODY_BYTES:
            add(
                findings,
                "warning",
                "skill-body-size",
                path,
                root,
                f"Skill body is {body_bytes} bytes. Grok inlines at most {SKILL_BODY_BYTES} bytes and cuts the rest at the last full line.",
            )
        if name and name != path.parent.name:
            add(
                findings,
                "warning",
                "skill-name-mismatch",
                path,
                root,
                f"Frontmatter name {name!r} does not match the directory {path.parent.name!r}.",
            )
        for key in ("paths", "disable-model-invocation", "context"):
            if key in blocks:
                add(
                    findings,
                    "error",
                    "skill-claude-only-field",
                    path,
                    root,
                    f"Move {key} off the shared skill. Claude-only fields belong on the .claude/skills copy.",
                )
        target = rel(root, path)
        mirror = root / ".claude" / "skills" / path.parent.name / "SKILL.md"
        canonical_body = split_frontmatter(read_text(path))[1]
        if not mirror.is_file():
            add(
                findings,
                "error",
                "claude-skill-mirror-missing",
                path,
                root,
                "Claude does not scan .agents/skills. Run sync to copy this skill into .claude/skills.",
            )
            continue
        mirror_fm, mirror_body = split_frontmatter(read_text(mirror))
        old_stub, _old_payload = strip_marker(mirror_body, STUB_PREFIX)
        pointed, payload = strip_marker(mirror_body, SKILL_MIRROR_PREFIX)
        if old_stub is not None:
            add(
                findings,
                "error",
                "claude-skill-stub",
                mirror,
                root,
                "This Claude skill is only a pointer. Run sync to replace it with a copy of the canonical body.",
            )
            continue
        if pointed is None:
            add(
                findings,
                "warning",
                "claude-skill-unmanaged",
                mirror,
                root,
                "This Claude skill has no generated-mirror marker, so sync will not replace it. Move the body to .agents/skills and let sync write the copy.",
            )
            continue
        mirror_blocks = frontmatter_blocks(mirror_fm or "")
        if (
            pointed != target
            or unquote(mirror_blocks.get("description", "")) != unquote(description)
            or normalized(payload) != normalized(canonical_body)
        ):
            add(
                findings,
                "error",
                "claude-skill-mirror-drift",
                mirror,
                root,
                "Claude copy does not match the canonical skill. Run sync.",
            )

    canonical_skills = {path.parent.name for path in skill_files(root)}
    for path in walk_files(root):
        if path.name != "SKILL.md":
            continue
        if ".agents" in path.parts and path.parent != root / ".agents" / "skills" / path.parent.name:
            add(
                findings,
                "warning",
                "skill-not-at-root",
                path,
                root,
                "Put shared skills directly in .agents/skills/<name>/SKILL.md. Deeper folders and package folders stay invisible when a tool is opened at the repo root.",
            )
        home = path.parent.parent.parent if len(path.parents) >= 3 else None
        if home is not None and home.name in {".grok", ".cursor"} and path.parent.parent.name == "skills":
            add(
                findings,
                "warning",
                "skill-vendor-copy",
                path,
                root,
                "Codex and Antigravity will not see a skill that lives only here. Put the body in .agents/skills and let sync write the Claude copy.",
            )
        if path.parent.parent == root / ".claude" / "skills" and path.parent.name not in canonical_skills:
            _frontmatter, body = split_frontmatter(read_text(path))
            if strip_marker(body, STUB_PREFIX)[0] is None and strip_marker(body, SKILL_MIRROR_PREFIX)[0] is None:
                add(
                    findings,
                    "warning",
                    "claude-skill-outside-agents",
                    path,
                    root,
                    "Claude-only skill body. Move it to .agents/skills/<name>/SKILL.md so Codex, Grok, and Antigravity can read it, then run sync.",
                )
    return findings


def is_rule_file(path: Path, folder: str) -> bool:
    if path.suffix != ".md" or path.name in {"AGENTS.md", "GEMINI.md", "SKILL.md"}:
        return False
    current = path.parent
    while current != current.parent:
        if current.name == "rules" and current.parent.name == folder:
            return True
        if current.name == folder:
            return False
        current = current.parent
    return False


def chain_bytes(root: Path, agents: Path) -> int:
    directories = [agents.parent]
    current = agents.parent
    while current != root and root in current.parents:
        current = current.parent
        directories.append(current)
    directories.reverse()
    total = 0
    pieces = 0
    for directory in directories:
        candidate = directory / "AGENTS.md"
        if candidate.is_file():
            total += len(read_text(candidate).encode("utf-8"))
            pieces += 1
    if pieces > 1:
        total += (pieces - 1) * 2
    return total


def write_if_changed(path: Path, text: str) -> str:
    if path.is_file() and read_text(path) == text:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "wrote"


def sync(root: Path) -> int:
    actions: list[str] = []
    expected_stubs: set[Path] = set()
    expected_mirrors: set[Path] = set()

    for skill in skill_files(root):
        name, description = skill_meta(skill)
        if not name or not description or "\n" in description or len(description) > DESCRIPTION_BUDGET:
            print(
                f"error {rel(root, skill)}: need a single-line name and description of at most {DESCRIPTION_BUDGET} characters before sync",
                file=sys.stderr,
            )
            return 1
        target = rel(root, skill)
        _frontmatter, body = split_frontmatter(read_text(skill))
        mirror = root / ".claude" / "skills" / skill.parent.name / "SKILL.md"
        expected_stubs.add(mirror.resolve())
        previous = read_text(mirror) if mirror.is_file() else ""
        previous_body = split_frontmatter(previous)[1] if previous else ""
        generated = (
            not previous
            or strip_marker(previous_body, STUB_PREFIX)[0] is not None
            or strip_marker(previous_body, SKILL_MIRROR_PREFIX)[0] is not None
        )
        if previous and not generated:
            actions.append(f"skipped {rel(root, mirror)} (not a generated mirror)")
            continue
        text = render_skill_mirror(
            name,
            description,
            target,
            existing_paths_block(previous) if previous else None,
            body,
        )
        actions.append(f"{write_if_changed(mirror, text)} {rel(root, mirror)}")

    for agents in agents_files(root):
        if agents.parent == root:
            continue
        source_rel = rel(root, agents)
        directory = agents.parent.relative_to(root).as_posix()
        title = first_heading(read_text(agents)) or "目录规则"
        description = " ".join(
            f"{title}。与 {directory}/AGENTS.md 相同；那份文件已在上下文中时不要再读这一份。".split()
        )
        mirror = root / ".agents" / "rules" / f"{slug_for(root, agents)}.md"
        expected_mirrors.add(mirror.resolve())
        if mirror.is_file():
            existing_body = split_frontmatter(read_text(mirror))[1]
            if strip_marker(existing_body, MIRROR_PREFIX)[0] is None:
                actions.append(f"skipped {rel(root, mirror)} (not a generated mirror)")
                continue
        text = render_mirror(source_rel, description, read_text(agents))
        actions.append(f"{write_if_changed(mirror, text)} {rel(root, mirror)}")

    for path in walk_files(root):
        if path.name != "SKILL.md":
            continue
        if path.parent.parent != root / ".claude" / "skills":
            continue
        if path.resolve() in expected_stubs:
            continue
        _frontmatter, body = split_frontmatter(read_text(path))
        if (
            strip_marker(body, STUB_PREFIX)[0] is None
            and strip_marker(body, SKILL_MIRROR_PREFIX)[0] is None
        ):
            continue
        path.unlink()
        actions.append(f"removed {rel(root, path)}")

    rules_dir = root / ".agents" / "rules"
    if rules_dir.is_dir():
        for path in sorted(rules_dir.glob("*.md")):
            if path.resolve() in expected_mirrors:
                continue
            _frontmatter, body = split_frontmatter(read_text(path))
            if strip_marker(body, MIRROR_PREFIX)[0] is None:
                continue
            path.unlink()
            actions.append(f"removed {rel(root, path)}")

    if not actions:
        print("nothing to sync")
    else:
        print("\n".join(actions))
    return 0


def print_findings(root: Path, findings: list[Finding]) -> int:
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity == "warning"]
    print(f"root: {root}")
    print(f"errors: {len(errors)}")
    print(f"warnings: {len(warnings)}")
    for item in findings:
        label = item.severity.upper()
        print(f"\n{label} {item.code} {item.path}")
        print(f"  {item.message}")
    return 1 if errors else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Audit or sync a progressive-disclosure layout.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "sync"):
        command = sub.add_parser(name)
        command.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    if args.command == "audit":
        return print_findings(root, audit(root))
    return sync(root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
