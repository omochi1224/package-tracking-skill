#!/usr/bin/env python3
"""Package tracking CLI for Japanese carriers.

Tracks packages for Yamato Transport, Sagawa Express, Japan Post and Askul by
scraping each carrier's public tracking page. Prints a single JSON object to
stdout so that an agent can read the result programmatically.

Usage:
    python3 track.py <tracking_number> [--carrier auto|yamato|sagawa|japanpost|askul]

Examples:
    python3 track.py 442676947510
    python3 track.py 4426-7694-7510 --carrier yamato
    python3 track.py LP009985404IN --carrier japanpost

Dependencies: requests, beautifulsoup4
    pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from datetime import datetime, timedelta, timezone

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.poolmanager import PoolManager
    from bs4 import BeautifulSoup
except ImportError as exc:
    print(
        json.dumps(
            {
                "error": "missing_dependency",
                "message": (
                    "必要なパッケージがありません。`pip install -r requirements.txt` "
                    "を実行してください (requests, beautifulsoup4)。"
                ),
                "detail": str(exc),
            },
            ensure_ascii=False,
        )
    )
    sys.exit(2)


JST = timezone(timedelta(hours=9))

USER_AGENT = "Mozilla/5.0 (compatible; PackageTrackingSkill/1.0)"
TIMEOUT = 10


# --- Shared helpers ---
def clean_number(number: str) -> str:
    return number.replace("-", "").replace(" ", "").strip()


def convert_to_iso8601(date_string: str, fmt_with_time: str, fmt_date_only: str) -> str | None:
    if not date_string or "―" in date_string:
        return None
    try:
        dt = datetime.strptime(date_string, fmt_with_time)
    except ValueError:
        try:
            dt = datetime.strptime(date_string, fmt_date_only)
        except ValueError:
            return None
        dt = dt.replace(hour=0, minute=0)
    return dt.replace(tzinfo=JST).isoformat()


def check_delivered(status_text: str, keywords: list[str]) -> bool:
    return any(kw in status_text for kw in keywords)


def build_result(
    carrier: str,
    carrier_jp: str,
    tracking_number: str,
    item_type: str,
    history: list[dict],
    delivered_keywords: list[str],
    complete_text: str = "",
) -> dict:
    last_status = history[-1]["status"]
    return {
        "carrier": carrier,
        "carrier_jp": carrier_jp,
        "tracking_number": tracking_number,
        "item_type": item_type,
        "is_delivered": check_delivered(last_status, delivered_keywords),
        "current_status": history[-1],
        "complete_text": complete_text,
        "history": history,
    }


def fetch_get(url: str, error_message: str) -> "requests.Response":
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException:
        raise ConnectionError(error_message)


def fetch_post(url: str, payload: dict, error_message: str) -> "requests.Response":
    try:
        response = requests.post(
            url, data=payload, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
        )
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException:
        raise ConnectionError(error_message)


# --- Yamato Transport / ヤマト運輸 ---
class _YamatoAdapter(HTTPAdapter):
    """Yamato's endpoint requires a relaxed cipher set over TLS 1.2."""

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers(
            "@SECLEVEL=2:ECDH+AESGCM:ECDH+CHACHA20:ECDH+AES:DHE+AES:AESGCM:"
            "!aNULL:!eNULL:!aDSS:!SHA1:!AESCCM:!PSK"
        )
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_version=ssl.PROTOCOL_TLSv1_2,
            ssl_context=ctx,
        )


def _yamato_date(date_str: str) -> str | None:
    current_year = datetime.now().year
    try:
        dt = datetime.strptime(f"{current_year}年 {date_str}", "%Y年 %m月%d日 %H:%M")
    except ValueError:
        try:
            dt = datetime.strptime(f"{current_year}年 {date_str}", "%Y年 %m月%d日")
        except ValueError:
            return None
    return dt.replace(tzinfo=JST).isoformat()


