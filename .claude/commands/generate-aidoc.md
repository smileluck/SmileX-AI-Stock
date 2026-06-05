---
description: 分析项目代码库并生成 AGENTS.MD + aiDoc/ 分层约束文档体系
---

# 项目约束文档生成器

你是项目约束文档生成器。你的任务是分析当前项目的代码库，然后按照 aiDoc 标准结构生成一套完整的 AI 协作约束文档。

用户提示：$ARGUMENTS

---

## 运行模式

根据 `$ARGUMENTS` 解析运行模式：

| 参数 | 行为 |
|---|---|
| （空） | 全量生成：探测项目并生成/覆盖所有 aiDoc 文件 |
| `--incremental` | 增量更新：读取已有 aiDoc，对比代码变化，只更新过时的文件 |
| `--scope backend` | 只重新生成 `modules/backend-layer-rules.md`、`examples/backend/` 等后端相关文件 |
| `--scope frontend` | 只重新生成 `frontend-backend/frontend-rules.md`、`frontend-backend/frontend-utils.md`、`examples/frontend/` |
| `--scope relations` | 只重新生成 `relations/` 下 3 个文件 |
| `--scope memory` | 只重新生成 `memory/` 下文件 |
| `--dry-run` | 只输出阶段 1 探测结果和生成计划，不写文件 |

**增量更新规则**（`--incremental` 时适用）：
- 每个文件头部维护 `<!-- last-updated: YYYY-MM-DD -->` 注释
- 先读取已有 aiDoc 文件，再用 `git diff` 判断自上次更新以来哪些代码目录有变化
- 只重新生成受影响范围内的文件
- 用户手动调优过的内容（非 AI 生成标记）应尽量保留

---

## 执行流程

严格按照以下三个阶段执行。每个阶段完成后向用户简要报告进度。

### 阶段 1：项目探测

#### 1.1 优先使用 graphify

若 `graphify-out/graph.json` 存在：
- 运行 `graphify query "project architecture and module structure"` 获取整体架构
- 运行 `graphify query "frontend-backend module mapping"` 获取前后端模块映射
- 运行 `graphify path "backend" "frontend"` 获取跨栈关系
- 用 graphify 结果替代部分手工 Glob/Grep 探索，跳过 1.2–1.3 中已被 graphify 覆盖的探测项

若 graphify 不存在，继续下面的手工探测。

#### 1.2 项目结构探测

- 列出根目录下的顶层目录和关键文件
- 识别是否有前端/后端/全栈目录分离
- 扫描每个顶层目录的子目录结构（深度 2-3 层即可）

#### 1.3 技术栈识别

读取以下文件（如存在）提取技术栈信息：

- `package.json` / `pnpm-workspace.yaml` / `lerna.json` → 前端依赖和脚本
- `pyproject.toml` / `requirements.txt` / `Pipfile` / `setup.py` → Python 后端依赖
- `go.mod` / `go.sum` → Go 后端依赖
- `pom.xml` / `build.gradle` → Java 后端依赖
- `Cargo.toml` → Rust 后端依赖
- `.nvmrc` / `.node-version` / `.python-version` → 运行时版本
- `Dockerfile` / `docker-compose.yml` → 部署配置

**框架识别策略**：优先从依赖列表自动匹配，而非硬编码特征。扫描 `dependencies`/`devDependencies`/`install_requires` 中是否包含以下关键词：

| 依赖关键词 | 框架/技术 |
|---|---|
| `fastapi`, `uvicorn` | FastAPI |
| `django` | Django |
| `flask` | Flask |
| `hono` | Hono |
| `fastify` | Fastify |
| `express`, `koa`, `nestjs` | Node.js 后端 |
| `gin`, `gorm`, `fiber` | Go (Gin/Fiber) |
| `spring-boot` | Spring Boot |
| `actix`, `axum` | Rust (Actix/Axum) |
| `vue`, `vite` + `.vue` | Vue |
| `react`, `.jsx`/`.tsx` | React |
| `angular` | Angular |
| `svelte`, `@sveltejs` | Svelte/SvelteKit |
| `next` | Next.js |
| `nuxt` | Nuxt |

未覆盖的框架通过依赖名 + 目录结构综合判断。

