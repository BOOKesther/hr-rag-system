# 人才知库 · 企业招聘档案 RAG 演示

基于 [PRD](requirements/PRD.md) 的本地应用：上传简历 → 解析清洗 → 候选人归并/版本管理 → 混合检索 → 带证据回答。

技术栈：Python 3.12、FastAPI、Gradio、SQLite FTS5、sqlite-vec、LlamaIndex。

## 启动

Windows PowerShell（安装 uv 后）：

```powershell
cd C:\Pycharm\Py_Projects\hr-kb\hr-kb-main
.\start.ps1
```

或手动执行：

```bash
uv sync --frozen --python 3.12
uv run python -m app
```

- 页面：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs
- 健康状态：http://127.0.0.1:8000/api/health

初次打开“上传与处理”，点击“导入 12 份演示简历”；随后到“档案库与证据”查询，或在“人才检索”使用示例问题。支持自己的 DOCX/PPTX/PDF。扫描件提示需要 OCR（按 PRD 澄清，MVP 不支持 OCR）。

## 模型配置

复制 `.env.example` 为 `.env`，修改后重启。默认无需密钥，使用 **词项哈希向量 + 证据摘录** 验证流程，不代表真实大模型语义检索效果。

启用兼容 API 的语义嵌入与生成模型：

```dotenv
HR_DATA_DIR=data-semantic
HR_EMBEDDING_PROVIDER=openai-compatible
HR_EMBEDDING_BASE_URL=https://your-provider.example/v1
HR_EMBEDDING_API_KEY=your-secret
HR_EMBEDDING_MODEL=your-embedding-model
HR_EMBEDDING_DIM=1024
HR_CHAT_BASE_URL=https://your-provider.example/v1
HR_CHAT_API_KEY=your-secret
HR_CHAT_MODEL=your-chat-model
```

`BASE_URL` 包含 `/v1` 或服务商相应兼容前缀，程序追加 `/embeddings` 或 `/chat/completions`。维度必须匹配模型实际输出。启用后清洗履历会发往配置的服务。不要提交 `.env` 或真实简历。

更换 embedding 模型、维度或 provider 后用新 `HR_DATA_DIR` 重导入；程序防止新旧向量混用。生成失败明确警告并退回证据摘录；embedding 入库失败不会替换已有活动版本。

## 页面快照

PDF 直接生成真实 PNG。DOCX/PPTX 需要 LibreOffice：

```dotenv
HR_SOFFICE_PATH=C:/Program Files/LibreOffice/program/soffice.exe
```

未配置时仍能解析、建库、检索，状态为 `partial_success`，页面提示缺少快照。配置后点击“重试处理 / 补齐快照”。Office 文本不冒充真实页面截图。

## 页面与接口

| 页面 | 能力 |
| --- | --- |
| 人才检索 | 自然语言、城市/年限/学历、BM25/向量开关、RRF、证据回答和调试 |
| 上传与处理 | 最多 20 份批量上传、阶段、失败原因、重试、合成数据导入 |
| 档案库与证据 | 当前候选人、结构化字段、知识文本、历史来源、快照、脱敏解析 JSON |

| API | 用途 |
| --- | --- |
| `POST /api/documents` | multipart `files`，返回任务 ID |
| `GET /api/documents` | 任务列表 |
| `GET /api/documents/{id}` | 阶段事件、状态与指标 |
| `POST /api/documents/{id}/retry` | 重试或补齐快照 |
| `GET /api/candidates` | 当前候选人列表 |
| `GET /api/candidates/{id}` | 当前档案和历史来源 |
| `POST /api/search` | 回答、证据和调试数据 |
| `POST /api/demo/import` | 导入合成简历 |

检索请求示例：

```json
{"query":"熟悉 Java、Spring Boot、MySQL 的后端应届生","top_k":5,"keyword":true,"vector":true}
```

默认 UI 同进程挂载。`HR_UI_MODE=standalone` 仅启动 API；另一个终端运行 `uv run python -m app.web` 开启 7860 端口的 UI，`HR_API_URL` 指向 API。

## 测试

```bash
uv run python -m pytest -q
uv run python -m scripts.verify_demo
```

第二条命令在空库中导入样本，运行三条 PRD 查询和不存在条件查询，输出 `data/verification.json`。12 个来源应归并为 10 位候选人；重复内容拒收，不同内容形成版本。最新来源独立建库，不拼接旧履历。

## 目录

```text
app/
  api.py          # API 与后台执行器
  web.py          # Gradio，只通过 HTTP API 操作业务
  service.py      # 上传、归并、版本事务和任务编排
  parsers.py      # OOXML/PDF、图片与渲染
  knowledge.py    # 字段、语义块、清洗、指纹
  storage.py      # SQLite/FTS5/sqlite-vec
  models.py       # LlamaIndex 类型与模型适配
  retrieval.py    # 过滤、召回、候选人级 RRF
  schemas.py      # 档案和知识投影验证
scripts/          # 演示基线验证
 tests/           # 端到端与安全回归
 data/            # 本地原件、解析 JSON、知识、快照和 SQLite，不提交
synthetic-data/   # 原有合成样本与开发工具
```

已实现能力与增强项边界见 [实现说明](docs/IMPLEMENTATION.md)。本应用只供本地演示，没有账号或权限系统；完整原文件下载含个人信息，不要直接公网部署。
