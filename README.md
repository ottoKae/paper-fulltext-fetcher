# Paper Fulltext Fetcher

一个侧重论文全文下载的 Codex Skill：从 Excel/CSV 书目出发，合法、低频、保护隐私地发现、下载、导入、验证和审计论文 PDF 或全文 XML。

它不是付费墙绕过器，也不会自动处理账号密码、验证码、CAPTCHA、Cloudflare 或访问暂停。

## 使用场景

这个 Skill 适合：

- 系统综述、Meta-analysis 或专题数据库需要从 DOI/题名清单补齐全文；
- 已经下载一部分论文，希望跳过现有文件并从断点继续；
- 同时使用开放获取、出版社 API/TDM、校园网订阅和人工下载；
- 需要区分“无 OA”“学校未订阅”“API 未授权”“被限流”和“文件身份错误”；
- 需要把人工下载的 PDF 安全匹配回书目，而不是直接复制和猜测文件名；
- 需要统计 PDF/XML 覆盖率、出版社分布和未获得原因；
- 希望将下载器发布到 GitHub，同时避免泄露开发者和使用者隐私。

这个 Skill 不适合：

- 绕过付费墙、验证码、WAF 或访问暂停；
- 对出版社网站进行高并发爬取；
- 未经许可使用机构账号批量下载；
- 将受版权保护的全文重新公开分发。

## 能做什么

- 检查本地 PDF/XML 库并跳过已经验证的记录；
- 规范化 DOI、标题、出版社和预期文件名；
- 为 Unpaywall、OpenAlex、Crossref 和机构知识库生成开放获取候选；
- 区分普通网页访问、CARSI 机构认证和出版社 TDM/API 权限；
- 生成出版社队列、人工下载队列和可点击 HTML；
- 对人工下载文件执行 PDF 容器、DOI/标题、哈希和重复检查；
- 为扫描型 PDF 保留独立的视觉审批证据；
- 输出可恢复事件日志、出版社覆盖率和失败原因；
- 在上传 GitHub 前扫描个人路径、密钥、Cookie、全文和运行日志风险。

## 不做什么

- 不绕过订阅、登录或机器人防护；
- 不自动填写学校账号和验证码；
- 不导出 Cookie、浏览器 Profile 或代理订阅；
- 不把网页人工阅读权限解释为批量下载权限；
- 不在出现 `403/418/429`、挑战页或访问暂停后继续高频重试；
- 不保证所有论文都能自动取得。

## 运行环境

| 项目 | 支持情况 |
|---|---|
| Python | 3.11 或更高版本 |
| Windows | 支持；示例使用 PowerShell 与 `py -3` |
| macOS/Linux | 支持核心 CLI；使用 `python3` |
| 输入书目 | CSV、XLSX、XLSM |
| 全文 | PDF、全文 XML |
| 浏览器 | 核心 CLI 不依赖浏览器；机构登录仍由用户人工完成 |
| 网络 | 离线命令无需网络；OA 发现和下载必须显式调用 |

依赖只有：

- `openpyxl`：读取 Excel；
- `pypdf`：解析并验证 PDF。

## 安装

### 使用 Codex Skill Installer（推荐）

在 Codex CLI 或 IDE 扩展的新对话中输入：

```text
$skill-installer 请从 https://github.com/ottoKae/paper-fulltext-fetcher 的仓库根目录安装 paper-fulltext-fetcher。
```

安装完成后，在下一轮对话中使用 `$paper-fulltext-fetcher` 显式调用。Codex 通常会自动发现新安装的 Skill；若 `/skills` 中没有出现，请重启 Codex。

也可以把本仓库目录放在项目级 `.agents/skills/paper-fulltext-fetcher` 或用户级 `.agents/skills/paper-fulltext-fetcher` 中。

### Windows PowerShell

```powershell
& .\scripts\bootstrap.ps1
$Fetcher = '.\scripts\run.ps1'
```

### macOS/Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

`bootstrap.ps1` 只在本 Skill 目录创建私有 `.venv`，不会修改系统 Python，也不会读取或写入论文下载凭据。再次运行时，如果依赖已经齐全，它会直接跳过安装。

## 30 秒离线自检

自检只使用临时目录和合成数据，不读取真实书目、论文或凭据，也不会联网。

Windows：

```powershell
& $Fetcher self-test
```

macOS/Linux：

