## Context

`test-new.py` 在模块导入期间修改运行库路径并加载 `kcps_frame`，随后以 JSON 字节调用 C ABI；`KcpsFrameInit`/`KcpsFrameExit` 非线程安全，而 `KcpsFrameExecute` 明确支持 worker 线程。C++ 业务通过 `instname` 选择连接，系统初始化代码也会执行 `DBSelect`。测试框架需要把这些进程级状态和测试级状态分开。

## Goals / Non-Goals

**Goals:** 提供可导入的 NativeFrame、GaussInstancePool、插件注册器和场景执行器；保证单次进程初始化、线程局部实例选择、C++ 并发 worker 编号、可诊断结果；支持 Windows/Linux 路径和驱动配置。

**Non-Goals:** 修改 C++ ABI、实现生产级连接池或事务代理、替代 pytest/unittest、在线执行数据库脚本、支持跨进程共享同一个已初始化框架。

## Decisions

1. **分层包结构**：`runtime` 负责动态库与生命周期，`native` 负责 `execute(func_id, payload, worker_id)`，`db` 负责配置解析和线程局部连接，`plugin`/`scenario` 负责扩展与编排。以 `ctypes.CDLL` 对齐现有 C ABI，显式设置 `argtypes/restype` 并复制返回字节后解析 JSON。
2. **进程级生命周期 +锁**：`FrameRuntime.initialize()` 使用锁和状态机确保只初始化一次；退出注册为显式 `close()` 和 atexit 兜底。初始化配置路径、库目录、DBTYPE、worker 数由构造参数传入，避免导入副作用。
3. **worker 分配**：场景执行器使用线程池；每个线程通过 `threading.local()` 保存 worker id，由单调计数器分配且不复用活动 id。native execute 捕获 C++ 返回中的 `RESULTCODE/EXTPARAM`，统一为 `CallResult`，并保留原始 JSON。
4. **数据库驱动**：配置文件采用 JSON（可另加 YAML 适配器），顶层 `instances` 按声明顺序映射 instid；每个条目包含 Python driver/server/port/database/user/password 及 native 子对象（dbtype、单一 C++ driver、ODBC 扩展、XA 参数）。默认使用 psycopg/psycopg2；通过驱动适配器可选 pyodbc。每个线程首次使用 instid 创建自己的连接并缓存，`use_instance(instid)` 仅切换当前线程上下文；`connection()` 未选择实例时抛出明确异常。
5. **插件协议**：`@plugin(name)` 注册 `PluginContext -> value` 的 Python callable；`native_plugin(name, func_id)` 是薄封装，调用同一 NativeFrame。插件不得隐式修改全局实例，需通过 context.db 显式切换。
6. **场景模型**：采用 `Scenario(name, steps)` → `Step(name, tasks, mode, max_workers, timeout)` → `Task(name, plugin, params, instid)`。场景中的步骤始终按列表串行；只有步骤内任务可配置 `serial` 或 `parallel`。当前步骤的所有已启动任务及其资源清理均结束且步骤成功后，才允许开始下一步骤。CLI 加载相同三级模型，不提供场景级并行开关。

## Risks / Trade-offs

- [C++ 动态库或依赖缺失] → 初始化前检查平台目录和依赖，错误包含实际路径，并提供 dry-run 配置校验。
- [C++ 内部仍存在未声明的全局状态] → 默认每个 worker 使用独立请求参数；提供并发 smoke test，文档标明进程内共享 memdb 的限制。
- [数据库连接泄漏] → 线程结束后提供 `close_thread_connection()`，场景执行器在 finally 清理；关闭框架时关闭主线程及可追踪连接。
- [驱动差异] → 驱动接口只暴露 execute/fetch/commit/rollback/close，GaussDB 连接串字段保留原始扩展参数。

## Migration Plan

先在联网准备环境生成目标平台的依赖交付包，再将框架源码、示例配置与完整 `dependencies/` 一并复制到目标机器，执行离线安装和环境检查。现有 `test-new.py` 保持不变。先运行 dry-run 和 mock 插件测试，再在具备动态库及 GaussDB 的环境运行 native/database smoke test。升级必须同时更新锁定清单和依赖包；回退时恢复对应版本的完整交付包并重建独立虚拟环境。

## 统一交互入口设计

新增 `cli.interactive.run_framework(...)` 作为可调用入口，`python -m macbs_test` 作为命令行入口；保留现有单场景 CLI。入口只协调流程，初始化辅助从示例提取到 `runtime.bootstrap`，插件配置加载放在 `plugin.loading`，场景目录加载放在 `scenario.loading`，框架模块不得反向导入 examples。

