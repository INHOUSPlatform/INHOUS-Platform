"""Populate a realistic week of viewings (Mon 22 - Fri 26 Jun 2026) across several
properties, covering every status: confirmed, pending, completed, declined."""
import json, urllib.request, urllib.error
BASE="http://localhost:5001/api"
def api(m,p,t=None,b=None):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(BASE+p,data=d,method=m); r.add_header("Content-Type","application/json")
    if t: r.add_header("Authorization","Bearer "+t)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode() or "{}")
        except: return e.code,{}
broker=api("POST","/auth/login",b={"email":"david@inhous.com","password":"inhous2026"})[1]["token"]
props=[p for p in api("GET","/properties",broker)[1]]
props.sort(key=lambda p:p["id"])
P=props[:6]
if len(P)<6: print("need >=6 properties"); raise SystemExit
def book(pidx,date,time,agency,buyer,status):
    pid=P[pidx]["id"]
    if status in ("pending","declined"):
        api("PATCH",f"/properties/{pid}/availability",broker,{"date_override":{"date":date,"mode":"confirm"}})
    code,r=api("POST",f"/properties/{pid}/viewings",broker,{"requested_date":date,"requested_time":time,"agency_name":agency,"negotiator_name":"INHOUS Desk","buyer_reference":buyer})
    if code!=201: print("  skip",P[pidx]["reference"],date,time,code); return
    vid=r["id"]
    if status=="completed":
        api("POST",f"/properties/{pid}/viewings/{vid}/feedback",broker,{"interest_level":"warm","buyer_type":"cash","comments":buyer})
    elif status=="declined":
        api("POST",f"/properties/{pid}/viewings/{vid}/confirm",broker,{"action":"decline","reason":"Vendor unavailable"})
    print(f"  {P[pidx]['reference']:<16} {date} {time}  {status:<10} {agency}")
SCHED=[
 (0,"2026-06-22","09:30","Knight Frank","Cash buyer, relocating from Geneva","confirmed"),
 (1,"2026-06-22","11:00","Savills","Family, chain-free","confirmed"),
 (2,"2026-06-22","14:00","Hamptons","Investor — buy to let","pending"),
 (3,"2026-06-22","16:00","Foxtons","Local downsizer","confirmed"),
 (0,"2026-06-23","10:00","Lisney","Second viewing — very keen","completed"),
 (4,"2026-06-23","12:30","Knight Frank","Overseas buyer","confirmed"),
 (5,"2026-06-23","15:00","Savills","First-time prime buyer","pending"),
 (1,"2026-06-24","09:00","Hamptons","Family office acquisition","confirmed"),
 (2,"2026-06-24","11:30","Foxtons","Needs full renovation","declined"),
 (3,"2026-06-24","13:00","Knight Frank","Cash, no chain","confirmed"),
 (0,"2026-06-24","17:00","Savills","Evening viewing","confirmed"),
 (4,"2026-06-25","10:30","Lisney","Corporate relocation","completed"),
 (5,"2026-06-25","14:00","Hamptons","Pied-a-terre","confirmed"),
 (1,"2026-06-25","16:00","Knight Frank","Upsizing family","pending"),
 (2,"2026-06-26","09:30","Savills","Developer","confirmed"),
 (3,"2026-06-26","11:00","Foxtons","Family — school catchment","completed"),
 (0,"2026-06-26","15:30","Knight Frank","VIP applicant","confirmed"),
]
print("Booking sample week of viewings (Mon 22 - Fri 26 Jun 2026):")
for s in SCHED: book(*s)
allv=api("GET","/viewings",broker)[1]
wk=[v for v in allv if "2026-06-22"<=v["requested_date"]<="2026-06-26"]
from collections import Counter
print(f"\nThat week: {len(wk)} viewings across {len(set(v['property_id'] for v in wk))} properties")
print("By status:", dict(Counter(v['status'] for v in wk)))
