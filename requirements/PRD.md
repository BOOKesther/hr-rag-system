# 企业招聘档案 RAG 演示系统 PRD

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | 企业招聘档案 RAG 演示系统产品需求文档 |
| 文档版本 | v0.1 |
| 编写日期 | 2026-07-15 |
| 产品形态 | 单体部署、逻辑分层的单机/小型服务端演示系统，FastAPI 提供服务接口，Gradio 提供 Web 界面 |
| 目标读者 | 产品、后端、数据处理、算法和演示人员 |
| 本期范围 | 招聘档案上传、预处理、建库、混合检索、RAG 生成和结果溯源 |

## 2. 背景与目标

人力资源档案管理是企业人力资源管理系统的重要组成部分。本项目聚焦其中的招聘档案管理场景，通过 RAG（Retrieval-Augmented Generation）展示如何把排版和格式不同的简历转化为可检索的结构化、非结构化数据，并支持基于自然语言的人才检索与解释。

系统不以完整 HRIS 为目标，不覆盖薪资、考勤、劳动合同、入职办理等业务；重点体现以下能力：

1. 通过网页上传 DOCX、PPTX、PDF 简历。
2. 通过静态预检和解析路由 Agent 判断每页适合的解析策略。
3. 使用原生解析、OCR 和视觉模型处理不同版式、扫描件和整页图片。
4. 先识别页面布局块，再归并语义内容块，最后构建检索 chunk。
5. 输出统一 JSON 档案、头像 Base64 资源和页面快照。
6. 以 SQLite 保存关系型档案和审计信息，以 FTS5 + sqlite-vec 建立混合检索索引。
7. 使用 LlamaIndex 组织文档节点、嵌入、检索和生成流程。
8. 使用 FastAPI 提供服务接口、任务编排和 RAG 服务，使用 Gradio 提供演示界面。

## 3. 对合成数据的分析

### 3.1 文件清单与逻辑实体

当前 synthetic-data/cv/ 包含 12 个源文件，对应 10 位候选人。这些文件用于系统构建阶段的格式分析、预处理器开发和回归测试，不代表系统必须一次性导入全部文件。

| 类型 | 数量 | 说明 |
| --- | ---: | --- |
| DOCX | 9 | 候选人 01-08、10；其中 01-08 为规则化的一页简历，10 为模板型简历 |
| PPTX | 1 | 候选人 09，单页、文本分散在大量形状中 |
| PDF | 2 | 候选人 03、09 的另一份来源格式 |
| 逻辑候选人 | 10 | 同一人的多个来源文件用于验证不同格式处理，以及重复提交、版本和候选人归并规则 |
| 头像 PNG | 10 | `synthetic-data/avatars/` 下每张约 1254×1254 像素，与候选人一一对应 |
| 模板 DOCX | 4 | synthetic-data/templates/template01.docx 至 template04.docx，仅作为合成数据和解析器开发参考，不纳入当前简历导入基线 |

这些文件用于构建系统时作为分析和测试的基础数据。

候选人 03 同时存在 DOCX/PDF，候选人 09 同时存在 PPTX/PDF，主要有两个用途：

1. 在测试时可以选择其中任意一种格式上传，用于分析格式和结构，并验证数据预处理器是否正常工作。
2. 模拟同一候选人分两次提交不同格式简历的情况。系统先比较文件大小、SHA-256 等文件属性，并在解析后比较归一化内容指纹；若确认文档内容完全一致，应拒收重复文档。若内容存在差异并接受新文档，系统必须区分“来源文档”和“候选人档案”：每次上传产生一个 document_id，同一候选人可关联多个来源文档，但默认检索只使用该候选人最新上传文档的相关内容，并按 candidate_id 去重。

### 3.2 版式与解析难点

| 样本类别 | 已观察到的结构 | 需求影响 |
| --- | --- | --- |
| 候选人 01-08 DOCX | A4 近似尺寸；正文段落；顶部 2 列摘要表；每份嵌入 1 张 1254×1254 头像；约 20-24 个正文段落 | 不能只读取纯段落；需读取表格、图片关系和段落顺序 |
| 候选人 10 DOCX / `template03` | 大量浮动形状、文本框、连接线和锚点；约 65 个绘图对象、33 个浮动/行内对象、2 个媒体条目；文本在 XML 中存在重复呈现 | 需按 shape id、锚点、坐标和文本框关系去重并重建阅读顺序 |
| 候选人 09 PPTX | 单页；约 66 个对象、11 个媒体条目；姓名、日期、技能等文本经常拆成多个文本框或文本 run | 需遍历 slide、group、shape、text run、图片和坐标，按版面聚合文本块 |
| 候选人 03/09 PDF | 为已有候选人的另一种来源格式，均为单页样本 | 需支持 PDF 文本块、坐标和嵌入图片，并用候选人归并消除重复档案 |
| 模板 01/02/04 | 分别包含行内/浮动图片、装饰性图标、线条、文本框和旧模板占位文本；仅作开发参考 | 解析器开发时可用来补充测试，但不纳入当前 12 个源文件的默认导入和验收统计；不能把模板水印或占位文字当作候选人经历 |

当前样本没有真实的复杂履历表、家属关系表或紧急联系人表；后续测试夹具必须补充工作经历表、教育经历表、键值信息表、家属关系表、紧急联系人表、合并单元格、多行表头和图标字段等样本。

因此，预处理器不能依赖 `python-docx.paragraphs` 或“按换行切文本”这一类单一策略。必须保留原始元素类型、页面/幻灯片编号、顺序、坐标和来源关系，以便复核和溯源。

### 3.3 当前数据涉及的业务字段

样本覆盖以下常见字段，可作为第一版抽取 schema 的基线：姓名、求职目标、年龄、性别、现居城市、电话、邮箱、期望薪资、到岗时间、个人概述、教育经历、工作经历、项目经历、技能、证书、荣誉奖励、语言、兴趣爱好和自我评价。

样本职业覆盖后端 Java、市场营销、行政人事、产品经理、企业销售、QA/测试开发、UI/UX、iOS、客户成功等方向，能够覆盖技能、岗位、行业、年限、城市和业绩指标等检索表达。

