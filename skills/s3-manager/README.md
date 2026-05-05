# s3-manager

这个 skill 用来指导 agent 管理 S3 或兼容 S3 的对象存储，不再只是上传文件，而是提供完整的对象管理能力。

支持两套配置同时存在：
- `public`：公开桶，适合返回直链、公开资源、静态文件
- `private`：私有桶，适合内部文件、敏感文档、需要签名链接的对象

所有环境变量都必须以 `AS_` 开头。

## 能力范围

这个 skill 当前支持：
- 上传或覆盖对象
- 列出对象和目录前缀
- 查询对象元信息
- 生成预览链接或下载链接
- 下载对象到本地
- 删除对象
- 复制对象
- 移动或重命名对象
- 更新对象 metadata
- 自动准备 `uv` 运行环境并安装依赖

## 目录结构

```text
skills/s3-manager/
├── SKILL.md
├── README.md
├── evals/
│   └── evals.json
└── scripts/
    └── s3_manager.py
```

## 依赖

需要 Python 3。

这个 skill 现在走 `uv` 管理运行环境，并且尽量做到拿来即用：

- 如果本机没有 `uv`，脚本会自动安装用户级 `uv`
- 如果 `skills/s3-manager/.venv` 不存在，脚本会自动创建它
- 如果 `.venv` 里没有 `boto3`，脚本会自动安装

也就是说，正常情况下你不需要手动先执行 `pip install boto3`。

自动安装依赖时需要：
- 当前机器可以访问外网下载安装 `uv` 和 Python 包
- 系统里有 `curl`

如果你仍然想手动准备环境，也可以执行：

```bash
uv venv skills/s3-manager/.venv
uv pip install --python skills/s3-manager/.venv/bin/python boto3
```

## 环境变量

### 公共桶配置

- `AS_PUBLIC_BUCKET`
- `AS_PUBLIC_ACCESS_KEY_ID`
- `AS_PUBLIC_SECRET_ACCESS_KEY`
- `AS_PUBLIC_REGION`，可选，默认 `us-east-1`
- `AS_PUBLIC_HOST`，可选，自定义 S3 Host
- `AS_PUBLIC_ENDPOINT_URL`，可选，和 `AS_PUBLIC_HOST` 二选一即可
- `AS_PUBLIC_SESSION_TOKEN`，可选，临时凭证时使用
- `AS_PUBLIC_PREFIX`，可选，上传或管理时自动加到对象 key 前面
- `AS_PUBLIC_BASE_URL`，可选，用于生成最终访问链接，比如 CDN 域名
- `AS_PUBLIC_ACL`，可选，比如 `public-read`
- `AS_PUBLIC_FORCE_PATH_STYLE`，可选，`true`/`false`，适合 MinIO 等场景
- `AS_PUBLIC_SIGNED_URL_EXPIRES`，可选；通常公开桶不会用到签名链接

### 私有桶配置

- `AS_PRIVATE_BUCKET`
- `AS_PRIVATE_ACCESS_KEY_ID`
- `AS_PRIVATE_SECRET_ACCESS_KEY`
- `AS_PRIVATE_REGION`，可选，默认 `us-east-1`
- `AS_PRIVATE_HOST`，可选，自定义 S3 Host
- `AS_PRIVATE_ENDPOINT_URL`，可选，和 `AS_PRIVATE_HOST` 二选一即可
- `AS_PRIVATE_SESSION_TOKEN`，可选，临时凭证时使用
- `AS_PRIVATE_PREFIX`，可选，上传或管理时自动加到对象 key 前面
- `AS_PRIVATE_BASE_URL`，可选，对私有桶一般不是必须
- `AS_PRIVATE_ACL`，可选
- `AS_PRIVATE_FORCE_PATH_STYLE`，可选，`true`/`false`
- `AS_PRIVATE_SIGNED_URL_EXPIRES`，可选，私有访问链接有效期，单位秒，默认 `259200`（3 天）

### 通用配置

- `AS_DEFAULT_TARGET`，可选，取值为 `public` 或 `private`，当命令使用 `auto` 时采用该值

