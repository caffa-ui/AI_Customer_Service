# 本轮修改说明

日期：2026-08-07

本轮以“保留现有 SCRM 业务设计，让项目先可正常启动”为目标，没有重写销售、售后、闲聊、退款和摘要的核心业务规则。

## MySQL 用户凭证与 JWT 认证

| 文件 | 说明 |
| --- | --- |
| `backend/sql/mysql/003_auth.sql` | 新增 `user_credentials` 与 `auth_refresh_tokens`，密码使用 Argon2 哈希，刷新会话通过外键关联原 `users.user_id`。 |
| `backend/app/auth/` | 新增认证配置、MySQL Repository、密码校验、JWT 签发、访问令牌校验、刷新令牌原子轮换和退出撤销。 |
| `backend/app/chat/runtime.py` | 新增 `create_runtime_services()`，让 FastAPI lifespan 共享同一个 MySQL Engine 下的聊天与认证服务；CLI 入口保持兼容。 |
| `backend/app/api/routes.py` | 新增 token、refresh、logout、me 接口；聊天接口改从 Bearer JWT 获取可信 `user_id`。 |
| `backend/app/api/schemas.py` | 聊天请求删除 `user_id`，新增令牌、刷新、当前用户和退出响应模型。 |
| `set_password.py` | 新增交互式密码设置入口；密码不回显，更新后撤销该用户全部刷新会话。 |
| `.env.example`、`.gitignore` | 增加 JWT 时效/签发方配置；本地密钥文件不进入版本控制。 |
| `requirements.txt` | 增加 PyJWT、pwdlib Argon2 与 OAuth2 表单解析依赖。 |
| `tests/test_auth_service.py`、`tests/test_api.py` | 覆盖登录失败隐藏、访问/刷新令牌类型隔离、刷新轮换、重放拦截、退出撤销和受保护聊天接口。 |

认证迁移已应用到当前 MySQL，三个演示用户均已有独立密码哈希。真实 FastAPI 验收已确认登录、`/auth/me`、刷新轮换、旧令牌 401 和退出撤销均正常；验收没有调用付费模型。现有智能体图、节点、工具、MySQL 业务表、PostgreSQL Checkpoint 和 RAG 均未修改，完成后全项目 56 项单元测试通过。

## FastAPI 最小接入

| 文件 | 说明 |
| --- | --- |
| `backend/app/api/main.py` | 新增 FastAPI 应用与 lifespan，复用现有 `create_chat_service()`，统一托管 PostgreSQL、MySQL、RAG Repository 和聊天服务。 |
| `backend/app/api/routes.py` | 新增 `/health`、`/ready` 和 `/api/v1/chat`；将用户/会话越权统一映射为 403，并为未就绪、校验失败和内部异常提供稳定响应。 |
| `backend/app/api/schemas.py` | 新增请求与响应模型，限制用户/会话/请求标识符格式、字段长度和额外字段。 |
| `run_api.py` | 新增单 worker 启动入口；读取 `API_HOST`/`API_PORT`，并在 Windows 强制使用 psycopg 兼容的 Selector 事件循环。 |
| `requirements.txt` | 增加 FastAPI、Uvicorn、Pydantic 和 Starlette TestClient 当前要求的 httpx2 显式依赖。 |
| `.env.example` | 增加 API 默认监听地址和端口示例。 |
| `tests/test_api.py` | 新增 6 项隔离接口测试，不连接数据库、不调用 DeepSeek/Gemini。 |
| `README.md` | 增加 API 启动、调用、会话 ID 使用方式和当前安全边界。 |

该阶段未修改智能体图、节点、工具参数、MySQL/PostgreSQL 表结构、Checkpoint 或 RAG 实现。当时 `user_id` 仍由请求体提供，完成后全项目 48 项单元测试通过；本轮上方的 JWT 认证阶段已替换这一临时边界。

## FastAPI 接入前的最小调整