```bash
python scripts/paper_fulltext_fetcher.py self-test
```

看到 `"passed": true` 才继续。然后检查 Python、依赖、配置路径和凭据是否存在：

```powershell
& $Fetcher doctor
```

`doctor` 不测试网络，不显示凭据值。它分别报告：

- `environment_ready`：Python、openpyxl 和 pypdf 是否就绪；
- `project_ready`：本地书目和工作目录是否存在；
- `credentials`：只报告对应环境变量为 `true/false`。

## 5 分钟快速开始

### 1. 初始化项目工作区

下面会创建本地配置和四个工作目录，不会写入密钥，也不会覆盖已有论文：

```powershell
& $Fetcher init `
  --workspace .\my-review `
  --input bibliography.xlsx
```

生成：

```text
my-review/
├── acquisition.local.toml
├── .gitignore
├── papers_pdf/
├── papers_xml/
├── manual_pdf_inbox/
└── outputs/acquisition/
```

如果工作区已有 `.gitignore`，初始化器不会修改它；请自行加入全文、书目、日志和配置排除规则。

将自己的 Excel 复制为 `my-review/bibliography.xlsx`。如果使用 CSV，在初始化时改成 `--input bibliography.csv`。

macOS/Linux 使用相同子命令，把 `& $Fetcher` 替换为 `.venv/bin/python scripts/paper_fulltext_fetcher.py`，并把路径分隔符改为 `/`。

### 2. 检查项目环境

```powershell
& $Fetcher doctor `
  --config .\my-review\acquisition.local.toml
```

### 3. 检查书目兼容性

```powershell
& $Fetcher inspect-input `
  --config .\my-review\acquisition.local.toml
```

该命令只输出记录数、列映射、DOI 覆盖率和工作表信息，不显示论文题名、DOI 值或作者名单。`ready_for_audit=true` 表示可以继续。

### 4. 审计已有全文

```powershell
& $Fetcher audit `
  --config .\my-review\acquisition.local.toml
```

主要输出：

- `outputs/acquisition/audit/summary.json`：总体覆盖率；
- `outputs/acquisition/audit/records.csv`：逐条状态；
- `outputs/acquisition/audit/missing.csv`：尚缺全文；
- `outputs/acquisition/audit/publisher_coverage.csv`：出版社覆盖率；
- `outputs/acquisition/audit/anomalies.csv`：孤立、损坏或重复文件。

### 5. 根据需求继续

| 用户需求 | 下一条命令 |
|---|---|
| 发现开放获取版本 | `discover-oa --config ... --limit 1` |
| 下载已审核 OA/API 地址 | `fetch-verified --config ...`，复核后加 `--execute` |
| 准备人工下载 | `manual-queue --config ...` |
| 导入人工 PDF | `import --config ... --dry-run` |
| 新增文件后更新统计 | 再次运行 `audit --config ...` |
| 上传 GitHub 前检查 | `privacy-scan --path .` |

## 适配不同书目格式

默认识别常见列名，例如：

- 标题：`Title`、`Article Title`、`Document Title`；
- DOI：`DOI`、`Digital Object Identifier`；
- 年份：`Year`、`Publication Year`；
- 期刊：`Source Title`、`Journal`、`Publication Name`；
- 出版社：`Publisher`。

每条记录至少需要标题或 DOI 之一；只有 DOI 的清单也可以运行。为了提高人工检索和错误文件识别能力，仍建议同时提供标题、DOI、年份和期刊。

Excel 默认读取活动工作表。指定其他工作表：

```powershell
& $Fetcher inspect-input `
  --config .\my-review\acquisition.local.toml `
  --sheet Records
```

自定义列名使用可重复的 `--column canonical=source_header`：

```powershell
& $Fetcher inspect-input `
  --config .\my-review\acquisition.local.toml `
  --column 'title=Research Name' `
  --column 'doi=Persistent Identifier' `
  --column 'year=Release Year'
```

确认后可以把映射写入私有的 `acquisition.local.toml`：

```toml
[project]
sheet = "Records"

[columns]
title = "Research Name"
doi = "Persistent Identifier"
year = "Release Year"
publisher = "Publisher Name"
```

不要把含个人路径或真实书目信息的 `acquisition.local.toml` 上传 GitHub。

## 人工下载与导入

生成可点击的人工下载队列：

```powershell
& $Fetcher manual-queue `
  --config .\my-review\acquisition.local.toml
```

