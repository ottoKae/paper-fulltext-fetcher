# 语料结构与字段

## Registry

`corpus/registry.csv` 是获取阶段与结构化阶段之间的冻结接口。一行对应一份经过验证的全文来源。

关键字段：

| 字段 | 含义 |
|---|---|
| `study_id` | 稳定、安全的记录 ID，不依赖文件顺序 |
| `record_id` | 获取阶段记录 ID |
| `source_format` | `pdf` 或 `xml` |
| `source_relpath` | 相对项目路径，不保存机器绝对路径 |
| `source_bytes` | 注册时文件大小 |
| `source_sha256` | 原始全文内容哈希 |
| `acquisition_status` | 获取审计确认状态 |
| `acquisition_validation` | 身份或视觉审批依据 |

标题、DOI、年份、来源、出版社和作者仅用于身份与质量核对，不代表已经完成综述编码。

## Conversion manifest

`corpus/manifests/conversion_manifest.csv` 是 append-only 事件表。相同论文可以有多个 profile 或配置版本。

它记录：

- `run_id`、`profile` 和 `config_sha256`；
- 来源格式、相对路径和哈希；
- Docling、docling-core 和 Python 版本；
- OCR、TableFormer 模式及表格功能是否启用；
- 状态、耗时、错误类别和脱敏错误摘要；
- JSON、Markdown、chunks、JATS source map 的相对路径和 SHA-256；
- 页数、文本项、表格、图片、字符和 chunk 数量。

`success` 与 `partial_success` 只表示文档转换完成，不等于内容质量合格。质量由 `corpus assess` 单独判断。

## Evidence chunks

每篇论文对应一个 JSONL 文件，每行一个有限长度证据块：

| 字段 | 含义 |
|---|---|
| `schema_version` | chunk 数据契约版本 |
| `chunk_id` | `{study_id}-C####` |
| `study_id` | registry 中的稳定 ID |
| `source_format` | PDF 或 XML |
| `section_path` | 标题层级路径 |
| `item_labels` | Docling/JATS 元素类型 |
| `locator_type` | PDF 为 `page`/`page_bbox`，XML 为 `xpath` |
| `locator_value` | 简洁定位字符串 |
| `page_start`, `page_end` | PDF 页码；XML 为 null |
| `bbox` | PDF 原始版面框；无定位时为空 |
| `source_item_ids` | Docling self-ref 或一个/多个 XPath |
| `text` | 证据文本，不应提交公共仓库 |
| `is_reference_section` | 是否位于参考文献区域 |
| `extraction_eligible` | 是否适合进入后续正文事实检索 |
| `source_sha256` | 原始全文哈希 |
| `docling_json_sha256` | 生成该块的结构化 JSON 哈希 |

自动生成的 chunk 是可定位证据单元，不是已经确认的研究事实。任何后续语义抽取都应另外记录候选、人工审核和最终确认状态。

## 目录

```text
corpus/
├─ registry.csv
├─ registry_summary.json
├─ manifests/
│  ├─ preflight.json
│  ├─ conversion_manifest.csv
│  └─ chunk_manifest_<hash>.csv
├─ derived/<profile>/<config-hash>/
│  ├─ docling_json/
│  ├─ markdown/
│  ├─ chunks/
│  ├─ jats/
│  └─ source_maps/
├─ chunk_sets/<chunk-config-hash>/
├─ quality/
└─ verification/
```

`outputs/corpus/runs/<run_id>/` 保存每次运行的命令摘要、环境、events、checkpoint、成功、失败、重试队列和 summary。所有路径均应保持为相对路径或文件名。