## 推荐配置示例

```bash
export AS_PUBLIC_BUCKET="public-assets"
export AS_PUBLIC_ACCESS_KEY_ID="your-public-key"
export AS_PUBLIC_SECRET_ACCESS_KEY="your-public-secret"
export AS_PUBLIC_REGION="us-east-1"
export AS_PUBLIC_HOST="https://s3.example.com"
export AS_PUBLIC_PREFIX="uploads/public"
export AS_PUBLIC_BASE_URL="https://cdn.example.com"
export AS_PUBLIC_ACL="public-read"
export AS_PUBLIC_FORCE_PATH_STYLE="true"

export AS_PRIVATE_BUCKET="private-assets"
export AS_PRIVATE_ACCESS_KEY_ID="your-private-key"
export AS_PRIVATE_SECRET_ACCESS_KEY="your-private-secret"
export AS_PRIVATE_REGION="us-east-1"
export AS_PRIVATE_HOST="https://s3.example.com"
export AS_PRIVATE_PREFIX="uploads/private"
export AS_PRIVATE_FORCE_PATH_STYLE="true"
export AS_PRIVATE_SIGNED_URL_EXPIRES="259200"

export AS_DEFAULT_TARGET="private"
```

## 命令概览

脚本入口：

```bash
python3 skills/s3-manager/scripts/s3_manager.py <command> [...flags]
```

支持的命令：
- `ensure-runtime`：准备 `uv` 和 `.venv` 运行环境
- `put`：上传或覆盖对象
- `list`：列出对象
- `stat`：查看对象元信息
- `url`：生成预览链接或下载链接
- `download`：下载对象到本地
- `delete`：删除对象
- `copy`：复制对象
- `move`：移动或重命名对象
- `set-metadata`：更新 metadata

## 使用示例

### 1. 预热运行环境

```bash
python3 skills/s3-manager/scripts/s3_manager.py ensure-runtime
```

行为：
- 自动安装 `uv`（如果缺失）
- 创建 `skills/s3-manager/.venv`
- 安装 `boto3`

### 2. 上传到公开桶

```bash
python3 skills/s3-manager/scripts/s3_manager.py put \
  --target public \
  --file "/absolute/path/to/file.png" \
  --key "images/file.png"
```

行为：
- 首次真实操作时，如有需要会自动安装 `uv`、创建 `.venv`、安装 `boto3`
- 上传到 public 配置对应的桶
- 返回可直接访问的公开链接

### 3. 上传到私有桶

```bash
python3 skills/s3-manager/scripts/s3_manager.py put \
  --target private \
  --file "/absolute/path/to/report.pdf" \
  --key "reports/report.pdf"
```

行为：
- 上传到 private 配置对应的桶
- 返回签名访问链接
- 默认有效期为 3 天

### 4. 列出某个目录下的对象

```bash
python3 skills/s3-manager/scripts/s3_manager.py list \
  --target private \
  --prefix "reports/2026/" \
  --delimiter "/" \
  --limit 50
```

### 5. 查询对象详情

```bash
python3 skills/s3-manager/scripts/s3_manager.py stat \
  --target private \
  --key "reports/2026/q1.pdf"
```

### 6. 获取预览链接

```bash
python3 skills/s3-manager/scripts/s3_manager.py url \
  --target private \
  --key "reports/2026/q1.pdf" \
  --mode preview
```

### 7. 获取下载链接

```bash
python3 skills/s3-manager/scripts/s3_manager.py url \
  --target private \
  --key "reports/2026/q1.pdf" \
  --mode download \
  --filename "Q1-report.pdf"
```

### 8. 下载对象到本地

```bash
python3 skills/s3-manager/scripts/s3_manager.py download \
  --target private \
  --key "reports/2026/q1.pdf" \
  --output "/tmp/q1.pdf"
```

### 9. 删除对象

```bash
python3 skills/s3-manager/scripts/s3_manager.py delete \
  --target public \
  --key "old/file1.js" \
  --key "old/file2.js"
```

### 10. 复制对象

