# Paper Fulltext Fetcher

**全面检索论文，通过用户合法渠道获取 PDF，将全文转成结构化信息。**

一个面向 Codex、也可独立运行的论文工作流助手：从文献清单到本地全文库，再到可检索、可定位的结构化语料，为快速查找论文、获取原文、整理证据和撰写综述提供基础。

```text
文献检索与书目汇集 → 多源发现全文 → 合法下载与校验 → PDF 结构化 → 后续检索、阅读与综述
```

可以从已有书目开始，也可以整理已经下载的论文，不必每次重跑整个流程。

## 三项核心能力

### 1. 全面检索论文，发现全文来源

接收 Excel、CSV、TSV 书目，对照本地文件找出已有与缺失论文；结合 Unpaywall、OpenAlex、Crossref 等服务，查找开放版本、出版社全文链接及相关线索，再衔接机构知识库、图书馆与人工检索渠道，减少遗漏。

当前内置命令主要完成**“已有书目与 DOI → 全文候选”**的发现。按主题、关键词进行的文献检索，需要先在学术数据库、图书馆或其他检索工具中完成，再导入书目；无 DOI 的记录需补全信息或人工查找。多源协同不等于保证穷尽所有论文。

### 2. 通过用户合法渠道下载论文 PDF

优先开放获取，结合用户已有的**校园网、学校订阅、机构登录和获准的出版社 API/TDM**获取全文。支持下载已审核的 URL，也支持用户在可见浏览器中认证、下载后统一导入。

下载不是终点：还会对照书目检查文件是否为目标论文，跳过已有文件，记录缺失及失败原因，便于中断后继续处理。以 PDF 为主，也可保留合法取得的全文 XML。

### 3. 将 PDF 转成结构化信息

使用本地 Docling 将已验证的 PDF/JATS XML 转为 **JSON、Markdown 和分块文本（JSONL）**，整理正文、章节和表格，按需进行 OCR，并保留论文标识、来源哈希及页码、版面坐标或 XML 定位信息。

这些结果可以接入后续全文搜索、知识库/RAG、阅读助手与综述写作流程，支持“找到相关内容 → 回到原文 → 核对证据”。本仓库负责获取和结构化准备，**不内置完整的语义检索系统，也不直接生成综述或确认研究结论**。

## 出版社与实际使用

项目已用于服务器环境中的实际论文获取工作，并非只面向单一出版社或少量 OA 示例。遥感论文涉及的 MDPI、Elsevier、IEEE、Springer Nature、Wiley、Taylor & Francis 等来源，应根据论文开放情况和用户授权，选择开放版本、机构网页、官方接口或人工下载路径。

这是一条多渠道协作流程，**不是单个命令自动下载所有出版社的保证**，也不代表每个平台都有内置专用API客户端。公共仓库不包含用户真实书目、全文、结构化正文或运行统计。出版社差异见[来源说明](references/providers.md)。换到新电脑或服务器后，需重新检查依赖、校园出口、授权和登录会话；历史成功不证明当前机器已就绪。

## 快速开始

### 交给 Codex

仓库提供 **3 个独立功能 Skill＋1 个轻量总入口**：

| Skill | 适用任务 |
|---|---|
| `paper-workflow` | 跨阶段任务，选择起点并串联流程 |
| `paper-search` | 制定主题检索策略，登记实际数据库导出、保留来源并按准确DOI去重 |
| `paper-fulltext-fetcher` | 校园网诊断、全文发现、合法获取、接收校验与审计 |
| `paper-corpus` | 本地Docling结构化、定位和质量检查 |

在本仓库内使用 Codex 时，技能位于 `.agents/skills/`。若要在其他综述目录使用，先克隆仓库，再预览用户级安装：

```powershell
python .\scripts\install_skills.py
python .\scripts\install_skills.py --execute
```

安装器将四个入口和一套版本化共享后端放入用户技能目录；不复制当前 `.venv`、论文或私人配置，不修改网络设置，也不覆盖已有技能。按安装输出定位共享后端并运行其 `scripts/bootstrap.ps1`。目录可用 `--destination` 指定；详细跨平台说明见[共享运行环境](references/skill-runtime.md)。

不要只复制 `SKILL.md`。根目录的同名 Skill 保留为旧版兼容入口，新旧安装二选一，避免重复加载。若新技能未出现，再重载客户端。提供书目、已有全文目录和可用的合法渠道，例如：

```text
请使用 paper-fulltext-fetcher 处理我的遥感论文书目。
先检查已有 PDF，再多源查找缺失论文，通过开放获取和我有权使用的学校渠道补齐全文。
需要登录或额外授权时请提示我。完成后将全文转成带原文定位的结构化语料，
供后续论文检索和综述写作使用，并报告仍然缺失或转换失败的记录。
```

