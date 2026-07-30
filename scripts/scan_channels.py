"""Rank channels on median views + hit-rate. No mean anywhere in the path.

Rev 1 of this scan prefiltered candidates by total_views/video_count - the mean -
which is the exact statistic the run then proved broken on 51 of 76 channels.
Channels with a steady median but no viral hit were discarded before the deep
scan could see them, biasing the sample toward lottery-shaped channels.

This revision does no ranked prefiltering at all: every channel passing the
basic subs/count/age gates gets deep-scanned, and the full candidate list is
persisted so any later re-filter is free rather than costing another search.
"""
import csv, os, statistics as st, sys
from datetime import datetime, timezone

sys.path.insert(0, "src")
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.providers.quota import QuotaLedger
from contentforge.cli import _live_transport

NICHES = {
    "space": "space explained",
    "psychology": "psychology explained",
    "history": "history explained",
    "biology": "biology explained",
    "technology": "technology explained",
    "economics": "how money works explained",
    "mythology": "mythology explained",
    "geography": "geography countries explained",
    "medicine": "how the human body works explained",
    "physics": "physics explained",
    "animals": "animals wildlife explained",
    "philosophy": "philosophy explained",
    "crime": "true crime forensics explained",
    "engineering": "how machines work explained",
    "kids_learning": "kids learning animated educational",
    "language": "learn english animated story",
    "survival": "survival scenarios explained",
    "cars": "cars automotive explained",
    "food_science": "food science explained",
    "ocean": "deep ocean creatures explained",
    "art": "art history explained",
    "aviation": "aviation aircraft explained",
    "architecture": "architecture buildings explained",
    "math": "mathematics explained visually",
}

# Loosened from rev 1: economics/medicine/engineering returned zero channels
# there, which was a filter artefact rather than an empty niche.
MIN_SUBS = 500
MIN_VIDEOS = 5
MAX_VIDEOS = 600
MAX_AGE_DAYS = 365 * 4
SHORTS_CUTOFF_S = 120
HIT_THRESHOLD = 100_000
QUOTA_STOP = 8_600        # leave headroom; today's earlier runs already spent ~2,250

OUT = os.environ["SCAN_OUT"]
CANDS_OUT = os.environ["CANDS_OUT"]
now = datetime.now(timezone.utc)
key = os.environ["YOUTUBE_API_KEY"]
client = YouTubeClient(key, _live_transport(key))
ledger = QuotaLedger(daily_limit=10_000)

fh = open(OUT, "w", newline=""); w = csv.writer(fh)
w.writerow(["niche","channel_id","title","subs","n_long","median","mean","skew",
            "hits","hit_rate","min","max","spread","newest_days","oldest_days","uploads_playlist"])
fh.flush()

cf = open(CANDS_OUT, "w", newline=""); cw = csv.writer(cf)
cw.writerow(["niche","channel_id","title","subs","total_views","video_count","age_days","passed_gates"])
cf.flush()

seen = set(); rows = 0; scanned = 0

def val(x):
    return x.value if hasattr(x, "value") else x

for niche, query in NICHES.items():
    if ledger.spent > QUOTA_STOP:
        print("quota headroom reached - stopping", flush=True); break
    try:
        refs, ledger = client.search_channels(query, ledger, max_results=50)
    except Exception as e:
        print(f"[{niche}] search failed: {str(e)[:110]}", flush=True)
        if "quota" in str(e).lower(): break
        continue

    fresh = [r.channel_id for r in refs if r.channel_id not in seen]
    seen.update(fresh)
    if not fresh: continue

    try:
        stats, ledger = client.get_channels(fresh, ledger)
    except Exception as e:
        print(f"[{niche}] channels.list failed: {str(e)[:110]}", flush=True); continue

    cands = []
    for s in stats:
        subs, nvid = val(s.subscribers), val(s.video_count)
        tot = val(s.view_count); age = (now - val(s.published_at)).days
        ok = subs >= MIN_SUBS and MIN_VIDEOS <= nvid <= MAX_VIDEOS and age <= MAX_AGE_DAYS
        cw.writerow([niche, s.channel_id, s.title, subs, tot, nvid, age, int(ok)])
        if ok:
            cands.append({"id": s.channel_id, "title": s.title, "subs": subs})
    cf.flush()
    if not cands:
        print(f"[{niche}] 0/{len(stats)} passed gates", flush=True); continue

    try:
        uploads, ledger = client.get_uploads_playlists([c["id"] for c in cands], ledger)
    except Exception as e:
        print(f"[{niche}] uploads failed: {str(e)[:110]}", flush=True); continue

    kept = 0
    for c in cands:
        if ledger.spent > QUOTA_STOP:
            print("quota headroom reached mid-niche", flush=True); break
        pl = uploads.get(c["id"])
        if not pl: continue
        try:
            ids, ledger = client.get_playlist_video_ids(pl, ledger, max_videos=50)
            if not ids: continue
            vids, ledger = client.get_videos(ids, ledger)
        except Exception as e:
            if "quota" in str(e).lower():
                print(f"QUOTA EXHAUSTED at {niche}/{c['title']}", flush=True)
                fh.close(); cf.close()
                print(f"wrote {rows} rows, spent {ledger.spent}"); sys.exit(0)
            continue
        scanned += 1
        longs = [v for v in vids if val(v.duration_seconds) >= SHORTS_CUTOFF_S]
        if len(longs) < MIN_VIDEOS: continue
        views = sorted(val(v.view_count) for v in longs)
        ages = [(now - val(v.published_at)).days for v in longs]
        med, mean = st.median(views), st.mean(views)
        hits = sum(1 for v in views if v >= HIT_THRESHOLD)
        w.writerow([niche, c["id"], c["title"], c["subs"], len(longs), round(med), round(mean),
                    round(mean / max(med, 1), 2), hits, round(100*hits/len(views), 1),
                    views[0], views[-1], round(views[-1]/max(views[0],1), 1),
                    min(ages), max(ages), pl])
        fh.flush(); rows += 1; kept += 1
    print(f"[{niche}] {kept} kept / {len(cands)} gated / {len(stats)} found  (spent {ledger.spent})", flush=True)

fh.close(); cf.close()
print(f"\nDONE: {rows} channels profiled, {scanned} deep-scanned, {ledger.spent} units")
