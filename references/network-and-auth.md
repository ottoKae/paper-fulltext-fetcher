# 网络、校园 IP、CARSI 与 TDM

## 权限分层

### 普通网页

供人工阅读和偶尔下载。网页可读不代表允许自动化批量获取。

### CARSI/机构认证

证明用户属于订阅机构。它通常建立浏览器会话或机构身份，但不自动授予出版社 API/TDM 权限。

### API/TDM

证明程序可以按照出版社条款获取或分析内容。它可能要求普通 API Key、机构 Token、TDM Token、OAuth client、项目审批或指定 collection。

## Clash Rule 模式

混合需求通常是：

- Codex/OpenAI 走代理；
- 学校、CARSI 和依赖校园出口 IP 的出版社网页/API 走 DIRECT；
- 不依赖校园 IP 且直连不可达的服务按需走代理；
- 规则位于 `MATCH` 等兜底规则之前。

不要自动修改用户的 Clash 配置。先只读检查 `mode`、端口和相关域名规则，输出建议，由用户审核和应用。

## 诊断顺序

1. 确认 Clash 是 Rule 而非 Global；
2. 在实时连接中确认 OpenAI 命中代理策略；
3. 确认学校数据库导航和出版社命中预期路由；
4. 确认网页是否显示机构名称；
5. 对 API 主机单独检查路由；
6. 用一篇 OA 或明确订阅文章测试 API；
7. 将网络问题、网页订阅问题和 API entitlement 问题分开记录。

## CORS

CORS 约束浏览器脚本的跨域请求。服务器端 Python 请求一般不受 CORS 控制。Developer Portal 中的 Website URL、Label 或 CORS Domain 不会赋予 Article Retrieval、TDM 或订阅全文权限。

## 浏览器 Profile

- 每个出版社使用独立 Profile 可以减少会话冲突；
- 调试地址必须是 `127.0.0.1`，不得监听局域网；
- Profile 路径通过本地配置传入；
- 不复制、打包、上传或读取 Cookie 数据库；
- 用户完成认证后，助手只能操作明确授权的目标文章队列。

## 网络隐私

检查配置时不要输出：代理节点、订阅 URL、用户名、密码、控制器 secret、Cookie 或完整请求 Header。域名与策略组名称通常可以报告，但公开文档应使用 `PROXY` 占位符。
