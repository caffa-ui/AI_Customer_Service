# SCRM AI 客服

这是一个基于 LangChain、LangGraph 和 FastAPI 的 SCRM 智能客服项目，当前包含销售导购、闲聊、普通售后、退款工单、商品/订单/物流/工单工具、RAG 售后知识检索、长对话摘要、PostgreSQL 持久会话、智能体调用监控和 HTTP 聊天接口。

## 运行环境

- Python 3.13
- DeepSeek：主客服对话、工具选择和最终回答
- Google Gemini Embedding：RAG 文档与查询向量
- Chroma：向量存储
- PostgreSQL：同一会话的 LangGraph Checkpoint 和用户归属

## 安装

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

复制 `.env.example` 为 `backend/.env`，至少配置 `DEEPSEEK_API_KEY`、`POSTGRES_DSN` 和 `MYSQL_DSN`。使用 RAG 时再配置 `GOOGLE_API_KEY`。

PostgreSQL 用户在第一次启动时需要有创建表和索引的权限。项目会幂等执行 LangGraph Checkpointer 初始化，并创建 `agent_conversations` 会话归属表；数据库本身需要提前创建。

## 启动

### 命令行

```powershell
python main.py
```

在命令行中输入消息即可对话，输入 `exit` 或 `quit` 退出。CLI 默认使用 `CLI_USER_ID=cli-user` 和 `CLI_CONVERSATION_ID=cli-default`；关闭程序后再次使用同一会话 ID，会从 PostgreSQL 恢复历史状态。

### FastAPI

```powershell
python run_api.py
```

默认监听 `http://127.0.0.1:8000`。启动后直接打开该地址即可使用登录与聊天网页；交互式 API 文档位于 `http://127.0.0.1:8000/docs`。可在 `backend/.env` 中通过 `API_HOST` 和 `API_PORT` 修改监听地址和端口。

项目使用 OAuth2 Password + Bearer JWT。初始化 MySQL 表后，需要先执行 `python set_password.py cli-user`，通过终端为已有用户安全设置登录密码；项目不提供固定默认密码。

登录并调用聊天接口：

```powershell
$tokens = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/v1/auth/token" `
    -Method Post `
    -ContentType "application/x-www-form-urlencoded" `
    -Body @{ username = "cli-user"; password = "your_cli_user_password" }