| 文件 | 说明 |
| --- | --- |
| `backend/app/agent/agent_config/llm_config.py` | `.env` 不再覆盖部署环境变量，便于后续由 FastAPI/Uvicorn 或容器注入配置。 |
| `backend/app/chat/runtime.py` | 新增通用生命周期入口 `create_chat_service()`；旧的 `create_postgres_chat_service()` 保留为兼容别名。 |
| `backend/app/chat/service.py` | 保持同一会话在单进程内串行执行，并在没有调用者和等待者后删除锁，避免 FastAPI 长期运行时锁缓存持续增长。 |
| `main.py` | CLI 切换到通用生命周期入口，行为不变。 |
| `tests/test_chat_service.py` | 新增同会话串行执行及锁释放测试。 |
| `README.md` | 增加未来 FastAPI lifespan 的最小接入示例和单 worker 边界说明。 |

本次没有安装 FastAPI，没有新增 HTTP 接口，也没有修改智能体节点、工具、数据库表、PostgreSQL Checkpoint 或 RAG 实现。

## MySQL 唯一业务运行数据源（第二阶段）

| 文件 | 说明 |
| --- | --- |
| `backend/app/product/factory.py`、`backend/app/order/factory.py`、`backend/app/ticket/factory.py` | 删除 static/mysql 选择分支，生产 factory 只创建 MySQL Repository；继续支持运行时注入共享 Engine。 |
| `backend/app/data/static_products.json`、`static_orders.json`、`static_tickets.json` | 从应用目录删除，运行时不再存在静态业务数据回退。 |
| `backend/app/product/static_repository.py`、`backend/app/order/static_repository.py`、`backend/app/ticket/static_repository.py` | 删除三个应用层静态 Repository。 |
| `tests/fixtures/` | 将原演示商品、订单和工单数据迁移为测试专用 fixture，保留原测试样例。 |
| `tests/fakes/business_repositories.py` | 新增测试专用商品、订单、工单和知识 Fake Repository；图测试显式注入，不连接真实 MySQL 或嵌入服务。 |
| `tests/test_*.py` | 去除静态数据源环境变量与应用静态 Repository 依赖。 |
| `backend/app/config/agent.yaml`、`backend/.env`、`.env.example` | 移除三个业务 Repository 选择配置；保留 MySQL 连接池、DSN 和 RAG 配置。 |
| `README.md` | 说明 MySQL 已是唯一生产业务数据源以及测试数据的新位置。 |

第二阶段没有更改智能体节点、路由、工具参数、MySQL 表结构、PostgreSQL 记忆或 RAG 逻辑。删除后完整 41 项测试通过。

## MySQL 唯一业务运行数据源（第一阶段）

| 文件 | 说明 |
| --- | --- |
| `backend/app/database/mysql.py` | 新增共享异步 MySQL Engine、DSN与连接池参数校验、启动 `SELECT 1` 检查，并统一会话时区为 UTC。 |
| `backend/app/user/` | 新增MySQL用户与标签Repository；用户不存在或状态非 `active` 时禁止创建或读取PostgreSQL会话。 |
| `backend/app/chat/runtime.py` | PostgreSQL会话池之外只创建一个MySQL连接池，统一注入用户、工单、订单和商品Repository并在退出时关闭。 |
| `backend/app/chat/service.py` | 在写入PostgreSQL会话前验证MySQL用户，并将用户名、性别和标签注入LangGraph状态。 |
| `backend/app/ticket/mysql_repository.py` | 工单列表和详情补齐主题、描述字段；实现事务化普通售后工单写入和UUID工单号。 |
| `backend/app/order/mysql_repository.py` | 新增按 `order_id + user_id` 隔离的订单、明细和物流读取。 |
| `backend/app/product/mysql_repository.py` | 新增商品、库存、有效促销查询，兼容MySQL JSON字段。 |
| `backend/app/product/search.py` | 提取静态与MySQL共用的商品筛选、评分和排序规则。 |
| `backend/app/*/factory.py` | 工单、订单、商品工厂均支持共享Engine的MySQL实现，同时暂时保留static回退。 |
| `backend/app/*/service.py` | 数据库异常只记录安全的异常类型，不记录DSN、业务参数或对话正文。 |
| `requirements.txt` | MySQL成为当前业务运行源后，将SQLAlchemy与asyncmy纳入主依赖。 |
| `backend/.env`、`.env.example`、`backend/app/config/agent.yaml` | 当前业务运行源切换为MySQL，知识库继续使用RAG，并增加连接池、超时和商品候选上限配置。 |
| `tests/test_chat_service.py` | 新增MySQL用户画像注入、未知用户阻止建会话和停用用户拒绝访问测试。 |

