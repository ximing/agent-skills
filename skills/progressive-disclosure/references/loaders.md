# 四个工具怎么加载

核对日期：2026-11-24。改布局时以这一页为准。

来源：

- Claude Code：[Memory](https://code.claude.com/docs/en/memory)、[Skills](https://code.claude.com/docs/en/skills)
- Codex：[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Build skills](https://learn.chatgpt.com/docs/build-skills)
- Grok Build 用户指南：`08-skills.md`、`12-project-rules.md`（本机 `~/.grok/docs/user-guide/`）
- Antigravity：[Rules](https://antigravity.google/docs/rules)、[Skills](https://antigravity.google/docs/skills)、[Customization discovery](https://antigravity.google/docs/customization-discovery)

个人主目录里的文件四个工具都会加载，但本技能只改目标仓库。

## 总原则

同一段正文只放一个自动加载的位置。四个工具对「同目录另一份文件」的处理不一样：

- Codex 在每个目录只收一个文件：`AGENTS.override.md`，否则 `AGENTS.md`，否则用户自己配置的 fallback 名。不要用 fallback，那是用户机器上的 `~/.codex/config.toml`，不是仓库契约。
- Claude Code 在工作目录及其祖先里只要存在 `CLAUDE.md`、`.claude/CLAUDE.md` 或 `CLAUDE.local.md`，默认就不再直接读任何 `AGENTS.md`，包括子目录里那份（需要 Claude Code v2.1.277 或更新版本才会直接读 `AGENTS.md`）。子目录按需加载写在「祖先链上没有这些 Claude 文件」的前提下。`@AGENTS.md` 这种 import 会在加载时展开，不是懒加载，而且一份根上的 `CLAUDE.md` 会让整棵子目录 `AGENTS.md` 都走不到。
- Grok 把同一目录里认得出的文件都加载。`AGENTS.md` 和 `CLAUDE.md` 同时存在时，两份都进上下文。Claude 兼容默认开启时，每一层的 `.claude/CLAUDE.md` 和 `.claude/CLAUDE.local.md` 也算。用户指南没有写 Grok 会展开 `@path`。
- Antigravity 把找到的规则累加。同一目录的 `AGENTS.md` 和 `GEMINI.md` 会一起进入始终生效的上下文。`AGENTS.md` / `GEMINI.md` 不使用 frontmatter，全文始终生效。Grok 的文件名列表里没有 `GEMINI.md`。

因此共享正文放在 `AGENTS.md`。不要再写一份内容相同的 `CLAUDE.md` 或 `GEMINI.md`。不要提交 `AGENTS.override.md`：Codex 会用它替换同目录的 `AGENTS.md`，另外三个工具不读它。

## 目录指令：`AGENTS.md`

无 frontmatter 的 Markdown。

| 工具 | 会话开始时 | 工作目录之下的文件 | 冲突时 |
| --- | --- | --- | --- |
| Codex | 从 Git 根走到当前目录，每层最多一个文件，拼成一条指令链 | 不加载。必须在那个目录里启动 Codex 才看得到 | 离当前目录更近的文件写在后面，后写的覆盖先写的 |
| Claude Code | 当前目录和每个祖先的 `AGENTS.md`。祖先链上若有 `CLAUDE.md`、`.claude/CLAUDE.md` 或 `CLAUDE.local.md`，则改走这些 Claude 文件，不再读 `AGENTS.md` | 同样只在祖先链上没有 Claude 文件时，才在 Read 到该子目录的文件后加载那里的 `AGENTS.md` | 文件是拼接的，冲突时 Claude 可能任选一边 |
| Grok | Git 仓库里从根走到当前目录。认 `Agents.md`、`Claude.md`、`CLAUDE.md`、`CLAUDE.local.md`、`AGENT.md`、`AGENTS.md`，外加每一层的 `.claude/CLAUDE.md`、`.claude/CLAUDE.local.md`，以及 `.grok/rules/`、`.claude/rules/`、`.cursor/rules/` | 去读、列出或编辑那些目录时再发现那里的指令文件 | 更深的文件排在后面，后写的优先 |
| Antigravity | 工作区本身和每个祖先，直到仓库根：`AGENTS.md`、`GEMINI.md`，以及 `.agents/AGENTS.md`、`.agents/GEMINI.md`、`.agents/rules/*.md` | 不加载。打开仓库根时，不会因为读了 `src/` 里的文件就加载 `src/AGENTS.md` | 累加，不互相替换 |

Codex 的 AGENTS.md 文档写的是：项目指令链默认在合计 32 KiB 处停止继续追加（`project_doc_max_bytes`）。进阶配置页又把同一项写成「每个 AGENTS.md 读多少字节」，两处措辞不一致。布局按合计 32 KiB 留余量。在仓库根启动时，根文件自己就要放进这 32 KiB。

Claude 建议每份 `CLAUDE.md` 少于 200 行。启动时加载的 `CLAUDE.md` 超过 4 MiB 会被整份跳过。约 4 万字符的按需上限写的是子目录 `CLAUDE.md`、它们 `@import` 的文件、子目录 `.claude/rules/`，以及带 `paths` 的规则。文档没有把这个上限写到 `AGENTS.md` 上。

Antigravity 单文件 24,000 字节，超出会截断。全局和 `always_on` 规则共享约 20,000 token 的预算，超了会把最大的文件降级成路径加描述。`@[label](path)` 会在计算体积之前把目标文件内联进来，不能用来假装懒加载。单独的 `@filename` 只改写成路径，不内联。

Grok 不截断项目指令，文件越长越不容易被遵守。被 `.gitignore` 忽略的指令文件 Grok 会跳过，所以被忽略的 `CLAUDE.local.md` 进不了 Grok，但 Claude 仍会加载它，并且它会阻止 Claude 直接读 `AGENTS.md`。

Claude 读到的 `AGENTS.md` 同样会展开 `@path` import，被 import 的内容跟父文件一起进入上下文。共享的 `AGENTS.md` 里不要写 `@path`，也不要写 Antigravity 的 `@[label](path)`。

## 路径规则

只放短约束。长说明放 skill。

### Claude Code：`.claude/rules/*.md`

- 没有 `paths` 的规则在会话开始时加载，优先级同 `.claude/CLAUDE.md`。
- 有 `paths` 时，Claude 对匹配文件做 Read、Write、Edit，或用算作读取的 Bash（如对单个文件 `cat` / `head`）时才加载。
- `paths` 是唯一被读取的 frontmatter 字段，相对该 `.claude` 目录所在的目录。其他字段被忽略，frontmatter 不会进入正文。
- 规则可以放在子目录里，Claude 会递归发现。为了和 Grok、Antigravity 对齐，仍然只放在 `.claude/rules/` 的直接子级。

### Antigravity：`.agents/rules/*.md`

文件必须带 frontmatter，且 `trigger` 只能是 `always_on`、`model_decision`、`glob`、`manual`。缺 frontmatter、或 `trigger` 写错（包括 `alwaysOn` 这种驼峰），文件会被静默丢掉。

- `model_decision`：会话里先只有路径和 `description`，任务匹配时再读全文。`description` 必填。
- `glob`：接触到匹配文件时加载。`globs`（或 `glob`）必填，逗号分隔；以 `*` 开头的模式加引号。
- `always_on`：每次都注入全文。这种内容写进 `AGENTS.md` 即可。
- `manual`：只有 `@` 提及时加载。Antigravity CLI 不支持规则提及。

Antigravity 只扫描 `rules/` 的直接子级。`rules/frontend/react.md` 这种嵌套文件默认看不到。

### Grok 会提前加载 Claude 规则

Grok 默认扫描每一层（从仓库根到 cwd）的 `.claude/rules/*.md`，整份加载，不按 Claude 的 `paths` 做懒加载。同一份文件再放进 `.grok/rules/` 会被 Grok 加载第二次。

所以 `.claude/rules/` 里只放几行约束。长的领域说明不要放这里。`.grok/rules/` 和 `.cursor/rules/` 同样会在 Grok 会话开始时加载；本技能不主动创建它们。

### Codex 没有路径规则

Codex 不会读 `.claude/rules` 或 `.agents/rules`。在仓库根启动时，它也看不到子目录的 `AGENTS.md`。反引号里的路径不是 import，Codex 不会因此加载那个文件。Codex 在仓库根必须遵守的约束留在根 `AGENTS.md` 或仓库根 skill 里。子目录 `AGENTS.md` 只在 Codex 从那个目录启动时进入指令链。

## Skill

四个工具都是先看到 `name` 和 `description`，决定使用时才读 `SKILL.md` 正文。

| 工具 | 仓库内位置 | 根会话能不能看到子目录里的 skill |
| --- | --- | --- |
| Codex | 从 cwd 向上直到仓库根的 `.agents/skills/<name>/SKILL.md`。同名不合并，两处都会出现 | 看不到 cwd 之下的 |
| Claude Code | `.claude/skills/<name>/SKILL.md`，含祖先目录。cwd 之下的要等 Claude 读到那个子目录里的文件才进入列表 | 懒加载，但启动时不在列表里 |
| Grok | 从 cwd 向上，每一层的 `.grok/skills/`、`.agents/skills/`、`.claude/skills/`、`.cursor/skills/`。同名保留优先级更高的一处 | 文档只写了向上扫描 |
| Antigravity | 工作区和祖先的 `.agents/skills/<name>/SKILL.md`。也认旧的 `.agent/skills/`。只扫 `skills/` 的直接子级 | 看不到工作区之下的 |

因此要在仓库根打开也能用的 skill，放在仓库根的 `.agents/skills/<name>/`，不要塞进包目录的下一级。

共享 `SKILL.md` 的 frontmatter 只写 Agent Skills 规范字段，默认只有单行 `name` 和单行 `description`。Codex 要求 `description` 非空、单行、不超过 500 字符。不要在共享文件里写 Claude 专属字段（`paths`、`disable-model-invocation`、`context`）或 `` !`command` ``。Claude Code 会忽略自己不认识的字段，但会执行它认识的那些专属字段。Codex 忽略多余字段。把 skill 打包上传到 Claude 时，规范之外的字段会直接报错。`` !`command` `` 在 Claude 里会执行，在 Grok 里是字面量。Codex 和 Antigravity 的文档没有写它们会执行这种语法。

Claude 不扫描 `.agents/skills/`。同步脚本把同一份正文复制到 `.claude/skills/<name>/SKILL.md`，Claude 加载的就是这份副本，不是一句「请去读另一个文件」。需要 Claude 按文件类型激活时，把 `paths` 写在这份副本的 frontmatter 上，同步会保留它。副本不复制 `scripts/` 或其他旁路文件。正文里要引用这些文件时，写仓库路径 `.agents/skills/<name>/...`，不要写 `${CLAUDE_SKILL_DIR}`。

Grok 的发现顺序是 `.grok/`、`.agents/`、`.claude/`、`.cursor/`，同名保留优先级更高的一处。按这个顺序，同一层的 `.agents/skills` 会盖过 `.claude/skills`，Grok 用正文那份，不把副本再注入一次。这个顺序是文档列出的优先级，不是一份专门对比这两处的例子。Grok 注入 skill 正文时最多 100,000 字节，超出的部分从最后一行整行截掉。项目指令文件没有这个上限。

Antigravity 的个人 skill 在 `~/.gemini/config/skills/`。CLI 还会读另外两个只属于 CLI 的目录。这些都不进仓库。

## 不要依赖的机制

- 用 `@path` 或符号链接把大文件收进根指令：Claude 会在启动时展开 import；Windows 上 Git 往往把符号链接检出成普通文本。
- 根上放一份只含 `@AGENTS.md` 的 `CLAUDE.md` 来迁就读不到 `AGENTS.md` 的 Claude 会话（v2.1.277 之前、内置插件被关掉、从 v2.1.276 或更早升级后的第一次会话，以及 v2.1.281 之前的部分 Bedrock 会话）。这份文件会挡住所有子目录 `AGENTS.md`。那些会话要覆盖子目录规则时，不能用这个布局。
- `AGENTS.override.md`、`GEMINI.md`、`.agents/AGENTS.md`、`.claude/AGENTS.md`，以及 `Agents.md`、`AGENT.md`、`Claude.md` 这种别名。Grok 会把认得出的别名和 `AGENTS.md` 一起加载。Claude 会加载 `.claude/AGENTS.md`。Codex 不读这些路径。
- 用户级 `project_doc_fallback_filenames`：只影响那台机器上的 Codex。
- 把流程写进根 `AGENTS.md`：四个工具每次会话都要带着它。

## 可选的人工核对

脚本审计不能代替产品里的加载结果。需要时：

- Claude Code：`/context all` 看启动时的 Memory files。子目录 `CLAUDE.md` 的 Loaded 行不能直接当成子目录 `AGENTS.md` 的说明。v2.1.280 之前，直接读到的 `AGENTS.md` 不会出现在 `/memory` 和 `/context` 里。
- Codex：在目标目录新开一次会话，让它列已加载的指令文件。指令链在每次启动时重建。
- Grok：`grok inspect` 列出规则文件和 skill。
- Antigravity：设置里的 Customizations，或 CLI 的 `/skills`。规则和 skill 在下一轮对话前会重读。
