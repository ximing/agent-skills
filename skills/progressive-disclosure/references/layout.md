# 目标布局

正文和镜像分开。带 `progressive-disclosure:` 标记的文件由 `scripts/progressive.py sync` 生成，不要手改。

```text
repo/
├── AGENTS.md                          # 正文：仓库基线
├── packages/web/AGENTS.md             # 正文：这个子树才有的约束
├── .agents/
│   ├── skills/deploy/SKILL.md         # 正文：流程
│   └── rules/
│       ├── testing.md                 # 正文：glob 约束的 Antigravity 半边
│       └── packages__web.md           # 镜像：由 packages/web/AGENTS.md 生成
└── .claude/
    ├── skills/deploy/SKILL.md         # 镜像：Claude 用的正文副本
    └── rules/testing.md               # 正文：同一条 glob 约束的 Claude 半边
```

不创建 `CLAUDE.md`、`GEMINI.md`、`AGENTS.override.md`、`.grok/rules/`、符号链接。

## 决策

| 内容 | 放哪 | 谁会懒加载 | 谁会在根会话里提前看到 |
| --- | --- | --- | --- |
| 每次开工都要成立的短约束 | 根 `AGENTS.md` | 没有。这就是基线 | 四个工具 |
| 只属于一个稳定子树、而且仓库根会话可以不带着的约束 | `<dir>/AGENTS.md` | Claude 在祖先链上没有 `CLAUDE.md` 时，读到该目录的文件才加载；Grok 读、列出或编辑该目录时加载；Antigravity 在仓库根通过 `model_decision` 镜像按描述再读 | Codex 从该目录或它的子目录启动时，这份文件在指令链里。Antigravity 把该目录当作工作区或工作区的祖先时，这份 `AGENTS.md` 始终生效，镜像不要再读一遍。反引号路径不会让 Codex 加载它 |
| 跨目录的短约束，能写成 glob | `.claude/rules/<topic>.md` 加 `.agents/rules/<topic>.md`，正文相同 | Claude 按 `paths`；Antigravity 按 `glob` | Grok 会在会话开始时加载 `.claude/rules` 里的整份文件。因此这里只留几行 |
| 多步流程或长说明 | 仓库根 `.agents/skills/<name>/SKILL.md`，同步出 Claude 副本 | 四个工具都是先看 description，用到时再读正文 | 只有 name 和 description |

## 什么目录才配 `AGENTS.md`

同时满足下面至少两条才写：

- 目录职责稳定
- 会反复被改到
- 对「文件放哪、这里怎么写」有额外约束
- 和父级相比真有增量

优先考虑独立的包、应用、服务，以及 `src/pages`、`src/components`、`src/services` 这类有放置边界的共享目录。

不写：`dist`、`build`、`coverage`、依赖目录、生成目录、一次性实验目录，以及只是在重复根规则的目录。

测试、Markdown、某类源文件这种横切约束用 glob 规则，不要给每个测试目录各写一份 `AGENTS.md`。

## 根 `AGENTS.md`

无 frontmatter。行数和字节上限见同目录的 `loaders.md`。

```markdown
# 仓库约定

## 基线

- 用具体命令写构建和测试，不写「跑一下测试」。

## 局部规则

这些目录另有约定。Codex 在仓库根不会加载它们：

- `packages/web/AGENTS.md`
```

这张清单只是地图。Codex 在仓库根必须遵守的句子留在上面的基线里。不要写成 `@packages/web/AGENTS.md`。

## 目录 `AGENTS.md`

```markdown
# packages/web

## 这个目录负责什么

- 一句职责。

## 约束

- 放什么
- 不放什么
- 私有内容应该去哪
```

第一行标题会被同步脚本写进 Antigravity 镜像的 `description`，格式是 `<标题>。与 <目录>/AGENTS.md 相同；那份文件已在上下文中时不要再读这一份。` 这样仓库根的 Antigravity 会在需要时读镜像，已经打开该目录时不会被描述推去再读一遍。

