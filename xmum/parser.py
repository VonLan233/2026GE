"""Normal 选课页面的 HTML 解析。

页面表格说明：
  data_table  — 可选课程列表
    课程代码 | 名称 | GE 领域 | 学分 | 周次 | 教师 | 时间/地点 | 名额 | 报名人数 | 操作
  data_table2 — 已选课程列表
    课程代码 | 名称(候补) | GE 领域 | 学分 | 周次 | 教师 | 时间/地点 | 名额 | 报名人数 | 心愿单 | 退课
"""

import re

from bs4 import BeautifulSoup


# ── ViewState ─────────────────────────────────

def extract_viewstate(html: str) -> str:
    """从 HTML 响应中提取 __VIEWSTATE 隐藏字段的值。"""
    soup = BeautifulSoup(html, "html.parser")
    vs = soup.find("input", {"name": "__VIEWSTATE"})
    return vs.get("value", "") if vs else ""


# ── 课程解析 ───────────────────────────────────

def parse_available_courses(html: str) -> list[dict]:
    """从 data_table 解析可选课程列表。"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="data_table")
    if not table:
        return []

    tbody = table.find("tbody")
    if not tbody:
        return []

    courses: list[dict] = []
    for row in tbody.find_all("tr", recursive=False):
        if "none" in (row.get("style") or ""):
            continue
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        option_cell = cells[9]
        option_text = option_cell.get_text(strip=True)

        xkid = _extract_postback_id(option_cell, "Select", "Add")
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


def parse_registered_courses(html: str) -> list[dict]:
    """从 data_table2 解析已选课程列表。"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="data_table2")
    if not table:
        return []

    tbody = table.find("tbody")
    if not tbody:
        return []

    courses: list[dict] = []
    for row in tbody.find_all("tr", recursive=False):
        cells = row.find_all("td")
        if len(cells) < 11:
            continue

        courses.append({
            "code": cells[0].get_text(strip=True),
            "name": cells[1].get_text(strip=True),
            "field": cells[2].get_text(strip=True),
            "credit": cells[3].get_text(strip=True),
            "quota": _parse_int(cells[7].get_text(strip=True)),
            "applicant": _parse_int(cells[8].get_text(strip=True)),
            "cancel_xkid": _extract_postback_id(cells[10], "Cancel", "Del"),
        })

    return courses


def parse_credit_info(html: str) -> dict | None:
    """从汇总表格解析学分信息（已选 / 上限）。"""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table", class_="data"):
        if table.get("id"):
            continue  # 跳过 data_table / data_table2
        if "Credits" not in table.get_text():
            continue
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 4:
                return {
                    "round": cells[0].get_text(strip=True),
                    "stage": cells[1].get_text(strip=True),
                    "max_credits": _parse_int(cells[2].get_text(strip=True)),
                    "chosen_credits": _parse_int(cells[3].get_text(strip=True)),
                }
    return None


def get_total_pages(html: str) -> int:
    """从分页链接中提取总页数。"""
    max_page = 1
    for m in re.finditer(r"__doPostBack\('Page','(\d+)'\)", html):
        max_page = max(max_page, int(m.group(1)))
    return max_page


def parse_alert(html: str) -> str | None:
    """提取页面 JavaScript alert() 中的消息文本，若不存在则返回 None。"""
    m = re.search(r"alert\([\"'](.+?)[\"']\)", html, re.DOTALL)
    if not m:
        return None
    return m.group(1).replace("\\r\\n", " ").replace("\\n", " ").strip()


# ── 内部工具 ───────────────────────────────────

def _parse_int(s: str) -> int:
    """从字符串中提取第一个整数，失败时返回 -1。"""
    m = re.search(r"\d+", s)
    return int(m.group()) if m else -1


def _extract_postback_id(cell, button_value: str, event_name: str) -> str | None:
    """从按钮的 onclick 属性中提取 __doPostBack('<事件>','<ID>') 的数字 ID。"""
    btn = cell.find("input", {"value": button_value})
    if not btn:
        return None
    onclick = btn.get("onclick", "")
    m = re.search(rf"__doPostBack\('{event_name}','(\d+)'\)", onclick)
    return m.group(1) if m else None