入口严格依次执行：
1. 构造 GaussInstancePool，读取全部数据库实例信息，此时不主动建立数据库连接。
2. 读取插件 JSON 并完成注册。格式为 `{"plugins":[{"name":"插件名","type":"python","target":"可信模块:方法"},{"name":"功能号插件","type":"native","func_id":1}]}`。拒绝重复名、未知类型、无效方法及非法功能号；注册阶段不调用任务。Python 模块导入可能执行顶层代码，使用者须提供无初始化副作用的可信插件模块。
3. 读取 frame XML，校验正整数 worker_number、功能号 0 及配置插件所需功能号；从已加载的 `instances.json` 中按 `instid` 取得 native 初始化字段并构造连接串。删除 `init_param.json` 和 `profile` 参数，避免同一实例存在两份配置。
4. 完成 KcpsFrameInit 和串行功能号 0 初始化，必须收到明确成功结果；随后才能读取场景目录配置。
5. 场景目录 JSON 使用 `{"scenarios":[{"file":"场景文件.json"}]}`，文件相对于目录配置所在位置，加载为已有三级模型。拒绝空目录、重名场景、未知插件/实例和超出 native 容量的步骤。
6. 提示按从 1 开始的编号或完整场景名选择，非法/空输入重新提示，不执行默认场景；q/exit/退出或输入结束退出。一次只运行一个场景，完成后返回菜单，同一会话只初始化一次。

全部命令行路径在切换工作目录前转为绝对路径。每次执行生成独立 JSON 报告并展示状态和报告位置；任务失败后允许继续选择，会话曾有失败则正常退出码为 1，全部成功或未选择为 0，启动/配置异常为 2，用户中断为 130。场景加载失败、菜单退出或中断均释放 native 和主线程数据库连接；线程内连接仍由任务作用域清理，native 关闭前等待在途场景线程结束。错误记录启动阶段及异常类型，不打印初始化密码或连接串。

本轮只实施统一入口及必要提取、配置、注释、示例和测试，不宣称完成原有跨 runtime 生命周期及完整 Linux 依赖管理待办；不增加第三方依赖，不执行真实联调。使用替身和事件记录验证严格顺序、重复选择仅初始化一次、失败阻止后续阶段和退出清理。

## Open Questions

- 是否将包纳入 macbs-base 的统一构建/发布产物，或仅作为 `bin64` 下本地工具交付。
- CI 是否提供可复现的 GaussDB 实例和动态库许可证。

## 模块边界与文档约束

包固定划分为 `runtime`（平台库与生命周期）、`native`（功能号 API 与结果模型）、`db`（实例配置、驱动和线程局部上下文）、`plugin`（插件协议与注册）、`scenario`（步骤编排与执行器）、`cli`（命令行适配）。依赖只能由上层指向下层，`db` 和 `native` 不得反向依赖 `scenario`；跨模块数据通过明确的数据类/协议传递。

每个源文件开头 SHALL 有模块职责注释；每个公开符号和关键私有辅助方法 SHALL 有中文 docstring/注释，至少说明目的、参数、返回值、异常、线程安全和资源释放责任。ctypes 指针生命周期、native 返回缓冲区复制、线程局部变量和连接关闭路径必须在代码旁说明。README、API 文档、配置样例和插件/场景教程与代码同步更新，并在任务验收中检查链接和示例。

## 第三方依赖离线交付

### 独立目录与版本管理

统一使用 `macbs-base/bin64/python_test_framework/dependencies/`，不将第三方源码、wheel 或动态库混入 `macbs_test/`。目录按目标环境标识隔离，每个标识记录操作系统、CPU 架构、Python 主次版本、ABI，以及 Linux 系统库兼容性信息；Windows x64、Linux x86_64、Linux ARM64 的制品不可混用。仅对已提供完整依赖并完成验证的组合声明支持，不把 Python 3.9+ 理解为任意版本均可安装。

每个目标环境下分别存放 Python wheel、原生依赖和版本锁定文件；目录根清单记录组件名称、精确版本、目标环境、用途（运行/测试/安装）、原始下载来源、相对路径、SHA-256 和许可证。清单不得记录仓库访问令牌或数据库凭据。

### 联网准备与离线安装分离

新增 `tools/` 下的依赖准备和离线安装工具，保持独立于六个业务模块；两类工具均编写中文职责注释、参数说明和失败处理说明。只有显式执行的依赖准备工具可以访问包源；初始化、导入、CLI 运行及离线安装均不触发下载。

准备工具根据目标环境锁定清单，下载直接和传递依赖到本地目录。Python 组件优先交付兼容 wheel；没有兼容 wheel 时，在匹配目标环境的联网构建机生成 wheel 并一起交付，不允许离线安装时临时下载编译工具或构建依赖。下载结束必须校验完整性，实际依赖文件是交付内容，只有依赖名称或下载脚本不算完成。

安装工具先校验目标平台、Python、文件完整性及原生依赖，再使用独立虚拟环境，仅从指定本地目录安装精确版本；禁止远程 URL、包索引和缓存回退。安装所需工具本身也须可从本地取得，或明确列入经过检查的系统前置条件。默认运行依赖和测试/检查依赖分别锁定，数据库适配器按启用组合准备；不得在缺少已选适配器时静默回退到另一个驱动。

