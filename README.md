# XMUM 小学期选课工具

针对厦门大学马来西亚分校 (XMUM) AC Online 选课系统 (`ac.xmu.edu.my`) 的自动化选课工具。支持课程余量查询和自动抢课（蹲守捡漏）。

## 功能

- **余量查询** — 一键查看所有课程的报名人数、剩余名额
- **自动抢课** — 持续监控目标课程，有空位立即提交选课
- **急速模式** — 选课开放瞬间高频提交，抢占先机
- **macOS 通知** — 选课成功时弹窗 + 声音提醒
- **断线重连** — 自动处理 SSL 断连和 Session 过期

## 项目结构

```
├── scraper.py      # 主脚本（登录、查询、抢课）
├── config.json     # 目标课程配置（课程名 + xkid + 优先级）
├── .env            # 登录凭据（不提交 git）
├── .gitignore
└── README.md
```

## 环境安装

### 1. Python 环境

需要 Python 3.10+。

```bash
python3 --version   # 确认版本 >= 3.10
```

### 2. 安装依赖

```bash
pip install requests beautifulsoup4 python-dotenv
```

或使用 conda：

```bash
conda install requests beautifulsoup4 python-dotenv
```

依赖说明：

| 包 | 用途 |
|---|---|
| `requests` | HTTP 请求（登录、选课提交） |
| `beautifulsoup4` | HTML 解析（课程表格、表单字段） |
| `python-dotenv` | 从 `.env` 文件读取环境变量 |

### 3. 配置凭据

创建 `.env` 文件：

```bash
cp .env.example .env   # 或手动创建
```

填入你的 AC Online 账号密码：

```env
XMU_USERNAME=你的学号
XMU_PASSWORD=你的密码
```

### 4. 配置目标课程

编辑 `config.json`，填入你想抢的课程：

```json
{
  "courses": [
    {"name": "课程名称", "xkid": "12345", "priority": 1},
    {"name": "另一门课", "xkid": "12346", "priority": 2}
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `name` | 课程名称（仅供显示和日志） |
| `xkid` | 选课系统内部 ID，通过 `query` 命令获取 |
| `priority` | 优先级，数字越小越先尝试 |

## 使用方法

### 查询所有课程余量

```bash
python3 scraper.py query
```

输出示例：

```
Round: Second Round | Stage: Second Stage | Credits: 3/6

=== Registered Courses ===
  MAT2002 Elementary Number Theory (3cr) — 28/30 applicants

=== Available Courses (180 total) ===
Code     Course Name                                          Cr  Quota  Apply  Left Option
--------------------------------------------------------------------------------------------
SWE2001  Python Programming in Business (Group 1)              3     30     30     0 Full
AIA1001  Agentic AI and Workflow Automation for Everyone        2     60     60     0 Full
MAT3001  Mathematical Theory of Games                          3     30     28     2 Select(24072)
```

带 `Select(xkid)` 的课程表示有余量可选，括号内的数字就是 `config.json` 需要的 `xkid`。

### 保存原始 HTML（调试用）

```bash
python3 scraper.py --dump
python3 scraper.py query --dump
```

### 自动抢课（蹲守模式）

```bash
# 默认每 5 秒一轮
python3 scraper.py grab

# 自定义间隔（秒）
python3 scraper.py grab --interval 3

# 急速模式：~0.3 秒一轮，适合选课刚开放或蹲退课
python3 scraper.py grab --rush
```

### 后台运行

```bash
# 使用 nohup 后台运行，日志输出到文件
nohup python3 -u scraper.py grab --rush > grab.log 2>&1 &

# 查看实时日志
tail -f grab.log

# 停止
kill %1   # 或 kill <PID>
```

> `-u` 参数禁用 Python 输出缓冲，确保日志实时写入文件。

## 工作原理

### 登录

POST 到 `ac.xmu.edu.my/index.php?c=Login&a=login`，使用 `requests.Session` 保持 Cookie。

### 选课页面

选课入口为 `c=Xk&a=Normal&id=<轮次ID>`，页面使用 ASP.NET 风格的 `__doPostBack` 机制：

- 选课：`__EVENTTARGET=Add`, `__EVENTARGUMENT=<xkid>`
- 退课：`__EVENTTARGET=Del`, `__EVENTARGUMENT=<xkid>`
- 翻页：`__EVENTTARGET=Page`, `__EVENTARGUMENT=<页码>`

每次请求需携带 `__VIEWSTATE` 隐藏字段，从上一次响应中提取。

### 抢课策略

`grab` 命令**不需要先加载课程页面**，直接循环提交 `Add` postback：

1. 登录并进入选课页面（获取初始 `__VIEWSTATE`）
2. 按优先级依次对每个目标课程提交 `Add` 请求
3. 检查响应中的 `alert()` 消息判断结果：
   - `"Your selection is successful."` → 选课成功
   - `"Limitation on applicant NO."` → 名额已满
   - `"Credit Limitation <= N"` → 学分超限
   - `"Schedule Conflict"` → 时间冲突
4. 成功则从监控列表移除，发送通知
5. 全部选完则退出，否则等待后重试

## 注意事项

- `ENTRY_ID` 每个选课轮次不同，需在 `scraper.py` 中更新（当前为 `1403`）
- 急速模式请求频率较高，服务器可能偶尔断开 SSL 连接，脚本会自动重试
- 轮询间隔建议不低于 0.3 秒，避免触发服务器限流
- 选课前确认学分余量是否足够，否则会持续收到 "Credit Limitation" 错误