真实MySQL验证覆盖用户、标签、商品搜索、库存、有效促销、订单明细、物流、工单详情、跨用户隔离与工单持久创建；共享连接会话时区为UTC。静态Repository与JSON尚未删除，只用于回退和单元测试，等待第二阶段确认。

## MySQL DSN 配置整理

| 文件 | 说明 |
| --- | --- |
| `backend/app/ticket/factory.py` | 将五个分散的 MySQL 环境变量合并为 `MYSQL_DSN`，校验必须使用 `mysql+asyncmy://` 且包含用户名、主机和数据库名。 |
| `backend/.env`、`.env.example` | 改用单一 MySQL DSN；后续第一阶段已将业务Repository正式切换到MySQL。 |
| `README.md` | 更新 MySQL 配置示例，并说明密码中特殊字符需要进行 URL 编码。 |
| `tests/test_ticket_factory.py` | 覆盖 DSN 创建、缺少配置和误用 PostgreSQL 协议的校验。 |

## MySQL 业务表初始化

| 文件 | 说明 |
| --- | --- |
| `backend/sql/mysql/001_schema.sql` | 新增8张与现有智能体业务工具字段对应的 MySQL 表，包含主键、外键、金额检查和常用查询索引。 |
| `backend/sql/mysql/002_seed_demo.sql` | 新增幂等演示数据：3个用户、4个用户标签、4个商品、库存、5条促销、3个订单及明细、4个工单。 |
| `README.md` | 说明 MySQL 表范围、与 PostgreSQL `user_id` 的逻辑关联，以及当前 Repository 接入边界。 |

已在现有 MySQL `langgraph_db` 中实际执行并验证：8张目标表创建成功，8个外键有效，无孤立订单或工单；MySQL 工单 Repository 对 `cli-user`、`demo-user`、`test-user-003` 分别返回2、1、1条工单，并成功阻止跨用户查询。PostgreSQL 中已有的 `cli-user` 会话与 MySQL 用户主键一致。

真实 `MYSQL_DSN` 已从 `.env.example` 安全迁移到被程序实际读取且被版本控制忽略的 `backend/.env`，示例文件已恢复为占位值。当前第一阶段已切换到MySQL运行；连接账号仍为高权限 `root`，后续必须改为最小权限账号。

## 核心运行文件

| 文件 | 说明 |
| --- | --- |
| `main.py` | 由空文件补齐为命令行启动入口，支持连续对话和 `exit`/`quit` 退出。 |
| `backend/app/agent/agent_config/graph.py` | 由空文件补齐 LangGraph，连接 Supervisor、销售、闲聊、售后分类、普通售后、退款工单和摘要节点。 |
| `backend/app/agent/agent_config/llm_config.py` | 明确加载 `backend/.env`，保留 DeepSeek V4 Pro，移除导入模块时自动发送模型请求的副作用。 |

## 配置与工具修复

