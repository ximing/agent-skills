---
name: progressive-disclosure
description: 把目标项目改造成 Codex、Claude Code、Grok、Antigravity 都能渐进式加载的指令布局。用户提到渐进式展开、渐进式加载、渐进式披露、拆分 AGENTS.md、拆分 CLAUDE.md、按目录下沉规则、让 coding agent 按需加载 skill 和规则、或要改造仓库以同时支持这四个工具时使用。默认直接改目标仓库。
---

# 渐进式展开

把目标仓库收成一份正文，让 Codex、Claude Code、Grok、Antigravity 各自用自己的懒加载入口去读它。

改任何文件之前，先读本技能目录里的两份参考，不要凭记忆重写加载规则：

- `references/loaders.md`：四个工具实际加载什么、何时加载、尺寸上限
- `references/layout.md`：目标布局、正文放哪、模板、同步脚本

加载事实只以 `references/loaders.md` 为准。文件该怎么写只以 `references/layout.md` 为准。

## 边界

本技能负责目标仓库里的指令文件和项目级 skill：发现、分类、改写、同步、审计。

本技能不负责：

- 用户主目录里的个人配置（`~/.codex`、`~/.claude`、`~/.grok`、`~/.gemini`）
- 业务代码、ADR、与指令无关的重构
- 给每个目录机械生成一份规则

目标仓库是用户点名的路径。用户没点名时，用当前工作区里要改造的那个项目，而不是本技能所在的 `agent-skills` 仓库。

## 模式

按用户的说法选一种。没说明时用改造。

### 改造

新仓库初始化，或已有 `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` 需要收成渐进式布局。盘点后直接改文件。

### 审计

只报告问题，不写文件。

### 同步

正文已经在 `AGENTS.md` 和 `.agents/skills/*/SKILL.md` 里。只再生 Claude 副本和 Antigravity 的目录镜像。

## 改造步骤

### 1. 盘点

在目标仓库运行：

```bash
python3 <skill-dir>/scripts/progressive.py audit --root <repo>
```

同时自己看目录职责：现有指令文件、稳定子系统、共享目录、测试与文档是横切还是目录内聚。`<skill-dir>` 是本 `SKILL.md` 所在目录。

列出 `{ path, kind, action, reason }`。`kind` 只用这四类：`baseline`、`directory`、`glob`、`procedure`。

### 2. 分类

用 `references/layout.md` 的门槛和决策表分类。判断不清就不要新建文件。

- 仓库级、每次开工都要成立的短约束 → 根 `AGENTS.md`
- 只在某个稳定子树里成立的约束 → 该目录的 `AGENTS.md`
- 跨目录、但能用文件模式描述的短约束 → 一对规则文件
- 多步流程、检查单、只在某类任务里需要的长说明 → `.agents/skills/<name>/`

子目录规则只补充父级，不重写父级，也不把父级整段再抄一遍。

下面这些 `SKILL.md` 不是项目技能。不要搬进 `.agents/skills/`，也不要为它们生成 Claude 副本：

- 测试夹具，路径里有 `fixtures`
- 仓库作为产品发给用户的技能包。正文是在操作这个产品，而不是在教人改这个仓库；frontmatter 里若有 `disable-model-invocation` 或 `user-invocable`，更要留在原处

### 3. 写正文

按 `references/layout.md` 的模板写。共享正文只放在：

- 根和子目录的 `AGENTS.md`
- `.agents/skills/<name>/SKILL.md`
- 成对的 glob 规则（`.claude/rules/<topic>.md` 与 `.agents/rules/<topic>.md` 正文相同）

已经有 `CLAUDE.md` 或 `GEMINI.md` 时，把仍然有效的句子并进对应的 `AGENTS.md`，然后删掉重复文件。只在某一侧出现的句子保留进 `AGENTS.md`，不要丢掉。

写进 `AGENTS.md` 的命令必须和你引用的 `package.json`、脚本或 CI 步骤一致，包括参数。某一步排除了文件、加了环境或限定了路径时，不要写成不带这些参数的同一条命令。

### 4. 同步镜像

```bash
python3 <skill-dir>/scripts/progressive.py sync --root <repo>
```

脚本只重生带标记的 Claude 副本和 Antigravity 目录镜像。没有标记的手写文件它会跳过。同步之后不要手改带 `progressive-disclosure:` 标记的文件；要改就改它指向的正文，再跑一次同步。仓库根会话必须遵守的约束留在根 `AGENTS.md`，不要放进子目录文件。

### 5. 再审计

再跑一次 `audit`。error 要清掉。warning 可以留下，但汇报里要写明为什么留下，例如某条 glob 规则必须让 Claude 命中，所以接受 Grok 在会话开始时加载这几行。

## 审计步骤

只运行 `audit`。按脚本输出说明每条 error 和 warning 对应布局上的哪条规则。不要在审计模式里改文件。

## 同步步骤

确认正文已经写在 `AGENTS.md` 和 `.agents/skills/*/SKILL.md` 之后运行 `sync`，再运行 `audit`。

## 何时停下来问

目录职责能从现有结构和文档看出来时，直接写。只有下面两种情况先问：

- 两份现存文档对同一件事给出相反约束，而且无法从代码判断哪边仍然有效
- 要删除的文件里有无法归进 `AGENTS.md` 或 skill 的独有内容

## 汇报

改造或同步结束后说明：

1. 用了哪种模式，目标仓库是哪个
2. 新的布局：哪些文件是正文，哪些是脚本生成的镜像
3. 每个新建目录规则为什么过了门槛
4. 故意没建规则的区域
5. 审计里留下的 warning
6. 没在四个工具里实际开会话验证。可选的人工核对命令写在 `references/loaders.md` 末尾
