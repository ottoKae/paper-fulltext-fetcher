# Paper Fulltext Fetcher

一个给 Codex 使用的论文全文下载与语料准备助手：从书目清单出发，合法获取并验证 PDF/XML；需要时，再把全文转换成可搜索、可定位、可审计的本地语料。

它不会绕过付费墙、验证码、访问限制或出版社条款。

## 什么时候适合用

适合这些情况：

- 手里有 Excel、CSV 或 TSV 书目，想批量整理 PDF/XML；
- 已下载一部分，想跳过已有文件并继续处理缺失项；
- 可以使用开放获取、学校订阅、出版社 API/TDM 或人工下载；
- 希望保留来源、失败原因和验证结果，方便复查。
- 想把 PDF/JATS XML 转成 Docling JSON、Markdown 和带页码或 XPath 的证据块。

不太适合这些情况：

- 只临时下载一两篇论文；
- 希望程序绕过登录、验证码、反爬限制或未订阅提示；
- 需要无人值守地模拟浏览器高速抓取出版社网站。

## 最快开始

### 让 Codex 安装

在 Codex 中说：

```text
$skill-installer 请从 https://github.com/ottoKae/paper-fulltext-fetcher 的仓库根目录安装 paper-fulltext-fetcher。
```

安装后重载 Codex，再直接描述任务，例如：

```text
请使用 paper-fulltext-fetcher 审计这份 Excel 对应的全文，跳过已有论文，输出缺失队列和失败原因。不要绕过任何访问限制。
```

### 在 Windows 本地运行

需要 Python 3.11 或更高版本。Skill 会使用自己的 `.venv`，不污染全局 Python：

```powershell
& .\scripts\bootstrap.ps1
& .\scripts\run.ps1 self-test
```

建立一个项目工作区：

```powershell
& .\scripts\run.ps1 init --workspace .\my-review --input .\bibliography.xlsx
& .\scripts\run.ps1 inspect-input --config .\my-review\acquisition.local.toml
& .\scripts\run.ps1 audit --config .\my-review\acquisition.local.toml
```

`init` 只生成本地配置和目录。请先检查 `acquisition.local.toml` 中的工作表、DOI/标题列与输出路径，再开始联网发现或下载。

macOS/Linux 可直接运行：

```bash
python scripts/paper_fulltext_fetcher.py self-test
```

建议在虚拟环境中安装可选依赖：

```bash
python -m pip install -r requirements.txt
```

只有需要语料结构化时，才安装较大的 Docling/OCR 依赖：

```powershell
& .\scripts\bootstrap.ps1 -Corpus
& .\scripts\run.ps1 corpus self-test
```

macOS/Linux 对应命令是：

```bash
python -m pip install -r requirements-corpus.txt
python scripts/corpus_tool.py self-test
```

## 它怎样完成任务

1. **检查书目**：识别 DOI、标题、年份等字段，但不在终端打印真实书目内容。
2. **审计已有全文**：把书目与本地 PDF/XML 对齐，得到已覆盖、缺失和可疑文件。
3. **逐级发现**：优先开放获取与机构知识库，再考虑获准的出版社 API/TDM。
4. **谨慎获取**：默认串行、限速、断点续作；浏览器与人工步骤保持可见、可停止。
5. **验证与留痕**：检查文件容器、页数、标题/DOI线索，记录来源、状态和失败原因。
6. **可选语料准备**：把已经验证的全文在本地转换成结构化 JSON、Markdown 和证据块；不做综述变量判断。

推荐顺序是：

```text
已有文件审计
  → 开放获取发现
  → 获准的出版社 API/TDM
  → 已登录的可见浏览器辅助
  → 人工下载与验证导入
```

每一层只处理上一层仍缺失的记录。这样既节省时间，也减少对出版社网站的重复请求。

## 可选：把全文变成可检索语料

先完成全文审计，再执行：

```powershell
& .\scripts\run.ps1 corpus self-test
& .\scripts\run.ps1 corpus register --config .\my-review\acquisition.local.toml
& .\scripts\run.ps1 corpus doctor --config .\my-review\acquisition.local.toml
& .\scripts\run.ps1 corpus convert --config .\my-review\acquisition.local.toml --profile benchmark
& .\scripts\run.ps1 corpus convert --config .\my-review\acquisition.local.toml --profile base --resume
& .\scripts\run.ps1 corpus assess --config .\my-review\acquisition.local.toml --profile base
& .\scripts\run.ps1 corpus verify --config .\my-review\acquisition.local.toml --profile base
```

原始 PDF/XML 保持不变。派生结果写入项目自己的 `corpus/`：

- Docling JSON：机器可复查的主记录；
- Markdown：便于人工阅读；
- JSONL chunks：带 `study_id`、来源哈希、页码/bbox 或 XML XPath；
- manifest、质量报告和 OCR 重试队列：支持断点续作与审计。

默认 `enable_remote_services=false`，论文内容不会发送到远程 Docling 服务。`benchmark` 用于小样本检查；`base` 用于常规批处理；`force-ocr` 只处理质量报告建议重试的 PDF；`accurate` 用于经选择的小型高精度批次。

这一阶段只建立语料，不回答“用了什么设备”“研究区在哪里”等综述问题。详细步骤见[语料准备工作流](references/corpus-preparation.md)。

## 828 篇论文实践告诉我们的事

这个 Skill 来自一个真实的 828 篇综述语料获取流程。最终形成 **816 篇 PDF + 12 篇全文 XML**，书目覆盖率为 100%。其中 219 篇原本已存在，另外 609 篇有可追溯的新获取记录：

