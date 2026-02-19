#!/usr/bin/env python3
"""XMUM 小学期选课 — 余量查询 + 自动抢课"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://ac.xmu.edu.my"
LOGIN_PAGE_URL = f"{BASE_URL}/index.php"
LOGIN_URL = f"{BASE_URL}/index.php?c=Login&a=login"
NORMAL_URL = f"{BASE_URL}/student/index.php?c=Xk&a=Normal"
ENTRY_ID = "1403"  # from the Entry button on the index page

# ANSI colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log(msg, color=""):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{RESET}")


def notify_macos(title, message):
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}" sound name "Glass"'],
            check=False,
        )
    except FileNotFoundError:
        pass


def notify_sound():
    try:
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Hero.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


# ──────────────────────────────────────────────
# Session & Login
# ──────────────────────────────────────────────

class Session:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        })
        self.logged_in = False
        self.viewstate = ""

    def login(self):
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

        if "form1" in resp.text and "password" in resp.text.lower() and "Wrong" in resp.text:
            log("Login FAILED — check credentials.", RED)
            sys.exit(1)

        self.logged_in = True
        log("Login successful!", GREEN)

    def ensure_logged_in(self):
        if not self.logged_in:
            self.login()

    def _is_login_page(self, text):
        return "form1" in text and "user_lb" in text

    def _get_with_retry(self, url, max_retries=3):
        """GET with automatic retry on network errors."""
        for attempt in range(max_retries):
            try:
                return self.session.get(url)
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait = 2 * (attempt + 1)
                    log(f"  Network error (GET): {e}. Retry in {wait}s ...", YELLOW)
                    time.sleep(wait)
                    self._recreate_session()
                else:
                    raise

    def _recreate_session(self):
        """Recreate session to clear broken SSL state, preserving cookies."""
        old_cookies = self.session.cookies
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        })
        self.session.cookies = old_cookies

    def fetch_normal_page(self, page=1):
        """Fetch the Normal enrollment page. Returns HTML text."""
        self.ensure_logged_in()

        if page == 1 and not self.viewstate:
            # Initial GET to enter the Normal page
            resp = self._get_with_retry(f"{NORMAL_URL}&id={ENTRY_ID}")
        else:
            # POST with __doPostBack for pagination
            resp = self._post_with_retry(NORMAL_URL, {
                "__EVENTTARGET": "Page",
                "__EVENTARGUMENT": str(page),
                "__VIEWSTATE": self.viewstate,
            })

        if self._is_login_page(resp.text):
            log("Session expired, re-logging in ...", YELLOW)
            self.logged_in = False
            self.login()
            resp = self._get_with_retry(f"{NORMAL_URL}&id={ENTRY_ID}")

        # Update viewstate
        soup = BeautifulSoup(resp.text, "html.parser")
        vs = soup.find("input", {"name": "__VIEWSTATE"})
        if vs:
            self.viewstate = vs.get("value", "")

        return resp.text

    def _post_with_retry(self, url, data, max_retries=3):
        """POST with automatic retry on network errors."""
        for attempt in range(max_retries):
            try:
                return self.session.post(url, data=data)
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait = 2 * (attempt + 1)
                    log(f"  Network error: {e}. Retry in {wait}s ...", YELLOW)
                    time.sleep(wait)
                    self._recreate_session()
                else:
                    raise

    def do_postback(self, event_target, event_argument):
        """Submit a __doPostBack action (Add, Del, etc.)."""
        self.ensure_logged_in()
        resp = self._post_with_retry(NORMAL_URL, {
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": event_argument,
            "__VIEWSTATE": self.viewstate,
        })

        if self._is_login_page(resp.text):
            log("Session expired, re-logging in ...", YELLOW)
            self.logged_in = False
            self.login()
            self.viewstate = ""
            self.fetch_normal_page(1)
            resp = self._post_with_retry(NORMAL_URL, {
                "__EVENTTARGET": event_target,
                "__EVENTARGUMENT": event_argument,
                "__VIEWSTATE": self.viewstate,
            })

        # Update viewstate from response
        soup = BeautifulSoup(resp.text, "html.parser")
        vs = soup.find("input", {"name": "__VIEWSTATE"})
        if vs:
            self.viewstate = vs.get("value", "")

        return resp.text


# ──────────────────────────────────────────────
# Parsing — Normal page (c=Xk&a=Normal)
# ──────────────────────────────────────────────
# data_table (available courses):
#   Code | Name | GE Field | Credit | Week | Lecturer | Time | Quota | Applicant No. | Option
# data_table2 (registered courses):
#   Code | Name(Waiting List) | GE Field | Credit | Week | Lecturer | Time | Quota | Applicant No. | Wishing List | Cancel

def parse_available_courses(html):
    """Parse available courses from data_table."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="data_table")
    if not table:
        return []

    courses = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr", recursive=False):
        if "none" in (row.get("style") or ""):
            continue
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        option_cell = cells[9]
        option_text = option_cell.get_text(strip=True)

        # Extract xkid from __doPostBack('Add','XXXXX')
        xkid = None
        btn = option_cell.find("input", {"value": "Select"})
        if btn:
            onclick = btn.get("onclick", "")
            m = re.search(r"__doPostBack\('Add','(\d+)'\)", onclick)
            if m:
                xkid = m.group(1)

        quota = _parse_int(cells[7].get_text(strip=True))
        applicant = _parse_int(cells[8].get_text(strip=True))

        courses.append({
            "code": cells[0].get_text(strip=True),
            "name": cells[1].get_text(strip=True),
            "field": cells[2].get_text(strip=True),
            "credit": cells[3].get_text(strip=True),
            "week": cells[4].get_text(strip=True),
            "lecturer": cells[5].get_text(strip=True),
            "time_venue": cells[6].get_text(" | ", strip=True),
            "quota": quota,
            "applicant": applicant,
            "remaining": quota - applicant if quota >= 0 and applicant >= 0 else -1,
            "option": option_text,
            "xkid": xkid,
        })

    return courses