## 4. 用户与使用场景

### 4.1 用户角色

演示系统仅考虑验证核心RAG流程，用于技术演示和算法验证。因此暂时不考虑用户角色。

### 4.2 核心场景

1. 上传一份或多份简历，查看处理进度、失败原因和生成的快照。
2. 查看候选人档案、结构化字段、原始 JSON、原文件和页面快照。
3. 重复上传相同文件或内容完全一致的不同格式文件，观察系统拒收并记录重复原因。
4. 上传内容有差异的新版本，观察系统保留历史来源文档，但默认档案和检索内容切换到最新文档。
5. 输入“上海 5 年以上 SaaS 产品经验，做过客户服务或知识库”的自然语言条件。
6. 系统同时使用结构化过滤、关键词召回和向量召回，返回去重后的候选人及匹配理由。
7. 点击回答中的证据，定位到候选人 JSON 字段、源文件页面或 snapNN.png。

## 5. 产品范围

### 5.1 本期包含

- DOCX、PPTX、PDF 上传和格式校验。
- 原始文件保存、SHA-256 重复检测/拒收和处理任务状态管理。
- 静态预检、解析路由 Agent、原生解析、OCR、视觉模型增强和解析质量校验。
- 页面布局块、语义内容块、内容关系和检索 chunk 构建。
- 文本、表格、文本框、浮动形状、图片和页面关系解析。
- 统一 JSON、头像 Base64、页面 PNG 快照生成。
- 生成独立的干净知识文档和检索 chunk；解析布局、OCR 结果和证据坐标不进入默认知识库内容。
- 候选人归并、关系型数据入库、FTS5 关键词索引和 sqlite-vec 向量索引。
- 结构化过滤 + BM25 + 向量检索 + RRF 融合。
- LlamaIndex 节点管理、检索编排和基于证据的 RAG 回答。
- FastAPI 服务接口和 Gradio 演示页面。

### 5.2 本期不包含

- 自动做出录用、淘汰或薪酬决策。
- 面试排期、候选人沟通、邮件/短信通知。
- OCR 之外的手写简历识别、音视频简历分析。
- 完整 HRIS、复杂审批流、账号登录、权限体系、企业级 SSO 和多租户隔离。
- 以年龄、性别、照片、民族、婚育等敏感属性作为排序依据。

## 6. 总体流程

```text
网页上传
  -> 文件校验与 SHA-256
  -> 文件属性预检 / 完全重复拒收
  -> 静态预检（格式、页数、文本层、图片占比、对象统计）
  -> 解析路由 Agent 生成页面级策略
  -> 原生解析 / OCR / 视觉模型按页执行
  -> 解析质量校验 / 异常页面定向降级
  -> 页面布局块识别
  -> 语义内容块归并与阅读顺序恢复
  -> 规则 + LLM 抽取结构化字段
  -> JSON / Base64 头像 / 页面快照（解析档案）
  -> 候选人识别与版本切换
  -> 清洗归一化与干净知识文档生成
  -> 干净知识 chunk 构建
  -> SQLite 关系索引 + FTS5 + sqlite-vec（默认只索引最新版本）
  -> 结构化过滤 + BM25 + 向量召回
  -> RRF 融合 / 可选重排
  -> LlamaIndex RAG 生成
  -> Gradio 展示候选人、证据和快照
```

每个阶段都必须有可持久化状态和错误信息。处理失败不得写入“看起来成功”的档案；允许保留原文件和失败日志供重新处理。重复文档应进入明确的 rejected_duplicate 状态，不得创建新的候选人版本。

## 7. 功能需求

### FR-01 文件上传与原件管理

- 支持扩展名 `.docx`、`.pptx`、`.pdf`，扩展名与文件签名必须同时校验。
- 支持单文件和批量上传；演示默认支持至少 20 个文件批次。
- 默认单文件大小上限建议为 20 MB，配置项可调整。
- 每次上传请求先生成 document_id；保存原文件名、媒体类型、大小、上传时间和哈希，演示系统不记录上传用户。
- 先使用文件大小、SHA-256 等属性做快速重复判断。完全相同的文件直接拒收并关联 duplicate_of_document_id。
- 对同一候选人的不同格式文件，在解析后计算归一化内容指纹；若内容完全一致，即使文件哈希不同，也应拒收。
- 若内容存在差异，接受为该候选人的新来源版本；旧版本保留但默认不参与候选人档案展示和检索。
- 上传文件必须存储在应用数据目录，禁止直接使用用户上传的文件名拼接路径。

### FR-02 处理任务状态

任务状态至少包括：uploaded、validating、preflighting、routing、parsing、ocr、vision_fallback、block_analysis、quality_check、rendering、extracting、cleaning、knowledge_quality_check、deduplicating、rejected_duplicate、version_accepted、indexing、knowledge_indexing、succeeded、partial_success、quality_failed、failed。

界面应展示：当前阶段、耗时、处理页数、抽取字段数、头像数、警告数和失败原因。处理过程应可重试，并支持针对单个文档重新处理。

### FR-03 DOCX 解析

必须读取并保留以下信息：

- 正文段落、段落样式、run、超链接和分页信息。
- 表格的行、列、合并单元格和单元格内文本。
- 原生表格必须先作为独立 table_block 保留结构，再参与语义块归并和结构化字段转换，不能只把单元格文本拼成普通段落。
- 页眉、页脚、文本框 `txbxContent`、浮动对象、行内对象和图形锚点。
- `document.xml` 与关系文件中的图片、超链接和对象引用。
- 形状名称、shape id、相对坐标、宽高、层级和 z-order（能取得时）。

对模板型 DOCX，按“页面坐标优先、XML 顺序辅助”的原则重建阅读顺序；同一文本因形状复制或渲染层重复出现时，必须基于 shape id、文本哈希和位置进行去重。

### FR-04 PPTX 解析

必须遍历每个 slide 及其 group shape，并读取：