将人工取得的 PDF 放入 `manual_pdf_inbox`，先 dry-run：

```powershell
& $Fetcher import `
  --config .\my-review\acquisition.local.toml `
  --dry-run
```

确认匹配结果后移除 `--dry-run`。导入器不会删除 inbox 原文件；无法提取文字的扫描型 PDF 会要求单独的视觉审批证据。

## 开放获取发现

凭据只通过环境变量提供：

```powershell
$env:UNPAYWALL_EMAIL = 'researcher@example.edu'
$env:OPENALEX_API_KEY = '<key>'
```

先测试一条：

```powershell
& $Fetcher discover-oa `
  --config .\my-review\acquisition.local.toml `
  --limit 1 `
  --delay 5
```

该命令只发现候选，不会自动下载全文。候选经人工或规则审核后，才可以放入 `fetch-verified` manifest。

## 下载经过审核的全文

打开 `outputs\oa_candidates.csv`，核对 DOI、标题、来源、许可线索和目标域名，只把确认可以合法下载的记录改为：

```csv
approved,approval_scope
true,open_access
```

第一次运行仍然是 dry-run：

```powershell
& $Fetcher fetch-verified `
  --config .\my-review\acquisition.local.toml `
  --allow-host repo.example.edu `
  --limit 1
```

确认计划中只有预期主机和文件后，显式增加 `--execute`：

```powershell
& $Fetcher fetch-verified `
  --config .\my-review\acquisition.local.toml `
  --allow-host repo.example.edu `
  --delay 10 `
  --limit 1 `
  --execute
```

下载器会：

- 只处理 `approved=true` 的记录；
- 只连接显式 `--allow-host` 中的公网主机；
- 拒绝 localhost、私网和保留地址；
- 检查跳转后的域名，拒绝跳转到未允许主机；
- 对 `403/418/429` 和连续失败自动熔断；
- 先写 `.part`，验证 PDF/XML 身份后再原子移动；
- 已存在文件自动跳过；
- 不携带浏览器 Cookie 或机构会话。

出版社订阅全文应优先使用已获批的官方 API/TDM，或由用户人工完成机构下载后使用 `import`；不要把带登录态的网页 URL 直接塞进这个命令。

## 常见问题

### `python` 或 `py` 找不到

安装 Python 3.11+，然后重新打开终端。Windows 可运行 `py -0p` 查看解释器；macOS/Linux 可运行 `python3 --version`。

### `ModuleNotFoundError: openpyxl` 或 `pypdf`

当前终端没有使用安装依赖的虚拟环境。直接调用虚拟环境解释器：

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\scripts\bootstrap.ps1
& .\scripts\run.ps1 self-test
```

### `environment_ready=true`，但 `project_ready=false`

程序环境正常，但书目文件或工作目录尚未就绪。先运行 `init`，再把书目复制到配置指定位置。

### `ready_for_audit=false`

通常是部分记录同时缺少标题和 DOI，或相关列没有被识别。运行 `inspect-input --sheet ... --column title=... --column doi=...`，确认后把设置写入私有 TOML。

### 找不到 Excel 工作表

`inspect-input` 会列出 `available_sheets`。使用完全一致的工作表名称；名称包含空格时加引号。

### 审计把所有论文都标记为 missing

检查 PDF/XML 是否放在配置目录。已有文件若没有标准文件名，程序会尝试 DOI/标题文本匹配；扫描型 PDF 没有可提取文字，需要视觉审批事件。

### `fetch-verified` 显示 0 条 approved records

候选 CSV 必须同时满足：

- `approved=true`；
- `approval_scope` 为 `open_access`、`institutional_repository` 或 `official_api`。

### `host_not_allowed` 或 `redirect_host_not_allowed`

把已经人工确认的实际公网域名通过可重复的 `--allow-host` 加入。不要允许 `localhost`、私网地址或不认识的跳转域名。

### HTTP 403、418、429 或挑战页

下载器会熔断。这不是提高并发或换 IP 的理由；应检查订阅/API 权限，或转人工、图书馆和作者渠道。

### Doctor 为什么不测试网络

这是隐私和安全设计。`doctor` 只检查本地环境；联网只发生在用户显式运行 `discover-oa` 或 `fetch-verified --execute` 时。

