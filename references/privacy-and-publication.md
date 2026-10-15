# 隐私安全与 GitHub 发布

## 禁止进入公共仓库的内容

- API Key、Token、密码、Authorization header；
- Cookie、浏览器 Profile、Local State、HAR、DevTools 快照；
- Clash 订阅 URL、节点地址、用户名和密码；
- 校园账号、真实个人邮箱和机构会话数据；
- `C:/Users/<name>`、`/home/<name>` 等个人路径；
- 带签名参数的全文 URL；
- 真实下载日志、书目清单和人工 inbox；
- 无公开再分发许可的 PDF/XML；
- 未核实许可证的第三方 vendor 代码。
- 由受版权保护全文生成的 Docling JSON、Markdown、chunks、source maps、质量报告和语料注册表。

## 代码设计要求

- 路径来自 CLI 或本地配置；
- 凭据只按环境变量名称读取；
- doctor 只输出 `configured: true/false`；
- 日志 URL 去除 query 与 fragment；
- 错误信息不得包含 Header 或响应中的秘密；
- fixtures 使用 `example.edu` 和合成 DOI；
- 浏览器调试端口只绑定 `127.0.0.1`；
- Skill 不自动修改 Clash 或系统代理。
- 语料转换默认禁用远程服务与外部插件；源全文及全部派生语料只保存在用户项目中。

## 发布检查

1. 运行 `privacy-scan`；
2. 检查 Git staged files 和完整历史；
3. 检查大文件、PDF/XML、JSONL、HAR、SQLite；
4. 搜索 token/key/password/cookie/authorization；
5. 搜索用户目录和项目绝对路径；
6. 审核第三方许可证；
7. 确认 README 示例都是占位值；
8. 在干净临时目录运行测试；
9. 用 Skill `quick_validate.py` 校验结构。

如果秘密曾经提交到 Git，仅从工作树删除并不足够：应撤销/轮换秘密，并根据仓库情况清理历史。

## 明确的发布清单

`assets/bundle-files.json`逐个列出共享运行环境和公开源码文件。安装器不再递归收集脚本、参考资料和资产；未列入的私人辅助脚本不会被安装或打包。新增通用模块时必须审查后显式加入清单。

```powershell
& .\.venv\Scripts\python.exe .\scripts\release_tools.py check --history --output .\outputs\validation\publication-before-stage.json
& .\.venv\Scripts\python.exe .\scripts\release_tools.py build --output-dir .\dist\public-candidate-001
```

审查差异并仅暂存明确批准的文件后，再使用`check --index --history`。该检查读取实际Git索引对象，拒绝未获准路径、符号链接、未解决冲突、未暂存的必要公开文件和索引/工作树内容差异；对当前可达历史中的文件对象做隐私扫描。不会提交、推送、改写历史、删除文件或轮换凭据。

公共候选包只复制清单文件，核对源文件和副本SHA-256，并扫描包本身。只有临时构建目录通过检查后，才发布为指定输出目录；隐私检查失败不会留下可误用的目标发布包。报告不输出匹配的秘密原文；检查器自身失败时也不打印原始错误。检查工件和本机路径只留在忽略的`outputs/validation/`中，不随公共包发布。

`.gitignore`不能保护已经追踪的文件，也不能删除历史秘密。扫描器是启发式检查，不是无泄露保证。发布前仍须审核实际文件内容、版权、来源和Git历史。发现历史风险时先停止发布，不自动强制推送或清理历史。