- 文本框、文本段落、文本 run、字体/样式线索和文本框坐标。
- 表格、图片、图表或其他可读对象的替代文本和关系。
- slide 编号、对象 id、对象类型、z-order、坐标和尺寸。
- `ppt/media/` 中的图片；无内容或损坏的媒体条目应记录警告并跳过。
- PPTX 原生表格、合并单元格和表格对象坐标必须保留为独立 table_block；图片表格进入 OCR 或视觉表格解析流程。

针对候选人 09 这类文本被拆分成多个 shape 的情况，应先按相邻坐标、对齐关系和视觉区域聚合成“内容块”，再交给章节识别和字段抽取。

### FR-05 PDF 解析

- 读取页面数、页面尺寸、文本块、字符位置、图片对象和页面顺序。
- 优先使用原生文本层；文本层为空或字符覆盖率过低时，标记 `needs_ocr=true`，调用可插拔 OCR 流程。
- 保留页码和文本块边界，确保 JSON 字段可回链到 PDF 页面。
- 对 PDF 原生表格保留表格边界、行列关系、单元格坐标和合并关系；扫描表格由 OCR/视觉解析重建，并保留原始页面快照作为证据。
- 支持渲染每一页为 PNG 快照；渲染失败时任务进入 `partial_success` 或 `failed`，不得静默跳过。

### FR-05A 解析策略路由与质量校验

解析器采用“静态预检 + 路由 Agent + 页面级执行 + 质量校验”的分级方案，不默认对整份文档反复试错。

- 静态预检不调用大模型，读取文件类型、页数、页面尺寸、文本层是否存在、每页文本字符数、图片面积占比、表格/文本框/形状数量、是否可生成低清页面预览等特征。
- 路由 Agent 根据静态特征、低分辨率页面预览和受控的初步文本信息，为每一页选择 native、ocr、vision 或 hybrid 策略，并输出原因、置信度和备用策略。
- 页面级路由至少支持：原生文本/版式解析、OCR、视觉模型、原生解析 + OCR、OCR + 视觉模型等组合；不因单页异常而让整份文档全部升级到视觉模型。
- OCR 用于从扫描页或图片中恢复文字、坐标和置信度；视觉模型用于理解复杂图文关系、表格区域、卡片布局和无法由 OCR 解释的视觉结构。
- 解析完成后执行质量校验，检查文本覆盖率、OCR 置信度、关键字段、内容块完整性、跨页连续性和解析结果冲突。质量不通过时，只对异常页面切换到下一等级策略。
- 路由决策必须缓存并记录文件哈希、预检特征、路由模型/提示版本、页面策略、置信度、实际执行策略和最终质量结果。
- 文档内容只作为待解析数据传给模型，不能被当作系统指令；路由 Agent 必须返回可校验的结构化 JSON。

### FR-06 内容归一化与分段

- 统一 Unicode、空白、换行、全角/半角和日期分隔符；保留原始文本。
- 识别中英文标题及同义章节：个人概述、教育背景、工作经历、项目经历、技能、证书、荣誉、自我评价等。
- 识别日期区间、当前工作、城市、年限、薪资、到岗时间、电话号码、邮箱和 URL。
- 保留列表序号、项目指标和数字单位，例如“96%”“420 万元”“300+ API”。
- 对无法确认的字段输出 `null` 或 `unknown`，不得用模型猜测补全。
- 将每个抽取字段绑定到一个或多个 `evidence`，记录来源文件、页码/幻灯片、元素类型、文本片段和坐标。

### FR-06A 内容板块分析与分层

在结构化字段抽取和向量索引之前，必须先完成内容板块分析。内容板块不等同于固定长度 chunk，采用三级表示：

1. 布局块 layout_blocks：页面上的视觉区域，例如顶部信息区、左栏、右栏、表格区、图片区；保留页码、坐标、原始元素和阅读顺序。
2. 语义块 semantic_blocks：具有完整业务意义的内容单元，例如个人概述、教育经历、一个工作经历、一个项目、技能列表；允许跨页面延续。
3. 检索块 chunks：在语义块基础上，为 FTS5、向量检索和 RAG 生成的索引单元；不得把无关章节或不完整经历强行拼接在一起。

板块分析要求：

- 先依据坐标、对齐、列结构、文本框关系、表格边界和 XML/对象顺序生成布局块。
- 再依据标题、时间、职位/公司、列表编号、相邻区域和语义关系，把布局块归并为语义块。
- 对双栏、卡片式和自由排版简历，页面几何关系优先于原始 XML 顺序；必要时由 Agent 判断视觉区域之间的归属。
- 至少支持 contains、belongs_to、continues_to、same_column、same_entry、before_after 等关系。
- 统一恢复“章节标题 + 条目标题 + 时间 + 正文/列表”的完整关系。例如工作经历中的公司、职位、时间和职责描述应作为一个语义块。
- 同一语义块跨页时合并内容，但保留每页证据；页眉、页脚、水印和装饰元素不能混入正文语义块。
- 每个语义块必须关联原始 element_id、页码/幻灯片、bbox、来源解析策略和置信度。
- Agent 只负责复杂布局的分组和关系判断，底层文本、坐标和对象仍以解析器/OCR结果为事实来源。

建议的内容块记录如下：

{
  "block_id": "block_001",
  "page_no": 1,
  "block_type": "employment_entry",
  "section": "工作经历",
  "bbox": [100, 320, 860, 620],
  "text": "...",
  "element_ids": ["shape_12", "shape_13"],
  "relations": [
    {"type": "belongs_to", "target": "section_experience"},
    {"type": "continues_to", "target": "block_002"}
  ],
  "confidence": 0.91
}

完成板块分析后，才进入章节归一化、结构化字段抽取和检索 chunk 构建。

### FR-06B 隐式字段标题与字段推断

简历中的字段标签可能使用中文、英文缩写、同义词、图标或完全省略。解析器必须把“字段标题识别”作为独立能力，不得只依赖固定中文标签。