#### 1.4 代码模式探测

- 后端：读取 2-3 个典型的 endpoint/controller、service、model 文件，识别分层模式
- 前端：读取 2-3 个典型的页面组件、API 封装、状态管理文件，识别组件模式
- 识别响应/请求的统一格式（如果有）
- 识别认证/鉴权机制
- 识别数据库访问模式（ORM 原生/sqlalchemy/typeorm/gorm/prisma 等）

**示例模块选择策略**（优先级从高到低）：

1. CRUD 完整的模块：同时拥有 model + schema + service + endpoint
2. 最近修改的模块：更能反映当前代码风格（用 `git log --format="" --name-only` 辅助判断）
3. 特性丰富的模块：包含分页、认证、关联关系等特性，覆盖面更广

#### 1.5 项目类型判定

根据探测结果，判定项目类型：

- **fullstack**：同时有前后端代码
- **backend-only**：仅有后端代码
- **frontend-only**：仅有前端代码

### 阶段 2：按模板生成文件

根据阶段 1 的探测结果，按以下顺序生成文件。

**自适应规则**：
- **backend-only**：跳过 `frontend-backend/frontend-rules.md`、`frontend-backend/frontend-utils.md`、`examples/frontend/`，`boundary.md` 改为 API 接口契约
- **frontend-only**：跳过 `modules/backend-layer-rules.md`、`examples/backend/`，`boundary.md` 改为 API 消费契约
- **fullstack**：生成全部文件

**并行生成**：同一并行组内的文件可以同时生成，组间按顺序执行。

| 顺序 | 并行组 | 文件 |
|---|---|---|
| 1 | — | `AGENTS.MD` |
| 2 | — | `aiDoc/README.md` |
| 3 | A | `aiDoc/relations/repo-profile.md`、`aiDoc/relations/development-workflow.md`、`aiDoc/relations/system-map.md` |
| 4 | B | `aiDoc/modules/backend-layer-rules.md`、`aiDoc/modules/module-development.md` |
| 5 | C | `aiDoc/frontend-backend/boundary.md`、`aiDoc/frontend-backend/frontend-rules.md`、`aiDoc/frontend-backend/frontend-utils.md` |
| 6 | D | `aiDoc/examples/backend/*.md`（model、schema、service、endpoint、router） |
| 7 | D | `aiDoc/examples/frontend/*.md`（api、view、utils-usage） |
| 8 | E | `aiDoc/examples/README.md` |
| 9 | F | `aiDoc/memory/` 全部文件 |

`--scope` 模式下只生成对应范围的并行组。

每生成一个并行组后，向用户简要报告进度。

---

#### 文件 1：`AGENTS.MD`

项目根目录的 AI 协作规则唯一真源。

内容要求：

```markdown
<!-- last-updated: YYYY-MM-DD -->
# AGENTS.MD

## 目的

本文件是本仓库内 AI 协作规则的唯一真源。

[工具目录].codex/[/].claude/[/].cursor/[/].trae/] 下的规则文件仅作为兼容适配层，不能再次演变成各自独立维护的 project rule 副本。

## 读取顺序

1. AGENTS.MD
2. aiDoc/README.md
3. 按任务读取 aiDoc/ 子目录
4. 仅在当前工具确实依赖时，再读取工具目录下的适配文件

若内容冲突，以 AGENTS.MD 为准。

## 仓库概览

[根据探测结果列出根目录和关键子目录的职责]

## 工程规则

### 架构
[根据实际分层模式填写，如 Endpoint -> Service -> Model]

### 前后端协作 / API 契约
[根据实际响应格式和约定填写]

### 模块与目录
[根据实际目录结构填写]

### 示例文档
[固定文本：aiDoc/examples/ 是讲解型示例层]

### 记忆规则
[固定文本：long-term/ 稳定偏好，business/ 每次业务需求]

### 文档维护
[固定文本：高层在 AGENTS.MD，细节在 aiDoc/]

### 代码读取约束
[固定文本：不读 node_modules/、.venv/、__pycache__/、vendor/ 等]

## AI 文档索引
[列出所有 aiDoc/ 文件路径]
```

---

#### 文件 2：`aiDoc/README.md`

文档索引和使用指南。

