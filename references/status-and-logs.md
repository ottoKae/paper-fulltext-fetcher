# 状态、证据与日志

## 推荐终态

| 状态 | 含义 |
|---|---|
| `valid_pdf` | PDF 容器和身份通过 |
| `valid_xml` | 确认为全文 XML |
| `visual_approved_pdf` | 图像型 PDF 经记录化视觉审批 |
| `already_present` | 最新审计已确认存在 |
| `not_subscribed` | 机构明确未订阅该内容 |
| `api_not_entitled` | Key 存在但 API/TDM 产品未授权 |
| `oa_not_found` | 已检查 OA 服务但没有开放位置 |
| `identity_mismatch` | 文件不是目标记录 |
| `invalid_container` | HTML、损坏 PDF 或摘要 XML |
| `challenge_or_block` | CAPTCHA、WAF、418 或暂停页面 |
| `rate_limited` | 429 或明确限流 |
| `manual_required` | 自动渠道结束，转人工处理 |
| `permanent_unavailable` | 在当前许可范围内不可获得 |

不要把所有结果都归为 `success/failed`。网络失败、无订阅、无 OA 和身份错误需要不同的下一步。

## JSONL 事件字段

- `timestamp_utc`
- `run_id`
- `record_id` / `excel_row`
- `doi` / `title`
- `provider` / `host`
- `action`
- `status` / `reason_code`
- `http_status`
- `output_relative_path`
- `bytes` / `sha256`
- `validation`
- `source_url_redacted`
- `retry_decision`

事件日志只追加，不覆盖以前运行。

## URL 脱敏

日志保留 scheme、host 和 path。默认删除 query 与 fragment，尤其是 `token`、`signature`、`key`、`auth`、`expires` 等参数。

## 审计摘要

至少包含：

- bibliography records；
- valid PDF；
- valid XML-only；
- visual-approved PDF；
- full-text coverage；
- missing；
- orphan/invalid/identity mismatch；
- duplicate content groups；
- publisher coverage。

报告必须标明生成时间和输入摘要。配置文件中的历史 snapshot 不能作为实时真值。
