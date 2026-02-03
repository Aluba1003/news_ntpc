import os
import time
import requests
import feedparser
import yaml
import json
from dotenv import load_dotenv
from collections import OrderedDict

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PUSHED_FILE = "pushed.json"
MAX_RECORDS = 1000

def load_pushed_records():
    if os.path.exists(PUSHED_FILE):
        try:
            with open(PUSHED_FILE, "r", encoding="utf-8") as f:
                return OrderedDict(json.load(f))
        except: pass
    return OrderedDict()

def save_pushed_records(records):
    while len(records) > MAX_RECORDS:
        records.popitem(last=False)
    with open(PUSHED_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

pushed_records = load_pushed_records()

def send_telegram(text: str, delay: int):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True})
    if resp.status_code == 429:
        retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
        time.sleep(retry_after)
        return send_telegram(text, delay)
    time.sleep(delay)

def fetch_rss(source_name, url, keywords, exclude_path, exclude_titles, match_mode="any"):
    results = []
    # 預設過濾字（當 YAML 為空時）
    target_excludes = exclude_titles if exclude_titles else ["娛樂", "生活"]

    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = entry.title.strip()
            link = entry.link.strip()
            summary = getattr(entry, "summary", getattr(entry, "description", "")).strip()
            
            # --- 強化過濾邏輯：標題正規化 ---
            # 把全形 ｜ 轉半形 |, 把全形 － 轉半形 -, 並去掉所有空格
            clean_title = title.replace('｜', '|').replace('－', '-').replace(' ', '')
            
            # 只要排除關鍵字（如：娛樂）出現在處理後的標題中，就跳過
            if any(ex_kw in clean_title for ex_kw in target_excludes):
                print(f"⏩ 成功攔截娛樂/排除新聞: {title}")
                continue

            # URL 路徑過濾
            url_parts = link.split('/')
            if exclude_path and any(path_kw in url_parts for path_kw in exclude_path):
                continue

            # 正面關鍵字檢查 (新北)
            text_to_check = f"{title} {summary}"
            if keywords:
                if match_mode == "any" and any(kw in text_to_check for kw in keywords):
                    results.append((source_name, title, link))
                elif match_mode == "all" and all(kw in text_to_check for kw in keywords):
                    results.append((source_name, title, link))
            else:
                results.append((source_name, title, link))
                
    except Exception as e:
        print(f"❌ {source_name} 錯誤: {e}")
    return results

def load_config():
    config = {}
    if os.path.exists("sources.yml"):
        with open("sources.yml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    
    secret_sources = os.getenv("SOURCES_YML")
    if secret_sources:
        try:
            secret_config = yaml.safe_load(secret_sources)
            if "sources" in secret_config:
                if "sources" not in config: config["sources"] = []
                config["sources"].extend(secret_config["sources"])
            for key in ["keywords", "match_mode", "delay", "exclude_path", "exclude_titles"]:
                if key in secret_config: config[key] = secret_config[key]
        except: pass
    return config

def main():
    config = load_config()
    if not config: return

    keywords = config.get("keywords", [])
    exclude_path = config.get("exclude_path", [])
    exclude_titles = config.get("exclude_titles", [])
    match_mode = config.get("match_mode", "any")
    delay = config.get("delay", 1)

    for source in config.get("sources", []):
        if not source.get("enabled", True): continue
        
        results = fetch_rss(source["name"], source["url"], keywords, exclude_path, exclude_titles, match_mode)

        for src, title, link in results:
            # 只有當 link 不在紀錄中，或是標題有更新時才推播
            if link not in pushed_records or pushed_records[link] != title:
                pushed_records[link] = title
                send_telegram(f"{src}\n{title}\n{link}", delay)
                save_pushed_records(pushed_records)

if __name__ == "__main__":
    main()