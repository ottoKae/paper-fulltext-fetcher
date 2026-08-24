# 本地语料准备工作流

## 阶段边界

`corpus` 模块只把已经验证的 PDF/JATS XML 转成可搜索、可定位、可审计的本地表示。它不判断论文是否属于某个综述，不抽取设备、方法、地点或结论，也不生成研究统计。

```text
经过验证的 PDF/JATS XML
  → registry
  → Docling JSON + Markdown
  → 带页码/bbox 或 XPath 的 chunks
  → 质量报告和选择性 OCR 队列
  → 完整性验证
```

原始全文是只读输入。所有派生内容保存在用户项目的 `corpus/`，不得放进 Skill 或公共 Git 仓库。

## 安装

基础下载功能不需要 Docling。只有使用本模块时才执行：

```powershell
& .\scripts\bootstrap.ps1 -Corpus
& .\scripts\run.ps1 corpus self-test
```

`corpus self-test` 只转换一份临时合成 JATS，用于确认 Docling 导入、JATS 解析和禁用远程服务的本地配置。它不读取用户论文，也不替代后续真实 PDF benchmark。

该命令在 Skill 自己的 `.venv` 中安装本地 PDF、JATS、TableFormer 和 RapidOCR 依赖。模型可以在首次使用前显式准备；模型下载与论文上传是两件不同的事。转换始终设置：

```text
enable_remote_services = false
allow_external_plugins = false
```

如果使用预下载模型，通过 `--artifacts-path` 指定本地目录。不要把模型缓存复制进仓库。

## 推荐执行顺序

### 1. 注册经过验证的全文

```powershell
& .\scripts\run.ps1 corpus register --config .\my-review\acquisition.local.toml
```

默认读取 `outputs/acquisition/audit/records.csv`。只有 `valid_pdf`、`visual_approved_pdf` 和 `valid_xml` 进入 registry；来源文件不存在、内容哈希变化、重复 ID 或重复内容会阻止写入。

### 2. 本地预检

```powershell
& .\scripts\run.ps1 corpus doctor --config .\my-review\acquisition.local.toml
```

预检核对可选依赖、来源数量、来源总体积和磁盘余量，不打印书目内容或本地绝对路径。

### 3. 小样本 benchmark

```powershell
& .\scripts\run.ps1 corpus convert --config .\my-review\acquisition.local.toml --profile benchmark
```

benchmark 从不同文件大小和格式中确定性选择少量来源。先检查 JSON、Markdown、表格、页码和 XML XPath，再运行全量。

如果 TableFormer 模型还不可用，可以增加 `--no-tables` 验证其余流程。manifest 会明确记录 `table_extraction=disabled`，不能把零表格解释为论文没有表格。

### 4. 常规转换与恢复

```powershell
& .\scripts\run.ps1 corpus convert --config .\my-review\acquisition.local.toml --profile base --resume
```

`--resume` 只有在来源哈希、配置哈希、全部派生文件和派生文件哈希都一致时才跳过论文。改变 OCR、表格或切块配置不会静默复用旧结果。

可使用 `--workers 1..4`。先从 1 开始；模型内存充足且 benchmark 稳定后再增加。每个 worker 都加载独立的 Docling 转换器。

### 5. 质量评估和选择性 OCR

```powershell
& .\scripts\run.ps1 corpus assess --config .\my-review\acquisition.local.toml --profile base
```

质量评估检查页数一致性、文本量、低文本页、替换字符、可打印字符、重复文本和标题/DOI身份线索。阈值来自本地配置 `[corpus_quality]`。

只对 `retry_ocr_base.csv` 中的 PDF 重试：

```powershell
& .\scripts\run.ps1 corpus convert `
  --config .\my-review\acquisition.local.toml `
  --profile force-ocr `
  --from-retry .\my-review\corpus\quality\retry_ocr_base.csv `
  --resume
```

### 6. 验证和状态

```powershell
& .\scripts\run.ps1 corpus verify --config .\my-review\acquisition.local.toml --profile base
& .\scripts\run.ps1 corpus status --config .\my-review\acquisition.local.toml
```

`verify` 核对来源哈希、JSON/Markdown/chunks 哈希、chunk schema、study ID 和定位器类型。只有 `ready=true` 的语料才适合进入后续检索或信息抽取。

## 转换 profile

| Profile | 用途 | OCR | 表格模式 |
|---|---|---|---|
| `benchmark` | 全量前的小样本检查 | 按需 | fast |
| `base` | 常规批处理 | 按需 | fast |
| `force-ocr` | 质量失败 PDF 的定向恢复 | 强制整页 | fast |
| `accurate` | 人工选择的小批高精度表格处理 | 按需 | accurate |

`force-ocr` 和 `accurate` 必须提供 `--selection` 或 `--from-retry`，避免无意中对整个语料执行高成本处理。

## JATS XML

- 支持原生 `<article>` 和 OAI-PMH 包裹且只含一个 `<article>` 的 JATS；
- 原文件保持不变，标准化副本写入派生目录；
- 不保留来源外部 DTD；派生副本只加入 Docling 识别所需、无 URL 且无实体的 JATS DOCTYPE 标记，并拒绝源 XML entity 声明；
- evidence chunks 从标准化 JATS 建立真实 XPath source map；
- 非 JATS 出版社专有 XML 会以明确失败原因保留，不伪造页码或静默降级。

## 可调配置

```toml
[corpus]
root = "corpus"
registry = "corpus/registry.csv"
runs_root = "outputs/corpus"
ocr_languages = ["english"]
target_chars = 2800
max_chars = 3600

[corpus_quality]
min_total_chars = 3000
low_page_chars = 100
max_low_text_page_ratio = 0.35
max_replacement_ratio = 0.005
min_printable_ratio = 0.98
max_repeated_line_ratio = 0.15
min_title_token_coverage = 0.45
```

短论文、摘要集或非英文语料可能需要调整质量阈值。修改配置后应保留新配置哈希并重新验证。

OCR 语言名由具体引擎定义。RapidOCR 的语言/模型选择在不同版本间仍有差异；默认 `english` 延续本工具验证过的配置。需要其他语言时，应先在 benchmark 中确认相应模型，而不要直接对全量语料运行。