| 文件 | 说明 |
| --- | --- |
| `backend/app/utils/config_handler.py` | 将配置路径从错误的 `.yml` 改为实际 `.yaml`；使用 `safe_load`；兼容字典和 `config("key")` 两种现有调用方式。 |
| `backend/app/utils/path_tool.py` | 移除每次获取路径时的调试输出。 |
| `backend/app/utils/file_handler.py` | 统一包导入；修复目录不存在时的返回值；修复误返回 `type(files)` 而非文件列表的问题；兼容 YAML 列表后缀。 |
| `backend/app/utils/logger_handler.py` | 统一包导入，修正日志格式中的行号占位符。 |
| `backend/app/utils/prompt_handler.py` | 统一 `app.utils` 包导入。 |
| `backend/app/config/prompt.yaml` | 将 Prompt 路径修正为实际 `.txt` 文件，新增 `rag_prompt` 配置。 |
| `backend/app/prompt/rag_prompt.txt` | 补充原本为空的 RAG Prompt，要求依据资料回答并禁止编造。 |

## RAG 与模型修复

| 文件 | 说明 |
| --- | --- |
| `backend/app/config/rag.yaml` | 经确认后，将已停止服务的 `text-embedding-004` 升级为 `gemini-embedding-2`。 |
| `backend/app/model/factory.py` | Gemini 对话和 Embedding 改为按需初始化，未配置 Google Key 时不再阻塞主客服启动；补充清晰的 Key 缺失错误。 |
| `backend/app/rag/vector_store.py` | 改用按需 Embedding；将 Chroma 目录改为项目绝对路径；修正 `K`/`k` 配置名不一致。 |
| `backend/app/rag/rag_service.py` | 修正 `vector_store` 包导入；改用按需 Gemini 模型；新增正确拼写 `rag_summarize`，同时保留原 `rag_summerize` 作为兼容别名。 |

## 新增工程文件

| 文件 | 说明 |
| --- | --- |
| `requirements.txt` | 记录项目当前核心依赖版本，包含 PDF 加载所需 `pypdf`。 |
| `.env.example` | 提供不含真实密钥的环境变量示例。 |
| `.gitignore` | 忽略真实 `.env`、虚拟环境、IDE 文件、日志、Chroma 库和 Python 缓存。 |
| `README.md` | 增加安装、配置、启动、测试和当前功能边界说明。 |
| `tests/test_graph_routes.py` | 使用本地假模型覆盖销售、闲聊、普通售后和退款四条路由。 |
| 各目录 `__init__.py` | 补充 Python 包标识，使导入行为更稳定。 |

## 未做的重大扩展

- 没有将退款工单写入真实数据库。
- 没有实现人工审核的 checkpoint 持久化与流程恢复。
- 没有新增 FastAPI/Web 接口。

## 验证结果

- 项目 Python 文件全部通过静态语法解析。
- 配置文件与四个 Prompt 全部可正常加载。
- `gemini-embedding-2` 可被当前 `langchain-google-genai` 适配器构造。
- 当前销售、闲聊、普通售后、退款、业务工具循环、RAG 导入和记忆处理共 25 项自动化测试通过。
- CLI 启动和退出检查通过。
- 为避免消耗用户 API 额度，未自动发起真实 DeepSeek/Gemini 请求。

## 工单查询工具扩展