def track_yamato(number: str) -> dict:
    clean = clean_number(number)
    if len(clean) != 12 or not clean.isdigit():
        raise ValueError("送り状番号は12桁の数字（ハイフン区切り可）で入力してください。")

    url = "https://toi.kuronekoyamato.co.jp/cgi-bin/tneko"
    payload = {
        "mypagesession": "",
        "backaddress": "",
        "backrequest": "get",
        "category": "0",
        "number01": clean,
    }

    session = requests.Session()
    session.mount("https://", _YamatoAdapter())
    try:
        response = session.post(
            url, data=payload, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        raise ConnectionError("ヤマト運輸のシステムにアクセスできませんでした。")

    soup = BeautifulSoup(response.text, "html.parser")
    package_info = soup.find("div", class_="parts-tracking-invoice-block")
    if not package_info:
        raise ValueError("ページの解析に失敗しました。番号を確認してください。")

    detail = package_info.find("div", class_="tracking-invoice-block-detail")
    if not detail:
        error_el = package_info.find("div", class_="is-urgent-red")
        if error_el:
            error_text = error_el.find("h4")
            if error_text:
                raise ValueError(error_text.text.strip())
        raise ValueError("荷物情報が見つかりませんでした。")

    item_type = ""
    summary_div = package_info.find("div", class_="tracking-invoice-block-summary")
    if summary_div:
        data_div = summary_div.find("div", class_="data")
        if data_div:
            item_type = data_div.text.strip()

    complete_text = ""
    is_complete = soup.find("div", class_="tracking-invoice-block-state is-complete-grey")
    if is_complete:
        title = is_complete.find("h4", class_="tracking-invoice-block-state-title")
        if title:
            complete_text = title.text.strip()

    statuses: list[dict] = []
    for item in detail.find_all("li"):
        divs = item.find_all("div")
        if len(divs) < 3:
            continue
        statuses.append(
            {
                "status": divs[0].text.strip(),
                "date": _yamato_date(divs[1].text.strip()),
                "name": divs[2].text.strip(),
            }
        )

    if not statuses:
        raise ValueError("配送履歴が見つかりませんでした。")

    return build_result(
        "yamato", "ヤマト運輸", number, item_type, statuses,
        ["完了", "お届け済み"], complete_text,
    )


# --- Sagawa Express / 佐川急便 ---
def _sagawa_date(date_str: str) -> str | None:
    if not date_str or "―" in date_str:
        return None
    current_year = datetime.now().year
    try:
        dt = datetime.strptime(f"{current_year}/{date_str}", "%Y/%m/%d %H:%M")
    except ValueError:
        try:
            dt = datetime.strptime(f"{current_year}/{date_str}", "%Y/%m/%d")
        except ValueError:
            return None
        dt = dt.replace(hour=0, minute=0)
    return dt.replace(tzinfo=JST).isoformat()


def track_sagawa(number: str) -> dict:
    clean = clean_number(number)
    if len(clean) != 12 or not clean.isdigit():
        raise ValueError("送り状番号は12桁の数字（ハイフン区切り可）で入力してください。")

    response = fetch_post(
        "https://k2k.sagawa-exp.co.jp/p/web/okurijosearch.do",
        {"okurijoNo": clean},
        "佐川急便のシステムにアクセスできませんでした。",
    )

    soup = BeautifulSoup(response.text, "html.parser")

    state_span = soup.find("span", class_="state")
    if state_span:
        state_text = state_span.text
        if "該当なし" in state_text or "お問い合わせ" in state_text:
            raise ValueError(state_text.strip())

    tables = soup.find_all("table", class_="table_basic table_okurijo_detail2")
    if len(tables) < 2:
        raise ValueError("荷物情報の解析に失敗しました。")

    statuses: list[dict] = []
    for row in tables[1].find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        statuses.append(
            {
                "status": cells[0].get_text(strip=True).replace("↓", "").replace("⇒", ""),
                "date": _sagawa_date(cells[1].get_text(strip=True)),
                "name": cells[2].get_text(strip=True),
            }
        )

    if not statuses:
        raise ValueError("配送履歴が見つかりませんでした。")

    return build_result("sagawa", "佐川急便", number, "", statuses, ["完了"])


# --- Japan Post / 日本郵便 ---
_INTERNATIONAL_RE = re.compile(r"^[A-Z]{2}[0-9]{9}[A-Z]{2}$")


def _japanpost_is_international(number: str) -> bool:
    return bool(_INTERNATIONAL_RE.match(clean_number(number)))


def _japanpost_domestic(history_table) -> tuple[str, list[dict]]:
    item_type = ""
    info_table = history_table.find_previous_sibling("table", class_="tableType01 txt_c m_b5")
    if info_table:
        td = info_table.find("td", class_="w_480")
        if td:
            item_type = td.text.strip()

    statuses: list[dict] = []
    for row in history_table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) <= 1:
            continue
        statuses.append(
            {
                "status": cells[1].get_text(strip=True),
                "date": convert_to_iso8601(
                    cells[0].get_text(strip=True), "%Y/%m/%d %H:%M", "%Y/%m/%d"
                ),
                "name": cells[3].get_text(strip=True) if len(cells) > 3 else "",
            }
        )
    return item_type, statuses