def parse_registered_courses(html):
    """Parse registered courses from data_table2."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="data_table2")
    if not table:
        return []

    courses = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr", recursive=False):
        cells = row.find_all("td")
        if len(cells) < 11:
            continue

        # Extract cancel xkid
        cancel_xkid = None
        cancel_cell = cells[10]
        btn = cancel_cell.find("input", {"value": "Cancel"})
        if btn:
            onclick = btn.get("onclick", "")
            m = re.search(r"__doPostBack\('Del','(\d+)'\)", onclick)
            if m:
                cancel_xkid = m.group(1)

        courses.append({
            "code": cells[0].get_text(strip=True),
            "name": cells[1].get_text(strip=True),
            "field": cells[2].get_text(strip=True),
            "credit": cells[3].get_text(strip=True),
            "quota": _parse_int(cells[7].get_text(strip=True)),
            "applicant": _parse_int(cells[8].get_text(strip=True)),
            "cancel_xkid": cancel_xkid,
        })

    return courses


def parse_credit_info(html):
    """Parse credit info (max/chosen) from the summary table."""
    soup = BeautifulSoup(html, "html.parser")
    # Find the summary table (first table with "Credits (max)" header)
    for table in soup.find_all("table", class_="data"):
        if table.get("id"):
            continue  # Skip data_table and data_table2
        text = table.get_text()
        if "Credits" in text:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 4:
                    return {
                        "round": cells[0].get_text(strip=True),
                        "stage": cells[1].get_text(strip=True),
                        "max_credits": _parse_int(cells[2].get_text(strip=True)),
                        "chosen_credits": _parse_int(cells[3].get_text(strip=True)),
                    }
    return None


def get_total_pages(html):
    """Extract total page count from pagination."""
    max_page = 1
    for m in re.finditer(r"__doPostBack\('Page','(\d+)'\)", html):
        max_page = max(max_page, int(m.group(1)))
    return max_page


def _parse_int(s):
    m = re.search(r"\d+", s)
    return int(m.group()) if m else -1


# ──────────────────────────────────────────────
# Fetch all pages
# ──────────────────────────────────────────────

def fetch_all_courses(sess):
    """Fetch all pages and return (available_courses, registered_courses, credit_info, first_page_html)."""
    html = sess.fetch_normal_page(1)
    total_pages = get_total_pages(html)

    all_available = parse_available_courses(html)
    registered = parse_registered_courses(html)
    credit_info = parse_credit_info(html)

    log(f"Page 1/{total_pages}: {len(all_available)} courses", CYAN)

    for p in range(2, total_pages + 1):
        page_html = sess.fetch_normal_page(p)
        page_courses = parse_available_courses(page_html)
        log(f"Page {p}/{total_pages}: {len(page_courses)} courses", CYAN)
        all_available.extend(page_courses)

    return all_available, registered, credit_info, html


# ──────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────

def _dump(html, filename="dump.html"):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"HTML saved to {path}", CYAN)


def cmd_dump(_args):
    sess = Session()
    html = sess.fetch_normal_page(1)
    _dump(html, "dump_normal.html")


def cmd_query(args):
    sess = Session()
    all_courses, registered, credit_info, html = fetch_all_courses(sess)

    if args.dump:
        _dump(html, "dump_normal.html")

    # Credit info
    if credit_info:
        print(f"\n{BOLD}Round: {credit_info['round']} | Stage: {credit_info['stage']} | Credits: {credit_info['chosen_credits']}/{credit_info['max_credits']}{RESET}")

    # Registered courses
    if registered:
        print(f"\n{BOLD}=== Registered Courses ==={RESET}")
        for c in registered:
            print(f"  {c['code']} {c['name']} ({c['credit']}cr) — {c['applicant']}/{c['quota']} applicants [cancel_id={c['cancel_xkid']}]")

    if not all_courses:
        log("No available course data found.", YELLOW)
        return

    # Available courses
    print(f"\n{BOLD}=== Available Courses ({len(all_courses)} total) ==={RESET}")
    header = f"{'Code':<8} {'Course Name':<52} {'Cr':>3} {'Quota':>6} {'Apply':>6} {'Left':>5} {'Option':<10}"
    print(BOLD + header + RESET)
    print("-" * len(header))

    for c in all_courses:
        remaining = c["remaining"]
        option = c["option"]

        if c["xkid"]:
            color = GREEN
            option_str = f"Select({c['xkid']})"
        elif "full" in option.lower():
            color = RED
            option_str = "Full"
        else:
            color = YELLOW
            option_str = option[:10]

        left_str = str(remaining) if remaining >= 0 else "?"
        print(f"{c['code']:<8} {c['name']:<52} {c['credit']:>3} {c['quota']:>6} {c['applicant']:>6} {color}{left_str:>5}{RESET} {color}{option_str:<10}{RESET}")

    print()


def cmd_grab(args):
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if not os.path.exists(config_path):
        log("ERROR: config.json not found.", RED)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    targets = sorted(config["courses"], key=lambda c: c["priority"])
    if not targets:
        log("No target courses in config.json", YELLOW)
        return

    for t in targets:
        if "xkid" not in t:
            log(f"ERROR: '{t['name']}' missing 'xkid' in config.json. Run query first.", RED)
            sys.exit(1)

    log(f"Target courses ({len(targets)}):", BOLD)
    for t in targets:
        log(f"  [{t['priority']}] {t['name']} (xkid={t['xkid']})", CYAN)

    interval = args.interval
    if args.rush:
        interval = 0.3  # small delay to avoid SSL rate-limiting
        log("RUSH MODE: direct submission, 0.3s between rounds", YELLOW)

    log("Press Ctrl+C to stop.\n", CYAN)

    sess = Session()
    log("Entering enrollment page ...", CYAN)
    sess.fetch_normal_page(1)

    remaining_targets = list(targets)
    attempt = 0

    try:
        while remaining_targets:
            attempt += 1

            grabbed = []
            for target in remaining_targets:
                try:
                    resp_html = sess.do_postback("Add", target["xkid"])
                except requests.RequestException as e:
                    log(f"  Network error: {e}", RED)
                    time.sleep(5)
                    try:
                        sess.viewstate = ""
                        sess.fetch_normal_page(1)
                    except requests.RequestException:
                        log("  Recovery failed, will retry next round ...", YELLOW)
                        sess._recreate_session()
                        sess.logged_in = False
                    break

                alert_match = re.search(r'alert\("([\s\S]*?)"\)', resp_html)
                if alert_match:
                    alert_msg = alert_match.group(1).replace("\\r\\n", " ").strip()
                    if "successful" in alert_msg.lower():
                        log(f"  ENROLLED: {target['name']}!", GREEN + BOLD)
                        notify_macos("选课成功!", f"已选上 {target['name']}")
                        notify_sound()
                        grabbed.append(target)
                    else:
                        if attempt % 20 == 1:
                            log(f"  #{attempt} [{target['priority']}] {target['name']}: {alert_msg}", RED)
                else:
                    new_registered = parse_registered_courses(resp_html)
                    if any(target["name"].lower() in r["name"].lower() for r in new_registered):
                        log(f"  ENROLLED: {target['name']}!", GREEN + BOLD)
                        notify_macos("选课成功!", f"已选上 {target['name']}")
                        notify_sound()
                        grabbed.append(target)

            for g in grabbed:
                remaining_targets.remove(g)

            if not remaining_targets:
                log("All target courses grabbed! Done.", GREEN + BOLD)
                notify_macos("全部选完!", "所有目标课程已选上")
                notify_sound()
            elif interval > 0:
                time.sleep(interval)

    except KeyboardInterrupt:
        log(f"\nStopped after {attempt} attempts.", YELLOW)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="XMUM 小学期选课工具")
    parser.add_argument("--dump", action="store_true", help="Save raw HTML")
    sub = parser.add_subparsers(dest="command")

    q = sub.add_parser("query", help="Query all courses")
    q.add_argument("--dump", action="store_true", help="Also save raw HTML")

    g = sub.add_parser("grab", help="Auto-grab courses from config.json")
    g.add_argument("--interval", type=int, default=5, help="Poll interval seconds (default: 5)")
    g.add_argument("--rush", action="store_true", help="Rush mode: 1s interval")

    args = parser.parse_args()

    if args.command is None:
        if args.dump:
            cmd_dump(args)
        else:
            parser.print_help()
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "grab":
        cmd_grab(args)


if __name__ == "__main__":
    main()