- 建立可配置的字段同义词和缩写词典，例如电子邮件、email、e-mail、邮箱、电话、mobile、tel 等；词典只用于候选标签识别，最终值仍必须来自原文证据。
- 对无显式标题的键值对，依据页面几何关系、相邻距离、对齐方式、字体/颜色/图标语义、字段值格式和所属内容板块推断字段类型。字段值格式至少覆盖邮箱、电话、URL、日期、城市、薪资和年限。
- 对用图片表示字段标题的情况，先识别图标或图片语义，再将其与邻近文本值建立 label_value 关系；图标无法可靠识别时，保留图片证据和 unknown_label，不得强行猜测。
- 对没有标题但值明显符合字段格式的内容，允许输出推断字段，但必须记录 inferred=true、推断规则/模型、confidence、原始文本和 evidence_ids。
- 显式标题优先于同义词和格式推断；发生冲突时保留多个候选解释并降低置信度。无法确认的内容进入 free_text 或 custom_fields，不得静默丢弃。
- 字段推断结果必须能回链到原始文本、图标/图片、页面坐标和对应的 layout_block 或 semantic_block。

### FR-06C 表格独立解析与转换

表格是独立的内容块和数据源。解析过程中先提取原始 table_block，再根据表头、行列关系和上下文转换为结构化记录或语义块。

- 每个 table_block 至少保存 table_id、document_id、page_no/slide_no、bbox、行列数、表头候选、cells、row_span、col_span、合并关系、原始单元格文本、图片/图标元素、解析策略、confidence 和 snapshot_ref。
- 依据表头和所在章节将表格分类为 key_value、employment、education、project、skill_certificate、family、emergency_contact、custom 或 unknown；分类不确定时保留 unknown 类型和原始表格。
- DOCX/PPTX 优先使用原生表格结构；PDF 优先使用表格线/坐标重建；扫描表格先 OCR 后按坐标聚类行列；图片表格或复杂合并表格可调用视觉模型。所有转换都必须保留 raw_cells 和原页面证据。
- 工作经历、教育经历和项目经历表格按行或逻辑记录转换为 semantic_block，并映射到 employment、education 或 projects；一条记录的公司/学校/项目、职位/专业、日期和描述不得被拆散。
- key_value 表格按字段标签和值转换为 profile 或 custom_fields；表头缺失时复用 FR-06B 的隐式字段推断，并记录 label_source 和 inference_confidence。
- 家属关系、紧急联系人等额外信息单独进入 relationships、emergency_contacts 或 custom_fields，不得混入 candidate_contacts；默认不参与普通人才检索、排序、向量索引和 RAG 上下文。
- 不能可靠归类的表格仍须保存原始结构、单元格坐标和页面快照；可生成一个 custom_table 记录供详情页查看，不能只保留拼接后的文本。
- 表格检索以“表头 + 完整行记录”为最小证据单元，避免只召回孤立单元格；每个转换字段必须包含 source_table_id、source_row、source_cell_ids、page_no 和 bbox。

### FR-07 统一 JSON 输出

每个来源文档输出一个 JSON 文件，建议结构如下：

```json
{
  "schema_version": "1.0",
  "document_id": "doc_xxx",
  "candidate_id": "cand_xxx",
  "source": {
    "filename": "resume_01_lin_chen_backend.docx",
    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "sha256": "...",
    "page_count": 1,
    "parser": "docx-ooxml",
    "parser_version": "...",
    "uploaded_at": "2026-07-15T00:00:00Z",
    "version_no": 1,
    "content_fingerprint": "...",
    "is_active": true
  },
  "parsing": {
    "document_strategy": "mixed",
    "router": {"type": "rule+agent", "model_version": "..."},
    "pages": [],
    "quality_gate": {"status": "passed", "warnings": []}
  },
  "blocks": {
    "layout_blocks": [],
    "semantic_blocks": [],
    "chunks": []
  },
  "tables": [],
  "relationships": [],
  "knowledge_projection": {
    "status": "pending",
    "knowledge_id": null,
    "clean_version": null,
    "artifact_path": null
  },
  "profile": {
    "name": "林晨",
    "target_roles": ["后端开发工程师", "Java"],
    "age": 23,
    "gender": "男",
    "current_city": "上海",
    "phone": "...",
    "email": "...",
    "salary_expectation": {"min": 10, "max": 13, "unit": "K/月"},
    "availability": "毕业后可到岗",
    "summary": "..."
  },
  "education": [],
  "employment": [],
  "projects": [],
  "skills": [],
  "certificates": [],
  "awards": [],
  "languages": [],
  "interests": [],
  "free_text": [],
  "emergency_contacts": [],
  "custom_sections": [],
  "custom_fields": [],
  "evidence": [],
  "assets": {"portrait": [], "embedded_images": [], "snapshots": [] },
  "quality": {"status": "succeeded", "warnings": [], "confidence": 0.0 }
}
```

其中 education、employment、projects 的每条记录应包含标准字段、原始描述、结构化日期、来源语义块和 evidence_ids。tables 保存原始及转换后的表格结构，relationships、emergency_contacts 和 custom_fields 用于承载额外信息；字段推断结果必须记录 inferred、confidence 和 evidence_ids。free_text 用于保留不能可靠归类的非结构化内容，避免抽取过程丢失信息。JSON 还必须保存解析路由、页面质量、布局块、语义块、表格和检索 chunk 的关联关系。

### FR-07A 清洗归一化与知识库投影

解析 JSON 是“处理档案”，用于保留原始内容、解析结果和证据链；知识库使用独立的“知识投影”，只承载清洗后的有效人员履历信息。两者必须分开生成、分开存储、分开索引。

知识投影处理要求：

