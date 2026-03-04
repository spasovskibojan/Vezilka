"""
VEZILKA - Synthetic Educational Data Generator
Generates 10 JSONL entries matching old_data/ style.
Reads keys from .env (GEMINI_API_KEY, GROQ_API_KEY).
Usage: python generate_synthetic_data.py
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Run: pip install requests python-dotenv")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("Run: pip install python-dotenv")
    sys.exit(1)

load_dotenv()

current_api = "gemini"

TOPICS = [
    ("Граѓанско образование 8", "Граѓанско образование", "ДЕМОКРАТИЈА И ГРАЃАНСТВО",    "УЛОГАТА НА ГРАЃАНИНОТ ВО ДЕМОКРАТИЈАТА", "gra_8"),
    ("Граѓанско образование 8", "Граѓанско образование", "ВЛАДЕЕЊЕ НА ПРАВОТО",           "УСТАВ И ЗАКОНОДАВСТВО",                   "gra_8"),
    ("Физика 7",                 "Физика",                "ТЕРМИКА",                       "ТЕМПЕРАТУРА И ТОПЛИНА",                   "fiz_7"),
    ("Физика 7",                 "Физика",                "ОПТИКА",                        "СВЕТЛИНА И ПРЕКРШУВАЊЕ",                  "fiz_7"),
    ("Географија 7",              "Географија",             "ПРИРОДНИ НЕПОГОДИ",             "ЗЕМЈОТРЕСИ И ВУЛКАНИ",                    "geo_7"),
    ("Географија 7",              "Географија",             "ДЕМОГРАФИЈА",                   "МИГРАЦИИ НА НАСЕЛЕНИЕ",                   "geo_7"),
    ("Хемија 7",                 "Хемија",                "ХЕМИСКИ РЕАКЦИИ",               "ВИДОВИ И ЗАКОНИ НА ХЕМИСКИ РЕАКЦИИ",      "hem_7"),
    ("Хемија 7",                 "Хемија",                "РАСТВОРИ",                      "КОНЦЕНТРАЦИЈА НА РАСТВОР",                "hem_7"),
    ("Македонски јазик 7",       "Македонски јазик",      "ГРАМАТИКА",                     "ВИДОВИ ИМЕНКИ И НИВНА УПОТРЕБА",          "mkd_7"),
    ("Музичко образование 8",    "Музичко образование",   "МАКЕДОНСКА НАРОДНА МУЗИКА",     "КАРАКТЕРИСТИКИ И ИНСТРУМЕНТИ",            "muz_8"),
]

STYLE_EXAMPLES = [
    "Граѓанинот е човек кој има слободи, права и должности во општествената заедница, а тоа значи дека може да гласа, да учествува во граѓански здруженија и граѓански иницијативи, да работи, да плаќа даноци, да почитува закони и да ги ужива сите права и слободи запишани во Уставот на државата.",
    "Физиката е научна дисциплина што се занимава со проучување на основните закони на природата, особено со својствата на материјата, енергијата и нивното меѓусебно заемнодејство. За да разбереме одредена појава, потребно е да ги испитаме сите услови под кои таа се случува, да утврдиме што влијае врз неа и да сфатиме како тие фактори се меѓусебно поврзани.",
    "Физичките величини се својства на телата или појавите кои можат да се измерат, како што се должината, масата, времето, температурата и многу други. Со мерење на овие величини можеме да ги опишеме телата и појавите околу нас.",
]

SYSTEM_PROMPT = """You are an experienced author of Macedonian primary school textbooks (grades 7-8). You write educational texts in Macedonian language to be used for training a language model called Vezilka.

RULES:
- Write ONLY in Macedonian Cyrillic script (no Latin characters)
- Style: formal, textbook-like, factual — not conversational
- Length: 200-500 words
- Plain prose only — no headings, no bullet points, no numbering
- Start directly with the content (do not begin with "In this text...")
- Include concrete examples related to Macedonia where appropriate

Style examples (match this tone and writing style exactly):
---
{ex1}
---
{ex2}
---"""

USER_PROMPT = """Write a textbook passage in Macedonian Cyrillic for the following:
SUBJECT: {subject}
TOPIC: {topic}
SUBTOPIC: {subtopic}