| 路径 | 数量 | 占 609 篇 |
|---|---:|---:|
| 开放来源、多源解析与官方 TDM | 361 | 59.3% |
| 已认证的可见浏览器 | 220 | 36.1% |
| 人工下载后验证导入 | 26 | 4.3% |
| 定向混合恢复 | 2 | 0.3% |

这不是“单个命令自动下载 100%”的成功率。该语料包含 33 个出版社/来源类别，其中 MDPI 298 篇、Elsevier 209 篇；学校订阅、开放获取比例和地区网络都会改变结果。

更可靠的结论是：**多路径接力、逐篇验证和人工兜底，比依赖一个下载器稳定得多。**

## 常用命令

```powershell
& .\scripts\run.ps1 --help
```

| 命令 | 用途 | 是否联网 |
|---|---|---:|
| `self-test` | 用合成数据完成离线自检 | 否 |
| `init` | 创建隐私安全的项目工作区 | 否 |
| `doctor` | 检查环境及凭据变量是否存在，不显示值 | 否 |
| `inspect-input` | 检查书目格式与列映射 | 否 |
| `audit` | 审计本地 PDF/XML 覆盖情况 | 否 |
| `discover-oa` | 发现 OA 候选链接，不下载全文 | 是 |
| `fetch-verified` | 仅下载已审核通过的 URL；默认 dry-run | 是 |
| `manual-queue` | 生成 CSV/HTML 人工处理队列 | 否 |
| `import` | 验证并复制人工取得的 PDF，不删原件 | 否 |
| `privacy-scan` | 检查敏感文件和疑似密钥，不打印命中值 | 否 |
| `corpus self-test` | 用合成 JATS 检查本地 Docling 环境 | 否 |
| `corpus register` | 从全文审计生成稳定语料注册表 | 否 |
| `corpus doctor` | 检查 Docling、模型与磁盘空间 | 否 |
| `corpus convert` | 生成 JSON、Markdown 和定位证据块 | 否* |
| `corpus chunk` | 不重跑解析器，生成新参数版本的证据块 | 否 |
| `corpus assess` | 评估文本质量并生成 OCR 重试队列 | 否 |
| `corpus verify` | 校验来源、派生文件、定位器和哈希 | 否 |
| `corpus status` | 查看紧凑的结构化进度 | 否 |

\* 转换本身在本地进行；首次准备模型可能需要联网下载模型文件，不会上传论文内容。

需要更多参数时运行：

```powershell
& .\scripts\run.ps1 audit --help
& .\scripts\run.ps1 discover-oa --help
& .\scripts\run.ps1 fetch-verified --help
& .\scripts\run.ps1 corpus --help
```

## 什么情况下效果好

- DOI 和标题较完整；
- 开放获取论文、作者存档或机构知识库覆盖较多；
- 学校确实订阅目标内容，且登录会话和网络出口一致；
- 已获出版社 API/TDM 授权；
- 批次小、请求慢、失败后及时停下来检查；
- 人工补录后仍执行身份验证。

## 什么情况下会停下来

- 学校未订阅该论文，或许可不包含程序化获取；
- 出版社返回 401/403/418/429、验证码、挑战页或访问暂停；
- 登录 Cookie 只存在于另一个浏览器配置中；
- VPN/代理改变了机构 IP，使订阅身份失效；
- 下载内容是登录页、HTML 错误页、补充材料或另一篇论文；
- 书目缺 DOI、标题含糊，无法可靠匹配。

这些状态应被记录为“缺失及原因”，而不是反复重试。需要登录或点击验证码时，应由使用者在可见浏览器中完成。

## CARSI、TDM 与浏览器登录

CARSI 或学校图书馆登录证明“你是机构的合法用户，可以阅读订购内容”。TDM/API 权限证明“程序可以按出版社规则批量获取和分析内容”。两者用途不同，有 CARSI 不代表自动拥有 TDM 权限。

浏览器辅助只复用使用者主动登录的可见会话；不要上传或提交浏览器配置、Cookie、会话文件。

## 隐私与安全

仓库只保存通用代码和文档。以下内容必须留在本机，并已被 `.gitignore` 排除：

- `.venv`、PDF/XML 与真实书目；
- Cookie、浏览器用户目录和登录会话；
- API Key、TDM Token、邮箱及校园网信息；
- 下载日志、失败队列和本地绝对路径。
- 含论文正文的 Docling JSON、Markdown、chunks 和质量产物。

密钥只通过环境变量或本地私有配置提供。提交前运行：

```powershell
& .\scripts\run.ps1 privacy-scan --path .
```

不要把凭据写入 README、命令历史、截图、日志或 Git 提交。发现访问暂停、版权限制或服务条款冲突时，立即停止自动化。

## 详细文档

- [完整工作流](references/workflow.md)
- [网络、校园网与认证](references/network-and-auth.md)
- [出版社与来源差异](references/providers.md)
- [状态、日志与失败原因](references/status-and-logs.md)
- [人工下载和安全导入](references/manual-import.md)
- [隐私与发布检查](references/privacy-and-publication.md)
- [语料准备工作流](references/corpus-preparation.md)
- [语料注册表与证据块字段](references/corpus-schema.md)

## 使用边界

本项目只帮助获取使用者依法有权访问的学术全文，并在本地准备可审计语料。它不绕过付费墙、验证码、机器人检查、访问暂停、机构订阅限制或出版社技术措施，也不从论文中判断、汇总或解释具体综述变量。

## License

Apache-2.0