## Glob 规则

两边正文保持一致，包括标题和列表。frontmatter 各写各的。

Claude，`.claude/rules/testing.md`：

```markdown
---
paths:
  - "**/*.test.ts"
  - "**/*.spec.ts"
---

# 测试

- 测行为，不测私有函数名。
```

`paths` 相对 `.claude` 所在的目录。没有 `paths` 的文件会在 Claude 和 Grok 启动时都加载。

Antigravity，`.agents/rules/testing.md`：

```markdown
---
trigger: glob
globs: "**/*.test.ts, **/*.spec.ts"
description: "测试文件的写法。编辑测试时应用。"
---

# 测试

- 测行为，不测私有函数名。
```

模式以 `*` 开头时必须加引号。这种文件不要带同步标记；它是手写正文，不是目录镜像。

目录镜像占用 `.agents/rules/<父路径用 __ 连接>.md`，例如 `packages/web/AGENTS.md` 生成 `packages__web.md`。手写的 topic 名不要包含 `__`，避免和镜像撞名。

## Skill 正文

仓库根 `.agents/skills/<name>/SKILL.md`：

```markdown
---
name: deploy
description: 发布这个仓库的服务。用户要发版、上线或回滚时使用。
---

# 发布

1. 先看哪一个环境。
2. 跑该环境的检查命令。
3. 发布之后看健康检查。
```

`name` 用小写字母、数字和连字符，并与目录名一致。`description` 一行，不超过 500 字符，写清在什么请求下启用。

路径里有 `fixtures` 的 `SKILL.md`，以及仓库发给用户使用的产品技能，都不是项目技能。产品技能的正文是在操作这个产品，不是在教人改这个仓库，frontmatter 里还常有 `disable-model-invocation` 或 `user-invocable`。这两类留在原处，不进 `.agents/skills/`，也不生成 `.claude/skills/` 副本。

Claude 按文件类型激活时，把 `paths` 写在 `.claude/skills/<name>/SKILL.md` 的 frontmatter 里。同步保留已有的 `paths`，并把正文换成 `.agents/skills` 里的副本：

```markdown
---
name: deploy
description: 发布这个仓库的服务。用户要发版、上线或回滚时使用。
paths:
  - "deploy/**"
---
```

正文和标记由脚本重写。技能要引用旁路文件时，写 `.agents/skills/<name>/...`。

## 脚本

```bash
python3 <skill-dir>/scripts/progressive.py audit --root <repo>
python3 <skill-dir>/scripts/progressive.py sync --root <repo>
```

只依赖 Python 3 标准库。

`sync` 会：

- 为仓库根 `.agents/skills/<name>/SKILL.md` 写入正文相同的 `.claude/skills/<name>/SKILL.md`
- 为根以外的每份 `AGENTS.md` 写入 `.agents/rules/<slug>.md`，`trigger: model_decision`，正文与那份 `AGENTS.md` 相同
- 删掉标记还在、但源文件已经不在的镜像
- 跳过没有标记的同名文件，并在输出里说明

`audit` 把违规分成 error 和 warning。error 是四个工具里会漏载、双载或静默丢弃的问题。warning 是体积和「Grok 会提前加载短规则」这类需要人判断的问题。

## 从旧文件迁走

- 根或子目录 `CLAUDE.md` 与 `AGENTS.md` 重复：保留 `AGENTS.md` 里没有的句子，删除 `CLAUDE.md`。
- 只有 `CLAUDE.md`：把正文移到同目录 `AGENTS.md`，去掉 frontmatter，再删除 `CLAUDE.md`。
- `GEMINI.md`：并进 `AGENTS.md` 后删除。
- `.claude/skills/<name>/SKILL.md` 已经是一份完整技能：把正文移到 `.agents/skills/<name>/SKILL.md`，再运行 `sync` 生成带标记的副本。文件里没有生成标记时，`sync` 不会覆盖它。