| 文件 | 说明 |
| --- | --- |
| `backend/app/ticket/models.py` | 新增统一 `Ticket` 模型，对智能体返回时自动隐藏内部 `user_id`。 |
| `backend/app/ticket/repository.py` | 定义异步 `TicketRepository` 协议，隔离智能体与具体数据库。 |
| `backend/app/ticket/static_repository.py` | 新增默认静态 Repository，不接数据库也能演示查询。 |
| `backend/app/ticket/mysql_repository.py` | 新增异步 MySQL 参考适配器，使用固定参数化 SQL 和用户权限过滤。 |
| `backend/app/ticket/service.py` | 新增工单业务服务，统一成功、未找到、身份缺失和后端故障返回格式。 |
| `backend/app/ticket/factory.py` | 根据 `TICKET_REPOSITORY` 选择 static/mysql，MySQL 依赖只在选中时加载。 |
| `backend/app/data/static_tickets.json` | 新增三条静态工单，包含权限隔离测试用户。 |
| `backend/app/agent/tool/ticket_tools.py` | 新增 `list_my_tickets` 和 `query_ticket`，`user_id` 由 `ToolRuntime` 安全注入。 |
| `backend/app/agent/nodes/support_node.py` | 改为异步可绑定工具节点，工单数据必须来自工具。 |
| `backend/app/agent/agent_config/graph.py` | 增加 `support_tools` ToolNode 和“售后→工具→售后”循环；`build_graph(repository)` 支持依赖注入。 |
| `main.py` | CLI 改为异步 `ainvoke`，启动时创建 Repository，退出时关闭，与未来 FastAPI lifespan 保持一致。 |
| `requirements-mysql.txt` | 新增可选 SQLAlchemy/asyncmy 依赖，不影响默认静态模式。 |
| `backend/app/agent/tool/middleware.py` | 日志改为只记录参数字段名和消息类型，不记录工单参数值或对话正文。 |
| `tests/test_ticket_service.py` | 覆盖列表查询、详情查询、跨用户隔离和工具参数隐藏。 |
| `tests/test_graph_routes.py` | 在原有四条路由之外，新增完整工单 ToolNode 循环测试。 |

该扩展没有新增 FastAPI，也没有连接或修改任何真实 MySQL 数据库。

## 进程内长期记忆修复

| 文件 | 说明 |
| --- | --- |
| `backend/app/agent/memory.py` | 新增统一记忆配置、长期摘要读取、最近消息截取和分类上下文格式化。 |
| `backend/app/config/agent.yaml` | 新增压缩 Token 阈值、保留轮数、摘要长度和节点上下文数量配置。 |
| `backend/app/agent/nodes/supervisor_node.py` | Supervisor 同时读取长期摘要和最近消息，可结合上下文理解“第二个”、“它”等指代；闲聊节点改为真正读取 `summary`。 |
| `backend/app/agent/nodes/sale_node.py` | 销售节点在客户画像和最近对话之外读取长期摘要。 |
| `backend/app/agent/nodes/support_node.py` | 售后节点读取长期摘要，但当前工单/物流状态仍强制以本轮工具结果为准。 |
| `backend/app/agent/nodes/support_classifier_node.py` | 售后细分分类器新增摘要和近期上下文，改善省略表达的判断。 |
| `backend/app/agent/nodes/summarize_node.py` | 压缩参数改为配置化；摘要使用固定结构；区分用户自述与工具确认事实；强制长度上限；移除 GBK 控制台不兼容的 Emoji 日志字符。 |
| `backend/app/prompt/sale_prompt.txt` | 同步长期记忆 Prompt 说明。 |
| `backend/app/prompt/support_prompt.txt` | 同步长期记忆及工具结果优先级说明。 |
| `backend/app/prompt/supervisor_prompt.txt` | 同步长期摘要与最近上下文占位。 |
| `tests/test_memory.py` | 新增节点记忆注入、分类上下文、状态隔离、工具结果摘要与摘要长度测试。 |

这一阶段没有新增 checkpoint 或持久化数据库；程序重启后的记忆恢复将在后续阶段单独实现。

## 冗余清理与提示词统一

