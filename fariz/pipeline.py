#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FARIZ KANAAN — خط التشغيل في GitHub Actions.

  fetch   : يطلب المنشور التالي من n8n (أو منشورات محددة من ملفات المستودع) ويصمّمه.
  notify  : بعد رفع الملفات إلى فرع fariz-media، يتحقق أن روابطها تعمل ثم يرسلها لـ n8n
            (n8n ينشرها على إنستغرام إذا كان النشر مفعّلًا، أو يحفظها للمراجعة).

الإعدادات من متغيرات البيئة:
  FARIZ_TOKEN, N8N_BASE_URL, FARIZ_PUBLISH (0/1), FARIZ_POSTS (مثل "3-10" للتشغيل المحلي)
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
JOBS = HERE / "out" / "jobs.json"
BASE = os.environ.get("N8N_BASE_URL", "https://farizk16.app.n8n.cloud").rstrip("/")
TOKEN = os.environ.get("FARIZ_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "ethecahack/noxveilx-render")


def log(m):
    print(m, flush=True)


def parse_posts(s):
    out = []
    for part in (s or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def fetch_next(post=None):
    params = {"token": TOKEN}
    if post:
        params["post"] = str(post)
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE}/webhook/fariz-next", params=params, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa
            log(f"n8n fetch attempt {attempt + 1} failed: {e}")
            time.sleep(10)
    raise RuntimeError("تعذّر الوصول إلى n8n")


def content_file(n, content_str):
    """المحتوى من n8n، أو من ملف المستودع إن وُجد (الدفعة التجريبية)."""
    local = HERE / "content" / f"POST_{n:03d}.json"
    if local.exists():
        return local
    if not content_str:
        raise RuntimeError(f"لا يوجد محتوى للمنشور {n}")
    d = json.loads(content_str)
    d["post_number"] = n
    tmp = HERE / "out" / f"_content_{n:03d}.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return tmp


def cmd_fetch():
    import render
    jobs = []
    local_posts = parse_posts(os.environ.get("FARIZ_POSTS", ""))
    items = []
    if local_posts and os.environ.get("FARIZ_PUBLISH", "0") == "1":
        # نشر منشورات محددة فعليًا: نأخذ سجلها من n8n حتى يُسجَّل النشر عليه
        for n in local_posts:
            it = fetch_next(post=n)
            if it and it.get("found") == "yes" and int(it["post_number"]) == n:
                items.append(it)
            else:
                log(f"المنشور {n} غير جاهز في n8n (ربما نُشر من قبل) — تم تخطيه")
    elif local_posts:
        items = [{"row_id": None, "post_number": n, "content": ""} for n in local_posts]
    else:
        count = int(os.environ.get("FARIZ_COUNT", "1"))
        for _ in range(count):
            it = fetch_next()
            if not it or it.get("found") != "yes":
                log("لا يوجد منشور جاهز في n8n.")
                break
            items.append(it)
    for it in items:
        n = int(it["post_number"])
        job = {"row_id": it.get("row_id"), "post_number": n}
        try:
            cf = content_file(n, it.get("content"))
            out, meta = render.render_post(cf, HERE / "out")
            job.update(meta)
            job["dir"] = out.name
        except Exception as e:  # noqa
            traceback.print_exc()
            job["render_error"] = f"{type(e).__name__}: {e}"[:800]
        jobs.append(job)
    JOBS.parent.mkdir(parents=True, exist_ok=True)
    JOBS.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"jobs: {len(jobs)}")


def url_ok(u):
    for attempt in range(12):
        try:
            r = requests.head(u, timeout=30, allow_redirects=True)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and ("image" in ct or "video" in ct):
                return True
            log(f"  waiting for {u} ({r.status_code} {ct})")
        except Exception as e:  # noqa
            log(f"  waiting for {u} ({e})")
        time.sleep(15)
    return False


def cmd_notify(sha):
    jobs = json.loads(JOBS.read_text(encoding="utf-8")) if JOBS.exists() else []
    publish = os.environ.get("FARIZ_PUBLISH", "0") == "1"
    cdn = f"https://cdn.jsdelivr.net/gh/{REPO}@{sha}"
    for j in jobs:
        body = {"token": TOKEN, "row_id": j.get("row_id"), "post_number": j["post_number"], "type": j.get("type"), "publish": publish}
        if j.get("render_error"):
            body["render_error"] = j["render_error"]
        else:
            files = [f"{cdn}/{j['dir']}/{f}" for f in j["files"]]
            body["caption"] = j["caption"]
            if j["type"] == "reel":
                body["video_url"] = files[1]
                body["cover_url"] = files[0]
            else:
                body["images"] = files
            bad = [u for u in files if not url_ok(u)]
            if bad:
                body["render_error"] = "media URL not reachable: " + ", ".join(bad)
        if j.get("row_id") is None:
            log(f"POST {j['post_number']:03d}: تشغيل تجريبي — لا يُرسل لـ n8n. الملفات: {body.get('images') or body.get('video_url')}")
            continue
        r = requests.post(f"{BASE}/webhook/fariz-publish", json=body, timeout=60)
        log(f"POST {j['post_number']:03d} -> n8n {r.status_code} (publish={publish})")


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        cmd_fetch()
    elif sys.argv[1] == "notify":
        cmd_notify(sys.argv[2])