跨阶段请求可直接使用 `$paper-workflow`。检索 Skill 可以编写查询和指导可用数据库检索，但当前后端**不会替用户执行所有学术数据库搜索**；`workflow search-register` 负责冻结真实导出与检索证据，见[检索记录说明](references/search-evidence.md)。

已有 PDF 时，可从文件校验与结构化开始，不必重新下载。

### 重复使用：下载 → Docling → 同目录归档

完成工作区初始化、依赖安装和单篇验证后，准备已核查的来源清单。运行：

```powershell
& .\scripts\run.ps1 workflow batch --config ..\my-review\acquisition.local.toml --output-dir ..\my-review\batches\batch-001 --approved-sources ..\my-review\approved.csv --allow-host repository.example.edu
```

默认只预览。确认后加`--execute`；中断后对相同输入加`--execute --resume`。已有全文跳过，新增全文使用本地Docling，随后按稳定编号同目录归档原文、Markdown、JSON、文本块、质量和来源记录，并生成`index.html`与SQLite全文检索库。默认每次最多请求10篇，开始间隔至少60秒；不自动登录、处理验证码或恢复受限路线。

没有待下载来源时可省略`--approved-sources`和`--allow-host`，只处理已有原件。期刊原版、作者稿、预印本和关联材料分别标记；学位论文章节不自动算作已补齐期刊全文。批次退出成功不代表全部论文获取成功，须查看缺失和解析状态。

来源字段、独立归档/检索命令、版本保护及合成端到端验证见[可复用流程](references/reusable-pipeline.md)。这套入口不依赖特定学校或综述项目，不迁移用户的旧私有目录。

### 本地电脑或服务器运行

需要 **Python 3.11+**。以下命令在仓库根目录执行；真实书目与论文建议保存在仓库外的独立工作区。

<details>
<summary><strong>Windows：安装与初始化</strong></summary>

```powershell
& .\scripts\bootstrap.ps1
& .\scripts\run.ps1 self-test
& .\scripts\run.ps1 init --workspace ..\my-review --input bibliography.xlsx
```

将书目放到 `../my-review/bibliography.xlsx`，已有全文放入工作区的 `papers_pdf/` 或 `papers_xml/`。检查生成的 `acquisition.local.toml` 中的工作表、列映射和目录，再运行：

```powershell
& .\scripts\run.ps1 doctor --config ..\my-review\acquisition.local.toml
& .\scripts\run.ps1 inspect-input --config ..\my-review\acquisition.local.toml
& .\scripts\run.ps1 audit --config ..\my-review\acquisition.local.toml
```

`init` 只创建目录和配置，不复制书目或下载论文；`--input` 相对于新工作区。已有全文位于其他目录时，可修改本地配置，无需重复复制。

</details>

