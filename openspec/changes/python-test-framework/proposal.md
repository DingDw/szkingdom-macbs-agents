## Why

现有 `macbs-base/bin64/test-new.py` 只能以脚本级方式初始化框架并交互式执行固定用例，数据库实例信息和并发控制也散落在脚本中，难以复用、组合和在持续集成中运行。需要一个可导入、可编排的本地 Python 测试框架，让业务测试同时覆盖 Python 逻辑和 C++ 功能号，并安全支持多实例、多线程场景。

## What Changes

- 新增 Python 测试框架包，复用 `test-new.py` 的动态库路径准备、依赖加载、`KcpsFrameInit/Execute/Exit` 生命周期。
- 提供带结构化参数和结构化结果的功能号调用 API，并分配稳定的 worker 线程索引。
- 初始化时按声明顺序解析 instances.json 的全部 GaussDB 实例连接信息，第一项作为 C++ 默认初始化配置，并提供按 `instid` 切换的线程局部连接 API。
- 提供插件注册机制，兼容普通 Python 方法与 C++ 功能号插件。
- 提供“场景 → 步骤 → 任务”三级编排：场景内步骤只能串行，每个步骤包含多个任务，步骤内任务可串行或线程池并发；提供步骤完成屏障、超时、失败传播和分层结果汇总。
- 增加示例配置、插件、场景及单元测试，不修改 C++ 业务动态库 ABI。
- 将依赖的第三方组件及其传递依赖预先下载到独立的 `dependencies/` 目录，随框架交付，支持离线安装和运行；按目标操作系统、CPU 架构、Python 版本及 ABI 分别准备依赖包。

## Capabilities

### New Capabilities
- `native-frame-runner`: 管理 C++ 框架生命周期并调用功能号。
- `gaussdb-instance-context`: 管理 GaussDB 实例配置和线程局部数据库连接。
- `plugin-and-scenario-orchestration`: 注册插件任务，场景内步骤固定串行，步骤内任务支持串行/并发。

### Modified Capabilities

无。

## Impact

新增独立 Python 包及 CLI/示例目录，依赖 Python 3.9+、标准库 `ctypes`/`threading`/`concurrent.futures`，以及可选的 GaussDB Python 驱动（优先 psycopg，必要时支持 pyodbc）。运行时依赖 `macbs-base/bin64` 的配置和 C++ 动态库；需要记录 native 调用的错误码、错误消息和异常。提案只覆盖日终清算测试调用，不改变生产流程或数据库脚本。

交付增加独立依赖目录、精确版本与文件校验清单、联网下载工具、离线安装工具及中文离线部署说明。依赖范围包含启用的数据库适配器及其原生运行库、测试/检查工具和安装所需组件；离线安装不得依赖开发机缓存或临时联网补包。Python 解释器及操作系统基础环境须在交付说明中明确版本与安装前提。

## 新增约束

- 新增统一交互入口，严格按“解析全部数据库实例 → 读取插件配置并注册 → 读取 C++ frame 配置 → 框架初始化及功能号 0 系统初始化 → 读取场景目录配置 → 提示选择场景”执行。支持重复选择执行和正常退出，整个会话复用同一 native 实例。
- 统一入口移除 `init_param` 和 `profile` 参数；C++ 初始化所需的 dbtype、driver、server、port、database、username、password、ODBC 扩展和 XA 参数全部并入 `instances.json` 的实例条目，按 JSON 声明顺序取第一项作为默认配置，不接受 instid 启动参数。

- 场景层不提供串并行模式；`mode`、`max_workers`、`timeout` 属于步骤，`plugin`、`params`、`instid` 属于任务。旧场景级 `mode` 及 `Step(name, plugin)` 配置须显式迁移，不能静默继续执行错误层级。
- 所有新增 Python 模块、公开类、公开方法、关键分支、线程/连接生命周期和 ctypes 边界 SHALL 编写详尽的中文代码注释，说明业务目的、输入输出、线程安全性、资源所有权和异常处理；禁止仅用“调用接口”“处理数据”等无意义注释。
- 包 SHALL 按 `runtime`、`native`、`db`、`plugin`、`scenario`、`cli` 明确分层，模块职责、依赖方向和线程模型 SHALL 在说明文档中维护。
- SHALL 提供中文 README、API 参考、配置说明、插件开发指南、场景编排指南、并发与故障排查文档；示例必须可对应执行。
- SHALL 将预下载依赖存放在 `macbs-base/bin64/python_test_framework/dependencies/`，与 `macbs_test/` 源码分离；依赖缺失、损坏或平台不兼容时给出明确错误，安装和运行阶段不得自动访问公网包源。相关验收规格纳入现有 `specs/python-test-framework/spec.md`。