- 输入为已完成字段抽取、表格转换、内容板块分析和候选人版本确认的标准档案；默认只使用该 candidate_id 最新活动来源文档的有效内容。
- 清除版面和解析痕迹，包括坐标、shape_id、XML 顺序、OCR 标记、重复 shape 文本、页眉页脚、水印、装饰图标名称、图片占位符、解析器名称、路由策略、模型版本和质量调试字段。
- 清除无法证明属于候选人履历的文本；低置信度、冲突且未解决的字段进入 quarantine 或 omitted 状态，不得由模型补写。
- 统一姓名、日期、公司、职位、技能、项目和业绩指标的表达；保留原始事实和数字，不改变原意，不把多个来源版本拼接成一个虚构经历。
- 表格转换为完整、可读的业务记录。表头、边框、单元格编号和合并单元格痕迹不进入知识文本；工作、教育和项目表格应生成自然语言或标准结构化记录。
- 生成按章节组织的 clean_text 和 clean_sections，例如个人概况、求职方向、教育经历、工作经历、项目经历、技能、证书和语言；每个检索 chunk 必须以完整语义条目为边界。
- 家属关系、紧急联系人、照片、年龄、性别及其他敏感字段默认不写入普通知识投影；若后续确需展示，必须通过独立字段和显式策略处理。
- 知识投影不得包含 evidence_ids、bbox、layout_blocks、semantic_blocks、raw_cells 等解析字段。证据映射单独保存在 knowledge_provenance 或 evidence 表中，仅用于结果回链，不作为默认 FTS5、向量或 RAG 内容。
- 可使用规则模板生成知识文本；允许 LLM 做受约束的语言整理，但只能改写已确认事实，禁止新增事实、推断缺失经历或覆盖结构化字段。
- 清洗完成后执行质量门禁：检查是否包含解析标记、重复段落、无意义符号、空洞文本、敏感字段和与标准档案不一致的事实。失败时知识投影状态为 quality_failed，不得进入索引。

建议的知识投影文件结构如下：

{
  "knowledge_schema_version": "1.0",
  "knowledge_id": "knowledge_xxx",
  "candidate_id": "cand_xxx",
  "source_document_id": "doc_xxx",
  "version_no": 1,
  "status": "ready",
  "clean_version": "1.0",
  "profile": {},
  "sections": [
    {"section": "工作经历", "text": "..."}
  ],
  "clean_text": "..."
}

该文件只用于知识库和检索，不替代解析 JSON。知识投影更新时重新生成全文索引和向量索引；原始解析档案和证据映射保持不变。

### FR-08 头像 Base64 与页面快照

目录约定如下，`document_id` 与文件名必须只使用安全字符：

```text
data/
  originals/{document_id}/source.ext
  processed/{document_id}.json
  processed/{document_id}/
    portrait_01.base64.txt
    portrait_01.png
    embedded_01.png
    snap01.png ... snap99.png
  knowledge/{candidate_id}/knowledge_v001.json
  knowledge/{candidate_id}/knowledge_v001.txt
```

- 人像照片必须导出为 Base64 文本文件，文件中保存纯 Base64 或明确的 data URI，并在 JSON 中记录 MIME 类型、尺寸、SHA-256、路径和 `encoding=base64`。
- 同时保留解码后的 PNG 预览，便于 Gradio 展示和数据校验；Base64 文件是规范产物。
- 装饰图标、线条和空媒体不应被误判为头像；其余有效嵌入图片可放入 `embedded_images` 并记录来源。
- 每个源文件按实际页面/幻灯片输出 PNG，使用两位编号 `snap01.png` 至 `snap99.png`，不输出空页、不覆盖其他文档。
- 快照需记录页码、宽高、渲染器、渲染时间和源文件哈希，便于重新渲染和证据定位。

### FR-09 候选人归并

- document_id 表示来源文件，candidate_id 表示逻辑候选人。
- 首先按标准化邮箱、标准化电话匹配；缺少联系方式时，再使用姓名 + 教育/工作组合等多字段规则，不得仅凭姓名归并。
- 完全重复的文件或归一化内容完全一致的跨格式文件直接拒收，不创建新版本。
- 内容有差异的新文件接受为该候选人的新版本，递增 version_no，并更新 candidates.latest_document_id。
- 同一候选人只允许一个来源文档处于 is_active=true；最新接受版本为活动版本，历史版本保留用于溯源和对比，但默认不进入档案展示、FTS5、向量索引和 RAG 上下文。最新文档内容作为候选人当前档案，不与旧版本字段拼接。
- 当前基线数据验收结果应为 12 个来源文档、10 个逻辑候选人，其中 03 和 09 各有 2 个来源文件；若测试时只上传其中任意一种格式，则按实际上传集合计算。

### FR-10 关系型档案库

SQLite 为系统事实源，至少包含以下表：

| 表 | 关键字段 | 作用 |
| --- | --- | --- |
| candidates | candidate_id, name, city, years_experience, latest_document_id, latest_uploaded_at, status | 候选人主档案及当前活动版本 |
| source_documents | document_id, candidate_id, path, sha256, content_fingerprint, mime_type, version_no, is_active, duplicate_of_document_id, status | 来源文件、重复关系与版本状态 |
| `candidate_contacts` | `candidate_id`, `type`, `value_hash`, `value_ciphertext` | 联系方式，支持去重与脱敏 |
| `education` | `candidate_id`, `school`, `major`, `degree`, `start_date`, `end_date` | 教育经历 |
| `employment` | `candidate_id`, `company`, `title`, `start_date`, `end_date`, `description` | 工作经历 |
| `projects` | `candidate_id`, `name`, `role`, `start_date`, `end_date`, `description` | 项目经历 |
| `skills` | `candidate_id`, `skill`, `normalized_skill`, `years` | 技能和同义词 |
| `assets` | `asset_id`, `candidate_id`, `type`, `path`, `mime_type`, `sha256` | 头像、嵌入图片和快照 |
| `evidence` | `evidence_id`, `document_id`, `page_no`, `element_type`, `text`, `bbox` | 字段和回答的来源证据 |
| knowledge_documents | knowledge_id, candidate_id, source_document_id, version_no, clean_text, clean_version, status, is_active | 清洗后的候选人知识投影 |
| knowledge_provenance | knowledge_id, section, source_document_id, evidence_ids | 知识内容到原始证据的内部映射，不进入检索文本 |
| chunks | chunk_id, knowledge_id, candidate_id, section, text, is_active, metadata_json | 干净知识文档的向量/关键词检索单元 |
| tables | table_id, candidate_id, document_id, table_type, page_no, bbox, raw_json, is_active | 原始表格及表格分类结果 |
| table_cells | cell_id, table_id, row_no, col_no, row_span, col_span, text, bbox | 单元格原文、位置和合并关系 |
| relationships | relationship_id, candidate_id, relationship_type, name, relation, source_table_id, evidence_id | 家属关系等额外关系信息 |
| emergency_contacts | contact_id, candidate_id, name, relation, phone, source_table_id, evidence_id | 紧急联系人，默认敏感隔离 |
| custom_fields | field_id, candidate_id, section, field_name, value, inferred, confidence, evidence_id | 未纳入标准 schema 的字段 |
| `processing_jobs` | `job_id`, `document_id`, `stage`, `status`, `error_json` | 任务和错误追踪 |

