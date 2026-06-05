<!-- last-updated: 2026-06-05 -->
# aiDoc

aiDoc/ 是本仓库的结构化 AI 文档层，用于把长期有效的项目上下文从工具目录中抽离出来，并按主题拆分成可维护的约束文档。

## 使用方式

1. 先读取 AGENTS.MD
2. 再查看本索引文件
3. 按任务只打开相关子目录
4. 不再把项目级规则塞回工具私有目录

## 目录说明

- relations/ — 仓库结构、技术栈、依赖关系、开发流程
- modules/ — 后端分层规则、模块职责
- frontend-backend/ — 前后端契约、前端规范、工具函数复用规则
- examples/ — 讲解型示例
- memory/ — AI 记忆层

## 常用入口

| 文件 | 用途 |
|------|------|
| relations/repo-profile.md | 项目定位与技术栈全貌 |
| relations/development-workflow.md | 启动项目、安装依赖、提交规范 |
| relations/system-map.md | 系统架构、目录职责、模块映射 |
| modules/backend-layer-rules.md | 后端分层约束与代码规范 |
| modules/module-development.md | 新建后端/前端功能的完整步骤 |
| frontend-backend/boundary.md | 前后端数据契约与字段映射 |
| frontend-backend/frontend-rules.md | 前端组件、命名、路由规范 |
| frontend-backend/frontend-utils.md | 前端工具函数复用规则 |

## 维护原则

- 稳定规则放这里，不放到工具私有目录里
- 临时会话草稿不要入库
- 项目级规则先写进 AGENTS.MD，细节拆到 aiDoc/