| 文件 | 说明 |
| --- | --- |
| `backend/audit_flow.py` | 删除未接入正式图的旧版聊天节点草稿。 |
| `backend/ee.gitignore` | 删除 Git 不会识别且规则已被根目录 `.gitignore` 覆盖的错误命名文件。 |
| `backend/app/agent/nodes/supervisor_node.py` | 删除与独立节点文件重复的 `sale_node` 和 `support_classifier_node`；保留主管与闲聊节点。主管提示词改为从文本文件加载。 |
| `backend/app/agent/nodes/sale_node.py` | 删除内嵌提示词，统一从 `sale_prompt.txt` 加载。 |
| `backend/app/agent/nodes/support_node.py` | 删除内嵌提示词，统一从 `support_prompt.txt` 加载；保留现有工单工具约束和退款边界。 |
| `backend/app/utils/prompt_handler.py` | 为提示词加载结果增加进程内缓存和返回类型标注，避免每次请求重复读取文件。 |
| `backend/app/prompt/supervisor_prompt.txt` | 作为主管节点提示词唯一来源，保留长期记忆、近期上下文和三路由输出约束。 |
| `backend/app/prompt/sale_prompt.txt` | 作为销售节点提示词唯一来源，保留客户画像、长期记忆和导购规则。 |
| `backend/app/prompt/support_prompt.txt` | 作为售后节点提示词唯一来源，保留工具结果优先、工单查询和禁止编造规则。 |

本次整理没有改变 LangGraph 的节点连接、路由名称、工具参数、Repository 接口或 FastAPI 后续接入方式。清理与提示词统一完成后，当时的完整 14 项单元测试全部通过。

## 销售与售后工具完善

| 文件/目录 | 说明 |
| --- | --- |
| `backend/app/product/` | 新增商品 Model、Repository、静态实现、Service 和工厂，支持搜索、详情、库存和促销查询。 |
| `backend/app/order/` | 新增订单与物流 Model、带用户隔离的 Repository、静态实现、Service 和工厂。 |
| `backend/app/knowledge/` | 新增售后知识 Model、Repository、Service 和工厂；后续将静态实现替换为纯 RAG Repository。 |
| `backend/app/data/static_products.json` | 新增四条静态商品数据，覆盖商品参数、库存和促销演示。 |
| `backend/app/data/static_orders.json` | 新增三条静态订单和物流数据，包含跨用户隔离样例。 |
| `backend/app/data/knowledge/support_knowledge.txt` | 提供通过 Google Embedding 导入 Chroma 的售后知识演示文档。 |
| `backend/app/agent/tool/product_tools.py` | 新增 `search_products`、`get_product_details`、`check_inventory`、`get_current_promotions`。 |
| `backend/app/agent/tool/support_tools.py` | 新增 `query_order`、`check_logistics` 和 `search_support_knowledge`。 |
| `backend/app/agent/tool/ticket_tools.py` | 新增 `create_support_ticket`；用户身份继续由可信状态注入。 |
| `backend/app/ticket/` | 扩展工单创建协议与 Service；静态 Repository 支持进程内创建、列表和详情查询，不改写 JSON。 |
| `backend/app/agent/nodes/sale_node.py` | 改为异步可绑定工具节点，结构与售后工具节点一致。 |
| `backend/app/agent/agent_config/graph.py` | 新增 `sale_tools` 循环；扩展 `support_tools`；四类 Repository 均支持启动阶段依赖注入。 |
| `backend/app/prompt/sale_prompt.txt` | 增加商品搜索、详情、库存、促销和禁止编造约束。 |
| `backend/app/prompt/support_prompt.txt` | 增加订单、物流、知识检索和经用户同意后创建普通工单的约束。 |
| `tests/test_product_service.py` | 覆盖商品搜索、详情、库存、促销和工具 Schema。 |
| `tests/test_support_services.py` | 覆盖订单隔离、物流查询、RAG Repository 接线和工具参数隐藏。 |
| `tests/test_graph_routes.py` | 新增销售商品工具循环与售后物流工具循环测试。 |

本阶段没有修改退款智能体，没有连接真实数据库，也没有新增 FastAPI。销售、售后、权限隔离、工具循环、记忆和原有路由共 24 项单元测试全部通过。

## 纯 RAG 售后知识库