联系方式等 PII 在演示环境也应支持脱敏显示；数据库不应把完整手机号/邮箱直接放入日志。

### FR-11 关键词与向量索引

- 使用 SQLite FTS5 对候选人名称、目标岗位、摘要、经历、项目、技能和证书建立全文索引。
- 可将已确认的非敏感 custom_fields 纳入全文索引；relationships、emergency_contacts 及其他敏感字段默认不进入 FTS5、向量索引和普通 RAG 上下文。
- FTS5 和 sqlite-vec 的唯一正文输入是 status=ready 的 knowledge_documents 及其 clean chunks；不得直接从解析 JSON、layout_blocks、raw_cells 或 evidence 表建索引。
- 索引 metadata 只保留 candidate_id、knowledge_id、section、is_active、索引版本等必要字段；解析策略、坐标和 OCR 置信度留在处理档案，不进入 RAG 内容。
- 对中文检索提供可配置的分词/归一化策略；至少支持关键词短语、数字指标和岗位/技能同义词扩展。
- 将通过知识投影质量门禁的 clean chunks 转为 LlamaIndex Node，生成可配置 embedding，写入 sqlite-vec 向量表。
- 向量记录必须带 candidate_id、knowledge_id、section、is_active 和 embedding 模型版本；来源文档和 evidence_ids 只在 knowledge_provenance/evidence 中维护。
- 默认只为最新活动来源文档生成或保留可检索的 FTS5/向量记录；历史版本索引可保留，但必须通过显式历史查询开关启用。
- embedding 模型或维度发生变化时建立新索引版本，不覆盖旧版本；索引必须可重建。
- clean chunk 必须基于已清洗的章节和完整经历/项目条目构建，默认 300-800 中文字符；不得为了满足长度强行拆开标题、时间和职责描述，也不得跨越无关章节。

### FR-12 混合检索与 RRF

检索请求先解析为结构化约束与语义查询。默认检索范围仅包含每个 candidate_id 的最新活动来源文档；历史版本不参与默认排名。

1. 结构化过滤：城市、岗位、经验年限、学历、到岗时间等明确条件；不得使用家属关系、紧急联系人、年龄、性别、照片等敏感或与岗位无关的信息作为默认过滤条件。
2. FTS5/BM25：召回岗位名、技能、公司、工具、数字业绩和关键词精确匹配。
3. 向量检索：召回表达不同但语义相近的经历和能力。
4. 对各路结果按候选人聚合，保留最高相关 chunk 和证据。
5. 使用 Reciprocal Rank Fusion 合并排名，默认 `k=60`；每路权重、top-k 和阈值可配置并记录在检索日志中。
6. 对融合后的前 N 个候选人执行可选重排；重排不能替代硬过滤。

建议输出字段：候选人、综合分、关键词分、向量分、结构化命中、匹配技能、相关经历、证据列表、来源文档和快照链接。

### FR-13 RAG 生成

- LlamaIndex 负责 QueryBundle、NodeWithScore、检索器组合、上下文拼装和响应生成。
- RAG 上下文只允许使用最新活动版本的 clean knowledge chunks；解析 JSON、布局块、OCR 原文、表格 raw_cells 和证据坐标不得直接进入上下文。
- 证据回链通过 knowledge_provenance/evidence 的内部映射在检索结果或界面层完成，不把解析痕迹混入知识文本。
- Prompt 明确要求：只根据给定证据回答；区分“简历明确写明”和“根据文本推断”；缺失信息输出“未提供”；不得编造任职经历、学历或能力。
- 回答至少包含：检索条件解释、推荐候选人、匹配理由、风险/缺失信息、证据来源。
- 生成结果必须保留 `retrieval_run_id`、使用的候选人/节点 id、模型版本和时间戳。
- 默认不把年龄、性别、头像等敏感属性用于排序；演示界面展示敏感字段时应默认脱敏，生产化权限控制不属于本期范围。

### FR-14 Gradio Web 前端

建议提供以下页面或 Tab：

1. **上传与处理**：多文件上传、格式/大小提示、进度、失败原因、重试按钮。
2. **档案库**：候选人列表、岗位/城市/经验过滤、头像、状态、来源文件数、更新时间。
3. **档案详情**：干净知识档案、结构化字段、解析 JSON、原始/转换后的表格、头像、源文件信息、页面快照翻页和证据定位；明确区分知识内容和解析详情。
4. **人才检索**：自然语言查询、结构化过滤、top-k、检索策略开关、候选人结果和 RAG 回答。
5. **检索调试**：展示 BM25、向量、结构化过滤和 RRF 的中间结果，服务于技术演示和问题定位。

## 8. 非功能需求

### NFR-01 可用性与性能目标

- 在当前 12 个源文件的基线数据上，冷启动后批量处理目标不超过 3 分钟；单个普通一页简历目标不超过 30 秒，实际指标写入处理日志。
- 单次检索应在 5 秒内返回检索结果；模型生成耗时单独展示。
- 页面快照不得阻塞数据库提交；允许先完成文本/JSON，再异步补齐快照，但状态必须为 `partial_success` 并给出原因。

### NFR-02 可靠性与可重复性

