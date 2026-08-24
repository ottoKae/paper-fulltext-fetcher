# Provider 路线选择

## 路由优先级

1. 本地已有验证全文；
2. 开放获取与机构知识库；
3. 出版社官方 API/TDM；
4. 用户已登录的可见浏览器；
5. 人工下载、图书馆服务或作者共享。

## 通用 OA Provider

### Unpaywall

使用 DOI 查询开放位置。要求学术联系邮箱。保留 host、版本和许可线索；候选仍需身份验证。

### OpenAlex

可按 DOI 或 Work ID 查询 OA location。API Key 只从环境读取。不要把 API Key 放入查询日志。

### Crossref

`link` 字段可能包含 TDM 或文本链接，但不保证无需授权。把它作为候选来源，遵守目标 host 的条款。

### PMC/机构知识库

优先使用官方 OA 包、仓储页和明确许可的作者稿。避免从聚合页面猜测 PDF URL。

## 出版社适配要点

### Elsevier

- Developer API Key 的 Label 只是名称；
- Article Retrieval 权限、机构订阅识别和 Journals Fetch/DaaS 是不同层级；
- DaaS 通常需要 OAuth client 和已批准 collection；
- 返回短 XML 时验证是否只有摘要；
- CORS 不控制服务器端 Python entitlement。

### Wiley

- 使用出版社官方 TDM Token 和客户端；
- Token 与学校订阅范围仍可能不同；
- 默认单篇 smoke、低速率、跳过已存在文件。

### Taylor & Francis

- 非商业 TDM 项目可能需要机构提前通知并获得技术接入；
- 不把第三方 API 描述当作已经获批的 Token；
- 无 TDM 项目时使用机构网页人工下载或 OA 版本。

### IEEE

- Xplore API、全文授权和网页订阅是不同能力；
- 官方期刊站可能存在合法 OA/导出版本，但必须验证身份；
- HTTP 418 或挑战页立即停止网页自动化。

### SAGE/IOP/ASCE/SPIE

- SAGE 的主站与地区/机构入口可能需要不同路由；
- IOP 出现 Radware 或验证时停止；
- ASCE 先 OA，再机构浏览器；
- SPIE 出现 access suspended/excessive usage 后禁用自动化，等待支持恢复或转人工渠道。

## 无 DOI 和小型出版社

组合标题、作者、来源和年份检索。不要仅凭文件名或模糊标题自动导入。优先生成带预期文件名的人工队列，并用图书馆或作者渠道确认。