| 文件 | 说明 |
| --- | --- |
| `backend/app/knowledge/rag_repository.py` | 新增按需初始化的 RAG Repository；首次知识查询时增量导入文档，并将 Chroma 检索结果统一转换为知识文章。 |
| `backend/app/knowledge/static_repository.py` | 删除静态关键词 Repository，知识检索不再回退到 JSON。 |
| `backend/app/data/static_support_knowledge.json` | 删除静态关键词知识数据。 |
| `backend/app/data/knowledge/support_knowledge.txt` | 新增 RAG 演示文档，用户可在同目录继续添加 TXT/PDF。 |
| `backend/app/rag/vector_store.py` | 整理为增量文档导入、变更/删除同步、相似度检索和来源元数据维护；Chroma 继续使用 Google Embedding。 |
| `backend/app/model/factory.py` | 保留 `gemini-embedding-2`；移除固定 `task_type`，由适配器分别对文档使用 `RETRIEVAL_DOCUMENT`、对查询使用 `RETRIEVAL_QUERY`。 |
| `backend/app/config/agent.yaml` | 将知识数据源固定为 `rag`。 |
| `backend/app/config/chroma.yaml` | 将知识目录限定为 `data/knowledge`，导入清单放在知识目录中。 |
| `ingest_rag.py` | 新增显式增量导入入口，便于部署和维护阶段预先构建 Chroma。 |
| `tests/test_support_services.py` | 使用假向量存储验证 RAG 延迟初始化、只初始化一次、来源信息及工具 Schema，不访问 Google。 |

RAG 只负责检索相关文档，最终答案由现有售后智能体生成一次，避免重复模型调用。普通 CLI 启动不会初始化 Google Embedding；只有执行 `ingest_rag.py` 或首次调用知识工具时才需要 `GOOGLE_API_KEY`。当前 65 个项目 Python 文件通过语法解析，25 项单元测试全部通过，自动验证没有发起真实 DeepSeek/Gemini 请求。

## PostgreSQL 跨重启、跨请求持久会话

| 文件 | 说明 |
| --- | --- |
| `requirements.txt` | 增加官方 `langgraph-checkpoint-postgres` 与 `psycopg` 异步连接池依赖。 |
| `backend/app/conversation/models.py` | 新增会话归属模型。 |
| `backend/app/conversation/repository.py` | 新增会话 Repository 协议和跨用户访问异常。 |
| `backend/app/conversation/postgres_repository.py` | 新增 PostgreSQL 会话归属表初始化、原子创建和用户校验。 |
| `backend/app/conversation/in_memory_repository.py` | 新增仅供无数据库单元测试使用的会话归属实现。 |
| `backend/app/chat/service.py` | 新增 CLI/FastAPI 共用的 `ChatService`；每轮仅提交新消息，以 `conversation_id` 作为 LangGraph `thread_id`。 |
| `backend/app/chat/runtime.py` | 新增 PostgreSQL 连接池、`AsyncPostgresSaver`、业务 Repository 和图的统一异步生命周期。 |
| `backend/app/agent/agent_config/graph.py` | `build_graph` 新增 Checkpointer 注入，原节点、路由和工具循环保持不变。 |
| `main.py` | CLI 改为通过持久 `ChatService` 调用，不再在 Python 变量中手动传递完整历史状态。 |
| `.env.example` | 增加 PostgreSQL DSN、连接池和 CLI 会话标识示例。 |
| `tests/test_chat_service.py` | 覆盖服务重建后的状态恢复、会话隔离、用户归属校验和增量消息不重复。 |

PostgreSQL 未配置或连接失败时会明确阻止 CLI 启动，不会静默降级为进程内记忆。现有摘要节点继续负责控制上下文长度，Checkpoint 负责保存摘要与剩余消息；销售、售后、RAG 和业务工具节点没有重写。