def _japanpost_international(history_table) -> tuple[str, list[dict]]:
    item_type = ""
    info_table = history_table.find_previous_sibling("table", class_="tableType01 txt_c m_b5")
    if info_table:
        td = info_table.find("td", class_="w_380")
        if td:
            item_type = td.text.strip()

    statuses: list[dict] = []
    skip_next = False
    for row in history_table.find_all("tr"):
        if skip_next:
            skip_next = False
            continue
        cells = row.find_all("td")
        if not cells or len(cells) < 2:
            continue
        first_td = cells[0]
        if first_td.get("rowspan") == "2":
            skip_next = True
        else:
            continue
        date_str = first_td.get_text(strip=True)
        country = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        office = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        name = f"{office} {country}".strip() if country else office
        statuses.append(
            {
                "status": cells[1].get_text(strip=True),
                "date": convert_to_iso8601(date_str, "%Y/%m/%d %H:%M", "%Y/%m/%d"),
                "name": name,
            }
        )
    return item_type, statuses


def track_japanpost(number: str) -> dict:
    clean = clean_number(number)
    is_intl = _japanpost_is_international(number)

    if not is_intl and (not clean.isdigit() or len(clean) != 12):
        raise ValueError(
            "お問い合わせ番号は12桁の数字（ハイフン区切り可）、"
            "または国際追跡番号（例: LP009985404IN）を入力してください。"
        )

    url = (
        f"https://trackings.post.japanpost.jp/services/srv/search"
        f"?requestNo1={clean}&search.x=58&search.y=12"
        f"&startingUrlPatten=&locale=ja"
    )
    response = fetch_get(url, "日本郵便の配達状況ページにアクセスできませんでした。")

    soup = BeautifulSoup(response.text, "html.parser")

    error_font = soup.find("font", color="ff0000")
    if error_font and "お問い合わせ番号が見つかりません" in error_font.text:
        raise ValueError("お問い合わせ番号が見つかりません。")

    h1 = soup.find("h1", class_="ttl_line")
    is_intl_page = bool(h1 and "国際" in h1.text)

    history_table = soup.find("table", class_="tableType01 txt_c m_b5", summary="履歴情報")
    if not history_table:
        raise ValueError("荷物情報の解析に失敗しました。")

    if is_intl_page:
        item_type, statuses = _japanpost_international(history_table)
    else:
        item_type, statuses = _japanpost_domestic(history_table)

    if not statuses:
        raise ValueError("配送履歴が見つかりませんでした。")

    return build_result(
        "japanpost", "日本郵便", number, item_type, statuses, ["お渡し", "お届け済み"]
    )


# --- Askul / アスクル ---
def track_askul(number: str) -> dict:
    clean = clean_number(number)
    if not clean.isdigit():
        raise ValueError("お問い合わせ番号は数字で入力してください。")

    url = f"https://cargo.askullogist.co.jp/delivery/status?no={clean}&ca=0"
    response = fetch_get(url, "アスクルの配送状況ページにアクセスできませんでした。")
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")

    error_el = soup.find("div", class_="alertBox attention")
    if error_el and "お問い合わせ番号が見つかりません" in error_el.text:
        raise ValueError("お問い合わせ番号が見つかりません。")

    table = soup.find("table")
    if not table:
        raise ValueError("荷物情報の解析に失敗しました。")

    rows = table.find_all("tr")
    if len(rows) <= 1:
        raise ValueError("配送履歴が見つかりませんでした。")

    statuses: list[dict] = []
    for row in rows[1:]:
        tds = row.find_all("td")
        if len(tds) < 4:
            continue
        statuses.append(
            {
                "status": tds[0].text.strip(),
                "date": convert_to_iso8601(
                    tds[1].text.strip(), "%Y年%m月%d日 %H:%M", "%Y年%m月%d日"
                ),
                "name": tds[3].text.strip(),
            }
        )

    if not statuses:
        raise ValueError("配送履歴が見つかりませんでした。")

    statuses.reverse()
    return build_result("askul", "アスクル", number, "", statuses, ["完了"])


# --- Dispatch ---
CARRIERS = {
    "yamato": ("ヤマト運輸", track_yamato),
    "sagawa": ("佐川急便", track_sagawa),
    "japanpost": ("日本郵便", track_japanpost),
    "askul": ("アスクル", track_askul),
}


def track_auto(number: str) -> dict:
    errors = []
    for key, (name, fn) in CARRIERS.items():
        try:
            result = fn(number)
            result["detected_carrier"] = name
            return result
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise ValueError("すべてのキャリアで該当なし:\n" + "\n".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="日本の配送業者の荷物追跡 (ヤマト・佐川・日本郵便・アスクル)"
    )
    parser.add_argument("number", help="追跡番号 (ハイフン区切り可)")
    parser.add_argument(
        "--carrier",
        default="auto",
        choices=["auto", *CARRIERS.keys()],
        help="キャリア指定。省略時は自動判別 (auto)。",
    )
    args = parser.parse_args(argv)

    try:
        if args.carrier == "auto":
            result = track_auto(args.number)
        else:
            name, fn = CARRIERS[args.carrier]
            result = fn(args.number)
            result["detected_carrier"] = name
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, ConnectionError) as exc:
        print(
            json.dumps(
                {"error": "tracking_failed", "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
