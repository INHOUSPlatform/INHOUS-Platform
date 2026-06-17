"""Case studies: upload + run listings across the UK, Ireland and Europe.
Each case proves country-specific postcode handling and per-country currency,
then runs a compact journey (invite -> view -> feedback -> offer -> accept)."""
import json, urllib.request, urllib.error

BASE = "http://localhost:5001/api"
SYM = {"GBP":"GBP ", "EUR":"EUR ", "USD":"USD ", "CHF":"CHF ", "AED":"AED "}

def call(method, path, token=None, body=None, label=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method)
    req.add_header("Content-Type","application/json")
    if token: req.add_header("Authorization","Bearer "+token)
    def parse(raw):
        try: return json.loads(raw or "{}")
        except json.JSONDecodeError: return {"_raw": (raw or "")[:160]}
    try:
        with urllib.request.urlopen(req) as r: out,code = parse(r.read().decode()), r.status
    except urllib.error.HTTPError as e: out,code = parse(e.read().decode()), e.code
    if label:
        tag = "OK " if 200 <= code < 300 else "ERR"
        print(f"      [{tag} {code}] {label}")
        if code >= 300: print("           -> "+json.dumps(out))
    return out, code

def fmt(cur, n): return f"{SYM.get(cur,'')}{n:,}"

# Each case: country, the postcode AS TYPED (lowercase, to prove normalisation),
# expected currency (derived by backend from country), and listing details.
CASES = [
    {"country":"United Kingdom","city":"London","region":"Greater London","pc":"sw1w 9da",
     "addr":"14 Eaton Square","cur":"GBP","guide":8500000,
     "agent":"agent.uk@demo.example","agency":"Knight Frank","buyer":"Sterling Family Office","offer":8300000},
    {"country":"Ireland","city":"Dublin","region":"Leinster","pc":"d04 k6x8",
     "addr":"42 Ailesbury Road, Ballsbridge","cur":"EUR","guide":4750000,
     "agent":"agent.ie@demo.example","agency":"Sherry FitzGerald","buyer":"O'Brien Holdings","offer":4600000},
    {"country":"France","city":"Paris","region":"Ile-de-France","pc":"75008",
     "addr":"12 Avenue Montaigne","cur":"EUR","guide":9200000,
     "agent":"agent.fr@demo.example","agency":"Barnes Paris","buyer":"Maison Lefebvre","offer":8900000},
    {"country":"Germany","city":"Berlin","region":"Berlin","pc":"10707",
     "addr":"Kurfuerstendamm 188","cur":"EUR","guide":3400000,
     "agent":"agent.de@demo.example","agency":"Engel & Voelkers","buyer":"Brandt Vermoegen","offer":3250000},
    {"country":"Spain","city":"Barcelona","region":"Catalonia","pc":"08013",
     "addr":"Carrer de Mallorca 401","cur":"EUR","guide":2950000,
     "agent":"agent.es@demo.example","agency":"Lucas Fox","buyer":"Familia Navarro","offer":2800000},
    {"country":"Portugal","city":"Lisbon","region":"Lisboa","pc":"1250-147",
     "addr":"Avenida da Liberdade 200","cur":"EUR","guide":1850000,
     "agent":"agent.pt@demo.example","agency":"JLL Portugal","buyer":"Costa Investimentos","offer":1780000},
]

broker = call("POST","/auth/login",body={"email":"david@inhous.com","password":"inhous2026"})[0]["token"]
print("Logged in as broker David Johnson\n")