真实连接验收时发现 psycopg 异步模式不支持 Windows 默认 `ProactorEventLoop`，因此 `main.py` 在 Windows 上改用 `SelectorEventLoop`；Linux/macOS 继续使用默认 `asyncio.run()`。

## 智能体监控中间件接入

| 文件 | 说明 |
| --- | --- |
| `backend/app/middleware/context.py` | 新增基于 `ContextVar` 的请求上下文；原始用户与会话 ID 转为不可逆短哈希。 |
| `backend/app/middleware/agent_monitoring.py` | 新增模型、工具和请求级 Callback 监控，记录耗时、字段名、Token 和异常类型，不记录正文或参数值。 |
| `backend/app/chat/service.py` | 每轮创建监控上下文并将 Callback 注入 LangGraph 配置；`ChatResponse` 新增 `request_id`。 |
| `backend/app/agent/tool/middleware.py` | 删除未接入正式图、仅适用于 `create_agent` 的旧中间件实现。 |
| `tests/test_agent_monitoring.py` | 覆盖上下文清理、标识哈希、Token 日志、工具 ToolNode 传播、异常隐私、请求 ID 校验和并发隔离。 |
| `tests/test_chat_service.py` | 继续验证持久会话，并通过实际 Callback 路径回归模型监控。 |

中间件只观察并重新抛出原异常，不改变 ToolNode 的用户友好错误行为。现有业务节点、工具参数、PostgreSQL 表和 LangGraph 路由没有修改；FastAPI 的认证、CORS、限流和 HTTP 日志中间件留到 API 阶段实现。

## FastAPI 收口与 Web 工作台

| 文件/目录 | 说明 |
| --- | --- |
| `backend/app/api/main.py` | 挂载 Web 静态资源，接入 CORS、HTTP 请求中间件、登录限流器和统一的未知异常响应。 |
| `backend/app/api/middleware.py` | 新增 HTTP 请求 ID、耗时日志、请求体大小限制和超时处理；日志不记录请求或响应正文。 |
| `backend/app/api/rate_limit.py` | 新增与当前单 worker 边界一致的登录失败滑动窗口限流。 |
| `backend/app/api/routes.py` | 根路径返回网页；新增修改密码、会话列表、会话历史和会话删除接口。聊天接口默认沿用 HTTP 请求 ID。 |
| `backend/app/api/schemas.py` | 补充密码与会话管理接口的请求/响应模型。 |
| `backend/app/auth/` | 新增密码修改逻辑；MySQL 中原子更新密码并撤销该用户全部刷新令牌。 |
| `backend/app/conversation/` | Repository 补充按用户列出、读取和删除；继续强制会话归属隔离。 |
| `backend/app/chat/service.py` | 补充会话列表、历史读取和删除；删除时同步清理 PostgreSQL Checkpoint。 |
| `backend/app/web/` | 新增无构建依赖的响应式登录/聊天工作台，支持令牌自动刷新、会话管理和修改密码。 |
| `.env.example` | 补充 CORS、HTTP 超时、请求体限制和登录限流配置样例。 |
| `tests/` | 补充 HTTP 中间件、登录限流、修改密码、网页资源及会话管理回归测试。 |

本阶段保留现有 LangGraph 业务节点、路由、工具和退款设计，没有引入前端框架，也没有执行真实 DeepSeek/Gemini 对话。FastAPI 根地址现在直接提供可操作网页，`/docs` 继续保留为接口调试入口。

## 公开仓库发布前安全整理

| 文件 | 说明 |
| --- | --- |
| `backend/sql/mysql/003_auth.sql` | 移除固定演示密码及可直接使用的 Argon2 哈希，只保留认证表结构。 |
| `README.md` | 删除固定登录密码，改为指导部署者通过 `set_password.py` 首次设置密码。 |

`set_password.py` 原本已经支持为 `users` 表中的已有用户首次创建认证记录，因此无需修改当前认证代码；这一整理不会连接或修改现有 MySQL 数据库。
