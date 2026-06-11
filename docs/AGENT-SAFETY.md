# Agent 执行安全 — Yolo 与黑名单

> 对应代码：`friday/safety.py`、`friday/interaction_modes.py`、`friday/tools/shell.py`、`friday/tools/python_runner.py`、`friday/python_code_safety.py`  
> 威胁模型：服务仅监听 `127.0.0.1`；主要风险是 **本机其他进程拿到 API Token** 或 **用户误开 Yolo** 后的自动执行。

---

## 1. 交互模式（Ask / Agent / Yolo）

| 模式 | 写入/执行 | 审批 |
|------|-----------|------|
| **Ask** | 禁止（只读工具） | 无 |
| **Agent** | 允许（受安全设置约束） | 每次高风险操作确认 |
| **Yolo** | 工作区内自动；路径强制 `restrict_to_workspace` | 开启时确认一次，之后工作区内写入可自动通过 |

### Yolo 解锁（`POST /api/chat/yolo-unlock`）

- 仅当设置中 `interaction_mode=yolo` 且用户在前端完成「开启 Yolo」确认后，服务端会话标记为 `yolo_unlocked`。
- **未解锁**时 Yolo 与 Agent 行为相同（仍须逐项审批）。
- **已解锁**时：
  - 工作区内 **WRITE** 类工具可自动执行（不再反复弹窗）。
  - **EXEC** 类工具（PowerShell / Python / 插件安装卸载）**始终**需要审批（见 `YOLO_EXEC_REQUIRES_APPROVAL`）。
  - **非可信来源下载**在 `require_trusted_downloads=true` 时，Agent 模式须二次确认；**Yolo 已解锁会跳过该确认**（见 `safety._evaluate_download`）——这是已知权衡，勿在不可信环境长期开启 Yolo。
  - 路径仍不得超出工作区（下载到用户指定盘符除外）。

---

## 2. 黑名单策略（PowerShell / Python）

### 设计原则

1. **纵深防御**：拦截明显破坏性命令，不是完整沙箱。
2. **非穷尽**：编码、间接调用、别名、外部二进制等仍可能绕过；回归测试见 `tests/tools/test_shell.py`、`tests/tools/test_python_env.py`。
3. **归一化后匹配**：去掉 PowerShell 反引号 `` ` ``、合并空白、小写化后再跑正则（缓解简单混淆）。
4. **下载分流**：禁止 PowerShell 访问 URL / `IWR` 等，引导使用 `download_software` / `download_file`（带域名信任评估）。

### PowerShell（`friday/tools/shell.py`）

拦截示例：格式化磁盘、递归删系统盘、关机、停关键进程、改防火墙/执行策略、清事件日志、提权、写 HKLM、`-EncodedCommand`、`Invoke-Expression` / `IEX`。

### Python（`friday/tools/python_runner.py` + `friday/python_code_safety.py`）

- **运行时黑名单**：`os.system`、`subprocess(..., shell=True)`、删系统目录、`format`/`diskpart`、`ctypes.windll` 等。
- **静态分析**（`run_python` / `run_python_script`）：禁止触碰 `%AppData%\Friday`；删除/覆盖须审批；工作区内新建写入走普通审批。

---

## 3. 已知限制（审查 P3）

| 风险 | 说明 |
|------|------|
| 黑名单可绕过 | 如 `Start-Process`、调用外部 exe、分段拼接字符串等未全部覆盖 |
| Yolo 扩大面 | 解锁后工作区写入与部分下载自动执行，依赖用户判断 |
| Token 泄露 | 持 Token 可改 MCP、触发更新、导入凭据包——见更新链与 API 鉴权文档 |
| PowerShell `-ExecutionPolicy Bypass` | 有意为之以便 Agent 跑管理任务；依赖黑名单 + 用户审批 |

新增危险模式时：**先加回归测试**（含混淆用例），再改正则。

---

## 4. 回归测试

```powershell
python -m pytest tests/tools/test_shell.py tests/tools/test_python_env.py tests/agent/test_interaction_modes.py tests/tools/test_safety.py -q
```

`test_shell.py` 含反引号、大小写、`-Enc` 等 bypass 用例；`test_interaction_modes.py` 覆盖 Yolo 边界。