Begin directly with the educational text:"""


class RateLimitError(Exception):
    pass

class APIError(Exception):
    pass


def call_gemini(api_key, user_msg, system_msg):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "systemInstruction": {"role": "user", "parts": [{"text": system_msg}]},
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 1200},
    }
    r = requests.post(url, json=payload, timeout=30)
    if r.status_code == 429:
        raise RateLimitError(f"Gemini 429: {r.text[:200]}")
    if r.status_code != 200:
        raise APIError(f"Gemini {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise APIError(f"Unexpected Gemini response: {r.text[:200]}")


def call_groq(api_key, user_msg, system_msg):
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.85,
        "max_tokens": 1200,
    }
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if r.status_code == 429:
        raise RateLimitError(f"Groq 429: {r.text[:200]}")
    if r.status_code != 200:
        raise APIError(f"Groq {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise APIError(f"Unexpected Groq response: {r.text[:200]}")


def generate_text(gemini_key, groq_key, subject, topic, subtopic):
    global current_api

    system_msg = SYSTEM_PROMPT.format(ex1=STYLE_EXAMPLES[0], ex2=STYLE_EXAMPLES[1])
    user_msg = USER_PROMPT.format(subject=subject, topic=topic, subtopic=subtopic)

    apis_to_try = []
    if current_api == "gemini" and gemini_key:
        apis_to_try.append(("gemini", gemini_key))
    if groq_key:
        apis_to_try.append(("groq", groq_key))
    if current_api == "groq" and gemini_key and ("gemini", gemini_key) not in apis_to_try:
        apis_to_try.append(("gemini", gemini_key))

    for api_name, api_key in apis_to_try:
        try:
            if api_name == "gemini":
                text = call_gemini(api_key, user_msg, system_msg)
            else:
                text = call_groq(api_key, user_msg, system_msg)
            current_api = api_name
            return text, api_name
        except RateLimitError:
            print(f"    {api_name.upper()} rate limit — switching API...")
            current_api = "groq" if api_name == "gemini" else "gemini"
        except APIError as e:
            print(f"    {api_name.upper()} error: {e}")

    raise RuntimeError("Both APIs failed or hit rate limits. Stopping.")


def make_record(text, source_label, topic, subtopic, prefix):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "id": f"textbook_{prefix}_{uuid.uuid4().hex[:12]}",
        "text": text,
        "type": "narrative",
        "last_modified_at": now,
        "meta": {
            "source": "GENERATED_BY_LLM",
            "url": "",
            "tags": [source_label, topic, subtopic],
            "labels": [],
            "scraped_at": now,
        }
    }


def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key   = os.getenv("GROQ_API_KEY")

    if not gemini_key and not groq_key:
        print("ERROR: Add GEMINI_API_KEY or GROQ_API_KEY to your .env file")
        sys.exit(1)

    global current_api
    current_api = "gemini" if gemini_key else "groq"

    print(f"\nVEZILKA - Synthetic Data PoC (10 samples)")
    print(f"Primary API : {current_api.upper()}")
    print(f"Fallback    : {'Groq' if gemini_key and groq_key else 'None'}\n")

    records = []
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc_output.jsonl")

    for i, (subject, source_label, topic, subtopic, prefix) in enumerate(TOPICS, 1):
        print(f"[{i:02d}/10] {source_label} -> {subtopic}")
        try:
            text, api_used = generate_text(gemini_key, groq_key, subject, topic, subtopic)
        except RuntimeError as e:
            print(f"\nSTOPPED: {e}")
            print(f"Generated {len(records)}/10 before stopping.")
            break

        record = make_record(text, source_label, topic, subtopic, prefix)
        records.append(record)
        cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
        print(f"       OK [{api_used.upper()}] {len(text)} chars | {cyrillic} Cyrillic chars")

        if i < len(TOPICS):
            time.sleep(4)

    print(f"\nGenerated {len(records)}/10 entries.")

    for i, r in enumerate(records, 1):
        print(f"\n-- Entry #{i} -- {r['meta']['tags'][1]} -> {r['meta']['tags'][2]}")
        print(f"   ID: {r['id']}")
        print()
        print(r['text'][:400] + ("..." if len(r['text']) > 400 else ""))

    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nSaved to: {output_path}\n")


if __name__ == "__main__":
    main()