- 所有处理步骤幂等，输入哈希 + 解析器版本 + schema 版本组成处理指纹。
- 保存解析器版本、embedding 模型、prompt 版本和索引版本。
- 失败任务可从失败阶段重试，已成功阶段可复用缓存。
- JSON 必须可被 schema 校验器验证；Base64 必须能解码；快照文件必须存在且可打开。
- 知识投影必须可独立生成、可重复生成并通过清洗质量门禁；知识库索引不得依赖解析调试字段。

### NFR-03 安全与隐私

- 上传文件按不可信输入处理：校验扩展名、MIME、文件签名、大小和压缩包路径，禁止宏执行。
- 文档内容只作为数据，不作为系统指令；模型抽取和生成时使用清晰的边界标记。
- 电话、邮箱、照片、年龄、家属关系和紧急联系人属于个人信息，日志和列表默认脱敏；演示系统不实现账号和权限，原文件与完整 JSON 仅在本地演示界面展示。
- 生成回答禁止输出与招聘无关的敏感推断，禁止根据照片、性别、年龄、家属关系或紧急联系人等信息进行推荐排序；敏感表格默认不进入普通 RAG 上下文。
- 认证、授权、审计、加密存储、病毒扫描和数据删除属于生产化扩展，不纳入本期演示实现。

### NFR-04 可观测性

每次处理、路由、板块分析、知识清洗和检索记录结构化日志：request_id、job_id、document_id、candidate_id、knowledge_id、stage、耗时、输入哈希、模型/索引版本、召回数量、清洗质量状态、失败原因、路由策略、路由置信度、质量门禁结果和结果状态。日志中不得记录完整 PII。

## 9. 推荐技术方案

### 9.1 后端

- Python 3.12+。
- Web/API：FastAPI，负责上传、处理任务、档案查询、混合检索和 RAG 服务。
- UI：Gradio。
- 文档解析：DOCX/PPTX 使用 OOXML/XML 级解析；PDF 使用文本块/图片/坐标解析；通过静态预检和解析路由 Agent 选择原生解析、OCR 或视觉模型；渲染使用 LibreOffice、Poppler 或等价可替换适配器。
- 编排：LlamaIndex，用于节点、embedding、检索器和生成链路；底层事实数据仍由 SQLite 管理。
- 数据库：SQLite + FTS5 + sqlite-vec；通过独立 adapter 接入 LlamaIndex VectorStore。
- 模型：embedding 和 chat model 通过配置注入，不将供应商写死在业务层。

### 9.2 当前版本架构判断

当前版本不属于严格意义上的前后端分离，而是“逻辑分层、单体部署”的演示架构：

- Gradio 负责页面、交互和结果展示，属于展示层。
- FastAPI 负责 API、业务编排、文件处理、索引、检索和 RAG，属于服务层。
- 两者可以位于同一个 Python 项目、同一个进程或同一容器中；不要求独立前端工程、独立构建和独立部署。

因此，当前方案具备前后端职责分离，但不是严格的前后端物理分离。通过让 Gradio 只调用 FastAPI API、固定请求/响应 schema，后续可以平滑替换为 React/Vue 等独立前端，实现严格前后端分离。

### 9.3 目录建议

```text
app/
  web/                 # Gradio 页面与事件处理
  api/                 # 服务接口、任务接口
  ingestion/           # 上传、校验、归档、去重
  parsers/             # docx、pptx、pdf 原生解析器
  routing/             # 静态预检与解析路由 Agent
  structure/           # 布局块、语义块、关系图和 chunk 构建
  rendering/           # 文档/幻灯片/PDF -> PNG
  extraction/          # 归一化、schema、规则和 LLM 抽取
  storage/             # SQLite、JSON、文件资产
  indexing/            # FTS5、sqlite-vec、LlamaIndex adapter
  retrieval/           # 结构化、BM25、向量、RRF、重排
  generation/          # Prompt、上下文、回答和引用
  schemas/             # Pydantic/JSON Schema
data/
  originals/
  processed/
  sqlite/
tests/
  fixtures/
  test_parsers/
  test_retrieval/
```

## 10. 验收标准

### 10.1 数据预处理验收

- [ ] 12 个源文件均能被识别，格式、大小、哈希和处理状态可查询。
- [ ] 12 个源文件中，完全相同文件或归一化内容完全一致的重复提交会被拒收，并记录 rejected_duplicate 与重复来源。
- [ ] 接受内容有差异的新版本后，10 位候选人被归并为 10 个 candidate_id；候选人 03、09 的多来源关系和最新版本关系正确。
- [ ] 8 份规则化 DOCX 的段落、顶部表格、头像和章节内容均能进入 JSON。
- [ ] 候选人 10 的浮动文本框内容不丢失，重复文本不会在 JSON 中成倍出现。
- [ ] 候选人 09 的 PPTX 文本能按视觉区域恢复姓名、联系方式、工作、项目、技能和教育等内容。
- [ ] 双栏、卡片式和浮动对象版式能生成布局块与语义块，语义块可回链到原始元素和页面坐标。
- [ ] 同一工作经历或项目的标题、时间和描述不会因布局切分而被拆到无关检索块。
- [ ] 2 份 PDF 可提取文本并保留页码；若触发 OCR，任务状态和警告可见。
- [ ] 对无文本层、整页图片或扫描件页面，路由 Agent 能选择 OCR 或视觉模型；路由结果、页面置信度和实际策略可追踪。
- [ ] 解析质量不通过时只对异常页面定向降级，不重复处理整份文档。
- [ ] 当前 10 张头像均能被识别为候选人头像；Base64 文件可解码，MIME/尺寸/哈希正确。
- [ ] 每个源文件均生成 `snap01.png` 等实际页数的快照，编号从 01 开始且不超过 99。
- [ ] 每个 JSON 通过 schema 校验，必填元数据、字段证据和质量状态齐全。
- [ ] 对标题缺失、英文缩写、图标标题和无标题的邮箱/电话等字段，系统能给出合理字段类型、推断标记、置信度和原始证据；无法确认时保留为 unknown/free_text。
- [ ] DOCX、PPTX、PDF 中的表格均先生成独立 table_block，保留行列、合并单元格、坐标、原文和快照证据。
- [ ] 工作/教育/项目表格能转换为完整记录；家属关系和紧急联系人能独立保存，不混入 candidate_contacts，也不会出现在默认人才检索结果中。
- [ ] JSON 中存在 layout_blocks、semantic_blocks 和 chunks 三层内容结构，并能追溯到解析策略和页面快照。
- [ ] 每个接受版本均能生成独立的 clean knowledge 文档；其中不包含坐标、shape_id、OCR 标记、解析器信息、重复文本和 raw_cells。
- [ ] FTS5 和向量索引仅来自质量门禁通过的 clean knowledge 文档，解析 JSON 和 evidence 不会被直接索引。
- [ ] 知识文本与原始证据可以分离展示：默认 RAG 只看到干净履历内容，用户需要时仍能回链到 JSON、源文件和页面快照。