<details>
<summary><strong>Linux / macOS：安装与初始化</strong></summary>

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/paper_fulltext_fetcher.py self-test
.venv/bin/python scripts/paper_fulltext_fetcher.py init --workspace ../my-review --input bibliography.xlsx
```

将书目放到 `../my-review/bibliography.xlsx`，已有全文放入工作区的 `papers_pdf/` 或 `papers_xml/`，检查 `acquisition.local.toml` 后运行：

```bash
.venv/bin/python scripts/paper_fulltext_fetcher.py doctor --config ../my-review/acquisition.local.toml
.venv/bin/python scripts/paper_fulltext_fetcher.py inspect-input --config ../my-review/acquisition.local.toml
.venv/bin/python scripts/paper_fulltext_fetcher.py audit --config ../my-review/acquisition.local.toml
```

后续获取命令使用 `.venv/bin/python scripts/paper_fulltext_fetcher.py`；结构化命令使用 `.venv/bin/python scripts/corpus_tool.py`，不再添加 `corpus` 前缀。

</details>

### 从缺失清单到全文

完成 `audit` 后，按需选择下一步：

| 你要做的事 | 使用方式 |
|---|---|
| 查找开放全文 | `discover-oa` 发现候选，不直接下载 |
| 下载已审核、获准获取的链接 | `fetch-verified` 默认预览，明确执行时才下载 |
| 经学校网页或其他合法渠道下载 | `manual-queue` 生成清单；下载后用 `import` 校验导入 |
| 查看补齐结果 | 再次运行 `audit`，更新覆盖率与缺失清单 |

发现阶段使用的邮箱或 API Key 通过环境变量配置，见[配置示例](assets/acquisition.example.toml)。联网前先确认来源、授权和请求间隔，再做单篇验证、小批处理。`discover-oa` 默认只处理 1 条记录；`fetch-verified` 要求候选已获批准，并用 `--execute` 与 `--allow-host` 明确执行和允许的主机。

命令参数用 `--help` 查看；详细操作见[获取工作流](references/workflow.md)与[人工导入说明](references/manual-import.md)。

### 校园网与浏览器下载：先诊断，再验证一篇

在项目本地配置中填写 `[institution]` 学校/认证域名与接入方式，以及 `[browser].downloads_dir` 实际下载目录；默认是项目 inbox，不假定是系统“下载”文件夹。先运行 `doctor`。Clash 是可选项，离线配置检查不证明校园出口或订阅已经可用。

用户从已经登录的浏览器合法保存 PDF 后，可以用单篇闭环接收：

```powershell
& .\scripts\run.ps1 workflow browser-receive --config ..\my-review\acquisition.local.toml --record-id RECORD_ID
& .\scripts\run.ps1 workflow browser-receive --config ..\my-review\acquisition.local.toml --record-id RECORD_ID --execute
```

第一条只预览；第二条有限等待并检查文件稳定性、首页/第二页身份、哈希，再执行导入预览、导入和审计。已有验证全文自动跳过；无文件、错误PDF或只打开阅读器均不算成功。也可在明确授权后连接现有本机浏览器、点击观察到的PDF控件；不会自动登录、处理验证码或调整阅读器/Clash设置。

首次浏览器下载先做一篇验证，再单并发、小批次执行。HTTP/浏览器停止状态分别持久化，只有新恢复证据与用户确认才能放行一次复测。详细配置、命令、回执与限制见[校园网启动与下载闭环](references/campus-onboarding.md)。

### 把全文转成结构化语料

只有使用这一阶段时，才需安装较大的 Docling/OCR 依赖。先完成全文审计，再做小样本转换；确认质量后批量运行。

<details>
<summary><strong>展开结构化命令</strong></summary>

Windows：

```powershell
& .\scripts\bootstrap.ps1 -Corpus
& .\scripts\run.ps1 corpus self-test
& .\scripts\run.ps1 corpus self-test --pdf
& .\scripts\run.ps1 corpus register --config ..\my-review\acquisition.local.toml
& .\scripts\run.ps1 corpus doctor --config ..\my-review\acquisition.local.toml
& .\scripts\run.ps1 corpus convert --config ..\my-review\acquisition.local.toml --profile benchmark
```

检查小样本的文本、表格和原文定位后，再执行：

```powershell
& .\scripts\run.ps1 corpus convert --config ..\my-review\acquisition.local.toml --profile base --resume
& .\scripts\run.ps1 corpus assess --config ..\my-review\acquisition.local.toml --profile base
& .\scripts\run.ps1 corpus verify --config ..\my-review\acquisition.local.toml --profile base
```

Linux / macOS 先执行 `.venv/bin/python -m pip install -r requirements-corpus.txt`，再将上面的 `& .\scripts\run.ps1 corpus` 替换为 `.venv/bin/python scripts/corpus_tool.py`，并使用对应的路径分隔符。

转换在本地执行，禁用远程 Docling 服务；首次使用可能联网下载模型，但不会因此上传论文。普通 `corpus self-test` 检查合成 JATS，`--pdf` 额外检查合成 PDF 的模型链路，不替代真实论文的小样本检查。JATS 以外的出版社专有 XML 不保证可直接转换。

源文件保持不变，JSON、Markdown、带定位的文本块及质量记录写入工作区的 `corpus/`。OCR 重试和转换参数见[结构化工作流](references/corpus-preparation.md)。

</details>

## 校园网、授权与隐私

- **网络：**依赖机构 IP 的出版社网页/API、学校和认证入口应使用正确的校园出口；其他服务可独立代理分流。切换设备后需验证实际路由和机构识别，工具不会自动修改 Clash 或系统代理。详见[网络与认证](references/network-and-auth.md)。
- **授权：**学校订阅、CARSI 登录与 API/TDM 权限并不等价。不绕过付费墙、验证码或访问限制；遇到封禁、挑战或限流时停止相应渠道，转向其他合法来源或人工处理。
- **隐私：**真实书目、论文、结构化正文、凭据、Cookie 和下载记录留在私有工作区，不提交公共仓库。密钥通过环境变量或本地私有配置提供；发布前运行 `privacy-scan` 并检查待提交内容，不依赖忽略规则兜底。

## 进一步阅读

| 文档 | 内容 |
|---|---|
| [完整工作流](references/workflow.md) | 从书目检查到全文补齐的操作顺序 |
| [出版社与来源](references/providers.md) | 各渠道的获取方式与权限差异 |
| [网络与认证](references/network-and-auth.md) | 校园网、Clash、CARSI、API/TDM |
| [人工导入](references/manual-import.md) | 人工下载、文件匹配与扫描版 PDF |
| [结构化工作流](references/corpus-preparation.md) | Docling、OCR、小样本验证与批处理 |
| [结构化字段](references/corpus-schema.md) | 语料目录、文本块及原文定位信息 |
| [状态与日志](references/status-and-logs.md) | 获取结果、失败原因与审计字段 |
| [隐私与发布](references/privacy-and-publication.md) | 敏感数据保护与发布检查 |

## License

[Apache-2.0](LICENSE)
