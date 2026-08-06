import csv, os, sys, statistics as st
from datetime import datetime, timezone
sys.path.insert(0,"src")
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.providers.quota import QuotaLedger
from contentforge.cli import _live_transport

EXCLUDE={"Art History Explained","Bluntly Explained","Explainer Chris","Paint Professor",
 "Brainosophy","Pilot Debrief","Air Crash Investigation","Joe Bart Philosophy",
 "How Money Works Uncut","Imagine the Physics"}

rows=[r for r in csv.DictReader(open("docs/evidence/2026-07-29/scan-rev2-channel-profiles.csv"))]
cand=[r for r in rows if r["title"].strip() not in EXCLUDE
      and int(r["n_long"])>=12 and float(r["spread"])>=5]
cand.sort(key=lambda r:-int(r["median"]))
print(f"{len(cand)} channels pass rules 1-3\n")

key=os.environ["YOUTUBE_API_KEY"]
c=YouTubeClient(key,_live_transport(key)); led=QuotaLedger(daily_limit=10_000)
now=datetime.now(timezone.utc)
out=[]
for r in cand:
    if len(out)>=48: break
    try:
        ids,led=c.get_playlist_video_ids(r["uploads_playlist"].strip(),led,max_videos=50)
        vids,led=c.get_videos(ids,led)
    except Exception as e:
        print(f"  {r['title'][:32]}: ERR {str(e)[:70]}"); continue
    longs=[v for v in vids if v.duration_seconds.value>=120]
    if len(longs)<12: continue
    # rule 4: age-matched pool = drop the newest 15% and oldest 15% by age
    longs.sort(key=lambda v:(now-v.published_at.value).days)
    k=max(1,len(longs)//7)
    pool=longs[k:len(longs)-k] if len(longs)-2*k>=6 else longs
    pool.sort(key=lambda v:-v.view_count.value)
    hits,flops=pool[:3],pool[-3:]
    ah=st.median([(now-v.published_at.value).days for v in hits])
    af=st.median([(now-v.published_at.value).days for v in flops])
    if abs(ah-af)>=60:
        print(f"  DROP {r['title'][:32]:<34} age gap {abs(ah-af):.0f}d"); continue
    if hits[-1].view_count.value <= flops[0].view_count.value: continue
    print(f"  KEEP {r['title'][:32]:<34} hits {hits[0].view_count.value:>9,}-{hits[-1].view_count.value:>8,} "
          f"flops {flops[0].view_count.value:>8,}-{flops[-1].view_count.value:>7,}  age {ah:.0f}/{af:.0f}d")
    for tag,sel in (("HIT",hits),("FLOP",flops)):
        for v in sel:
            out.append([r["title"],tag,v.view_count.value,(now-v.published_at.value).days,v.video_id,v.title])
with open(os.environ["OUT"],"w",newline="") as fh:
    w=csv.writer(fh); w.writerow(["channel","tag","views","age","video_id","title"]); w.writerows(out)
print(f"\n{len(out)} videos from {len(out)//6} channels; units {led.spent}")