内容要求：

```markdown
<!-- last-updated: YYYY-MM-DD -->
# aiDoc

aiDoc/ 是本仓库的结构化 AI 文档层，用于把长期有效的项目上下文从工具目录中抽离出来，并按主题拆分成可维护的约束文档。

## 使用方式

1. 先读取 AGENTS.MD
2. 再查看本索引文件
3. 按任务只打开相关子目录
4. 不再把项目级规则塞回工具私有目录

## 目录说明

- relations/: 仓库结构、技术栈、依赖关系、开发流程
- modules/: 后端分层规则、模块职责
- frontend-backend/: 前后端契约、前端规范、工具函数复用规则（如适用）
- examples/: 讲解型示例
- memory/: AI 记忆层

## 常用入口

[每个文件一行描述]

## 维护原则

- 稳定规则放这里，不放到工具私有目录里
- 临时会话草稿不要入库
- 项目级规则先写进 AGENTS.MD，细节拆到 aiDoc/
```

---

#### 文件 3：`aiDoc/relations/repo-profile.md`

项目定位与技术栈。

内容要求：

- **项目定位**：根据 package.json/pyproject.toml 的 name/description、README.md、用户提示推断
- **后端技术栈**：列出语言、框架、ORM、数据库、缓存、迁移工具、认证方式等
- **前端技术栈**：列出框架、构建工具、UI 库、状态管理、路由、样式方案等
- **包管理**：uv/pip/npm/pnpm/yarn/go mod 等
- **核心特性**：表格列出项目特有的关键特性（统一响应格式、ID 策略、认证方式等）

---

#### 文件 4：`aiDoc/relations/development-workflow.md`

开发流程与提交规范。

内容要求：

- **推荐开发顺序**：根据实际分层设计开发步骤
- **前后端协作**：后端先接口、前端并行、联调验证
- **分支策略**：main/develop/feature/hotfix
- **提交规范**：type(scope): description 格式
- **环境与依赖**：具体的安装、启动、迁移命令
- **API 文档**：Swagger/ReDoc 地址（如有）

---

#### 文件 5：`aiDoc/relations/system-map.md`

系统架构与组件关系。

内容要求：

- **根目录职责**：表格列出每个顶层目录的用途
- **后端分层关系**：根据实际分层模式绘制（如 Router → Controller → Service → Model）
- **核心基础设施**：表格列出基础设施目录及其职责
- **前端数据流**（如有前端）：API 封装 → 状态管理 → 路由 → 视图 → 类型声明
- **模块对应关系**：后端模块 ↔ 前端页面的映射
- **配置文件**：列出关键配置文件及其用途

---

#### 文件 6：`aiDoc/modules/backend-layer-rules.md`（有后端时生成）

后端分层约束。

内容要求：

- **总原则**：严格分层，不跨层调用
- **Model 层**：基类继承、字段声明方式、表名规则、存放位置
- **Schema/DTO 层**：请求/响应基类、序列化规则、验证方式
- **Service 层**：纯业务逻辑、方法签名模式、异常处理、查询优化
- **Controller/Endpoint 层**：参数提取、响应格式化、分页处理
- **Router 层**：路由注册方式
- **错误码分配**（如有）：列出已使用的错误码范围
- **所有规则必须引用实际代码中的类名和文件路径**

---

#### 文件 7：`aiDoc/modules/module-development.md`（有后端时生成）

模块开发指南。

内容要求：

- **新建后端模块**：完整步骤（创建目录 → 定义模型 → Schema → Service → Endpoint → Router → 注册 → 迁移）
- **新建前端功能**（如有前端）：完整步骤（定义类型 → API 函数 → i18n → 页面 → 生成路由）
- **设计原则**：自包含、遵循现有模式
- **引用真实的参考文件路径**

---

#### 文件 8：`aiDoc/frontend-backend/boundary.md`（前后端项目适用）

前后端边界与数据契约。

内容要求：

- **责任边界**：后端/前端各自的职责表格
- **统一响应结构**：根据实际代码填写 JSON 结构和字段说明
- **统一分页结构**（如有）：字段说明
- **字段命名规范**：snake_case / camelCase
- **关键类型桥接**：如果有特殊类型转换（如 bool ↔ string），必须详细说明转换流程和涉及的代码位置
- **时间字段**（如有特殊处理）：格式和时区
- **变更规则**和**完成前检查清单**

