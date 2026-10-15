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
| `identity_mismatch` | 身份规则未通过；须区分错误论文、提取失败和语言限制 |
| `invalid_container` | HTML、损坏 PDF 或摘要 XML |
| `challenge_or_block` | CAPTCHA、WAF、418 或暂停页面 |
| `rate_limited` | 429 或明确限流 |
| `manual_required` | 自动渠道结束，转人工处理 |
| `permanent_unavailable` | 在当前许可范围内不可获得 |

不要把所有结果都归为 `success/failed`。网络失败、无订阅、无 OA 和身份错误需要不同的下一步。

工具安全停止、监督进程超时和临时设置未恢复另记在执行回执中。它们不是当前下载CLI新增的状态枚举。记录原始工具错误、停止范围、受影响进程、已保存文件和下一项允许的操作。不得用出版社的路线恢复命令消除工具安全停止。

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

## 持久化通道状态与接收回执

HTTP下载与可选浏览器助手在工作区 `outputs/acquisition/access/` 中按主机与通道保留独立事件文件。`attempt_started` 未完成也会阻止无声重跑；`recovery_authorized` 只允许一次有证据的恢复测试，不表示下载成功。不得把临时网络错误解释为永久无订阅，也不得借切换通道重复请求仍受限制的同一资源。

`workflow browser-receive` 的 `watch_timeout` 表示未在时间上限内保存可验证文件；`manual_required` 表示当前控件/阅读器需要人工处理；`local_execution_error` 与出版社拒绝不同。`existing_invalid` 保留原文件，不覆盖。每次运行保存开始、结束、来源哈希、工具哈希、导入日志和前后审计；历史回执不改写，`audit/` 仅是可更新的最新视图。

恢复、手动停止和确认的命令见[校园网启动与下载闭环](campus-onboarding.md)。所有“已存在”也必须经验证，不能仅凭文件名存在计数。

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

发布前冻结同一次审计，核对逐篇文件哈希与数量平衡。不要把较早的摘要与较新的文件数量混在同一报告中。新增数须注明起点；累计数须注明候选总数。文件在超时前已通过验证时，追加纠正回执，保留超时与成功传输两个事实。正式纳入、结构化完成和视觉审批角色分别报告。详见[中断下载与检查点](browser-capabilities.md)。
