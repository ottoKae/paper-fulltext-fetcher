# 可复用的获取、结构化与归档

目标：用一份书目和私有工作区重复执行同一流程，不依赖某个综述项目的脚本、学校或机器路径。

## 输入与边界

- 使用Python 3.11+和本运行环境的依赖。结构化另需`bootstrap.ps1 -Corpus`；首次使用可能下载本地模型，不上传论文。
- 在仓库外初始化私有工作区。已有原件可以先用`import`或`workflow browser-receive`验证入库。
- 主题检索和来源发现仍是独立阶段。本批次入口不自动搜索所有数据库，也不凭元数据中的任意链接下载论文。
- `approved.csv`沿用`fetch-verified`书目字段，另需`candidate_url`、`approved=true`、`approval_scope`、`report_role=primary`、`source_version`和`license_evidence`。`approval_scope`取`open_access`、`institutional_repository`或`official_api`；缺失或错误的批准字段会报错，不静默跳过。
- `source_version`取`published`、`accepted_manuscript`、`preprint`、`author_copy`、`repository_copy`或`fulltext_xml`。这是来源核查后填写的版本声明，不由文件名或OA图标推断。下载文件的题名、DOI和目标文件名必须对应书目。
- `license_evidence`记录实际合法来源依据，不强制要求CC许可，也不将公开可读等同于获准再分发或商业TDM。
- 学位论文章节、补充材料、数据集和相关报告不能填写为期刊原版来关闭缺失项。需要保留时，在独立书目及工作区处理，并记录与原候选的关联。当前主库命令不自动判定版本等价或独立研究数量。
- 不使用带凭据或临时签名参数的URL作为冻结输入。不要保存Cookie、Authorization header或登录会话。

## 快速执行

下面的`example.edu`、路径和记录仅为占位值。先审查来源和主机，再执行。

```powershell
& .\scripts\run.ps1 workflow batch --config ..\my-review\acquisition.local.toml --output-dir ..\my-review\batches\batch-001 --approved-sources ..\my-review\approved.csv --allow-host repository.example.edu
```

默认只预览，不创建批次目录，不联网。确认来源和授权后，在同一命令末尾加`--execute`。

1. 冻结候选分母、输入和配置哈希。
2. 重新审计本地原件，跳过已验证文件。
3. 对获准来源逐篇调用下载Skill。默认最多请求10篇，可用`--limit`调整；每次开始至少间隔60秒。
4. 每个主机检查HTTP路线台账。失败或受限路线不自动恢复；其他独立获准主机仍可继续。重定向按当前来源的主机白名单检查，嵌套子域沿用获取器规则，不自动扩大到其他出版社或CDN。
5. 再次审计，注册本地全文，运行Docling转换、质控和完整性检查。
6. 新建只读用途的归档快照，核对原件及派生哈希，生成索引和SQLite全文检索库。

`--skip-structure`只完成获取及原件归档。`--no-tables`明确关闭表格提取，不得解释为论文没有表格。普通结构化使用base；高精度表格或OCR修复仍通过`paper-corpus`的定向命令处理，不对全库自动重试。

进程退出0表示批次处理完成并已保存状态，不表示候选全部补齐。查看最新`attempts/NNN/summary.json`中的`missing`、`complete_acquisition`、`structured`和`complete_structuring`。

## 恢复和版本保护

对同一输入，在原命令末尾加`--execute --resume`。每次执行新建`attempts/001`、`002`等目录，不覆盖旧快照。

- 恢复前核对书目、配置、来源清单及关键工具哈希。变更后需要新建批次，不静默改写冻结输入。
- 已尝试的来源不会在同一批次自动再请求。进程中断后，先审计实际保存的文件；没有文件的未知传输保持未完成，不以再次点击或请求代替核查。
- Docling只在源文件、转换配置和派生文件哈希一致时复用已有结果。
- 工作区锁防止多个批次或接收器同时写入。中断留下锁时，不自动删除。先确认相关进程已停止，再由操作者清理锁并恢复。
- 本入口不能阻止用户另外启动不遵守该锁的旧脚本。因此不要并发运行同一工作区的其他写入命令。
- 同一来源的旧质量警告随`--previous-snapshot`保留，恢复同一批次时自动衔接上一次完整快照。机器重新评估为可用不会自动撤销旧警告。修复后应保存独立的复核证据，再明确建立新选择版本。
- 快照使用`paper-library-v1`格式。旧项目自定义快照不自动迁移，必须显式建立字段映射和哈希验证，不能把旧私有脚本直接复制进公共运行环境。

## 归档与检索

```text
library/
  index.html
  index.csv
  manifest.json
  summary.json
  missing.csv
  search.sqlite
  provenance/
  papers/RECORD_ID/
    source.pdf 或 source.xml
    fulltext.md
    docling.json
    chunks.jsonl
    source_map.json（适用时）
    metadata.json
```

尚未完成转换的原件仍可归档，但明确标为`awaiting_structure`，不虚构JSON、文本块或解析成功状态。原件和已生成的派生文件按记录同目录保存。没有版本依据的旧文件标为`unknown_not_assumed`。

可独立使用归档和验证入口：

```powershell
& .\scripts\run.ps1 workflow archive --config ..\my-review\acquisition.local.toml --output-dir ..\my-review\libraries\snapshot-001 --execute
& .\scripts\run.ps1 workflow archive-verify --snapshot ..\my-review\libraries\snapshot-001
& .\scripts\run.ps1 workflow library-search --snapshot ..\my-review\libraries\snapshot-001 --query "satellite OR plantation" --limit 5
```

`archive`默认也是预览。已有归档目录拒绝覆盖。可用`--sources-metadata`传入版本依据，`--previous-snapshot`传入本格式旧库。验证检查原件、派生文件、逐篇元数据、输入哈希、文本块定位和索引数量，不证明科学结论正确。

## 可重复验证

```powershell
& .\.venv\Scripts\python.exe .\tests\e2e_reuse.py --output .\outputs\validation\reuse-001
```

该端到端测试使用合成PDF/JATS、本机HTTP测试代理、真实命令入口和本地Docling。先在正常运行环境准备模型缓存，例如执行`corpus self-test --pdf`；端到端测试将模型加载设为离线。请求目标是保留的`example.edu`占位域名；仅在测试子进程设置本机代理，不修改系统代理或Clash，不放宽获取器的私网IP防护。覆盖接收、下载、错误身份拒绝、403停止、三份原件归档、全文检索、重复执行不重下载、旧快照和质量警告保护、输入变化拒绝、工作区锁及安装发布包；也验证错误批准、相关报告、签名URL、冲突元数据和夹带私人文件时会拒绝。正常测试至少需要两次60秒请求间隔。输出目录必须是新目录。

`verification.json`保留实际命令、Python/Docling版本、输入哈希、预期与实际、通过或失败、输出和复现命令。时间、临时端口和run ID会变化，不要求这些字段逐字相同。该测试不验证真实学校登录或出版社订阅；新用户仍须独立验证一份合法保存的真实PDF。