results = []
for c in CASES:
    print("="*74)
    print(f"  CASE STUDY: {c['country']}  —  {c['addr']}, {c['city']}")
    print("="*74)

    # 1. Upload the property — send country only; backend derives currency + normalises postcode
    pid = call("POST","/properties",broker,{
        "address_line1":c["addr"],"city":c["city"],"state_region":c["region"],
        "postcode":c["pc"],"country":c["country"],"guide_price":c["guide"],
        "tenure":"Freehold","bedrooms":4,"sale_mode":"managed"
    },label=f"upload listing (typed postcode '{c['pc']}')")[0]["id"]

    # 2. Verify what was stored
    prop = call("GET",f"/properties/{pid}",broker)[0]
    cur = prop.get("currency"); pc = prop.get("postcode"); reg = prop.get("state_region")
    cur_ok = "OK" if cur == c["cur"] else f"MISMATCH(got {cur})"
    pc_ok  = "OK" if pc == c["pc"].upper() else f"MISMATCH(got {pc})"
    print(f"      stored: currency={cur} [{cur_ok}]  postcode={pc} [{pc_ok}]  region={reg}")
    print(f"      guide price renders as: {fmt(cur, c['guide'])}")

    # 3. Compact journey: invite agent -> book viewing -> feedback -> offer
    itok = call("POST",f"/properties/{pid}/invite",broker,{"email":c["agent"],"role":"agent","agency_name":c["agency"]})[0]["token"]
    atok = call("POST","/auth/register-invite",body={"token":itok,"password":"Agent-Pass2026","full_name":c["agency"]+" Agent","phone":"+000"})[0]["token"]
    vid = call("POST",f"/properties/{pid}/viewings",atok,{"requested_date":"2026-06-22","requested_time":"11:00","buyer_reference":c["buyer"]})[0]["id"]
    call("POST",f"/properties/{pid}/viewings/{vid}/feedback",atok,{"interest_level":"hot","buyer_type":"cash","chain_status":"no_chain","budget_range":fmt(cur,c['guide']),"comments":"Strong interest"},label="viewing + feedback")
    call("POST",f"/properties/{pid}/offers",atok,{"amount":c["offer"],"buyer_full_name":c["buyer"],"buyer_type":"cash","purchase_method":"cash","cash_percent":100,"proof_of_funds_status":"confirmed","chain_status":"no_chain"},label=f"agent offers {fmt(cur,c['offer'])}")

    # 4. Prove the backend formats the notification in the right currency
    notifs = call("GET","/notifications",broker)[0]
    offer_note = next((n["title"] for n in notifs if n["title"].startswith("New offer")), "(none)")
    print(f"      broker notification reads: \"{offer_note}\"")

    # 5. Broker accepts
    offers = call("GET",f"/properties/{pid}/offers",broker)[0]
    call("POST",f"/properties/{pid}/offers/{offers[0]['id']}/action",broker,{"action":"accept"},label="broker accepts offer")
    prop2 = call("GET",f"/properties/{pid}",broker)[0]
    print(f"      property status -> {prop2['status'].upper()}\n")

    results.append({"country":c["country"],"pc":pc,"cur":cur,"guide":fmt(cur,c["guide"]),
                    "offer":fmt(cur,c["offer"]),"status":prop2["status"],
                    "cur_ok":cur_ok=="OK","pc_ok":pc_ok=="OK","note":offer_note})

# ── Summary ───────────────────────────────────────────────────────────────────
print("="*74)
print("  SUMMARY — INTERNATIONAL LISTINGS")
print("="*74)
print(f"  {'Country':<16}{'Postcode':<12}{'Cur':<5}{'Guide':>14}{'Accepted':>14}  Status")
print("  "+"-"*70)
for r in results:
    print(f"  {r['country']:<16}{r['pc']:<12}{r['cur']:<5}{r['guide']:>14}{r['offer']:>14}  {r['status']}")
allok = all(r["cur_ok"] and r["pc_ok"] for r in results)
print("  "+"-"*70)
print(f"  Currency derivation: {sum(r['cur_ok'] for r in results)}/{len(results)} correct   "
      f"Postcode normalisation: {sum(r['pc_ok'] for r in results)}/{len(results)} correct")
print(f"\n  {'ALL CASE STUDIES PASSED' if allok else 'SOME CHECKS FAILED'} — "
      f"{len(results)} countries, each uploaded, journeyed and sold in local currency.")