---

#### 文件 9：`aiDoc/frontend-backend/frontend-rules.md`（有前端时生成）

前端开发规范。

内容要求：

- **基础规则**：HTTP 请求方式、状态管理、路由
- **命名规范**：文件、组件、变量、API 函数的命名约定表格
- **TypeScript/类型要求**（如适用）
- **组件规范**：公共组件/页面组件的位置、Props 定义方式
- **页面规范**：新增页面必须完成的步骤
- **样式规范**：CSS 方案优先级
- **国际化规范**（如有 i18n）
- **环境变量**
- **常用脚本命令**：表格列出
- **代码注释要求**

---

#### 文件 10：`aiDoc/frontend-backend/frontend-utils.md`（有前端时生成）

前端工具函数复用规则。

内容要求：

- **核心原则**：先查现有工具，不重复造轮子
- **关键工具**：列出 src/utils/ 或类似目录下的工具函数，说明用途
- **工作区子包**（如有 monorepo）：列出每个包的职责
- **强制使用场景清单**：表格列出场景和必须使用的工具

---

#### 文件 11：`aiDoc/examples/README.md`

```markdown
# 示例层

aiDoc/examples/ 是讲解型示例层，告诉 AI 每一层应该按什么标准组织和书写。

## 用途

- 示例不是要求逐字复制，而是展示项目标准的代码组织方式
- 当 AI 需要新增某一层文件时，应先阅读对应示例

## 后端开发阅读顺序
[列出后端示例文件]

## 前端开发阅读顺序（如有前端）
[列出前端示例文件]

## 原则

- 仓库真实代码与示例不一致时，以真实代码为准，并更新示例
```

---

#### 文件 12-16：`aiDoc/examples/backend/*.md`（有后端时生成）

为后端的每一层生成一个示例文件：

- `model-example.md`：ORM 模型示例（展示基类继承、字段声明、关联关系）
- `schema-example.md` 或 `dto-example.md`：请求/响应 Schema 示例
- `service-example.md`：Service 层示例（展示方法签名、异常处理）
- `endpoint-example.md` 或 `controller-example.md`：API 端点示例
- `router-example.md`：路由注册示例

每个示例文件格式：

```markdown
<!-- last-updated: YYYY-MM-DD -->
# [层名]示例

## 用途
[说明这个示例展示什么]

## 核心原则
[2-3 条关键规则]

## 示例
[从项目中读取的真实代码示例，去除敏感信息]

## 关键点
[解释示例中的关键设计决策]

## 真实参考文件
- [实际文件路径]
```

**重要**：示例代码必须从项目实际代码中提取，而非凭空编写。如果项目中没有足够的示例代码，基于探测到的模式编写符合项目风格的代码。

---

#### 文件 17-19：`aiDoc/examples/frontend/*.md`（有前端时生成）

- `api-example.md`：API 封装示例
- `view-example.md`：页面组件示例
- `utils-usage-example.md`：工具函数使用示例

格式与后端示例一致。

---

#### 文件 20-24：`aiDoc/memory/` 记忆层

`memory/README.md`：

```markdown
# 记忆层

aiDoc/memory/ 是 AI 的记忆层。

## 目录说明

- long-term/: 长期稳定的用户偏好、协作方式
- business/: 每次用户提出的业务需求记录

## 使用规则

- 用户提出业务需求时，AI 必须新增或更新一条 business/ 记忆
- 沉淀为稳定模式时，提炼到 long-term/
- 临时草稿不入库
```

`memory/project-memory.md`：

```markdown
# 项目记忆索引

## 长期记忆
暂无。

## 业务需求记忆
暂无。

## 维护说明
- 新增记忆时创建文件并更新此索引
- 过时记忆及时清理
```

`memory/long-term/README.md`：

```markdown
# 长期记忆

存放跨任务、跨会话长期有效的用户偏好和协作约束。

## 规则

- 只记录经过多次验证的稳定模式
- 每条记忆包含：规则描述、适用场景、来源
- 过时记忆及时删除
```

`memory/business/README.md`：