### 原生依赖与运行条件

按启用驱动收集所需 libpq、GaussDB ODBC 驱动、ODBC 管理器及其运行库，标明哪些已包含在 wheel、哪些需要独立安装，避免仅安装 Python 包却缺少底层动态库。可合法分发的第三方组件应放入 `dependencies/`；需厂商授权取得的驱动或安装包由准备流程接收本地文件并校验后纳入离线交付，不得假定目标机能够联网获取。

MACBS 自有 C++ 动态库和运行配置沿用 `bin64`，Python 解释器、操作系统基础环境和有效许可证列为明确前置条件。离线检查必须逐项报告缺失内容。离线运行指不访问公网包源，调用测试数据库仍需具备到指定 GaussDB 的连接条件。

### 验收与文档

在对应目标环境的新建虚拟环境中禁用外部包源访问、禁止依赖下载缓存，验证从交付目录安装、依赖一致性检查、关键模块导入、CLI dry-run 和 mock 单元测试。数据库驱动与 native 库加载、实际测试数据库调用另行验证并记录环境，不以 mock 通过替代。覆盖缺包、校验失败、平台/ABI 错误，确保失败时不尝试联网补齐。

中文离线部署文档必须包含依赖目录约定、平台矩阵、联网下载步骤、复制交付步骤、离线安装、前置条件、驱动选择、校验方法、升级/回退及排障。原任务的已完成状态不代表离线能力已验收；新增任务须独立完成并留存验证记录。

## 场景、步骤和任务的执行契约

### 模型与配置

`scenario/models.py` 定义三个独立模型，`scenario/runner.py` 只负责执行，`scenario/loading.py` 负责 JSON/Python 模块加载，`cli` 负责参数和报告输出。场景必须至少有一个步骤，每步至少有一个任务；同场景步骤名、同步骤任务名唯一，插件须在开始任何任务前全部解析成功。步骤默认 `mode="serial"`，并发时 `max_workers` 为正整数；`timeout` 为可选的正数秒数，使用单调时钟计算整个步骤的截止时间。

```json
{
  "name": "准备后执行",
  "steps": [
    {"name": "准备", "mode": "serial", "tasks": [
      {"name": "准备甲", "plugin": "prepare", "params": {"batch": "甲"}},
      {"name": "准备乙", "plugin": "prepare", "params": {"batch": "乙"}}
    ]},
    {"name": "执行", "mode": "parallel", "max_workers": 2, "tasks": [
      {"name": "执行甲", "plugin": "execute", "params": {"batch": "甲"}},
      {"name": "执行乙", "plugin": "execute", "params": {"batch": "乙"}}
    ]}
  ]
}
```

任务 `params` 深拷贝到独立 `PluginContext.metadata["payload"]`，上下文同时带有场景名、步骤名、任务名和 worker 编号；可选 `instid` 只设置本任务所属线程的数据库上下文。任务结束在同线程清理任务创建的连接并恢复之前的线程上下文，避免线程池复用串库。任务调用 Python 插件或同一 native 功能号 API；场景层不重新初始化 C++ 框架。

### 顺序、失败和超时

串行步骤逐任务执行，首个失败后其余任务标记 `skipped`；并发步骤仅在本步骤内使用线程池，异常独立记录，收集所有已提交任务，不因单个任务结束就推进后续步骤。任一步骤失败或超时，剩余步骤及其任务全部标记 `skipped`。

步骤超时时取消尚未启动任务，已运行的 Python/native 调用不能被安全强杀，必须等待其返回及清理；报告如实记录 `timeout` 或 `cancelled`，不得假称它们已中止，后续步骤不运行。串行模式在每次调用前后检查截止时间，超时也不意味着能够立即返回。对 native 调用的硬超时或强制终止不在本次修改范围。

报告结构为场景结果含 `steps`，步骤结果含 `tasks`；三层均记录名称、状态和耗时，任务记录插件、结果、异常及实际 worker 编号。即使并发完成顺序不同，报告始终按配置声明顺序排列。所有路径（成功、失败、跳过、取消）保留完整层级。

### 迁移与验证

移除旧场景级 `mode/max_workers/timeout`；将并发参数移到对应步骤，把原来的插件项转换为步骤中的 `Task`。JSON 中出现旧场景级并行字段或步骤直接包含 `plugin` 时，执行前给出迁移错误。Python 接口采用新构造参数，不自动猜测旧配置含义。

本次仅实现三级模型纠正及必要的插件/数据库上下文/CLI 接入。使用屏障和事件的确定性 mock 测试验证：步骤之间绝不重叠、步骤内串行顺序、步骤内实际并发及上限、失败后跳过、超时后等待已运行任务退出、参数/连接隔离及报告层级。不执行此前暂缓的真实数据库/C++ 联调。
