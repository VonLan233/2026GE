"""HTTP 会话管理：登录、自动重试、ViewState 维护。"""

import os
import sys
import time

import requests

from .constants import (
    CYAN, GREEN, LOGIN_PAGE_URL, LOGIN_URL, NORMAL_URL, ENTRY_ID,
    RED, USER_AGENT, YELLOW, log,
)
from .parser import extract_viewstate


class Session:
    def __init__(self):
        self.session = self._new_session()
        self.logged_in = False
        self.viewstate = ""

    # ── 登录 ──────────────────────────────────

    def login(self) -> None:
        """使用 .env 中的账号密码登录，失败则退出程序。"""
        username = os.getenv("XMU_USERNAME")
        password = os.getenv("XMU_PASSWORD")
        if not username or not password:
            log("ERROR: Set XMU_USERNAME and XMU_PASSWORD in .env", RED)
            sys.exit(1)

        log(f"Logging in as {username} ...", CYAN)
        self.session.get(LOGIN_PAGE_URL)
        resp = self.session.post(LOGIN_URL, data={
            "username": username,
            "password": password,
            "user_lb": "Student",
        }, allow_redirects=True)

        if self._is_login_page(resp.text):
            hint = ""
            if "wrong" in resp.text.lower():
                hint = " (wrong username or password)"
            log(f"Login FAILED{hint} — check credentials.", RED)
            sys.exit(1)

        self.logged_in = True
        log("Login successful!", GREEN)

    def ensure_logged_in(self) -> None:
        """若尚未登录则自动触发登录流程。"""
        if not self.logged_in:
            self.login()

    # ── 页面请求 ───────────────────────────────

    def fetch_normal_page(self, page: int = 1) -> str:
        """获取 Normal 选课页面，返回原始 HTML。"""
        self.ensure_logged_in()

        if page == 1 and not self.viewstate:
            # 首次进入，使用 GET 加载入口页
            resp = self._request("GET", f"{NORMAL_URL}&id={ENTRY_ID}")
        else:
            # 翻页使用 __doPostBack
            resp = self._postback("Page", str(page))

        if self._is_login_page(resp.text):
            # Session 过期：重新登录后，先取第 1 页拿到新 ViewState，再跳到目标页
            self._relogin()
            resp = self._request("GET", f"{NORMAL_URL}&id={ENTRY_ID}")
            self.viewstate = extract_viewstate(resp.text)
            if page > 1:
                resp = self._postback("Page", str(page))

        self.viewstate = extract_viewstate(resp.text)
        return resp.text

    def do_postback(self, event_target: str, event_argument: str) -> str:
        """提交 __doPostBack 动作（Add / Del 等），返回响应 HTML。"""
        self.ensure_logged_in()
        resp = self._postback(event_target, event_argument)

        if self._is_login_page(resp.text):
            # Session 过期：重新登录并刷新 ViewState 后重试
            self._relogin()
            self.viewstate = ""
            self.fetch_normal_page(1)
            resp = self._postback(event_target, event_argument)

        self.viewstate = extract_viewstate(resp.text)
        return resp.text

    def recover(self) -> None:
        """网络故障后的尽力恢复：重新进入选课页，失败则重建 Session。"""
        self.viewstate = ""
        try:
            self.fetch_normal_page(1)
        except requests.RequestException:
            log("  Recovery failed, will retry next round ...", YELLOW)
            self._recreate_session()
            self.logged_in = False

    # ── 内部方法 ───────────────────────────────

    def _postback(self, target: str, argument: str) -> requests.Response:
        """封装 __doPostBack POST 请求。"""
        return self._request("POST", NORMAL_URL, data={
            "__EVENTTARGET": target,
            "__EVENTARGUMENT": argument,
            "__VIEWSTATE": self.viewstate,
        })

    def _request(self, method: str, url: str, max_retries: int = 3,
                 **kwargs) -> requests.Response:
        """统一的 GET/POST 请求，网络异常时按指数退避自动重试。"""
        if max_retries <= 0:
            return self.session.request(method, url, **kwargs)
        for attempt in range(max_retries):
            try:
                return self.session.request(method, url, **kwargs)
            except requests.RequestException:
                if attempt < max_retries - 1:
                    wait = 2 * (attempt + 1)
                    log(f"  Network error ({method}). Retry in {wait}s ...", YELLOW)
                    time.sleep(wait)
                    self._recreate_session()
                else:
                    raise

    def _relogin(self) -> None:
        """重置登录状态并重新登录。"""
        log("Session expired, re-logging in ...", YELLOW)
        self.logged_in = False
        self.login()

    def _recreate_session(self) -> None:
        """重建 requests.Session 以清除损坏的 SSL 连接，同时保留 Cookie。"""
        old_cookies = self.session.cookies
        self.session = self._new_session()
        self.session.cookies = old_cookies

    @staticmethod
    def _new_session() -> requests.Session:
        """创建并返回一个配置好 User-Agent 的新 Session。"""
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        return s

    @staticmethod
    def _is_login_page(text: str) -> bool:
        """判断响应是否为登录页（Session 过期标志）。"""
        return "form1" in text and "user_lb" in text
