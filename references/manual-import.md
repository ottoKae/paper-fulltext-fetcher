# 人工下载与导入

## 人工队列

每条记录提供：

- 记录 ID 或 Excel 行；
- 标题、DOI、年份、来源、出版社；
- DOI landing page；
- 推荐渠道；
- 预期文件名；
- 人工状态和备注。

## 普通 PDF 导入

1. 用户通过合法渠道下载到独立 inbox；
2. 先检查 `%PDF-` 签名和可解析页数；
3. 提取前若干页文字；
4. 优先匹配 DOI，否则使用标题 token 覆盖率；
5. 多个候选接近时标记 `ambiguous_match`；
6. dry-run 列出匹配结果；
7. 确认后复制到 `.part` 文件；
8. 验证哈希后原子重命名；
9. 不删除 inbox 原件；
10. 重新审计。

## 图像型 PDF

没有可提取文字的 PDF 不应被普通导入器自动接受。视觉审批 manifest 至少包括：

- `source_path`
- `expected_filename`
- `record_id` / `excel_row`
- `title`
- `doi`
- `visual_approved=true`
- `approval_evidence`

审批事件还应记录页数、字节数和 SHA-256。审计时只有事件哈希与当前文件一致才承认。

## 隔离

HTML 假 PDF、损坏容器、错误论文和歧义匹配进入 quarantine 或保留在 inbox；不得覆盖正式语料中的同名文件。
