import csv, os, sys
from datetime import datetime, timezone
sys.path.insert(0,"src")
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.providers.quota import QuotaLedger
from contentforge.cli import _live_transport
key=os.environ["YOUTUBE_API_KEY"]
c=YouTubeClient(key,_live_transport(key)); led=QuotaLedger(daily_limit=10_000)
now=datetime.now(timezone.utc)
TARGETS={"Pilot Debrief","Air Crash Investigation","How Money Works Uncut",
         "Joe Bart Philosophy","Imagine the Physics"}
rows=[r for r in csv.DictReader(open(os.environ["SCAN"]))]
out=[]
for r in rows:
    if r["title"].strip() not in TARGETS: continue
    pl=r["uploads_playlist"].strip()
    try:
        ids,led=c.get_playlist_video_ids(pl,led,max_videos=50)
        vids,led=c.get_videos(ids,led)
    except Exception as e:
        print(f"{r['title']}: ERR {str(e)[:90]}"); continue
    longs=[v for v in vids if v.duration_seconds.value>=120]
    longs.sort(key=lambda v:-v.view_count.value)
    print(f"\n### {r['title']}  ({len(longs)} long-form)")
    for tag,sel in (("HIT",longs[:3]),("FLOP",longs[-3:])):
        for v in sel:
            age=(now-v.published_at.value).days
            print(f"  {tag:<5}{v.view_count.value:>10,}  {age:>4}d  {v.video_id}  {v.title[:70]}")
            out.append((r["title"],tag,v.view_count.value,age,v.video_id,v.title))
with open(os.environ["OUT"],"w",newline="") as fh:
    w=csv.writer(fh); w.writerow(["channel","tag","views","age","video_id","title"]); w.writerows(out)
print(f"\nunits {led.spent}")