$headers = @{ Authorization = "Bearer $($tokens.access_token)" }
$body = @{
    conversation_id = "web-demo"
    message = "查询一下我的工单"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/v1/chat" `
    -Method Post `
    -ContentType "application/json" `
    -Headers $headers `
    -Body $body
```

`conversation_id` 可以省略，服务端会生成新的会话 ID，并在响应中返回。调用方需要保存该 ID，后续请求继续传入它才能恢复同一份 PostgreSQL 会话记忆。`request_id` 也可以由调用方提供，用于串联日志；省略时由服务端生成。

在 Swagger 文档中，可以先点击 `Authorize`，输入 MySQL 用户的 `user_id` 和密码。授权后再调用聊天接口，Swagger 会自动携带 Bearer 访问令牌。聊天请求体不再接收 `user_id`，可信身份只取自 JWT。

系统接口：

- `GET /health`：进程存活检查。
- `GET /ready`：聊天和认证服务生命周期是否已经完成初始化。
- `POST /api/v1/auth/token`：使用用户名密码登录，签发访问令牌和刷新令牌。
- `POST /api/v1/auth/refresh`：轮换刷新令牌并签发一对新令牌；旧刷新令牌立即失效。
- `POST /api/v1/auth/logout`：撤销当前刷新令牌。
- `GET /api/v1/auth/me`：验证访问令牌并返回当前 `user_id`。
- `POST /api/v1/auth/change-password`：校验当前密码、更新密码并撤销该用户的刷新令牌。
- `GET /api/v1/conversations`：分页列出当前用户的持久会话。
- `GET /api/v1/conversations/{conversation_id}`：读取当前用户指定会话的消息历史。
- `DELETE /api/v1/conversations/{conversation_id}`：删除会话元数据及其 PostgreSQL Checkpoint。
- `POST /api/v1/chat`：执行一轮智能体对话。

当前 API 默认只监听本机且固定单 worker。访问令牌默认有效 30 分钟，刷新令牌默认有效 7 天；每次刷新都会在 MySQL 中原子撤销旧令牌，退出登录也会撤销刷新会话。访问聊天接口时还会再次检查用户是否处于 `active` 状态。

HTTP 层会为每次请求生成或接收合法的 `X-Request-ID`，返回处理耗时，限制请求体大小和执行时间，并对登录失败进行单进程限流。默认允许当前本机网页来源跨域访问；这些值可通过 `.env.example` 中的 `CORS_ALLOWED_ORIGINS`、`API_REQUEST_TIMEOUT_SECONDS`、`API_MAX_BODY_BYTES`、`AUTH_LOGIN_MAX_ATTEMPTS` 和 `AUTH_LOGIN_WINDOW_SECONDS` 调整。

修改某个 MySQL 用户的密码：

```powershell
python set_password.py cli-user
```

脚本通过终端安全读取两次新密码，不回显内容；修改成功后会撤销该用户所有未过期的刷新令牌。

## PostgreSQL 持久会话

在 `backend/.env` 中配置：

```dotenv
POSTGRES_DSN=postgresql://scrm_user:your_password@127.0.0.1:5432/scrm_agent
POSTGRES_POOL_MIN_SIZE=1
POSTGRES_POOL_MAX_SIZE=10
POSTGRES_POOL_TIMEOUT_SECONDS=30

CLI_USER_ID=cli-user
CLI_CONVERSATION_ID=cli-default
```

持久化分为两部分：

- `agent_conversations`：保存 `conversation_id` 与 `user_id` 的归属，阻止跨用户读取会话。
- LangGraph Checkpointer 表：保存消息、摘要、用户画像、工具调用结果和图执行状态。

图调用必须始终使用同一 `conversation_id` 作为 `thread_id`。`ChatService` 每轮只提交本轮新消息，历史由 `AsyncPostgresSaver` 自动恢复，避免 `add_messages` 重复合并完整历史。

PostgreSQL 未配置或无法连接时，CLI 会明确启动失败，不会静默回退到进程内记忆。单元测试使用 `InMemorySaver` 和假模型，不要求本地运行 PostgreSQL。

Windows 下 CLI 和 `run_api.py` 都会显式使用 `SelectorEventLoop`，因为 psycopg 异步连接不支持 Uvicorn 默认选择的 `ProactorEventLoop`。请优先使用项目入口启动 API，不要绕过该兼容设置直接执行普通 Uvicorn 命令。

## 智能体监控中间件

`ChatService` 会为每次聊天生成或接收一个 `request_id`，并通过 LangChain Callback 统一监控模型与工具调用。监控范围包括：

- 请求开始、结束、状态和总耗时。
- 模型名称、消息数量、耗时、异常类型和可用的 Token 统计。
- 工具名称、参数字段名、耗时、成功或失败。

为了避免敏感数据进入日志，中间件不会记录聊天正文、Prompt、模型完整回答、工具参数值、工具返回正文、数据库密码或 API Key。`user_id` 和 `conversation_id` 会先转换为不可逆短哈希，只以 `user_ref` 和 `conversation_ref` 出现在日志中。客户端提供的 `request_id` 只允许字母、数字、点、下划线、冒号和短横线，最长 128 个字符，避免日志注入。

监控日志使用现有日志系统，写入：

```text
backend/app/logs/agent_monitoring_YYYY-MM-DD_HH.log
```

日志示例：

```text
event=request_started request_id=... user_ref=... conversation_ref=...
event=model_started model=deepseek-v4-pro message_count=4
event=tool_started tool=query_ticket arg_fields=["ticket_id"]
event=tool_finished tool=query_ticket status=ok duration_ms=35
event=request_finished status=ok duration_ms=921
```

该中间件属于智能体调用层，CLI 与 FastAPI 已共用。FastAPI 另外接入了 CORS、登录失败限流、请求超时、请求体限制和独立 HTTP 请求日志；两层共用 `request_id` 串联一次聊天调用。

## MySQL 工单查询与创建

项目运行时从 MySQL `support_tickets` 读取工单。CLI 默认用户 `cli-user` 在演示数据库中内置两条工单：

- `TK-20001`：物流工单，状态为 `processing`。
- `TK-20002`：维修工单，状态为 `pending`。

可以在对话中输入：

```text
查询一下我的工单
帮我查一下 TK-20001
```

售后智能体可调用：

- `list_my_tickets`：按当前会话的 `user_id` 查询工单列表。
- `query_ticket`：按工单号和当前 `user_id` 查询详情。
- `create_support_ticket`：用户明确同意后创建普通人工售后工单。

`user_id` 由 LangGraph 状态注入，不作为模型可填写的工具参数。

普通售后工单通过参数化 SQL 写入 MySQL，程序重启后仍可查询。工单查询和创建均使用会话中的可信 `user_id`，数据库外键保证工单用户必须存在。

## MySQL 销售工具

项目从 MySQL `products`、`product_inventory` 和 `product_promotions` 查询商品、库存与当前有效促销。商品搜索继续使用已有的筛选、评分和排序规则，数据迁移后推荐行为保持一致。

销售智能体可调用：

- `search_products`：按用途、分类、预算和价格区间搜索商品。
- `get_product_details`：查询明确商品编号的参数和说明。
- `check_inventory`：查询当前库存和是否有货。
- `get_current_promotions`：查询当前价格和促销说明。

可以尝试：

```text
推荐一款六千元以内的轻薄办公本
P-1001 有货吗
P-1002 现在有什么优惠
```

销售节点只获得商品工具，工具由图中的 `sale_tools` 执行；价格、库存和促销必须以本轮工具返回结果为准。

## MySQL 订单、物流与 RAG 售后知识

订单和物流从 MySQL `orders` 与 `order_items` 查询。

CLI 用户 `cli-user` 可以查询 `ORD-20260801` 和 `ORD-20260720`。售后智能体新增：

- `query_order`：按订单号和当前用户查询订单。
- `check_logistics`：查询当前用户订单的物流信息。
- `search_support_knowledge`：使用 Google Embedding 和 Chroma 检索售后知识文档。

订单和物流工具同样从 LangGraph 状态注入 `user_id`，不能跨用户读取订单。

知识库只使用 RAG，不再提供静态关键词回退。将 `.txt` 或 `.pdf` 文件放入：

```text
backend/app/data/knowledge/
```

项目内置 `support_knowledge.txt` 作为演示文档。在 `backend/.env` 配置 `GOOGLE_API_KEY` 后，可以提前执行增量导入：

```powershell
python ingest_rag.py
```

导入结果保存在 `backend/app/chroma_db/`，文件摘要清单保存在知识目录的 `.ingested.json`，二者都不会提交到版本控制。文件未变化时不会重复生成向量；文件更新或删除后，下次导入会同步 Chroma。

如果没有提前导入，第一次调用 `search_support_knowledge` 时也会按需初始化并增量导入。未配置 Google Key 或向量服务失败时，工具会返回“知识库暂时不可用”；知识目录为空或没有达到相关度阈值的资料时返回空结果。两种情况都不会回退到关键词匹配或编造答案。

## MySQL 业务数据源

MySQL 已是当前业务运行必需依赖，`requirements.txt` 已包含 SQLAlchemy 与 asyncmy。安装项目依赖：

```powershell
python -m pip install -r requirements.txt
```

在 `backend/.env` 中配置：

```dotenv
KNOWLEDGE_REPOSITORY=rag
MYSQL_DSN=mysql+asyncmy://scrm_reader:your_mysql_password@127.0.0.1:3306/scrm?charset=utf8mb4
MYSQL_POOL_SIZE=5
MYSQL_MAX_OVERFLOW=10
MYSQL_POOL_RECYCLE_SECONDS=1800
MYSQL_POOL_TIMEOUT_SECONDS=30
MYSQL_CONNECT_TIMEOUT_SECONDS=10
MYSQL_READ_TIMEOUT_SECONDS=30
MYSQL_PRODUCT_CANDIDATE_LIMIT=1000
```

`MYSQL_DSN` 必须使用 `mysql+asyncmy://` 协议。密码包含 `@`、`:`、`/`、`#`、`%` 等 URL 特殊字符时，需要先进行百分号编码，且不要将真实凭据提交到版本控制。

MySQL Engine 由聊天运行时统一创建，用户、工单、订单和商品 Repository 共享同一个连接池。启动阶段会执行连接检查，并把连接会话时区设为 UTC；MySQL 不可用时项目拒绝启动，避免智能体在缺少业务数据时编造回答。

MySQL 业务表定义与演示数据分别保存在：

- `backend/sql/mysql/001_schema.sql`
- `backend/sql/mysql/002_seed_demo.sql`
- `backend/sql/mysql/003_auth.sql`

当前结构包含原有业务表，以及认证专用的 `user_credentials` 和 `auth_refresh_tokens`。密码只保存 Argon2 哈希；刷新令牌表保存可撤销的令牌 ID，不保存密码或 JWT 正文。`user_id` 在 MySQL 业务表与 PostgreSQL `agent_conversations` 中使用同一标识做逻辑关联；两个数据库之间不建立跨库外键。

`003_auth.sql` 只创建认证表，不写入默认密码。依次执行建表和演示数据脚本后，请为需要登录的已有用户设置密码：

```powershell
python set_password.py cli-user
```

`set_password.py` 会交互式读取两次密码，为用户首次创建或更新 Argon2 密码哈希，并撤销该用户已有的刷新令牌。

`MySQLUserRepository` 会在创建 PostgreSQL 会话前检查用户存在且状态为 `active`，并将用户名、性别和标签注入智能体状态。MySQL 与 PostgreSQL 使用相同 `user_id` 做应用层关联，不建立跨数据库外键。

`build_graph(ticket_repository, product_repository, order_repository, knowledge_repository, checkpointer)` 支持在应用启动时分别注入 Repository 和 Checkpointer。FastAPI lifespan 通过 `create_runtime_services()` 在应用启动时统一创建 PostgreSQL、MySQL、认证服务、RAG Repository 和 `ChatService`，在关闭时释放资源；CLI 继续使用兼容的 `create_chat_service()`。旧名称 `create_postgres_chat_service()` 仍保留兼容。

JWT 配置：

```dotenv
JWT_ISSUER=scrm-agent
JWT_AUDIENCE=scrm-api
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
# 生产环境必须显式提供至少 32 字符的随机值
# JWT_SECRET=replace_with_a_random_secret
```

本地未设置 `JWT_SECRET` 时，项目会首次启动时自动生成 `backend/.jwt_secret`，该文件已被 `.gitignore` 忽略并可跨重启复用。生产和多实例部署必须通过环境变量为所有实例提供同一个安全随机密钥，不能依赖本地文件。

部署环境中预先设置的环境变量优先于 `backend/.env`。当前会话串行锁属于单进程锁，因此 `run_api.py` 固定使用单 worker；需要多 worker 时应先增加跨进程的同会话并发协调。

商品、订单和工单的生产 factory 已固定创建 MySQL Repository，不再提供静态 JSON 回退，也不再需要 `TICKET_REPOSITORY`、`PRODUCT_REPOSITORY`、`ORDER_REPOSITORY` 三个选择变量。知识库固定使用 RAG Repository，不进入 MySQL。

## 会话记忆

当前智能体使用“PostgreSQL 持久状态 + 双层上下文记忆”：

- PostgreSQL Checkpoint：跨请求、跨程序重启保存整个 LangGraph 状态。
- `state["summary"]`：长期压缩记忆。
- `state["messages"]`：最近的短期完整对话。

Supervisor、销售、闲聊、售后和售后分类都会同时读取长期摘要与最近上下文。消息超过阈值后，摘要节点会保留最近完整轮次，并将更早内容更新到 `summary`。

工具返回会在摘要时标记为“工具已确认”，用户自述与系统事实分开记录。

可在 `backend/app/config/agent.yaml` 调整：

```yaml
memory:
  min_tokens_to_compress: 3000
  keep_turns: 10
  max_summary_chars: 1200
  recent_context_messages: 20
  supervisor_context_messages: 6
```

同一 `conversation_id` 会恢复同一份 `messages`、`summary` 和用户画像；不同会话分别使用独立的 `thread_id`。会话归属表会校验 `user_id`，仅知道其他用户的会话 ID 也不能通过 `ChatService` 读取状态。

## 测试

```powershell
python -m unittest discover -s tests -v
```

路由测试使用本地假模型和 `tests/fakes/` 下的 Fake Repository，不会连接真实 MySQL，也不会调用 DeepSeek/Gemini。FastAPI 测试通过 lifespan 注入假的聊天和认证服务，验证登录、Bearer 身份、令牌刷新/重放拦截、退出、输入校验、会话 ID 和错误映射。原演示业务数据已迁移到 `tests/fixtures/`，仅供自动化测试使用，不会成为应用运行时的数据回退。

## 当前边界

- 退款目前为模拟人工审核流程：用户提交明确订单号后创建 `refund` 工单，并在独立的 `refund-*` LangGraph 线程中通过 `interrupt()` 等待审核；不会调用真实支付渠道。
- 管理员可通过 `GET /api/v1/admin/refunds` 查看待审工单，并通过 `POST /api/v1/admin/refunds/{ticket_id}/review` 提交 `approved` 或 `rejected` 审核结果。默认管理员用户 ID 为 `admin`，可用 `ADMIN_USER_IDS` 配置。
- 用户、商品、库存、促销、订单、物流和普通售后工单已经使用 MySQL；当前开发连接仍需从 `root` 更换为最小权限运行账号。
- 售后知识只通过 Google Embedding 与 Chroma RAG 检索，不再使用静态 JSON 关键词知识库。
- 应用层静态 Repository 与静态业务 JSON 已删除；自动化测试使用独立 Fake Repository 和 fixture。
- PostgreSQL 已持久化主聊天和独立退款审核线程的图状态；当前审核结果通过管理员接口恢复退款线程，用户端可继续使用主聊天会话。
- PostgreSQL 当前必须由部署者提前创建数据库；项目负责初始化 Checkpointer 表和会话归属表。
- FastAPI 已提供网页、JWT 认证、会话管理、聊天、CORS、登录限流和独立 HTTP 日志；访问令牌即时吊销及多 worker 分布式协调尚未实现，当前不应直接暴露到公网。
- `003_auth.sql` 不内置密码；首次登录前必须通过 `set_password.py` 为对应 MySQL 用户设置密码。
- RAG 已通过 `search_support_knowledge` 接入售后工具循环，最终答案仍由售后智能体统一生成。
- 真实 API 调用会产生模型费用，本次自动测试没有发起付费请求。