```markdown
# 业务需求记忆

存放每次用户提出的业务需求记录。

## 规则

- 用户提出业务需求时，必须新增或更新一条记录
- 使用 TEMPLATE.md 作为新记录模板
- 记录完成后在 project-memory.md 中更新索引

## 需求索引
暂无。
```

`memory/business/TEMPLATE.md`：

```markdown
# 业务需求模板

## 需求描述
<!-- 简要描述需求内容 -->

## 状态
<!-- 待开发 / 开发中 / 已完成 / 已取消 -->

## 涉及范围

### 后端
<!-- 涉及的模块、模型、接口 -->

### 前端
<!-- 涉及的页面、组件、API -->

## 约束与备注
<!-- 特殊的业务规则、限制条件 -->

## 相关文件
<!-- 列出涉及的关键文件路径 -->

## 记录日期
<!-- YYYY-MM-DD -->
```

---

### 阶段 3：适配层处理

#### 3.1 扫描所有工具目录

不仅检查已知目录，还要扫描根目录下所有以 `.` 开头且可能包含规则文件的目录：

**已知工具目录**：
- `.trae/rules/project_rules.md`
- `.cursor/rules/`
- `.claude/` 下的 CLAUDE.md 或规则文件
- `.codex/` 下的规则文件
- `.github/copilot-instructions.md`
- `.windsurf/`
- `.aider/`

**自动扫描**：
```bash
# 列出所有 .开头的目录中可能包含规则/指令的文件
ls -d .*/  # 检查是否有遗漏的 AI 工具目录
```

对于任何包含规则/instructions 类文件的 `.` 目录，都应处理为适配层。

#### 3.2 改写为薄适配层

如果规则文件内容较长（超过 50 行），将其改写为薄适配层：

```markdown
---
tool: [trae/cursor/claude/codex/copilot/windsurf/aider]
role: compatibility-adapter
canonical_source: /AGENTS.MD
structured_context: /aiDoc
---

# [工具名] 规则适配层

本文件只用于兼容 [工具名] 现有的自动加载路径。

## 真实规则入口

请按下面顺序读取：

1. /AGENTS.MD
2. /aiDoc/README.md
3. /aiDoc/ 中与当前任务相关的文件

## 适配层约束

- 不要在这里扩写项目级规则
- 项目级规则变更时，先更新 /AGENTS.MD 与 /aiDoc/
- 工具目录只保留薄适配层职责
```

---

## 写作风格要求

所有文档必须遵循以下风格：

1. **简洁指令性语言**：使用"必须"/"应该"/"禁止"，无填充文本
2. **精确路径引用**：每个规则引用实际文件路径和类名/函数名（如 `app/models/common/page.py:PageRequest`）
3. **清晰 Markdown 层次**：使用 `##`/`###` 组织，善用表格
4. **文档间交叉引用**：引用其他 aiDoc 文件时使用相对路径
5. **中文为主**：代码标识符和技术术语保持英文
6. **内容来源真实**：所有技术细节必须来自实际代码探测，不可凭空编造

## 生成完成后的验证

生成全部文件后，**实际执行**以下验证步骤：

### 自动验证（必须执行）

1. **索引完整性**：读取生成的 AGENTS.MD，提取 AI 文档索引中列出的所有路径，用 Glob 逐一确认文件存在
2. **路径真实性**：用 Grep 搜索所有生成文件中引用的代码路径（如 `app/models/xxx.py`），确认引用的文件存在
3. **符号一致性**：用 Grep 搜索 boundary.md 中引用的类名/函数名（如 `PageRequest`、`ResponseModel`），确认在代码中确实存在
4. **示例参考有效性**：提取所有示例文件的"真实参考文件"路径，用 Glob 确认存在

### 报告输出

向用户输出以下内容：

```
## 验证结果

### 通过
- [x] 索引完整性：N/N 文件已索引
- [x] 路径真实性：N/N 路径有效
- [x] 符号一致性：N/N 符号已验证
- [x] 示例参考：N/N 参考文件存在

### 失败（如有）
- [ ] 路径不存在：xxx
- [ ] 符号未找到：xxx

## 生成文件清单
[列出所有生成/更新的文件及大小]
```
