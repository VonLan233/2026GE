"""公共常量、ANSI 颜色及日志工具。"""

import os
from datetime import datetime

# ── 请求地址 ───────────────────────────────────

BASE_URL = "https://ac.xmu.edu.my"
LOGIN_PAGE_URL = f"{BASE_URL}/index.php"
LOGIN_URL = f"{BASE_URL}/index.php?c=Login&a=login"
NORMAL_URL = f"{BASE_URL}/student/index.php?c=Xk&a=Normal"
ENTRY_ID = "1403"  # 选课轮次入口 ID，每轮不同，需手动更新

# ── HTTP ──────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# ── ANSI 颜色 ──────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── 路径 ───────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── 日志 ───────────────────────────────────────

def log(msg: str, color: str = "") -> None:
    """打印带时间戳的彩色日志。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{RESET}")