### 10.2 建库与检索验收

- [ ] 候选人、来源文档、教育、工作、项目、技能、资产、证据、知识投影、clean chunk 和任务状态可在 SQLite 查询。
- [ ] FTS5 能命中姓名、岗位、公司、技能、工具和数字业绩。
- [ ] sqlite-vec 能按 embedding 检索语义近似的经历，并能按 `candidate_id` 过滤。
- [ ] 检索日志可分别查看结构化、BM25、向量和 RRF 结果；RRF 参数可配置。
- [ ] 同一候选人的多个 chunk 在最终候选人结果中合并，不重复占满名次。
- [ ] 默认检索只使用每个候选人最新活动来源文档的内容；历史版本不会污染默认 FTS5、向量召回和 RAG 上下文。

### 10.3 RAG 与界面验收

- [ ] 查询“上海 5 年以上 SaaS 产品经验，做过客户服务或知识库”时，候选人 04、10 等相关记录能被召回，回答引用对应经历证据。
- [ ] 查询“熟悉 Java、Spring Boot、MySQL 的后端应届生”时，候选人 01 的关键词和经历证据可定位。
- [ ] 查询“带领测试团队并做过接口自动化”时，候选人 07 的团队和自动化经历可定位。
- [ ] 明确不存在的条件不会被生成模型伪造；无结果时显示无结果及可能原因。
- [ ] Gradio 可完成上传、进度查看、档案查看、快照查看、检索和证据回链。
- [ ] 处理失败、索引失败、模型失败和快照失败均有可读错误信息与重试入口。

## 11. 测试策略

1. **解析器单元测试**：为段落、表格、浮动文本框、重复 shape、PPTX 多文本框、PDF 空文本层、整页图片和扫描件准备 fixture。
2. **字段与表格测试**：覆盖中文/英文同义词、隐式字段、图标字段、无标题邮箱/电话、DOCX/PPTX/PDF 原生表格、OCR/视觉表格、合并单元格、多行表头、工作履历表、家属关系表和紧急联系人表。
3. **解析路由测试**：覆盖原生解析、OCR、视觉模型、混合策略、页面级降级、路由缓存和质量门禁。
4. **重复与版本测试**：覆盖相同 SHA-256、不同格式但内容指纹相同、内容有差异的新版本，以及最新版本切换。
5. **内容板块测试**：覆盖单栏、双栏、卡片、跨页连续内容、页眉页脚排除、布局块到语义块归并和 chunk 完整性。
6. **数据契约测试**：JSON Schema、知识投影 Schema、Base64 解码、路径安全、候选人归并、解析计划和证据完整性。
7. **清洗与索引测试**：清除解析痕迹、重复段落和敏感字段；验证 clean chunk、FTS5、向量维度/模型版本、RRF 排名稳定性、活动版本过滤和语义边界。
8. **端到端测试**：从上传样本、路由、分级解析、内容板块分析、清洗投影、重复拒收/版本接受到前端检索结果的完整流程。
9. **回归测试**：解析器、路由 Agent 或模型版本变化后，对 10 位候选人的字段、内容块、关键证据和召回结果做差异报告。
10. **安全测试**：恶意扩展名、损坏压缩包、路径穿越、超大文件、宏文档、Prompt 注入文本和日志脱敏。

## 12. 交付阶段建议

### 阶段一：可解析与可查看

完成上传、原件归档、文件属性预检、解析路由 Agent、原生/OCR/视觉解析适配器、页面快照、布局块/语义块/table_block 模型、隐式字段推断、JSON Schema、Gradio 档案查看和基线数据导入。

### 阶段二：可检索

完成候选人归并、来源版本管理、最新版本切换、内容板块关系、清洗归一化、知识投影、SQLite 表、FTS5、sqlite-vec、clean chunk 策略、结构化过滤和 RRF 调试页。

### 阶段三：可问答与可演示

完成 LlamaIndex 基于 clean knowledge 的检索编排、证据约束 Prompt、回答引用、检索可视化、错误重试和端到端验收。

### 阶段四：增强项

加入视觉模型增强、人工合并/拆分候选人、字段修订、敏感字段权限、解析质量评估集和多模型对比。

## 13. 待确认配置项（已经澄清）

- embedding 模型、向量维度和是否允许本地模型。

  澄清：通过 .env 配置 embedding 模型、向量维度和是否允许本地模型。

- chat model、温度、最大上下文和是否启用重排模型。

  澄清：通过 .env 配置 chat model、温度、最大上下文和是否启用重排模型。

- 单文件大小、批量数量、快照 DPI/长边尺寸。

  澄清：通过 .env 配置单文件大小、批量数量、快照 DPI/长边尺寸。

- OCR 是否属于 MVP，中文 OCR 的运行时和模型来源。

  澄清：MVP 不考虑 OCR。

- 头像/联系方式在演示环境的默认脱敏策略。

  澄清：通过 .env 配置头像/联系方式在演示环境的默认脱敏策略。

- Gradio 是挂载到 FastAPI 的同进程模式，还是作为独立进程调用 FastAPI API；MVP 默认采用同进程或单容器模式。

  澄清：通过 .env 配置 Gradio 的运行模式。MVP 默认采用同进程模式。
