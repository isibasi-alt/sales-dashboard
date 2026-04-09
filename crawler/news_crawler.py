#!/usr/bin/env python3
"""
和上ホールディングス 業界ニュースクローラー
毎朝9時(JST)に太陽光発電・系統用蓄電池関連ニュースを収集しLINE Notifyに送信
"""
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import feedparser
import requests

LINE_NOTIFY_TOKEN = os.environ["LINE_NOTIFY_TOKEN"]
JST = timezone(timedelta(hours=9))

# 検索クエリと分類ラベル（Google News RSS）
QUERIES = [
    ("太陽光発電 販売 施工 住宅", "太陽光"),
    ("系統用蓄電池 設置 事業", "系統蓄電池"),
    ("経済産業省 再生可能エネルギー 太陽光", "経産省"),
    ("FIT FIP 売電 制度", "FIT/FIP"),
    ("蓄電池 補助金 助成金", "補助金"),
    ("環境省 太陽光 蓄電池", "環境省"),
]

# 重要度スコアリング用キーワード
HIGH_PRIORITY_KEYWORDS = [
    "系統用蓄電池", "太陽光発電", "補助金", "FIT", "FIP", "蓄電池",
    "経済産業省", "環境省", "再生可能エネルギー", "売電", "施工", "導入",
    "電力", "パワコン", "EPC", "蓄電", "系統",
]


def fetch_rss(query: str) -> list:
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"})
    )
    try:
        feed = feedparser.parse(url)
        return feed.entries[:15]
    except Exception as e:
        print(f"RSS取得エラー ({query}): {e}")
        return []


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def is_recent(entry, hours: int = 25) -> bool:
    if not getattr(entry, "published_parsed", None):
        return True
    pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - pub < timedelta(hours=hours)


def score_entry(entry) -> int:
    text = entry.get("title", "") + " " + entry.get("summary", "")
    return sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text)


def clean_title(title: str) -> str:
    """Google News が付与する ' - 媒体名' を除去"""
    parts = title.rsplit(" - ", 1)
    return parts[0].strip() if len(parts) == 2 else title.strip()


def build_message(top_articles: list) -> str:
    now = datetime.now(JST)
    lines = [f"【和上HD業界ニュース】{now.strftime('%m/%d(%a)')}"]
    lines.append("")

    if not top_articles:
        lines.append("本日の重要ニュースはありませんでした")
        return "\n".join(lines)

    for i, (label, entry) in enumerate(top_articles, 1):
        title = clean_title(entry.get("title", "タイトルなし"))[:50]
        snippet = strip_html(entry.get("summary", ""))[:55].replace("\n", " ")
        source = ""
        src = getattr(entry, "source", None)
        if src and hasattr(src, "title"):
            source = f" ({src.title})"
        lines.append(f"{i}.[{label}] {title}{source}")
        if snippet:
            lines.append(f"   {snippet}…")
        lines.append("")

    return "\n".join(lines).rstrip()


def send_line_notify(message: str) -> None:
    resp = requests.post(
        "https://notify-api.line.me/api/notify",
        headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"},
        data={"message": "\n" + message},
        timeout=15,
    )
    if resp.status_code == 200:
        print("LINE Notify 送信成功")
    else:
        raise RuntimeError(f"LINE Notify 送信失敗: {resp.status_code} {resp.text}")


def main():
    seen_titles: set[str] = set()
    candidates: list[tuple[int, str, object]] = []

    for query, label in QUERIES:
        for entry in fetch_rss(query):
            if not is_recent(entry):
                continue
            key = clean_title(entry.get("title", ""))
            if key in seen_titles:
                continue
            seen_titles.add(key)
            candidates.append((score_entry(entry), label, entry))
        time.sleep(0.8)  # レート制限

    candidates.sort(key=lambda x: -x[0])
    top = [(label, entry) for _, label, entry in candidates[:7]]

    message = build_message(top)

    # LINE Notify は1メッセージ1000文字上限
    if len(message) > 990:
        message = message[:990] + "…"

    print(message)
    send_line_notify(message)


if __name__ == "__main__":
    main()
