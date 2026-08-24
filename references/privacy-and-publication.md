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

## 代码设计要求

- 路径来自 CLI 或本地配置；
- 凭据只按环境变量名称读取；
- doctor 只输出 `configured: true/false`；
- 日志 URL 去除 query 与 fragment；
- 错误信息不得包含 Header 或响应中的秘密；
- fixtures 使用 `example.edu` 和合成 DOI；
- 浏览器调试端口只绑定 `127.0.0.1`；
- Skill 不自动修改 Clash 或系统代理。

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