```bash
python3 skills/s3-manager/scripts/s3_manager.py copy \
  --source-target private \
  --source-key "reports/q1.pdf" \
  --dest-target public \
  --dest-key "shared/q1.pdf"
```

### 11. 移动或重命名对象

```bash
python3 skills/s3-manager/scripts/s3_manager.py move \
  --source-target public \
  --source-key "drafts/logo.svg" \
  --dest-key "published/logo.svg"
```

### 12. 更新 metadata

```bash
python3 skills/s3-manager/scripts/s3_manager.py set-metadata \
  --target public \
  --key "assets/app.js" \
  --metadata release=2026-05 \
  --metadata source=agent \
  --cache-control "public, max-age=86400"
```

## 返回结果说明

脚本输出 JSON，常见字段如下：

- `status`：是否成功，或部分成功
- `operation`：执行的操作名
- `target` / `source_target` / `dest_target`：使用的目标
- `bucket` / `source_bucket` / `dest_bucket`：目标桶
- `key` / `source_key`：对象 key
- `local_file` / `output_file`：本地输入或输出文件
- `s3_uri` / `source_s3_uri`：S3 URI
- `url`：最终访问链接
- `access_url`：访问链接，和 `url` 一致
- `object_url`：对象原始地址
- `access_url_type`：`direct` 或 `presigned`
- `expires_in_seconds`：私有签名链接有效期；公开对象通常为 `null`
- `metadata`：对象 metadata
- `count` / `objects`：列表操作的结果
- `deleted_keys`：删除成功的 key 列表
- `errors`：批量删除时的失败详情

## public 和 private 的差异

### public

适合：
- 图片
- 构建产物
- 可公开下载的文件
- 需要直接发链接给别人访问的资源

返回：
- 直接访问链接

### private

适合：
- 内部文档
- 敏感文件
- 仅限授权访问的对象

返回：
- 签名访问链接
- 默认有效期 3 天
- 可通过 `AS_PRIVATE_SIGNED_URL_EXPIRES` 或 `url --expires-in` 调整

## Agent 使用建议

当 agent 使用这个 skill 时，建议按下面规则选择：

- 用户明确说“公开可访问”“给别人直接打开”时，选 `public`
- 用户明确说“内部使用”“私有”“不要公开”时，选 `private`
- 用户要做对象管理动作，比如列目录、删文件、改 metadata、改名、复制、生成预览链接时，优先使用这个 skill
- 用户没有明确说明，但对象可能敏感时，优先选 `private`
- 如果用户已经指定桶类型，直接遵循用户要求

## 常见问题

### 1. 缺少环境变量

脚本会直接报错，并告诉你缺少哪些变量名。
不会输出密钥内容。

### 2. 自动安装依赖失败

优先检查：
- 机器是否能访问外网
- `curl` 是否可用
- `uv` 安装后目录是否在 PATH 中，通常是 `~/.local/bin`

如果你不想依赖自动安装，也可以先手动执行：

```bash
uv venv skills/s3-manager/.venv
uv pip install --python skills/s3-manager/.venv/bin/python boto3
```

### 3. MinIO 或其他 S3-compatible 平台操作失败

优先检查：
- `AS_<TARGET>_HOST` 或 `AS_<TARGET>_ENDPOINT_URL` 是否正确
- 是否需要设置 `AS_<TARGET>_FORCE_PATH_STYLE=true`

### 4. 返回的链接不是你想要的域名

如果你希望返回 CDN 域名或自定义域名，设置：

- `AS_PUBLIC_BASE_URL`
- 或对应 target 的 `AS_<TARGET>_BASE_URL`

### 5. 私有链接有效期要调整

例如改成 7 天：

```bash
export AS_PRIVATE_SIGNED_URL_EXPIRES="604800"
```

## 快速结论

- 公开桶：返回直链
- 私有桶：返回默认 3 天有效的签名链接
- 配置统一走 `AS_` 环境变量
- 运行环境由 `uv` 管理，缺依赖时自动安装
- 推荐直接调用 `scripts/s3_manager.py`
- 这个 skill 已支持完整对象管理能力，而不仅仅是上传