## 退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 命令完成，或 dry-run 正常 |
| 2 | 配置、依赖、输入或身份验证问题 |
| 3 | 隐私风险命中或网络熔断 |
| 130 | 用户中断；已有事件日志保留 |

## CARSI 与 TDM

CARSI 证明您是学校的合法用户，可以人工访问学校订购内容。TDM/API 权限证明程序可以按照出版社规则批量获取或分析内容。二者独立：网页显示机构访问，不表示 Python API 已获授权。

Elsevier Developer Portal 的 Key 名称和 CORS 配置不会自动赋予 Article Retrieval 或 Journals Fetch/DaaS 权限。Wiley 等出版社也可能要求单独的 TDM Token。

详细说明见：

- [完整工作流](references/workflow.md)
- [校园网、Clash、CARSI 与 TDM](references/network-and-auth.md)
- [出版社路线](references/providers.md)
- [状态与日志](references/status-and-logs.md)
- [人工导入](references/manual-import.md)
- [隐私与发布](references/privacy-and-publication.md)

## Clash Rule 模式

典型目标是：

- Codex/OpenAI 域名走代理策略组；
- 学校、CARSI 和依赖校园 IP 的出版社域名走 `DIRECT`；
- 个别不依赖机构 IP 且直连不可达的服务按需代理；
- 出版社 API 主机必须单独验证路由和 entitlement；
- 规则位于最终兜底规则之前。

Helper 首版只检查和生成建议，不自动覆盖 Clash 配置，也不会读取或输出节点密码与订阅 URL。

## 安全默认值

- 全局并发和同域名并发均为 1；
- OA/API 默认每域名至少间隔 5 秒；
- 浏览器辅助建议随机间隔 60–90 秒；
- 先一篇 smoke，再 3–5 篇 pilot，然后才进入小批次；
- 连续两次失败或出现 `403/418/429`、挑战页、访问暂停时停止；
- 所有成功文件先写临时文件，验证后再原子化进入语料目录。

## 隐私安全

### 使用者隐私

- `doctor`、`audit`、`manual-queue`、`import --dry-run` 和 `privacy-scan` 默认不联网；
- `discover-oa` 会把目标 DOI 发送给所选 OA 服务，并把联系邮箱发送给 Unpaywall；
- `fetch-verified --execute` 只连接人工批准且通过 `--allow-host` 明确允许的主机；
- 项目不包含遥测、崩溃上报、使用分析或后台网络请求；
- 凭据只从环境变量读取，日志只记录“是否配置”，不会记录实际值；
- URL 日志默认删除 query 和 fragment，避免泄露签名参数；
- 审计和事件日志只保存相对路径或文件名，不保存开发者的项目绝对路径；
- 运行结果仅保存在用户指定的本地目录。

### 开发者隐私

- 源码、测试和示例不得包含开发者姓名、邮箱、用户名和本机绝对路径；
- 测试只能使用合成书目、`example.edu`、合成 DOI 和临时目录；
- 不提交 `.env`、API Key、Token、Cookie、浏览器 Profile、Clash 订阅或节点；
- 不提交真实 bibliography、PDF/XML、人工 inbox、JSONL、HAR、SQLite 和运行 outputs；
- 隐私扫描只输出相对文件名、行号和风险类型，不回显命中的秘密内容；
- 顶层错误信息会遮盖用户目录、邮箱和签名参数，避免终端截图意外泄露；
- 发布前既要扫描工作树，也要检查 Git staged files 与历史提交。

上传 GitHub 前运行：

```powershell
& $Fetcher privacy-scan --path .
```

公共仓库不得包含：

- API Key、Token、Cookie、Authorization header；
- 真实邮箱、校园账号、代理订阅和节点信息；
- 浏览器 Profile、HAR、DevTools 页面快照；
- 个人绝对路径；
- 下载日志中的签名 URL；
- 受版权保护的 PDF/XML；
- 真实书目、人工下载 inbox 和运行 outputs。

仓库示例和测试必须使用合成数据或明确允许公开的材料。

本项目使用 Apache License 2.0，完整条款见仓库根目录的 `LICENSE`。许可证不授予任何第三方重新分发通过本工具取得的受版权保护论文全文的权利。

## 使用边界

用户对机构和出版社许可的确认优先于自动化便利。如果站点明确不订阅、要求人工验证、暂停 IP 或禁止自动下载，应停止相应自动化并改用开放版本、图书馆全文传递、馆际互借或联系作者。
