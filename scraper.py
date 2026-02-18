#!/usr/bin/env python3
"""XMUM 小学期选课 — 余量查询 + 自动抢课"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://ac.xmu.edu.my"
LOGIN_URL = f"{BASE_URL}/index.php"
COURSE_URL = f"{BASE_URL}/student/index.php?c=Xk&a=index"

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
    """Send a macOS notification."""
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}" sound name "Glass"',
            ],
            check=False,
        )
    except FileNotFoundError:
        pass


def notify_sound():
    """Play a short alert sound on macOS."""
    try:
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Hero.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


# ──────────────────────────────────────────────
# Login
# ──────────────────────────────────────────────

class Session:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            }
        )
        self.logged_in = False

    def login(self):
        username = os.getenv("XMU_USERNAME")
        password = os.getenv("XMU_PASSWORD")
        if not username or not password:
            log("ERROR: Set XMU_USERNAME and XMU_PASSWORD in .env", RED)
            sys.exit(1)

        log(f"Logging in as {username} ...", CYAN)

        # GET the login page first to pick up any hidden fields / cookies
        resp = self.session.get(LOGIN_URL)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Build payload — start with all hidden inputs on the form
        payload = {}
        form = soup.find("form")
        if form:
            for inp in form.find_all("input", attrs={"type": "hidden"}):
                name = inp.get("name")
                if name:
                    payload[name] = inp.get("value", "")

        payload.update(
            {
                "username": username,
                "password": password,
                "Category": "Student",
            }
        )

        # Determine the form action URL
        action = LOGIN_URL
        if form and form.get("action"):
            action_url = str(form["action"])
            if action_url.startswith("http"):
                action = action_url
            else:
                action = f"{BASE_URL}/{action_url.lstrip('/')}"

        resp = self.session.post(action, data=payload, allow_redirects=True)

        # Check success: if response still contains a login form, we failed
        if "password" in resp.text.lower() and "login" in resp.text.lower():
            # Save the response for debugging
            _dump(resp.text, "dump_login_fail.html")
            log("Login FAILED — check credentials. Response saved to dump_login_fail.html", RED)
            sys.exit(1)

        self.logged_in = True
        log("Login successful!", GREEN)

    def ensure_logged_in(self):
        if not self.logged_in:
            self.login()

    def fetch_course_page(self):
        """Fetch the course selection page HTML."""
        self.ensure_logged_in()
        resp = self.session.get(COURSE_URL)

        # Detect session expiry (redirected back to login)
        if "password" in resp.text.lower() and "login" in resp.text.lower():
            log("Session expired, re-logging in ...", YELLOW)
            self.logged_in = False
            self.login()
            resp = self.session.get(COURSE_URL)

        return resp.text


# ──────────────────────────────────────────────
# Parsing (placeholder — fill in after dump)
# ──────────────────────────────────────────────

def parse_courses(html):
    """Parse the course page HTML and return a list of course dicts.

    Each dict: {
        "name": str,
        "teacher": str,
        "enrolled": int,
        "capacity": int,
        "remaining": int,
        "course_id": str | None,   # for submitting enrollment
        "row_data": dict,          # raw data for debugging
    }

    TODO: Update selectors after analyzing dump.html
    """
    soup = BeautifulSoup(html, "html.parser")
    courses = []

    # ── Attempt: look for a <table> with course rows ──
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        # Use first row as header
        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells:
                continue
            row_data = dict(zip(headers, cells))

            # Try to extract a course_id from a link or button in the row
            course_id = None
            link = row.find("a", href=True)
            if link:
                course_id = link["href"]
            btn = row.find("button") or row.find("input", attrs={"type": "submit"})
            if btn:
                course_id = btn.get("value") or btn.get("onclick", "")

            courses.append(
                {
                    "name": row_data.get(headers[0] if headers else "", cells[0] if cells else ""),
                    "teacher": row_data.get(headers[1] if len(headers) > 1 else "", cells[1] if len(cells) > 1 else ""),
                    "enrolled": _safe_int(cells, 2),
                    "capacity": _safe_int(cells, 3),
                    "remaining": _safe_int(cells, 4),
                    "course_id": course_id,
                    "row_data": row_data,
                }
            )

    if not courses:
        log("WARNING: No courses parsed. Run with --dump and share dump.html for analysis.", YELLOW)

    return courses


def _safe_int(cells, idx):
    try:
        return int(cells[idx])
    except (IndexError, ValueError):
        return -1


def submit_enrollment(session_obj, course):
    """Submit the enrollment request for a course.

    TODO: Implement after analyzing the actual enrollment form/API.
    Likely a POST request with course_id and possibly semester/round params.
    """
    log(f"  -> Attempting to enroll in: {course['name']} (id={course.get('course_id')})", CYAN)

    # ── PLACEHOLDER: replace with actual enrollment API ──
    # Example skeleton:
    # resp = session_obj.session.post(
    #     f"{BASE_URL}/student/index.php?c=Xk&a=select",
    #     data={"course_id": course["course_id"], ...},
    # )
    # return "success" in resp.text.lower()

    log("  -> Enrollment submission NOT YET IMPLEMENTED (need to analyze dump.html first)", YELLOW)
    return False


# ──────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────

def _dump(html, filename="dump.html"):
    path = os.path.join(os.path.dirname(__file__), filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"HTML saved to {path}", CYAN)


def cmd_dump(args):
    """Save raw course page HTML for analysis."""
    sess = Session()
    html = sess.fetch_course_page()
    _dump(html)


def cmd_query(args):
    """Query and display all course availability."""
    sess = Session()
    html = sess.fetch_course_page()

    if args.dump:
        _dump(html)

    courses = parse_courses(html)
    if not courses:
        log("No course data found. Try --dump to inspect the page.", YELLOW)
        return

    # Print table
    print()
    print(f"{BOLD}{'课程名称':<24} {'授课教师':<12} {'已选/容量':<12} {'剩余':>6}{RESET}")
    print("-" * 58)
    for c in courses:
        remaining = c["remaining"]
        if remaining == -1:
            remaining_str = "?"
            color = YELLOW
        elif remaining == 0:
            remaining_str = "0 (已满)"
            color = RED
        else:
            remaining_str = str(remaining)
            color = GREEN

        enrolled_str = f"{c['enrolled']}/{c['capacity']}" if c["capacity"] != -1 else "?/?"
        print(
            f"{c['name']:<24} {c['teacher']:<12} {enrolled_str:<12} {color}{remaining_str:>6}{RESET}"
        )
    print()


def cmd_grab(args):
    """Auto-grab courses based on config.json priority list."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        log("ERROR: config.json not found. Create it with target courses.", RED)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    targets = sorted(config["courses"], key=lambda c: c["priority"])
    if not targets:
        log("No target courses in config.json", YELLOW)
        return

    log(f"Target courses ({len(targets)}):", BOLD)
    for t in targets:
        log(f"  [{t['priority']}] {t['name']}", CYAN)

    interval = args.interval
    if args.rush:
        interval = 1
        log("RUSH MODE: 1-second interval", YELLOW)

    log(f"Polling every {interval}s. Press Ctrl+C to stop.\n", CYAN)

    sess = Session()
    remaining_targets = list(targets)
    attempt = 0

    try:
        while remaining_targets:
            attempt += 1
            log(f"── Attempt #{attempt} ──", BOLD)

            try:
                html = sess.fetch_course_page()
            except requests.RequestException as e:
                log(f"Network error: {e}. Retrying in {interval}s ...", RED)
                time.sleep(interval)
                continue

            courses = parse_courses(html)
            if not courses:
                log("No courses parsed yet. Will retry ...", YELLOW)
                time.sleep(interval)
                continue

            # Match targets against available courses
            grabbed = []
            for target in remaining_targets:
                keyword = target["name"]
                matched = [c for c in courses if keyword in c["name"]]
                if not matched:
                    log(f"  [{target['priority']}] '{keyword}' — not found on page", YELLOW)
                    continue

                for course in matched:
                    remaining = course["remaining"]
                    if remaining > 0:
                        log(
                            f"  [{target['priority']}] '{course['name']}' has {remaining} spot(s)!",
                            GREEN,
                        )
                        success = submit_enrollment(sess, course)
                        if success:
                            log(f"  ENROLLED in '{course['name']}'!", GREEN + BOLD)
                            notify_macos("选课成功!", f"已选上 {course['name']}")
                            notify_sound()
                            grabbed.append(target)
                            break
                        else:
                            log(f"  Enrollment attempt failed for '{course['name']}'", RED)
                    elif remaining == 0:
                        log(f"  [{target['priority']}] '{course['name']}' — full ({course['enrolled']}/{course['capacity']})", RED)
                    else:
                        log(f"  [{target['priority']}] '{course['name']}' — capacity unknown", YELLOW)

            for g in grabbed:
                remaining_targets.remove(g)

            if remaining_targets:
                log(f"  Waiting {interval}s before next attempt ...\n", CYAN)
                time.sleep(interval)
            else:
                log("All target courses grabbed! Done.", GREEN + BOLD)
                notify_macos("全部选完!", "所有目标课程已选上")
                notify_sound()

    except KeyboardInterrupt:
        log("\nStopped by user.", YELLOW)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="XMUM 小学期选课工具")
    parser.add_argument("--dump", action="store_true", help="Save raw HTML to dump.html")
    sub = parser.add_subparsers(dest="command")

    # query
    q = sub.add_parser("query", help="Query course availability")
    q.add_argument("--dump", action="store_true", help="Also save raw HTML")

    # grab
    g = sub.add_parser("grab", help="Auto-grab courses from config.json")
    g.add_argument("--interval", type=int, default=5, help="Polling interval in seconds (default: 5)")
    g.add_argument("--rush", action="store_true", help="Rush mode: 1-second interval")

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
