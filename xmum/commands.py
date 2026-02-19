"""CLI 子命令实现：query（查询）、grab（抢课）、dump（保存 HTML）。"""

import json
import os
import sys
import time

import requests

from .constants import (
    BOLD, CYAN, GREEN, PROJECT_DIR, RED, RESET, YELLOW, log,
)
from .notify import notify_success
from .parser import (
    get_total_pages,
    parse_alert,
    parse_available_courses,
    parse_credit_info,
    parse_registered_courses,
)
from .session import Session


# ── 内部工具 ───────────────────────────────────

def _dump(html: str, filename: str = "dump.html") -> None:
    """将 HTML 内容保存到项目根目录下的指定文件。"""
    path = os.path.join(PROJECT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"HTML saved to {path}", CYAN)


def _fetch_all_courses(sess: Session):
    """翻取全部分页，返回 (可选课程, 已选课程, 学分信息, 首页 HTML)。"""
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


def _load_grab_config() -> list[dict]:
    """加载并校验 config.json，出错则打印提示后退出。"""
    config_path = os.path.join(PROJECT_DIR, "config.json")
    if not os.path.exists(config_path):
        log("ERROR: config.json not found.", RED)
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        log(f"ERROR: config.json is not valid JSON: {e}", RED)
        sys.exit(1)

    if "courses" not in config or not isinstance(config["courses"], list):
        log("ERROR: config.json must contain a 'courses' array.", RED)
        sys.exit(1)

    targets = sorted(config["courses"], key=lambda c: c.get("priority", 999))
    if not targets:
        log("No target courses in config.json", YELLOW)
        sys.exit(0)

    for t in targets:
        if "xkid" not in t:
            log(f"ERROR: '{t.get('name', '?')}' missing 'xkid'. Run query first.", RED)
            sys.exit(1)

    return targets


# ── 子命令 ─────────────────────────────────────

def cmd_dump(_args) -> None:
    """保存选课页面原始 HTML（调试用）。"""
    sess = Session()
    html = sess.fetch_normal_page(1)
    _dump(html, "dump_normal.html")


def cmd_query(args) -> None:
    """查询并展示所有课程余量及已选课程。"""
    sess = Session()
    all_courses, registered, credit_info, html = _fetch_all_courses(sess)

    if args.dump:
        _dump(html, "dump_normal.html")

    if credit_info:
        print(
            f"\n{BOLD}Round: {credit_info['round']} | "
            f"Stage: {credit_info['stage']} | "
            f"Credits: {credit_info['chosen_credits']}/{credit_info['max_credits']}{RESET}"
        )

    if registered:
        print(f"\n{BOLD}=== Registered Courses ==={RESET}")
        for c in registered:
            print(
                f"  {c['code']} {c['name']} ({c['credit']}cr) "
                f"— {c['applicant']}/{c['quota']} applicants "
                f"[cancel_id={c['cancel_xkid']}]"
            )

    if not all_courses:
        log("No available course data found.", YELLOW)
        return

    print(f"\n{BOLD}=== Available Courses ({len(all_courses)} total) ==={RESET}")
    header = (
        f"{'Code':<8} {'Course Name':<52} {'Cr':>3} "
        f"{'Quota':>6} {'Apply':>6} {'Left':>5} {'Option':<10}"
    )
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
        print(
            f"{c['code']:<8} {c['name']:<52} {c['credit']:>3} "
            f"{c['quota']:>6} {c['applicant']:>6} "
            f"{color}{left_str:>5}{RESET} {color}{option_str:<10}{RESET}"
        )

    print()


def cmd_grab(args) -> None:
    """持续轮询并自动抢课，直到所有目标课程选完或手动中断。"""
    targets = _load_grab_config()

    log(f"Target courses ({len(targets)}):", BOLD)
    for t in targets:
        log(f"  [{t.get('priority', '-')}] {t['name']} (xkid={t['xkid']})", CYAN)

    interval = args.interval
    if args.rush:
        interval = 0.3  # 急速模式：极短间隔，避免触发 SSL 限流
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
            grabbed = _grab_round(sess, remaining_targets, attempt)

            for g in grabbed:
                remaining_targets.remove(g)

            if not remaining_targets:
                log("All target courses grabbed! Done.", GREEN + BOLD)
                notify_success("全部选完!", "所有目标课程已选上")
            elif interval > 0:
                time.sleep(interval)

    except KeyboardInterrupt:
        log(f"\nStopped after {attempt} attempts.", YELLOW)


def _grab_round(sess: Session, targets: list[dict], attempt: int) -> list[dict]:
    """对每个目标课程提交一次 Add 请求，返回本轮成功抢到的课程列表。"""
    grabbed: list[dict] = []

    for target in targets:
        try:
            resp_html = sess.do_postback("Add", target["xkid"])
        except requests.RequestException as e:
            log(f"  Network error: {e}", RED)
            time.sleep(5)
            sess.recover()
            break  # 本轮剩余课程下轮重试

        if _check_enrolled(resp_html, target):
            grabbed.append(target)
        else:
            alert_msg = parse_alert(resp_html)
            if alert_msg and attempt % 20 == 1:
                # 每 20 轮打印一次失败原因，避免刷屏
                log(
                    f"  #{attempt} [{target.get('priority', '-')}] "
                    f"{target['name']}: {alert_msg}",
                    RED,
                )

    return grabbed


def _check_enrolled(html: str, target: dict) -> bool:
    """判断是否已选上目标课程，若是则触发通知并返回 True。"""
    alert_msg = parse_alert(html)
    if alert_msg and "successful" in alert_msg.lower():
        _announce_enrolled(target)
        return True

    if alert_msg:
        # 有 alert 但内容不含 successful，说明失败（名额满 / 学分超限等）
        return False

    # 无 alert 时，通过已选列表兜底判断
    registered = parse_registered_courses(html)
    if any(target["name"].lower() in r["name"].lower() for r in registered):
        _announce_enrolled(target)
        return True

    return False


def _announce_enrolled(target: dict) -> None:
    """打印选课成功日志并发送桌面通知。"""
    log(f"  ENROLLED: {target['name']}!", GREEN + BOLD)
    notify_success("选课成功!", f"已选上 {target['name']}")
