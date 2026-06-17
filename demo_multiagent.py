"""Multi-agent demo: several agencies compete on one listing.
Each agent books a viewing -> carries it out -> lodges buyer details + feedback -> (maybe) offers.
Then the broker sees the consolidated, ranked picture."""
import json, urllib.request, urllib.error

BASE = "http://localhost:5001/api"

def call(method, path, token=None, body=None, label=None, quiet=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    def parse(raw):
        try: return json.loads(raw or "{}")
        except json.JSONDecodeError: return {"_raw": (raw or "")[:160]}
    try:
        with urllib.request.urlopen(req) as r:
            out, code = parse(r.read().decode()), r.status
    except urllib.error.HTTPError as e:
        out, code = parse(e.read().decode()), e.code
    if label and not quiet:
        tag = "OK " if 200 <= code < 300 else "ERR"
        print(f"      [{tag} {code}] {label}")
        if code >= 300: print("           -> " + json.dumps(out))
    return out, code

def section(t): print(f"\n{'='*72}\n  {t}\n{'='*72}")
def money(n): return f"GBP {n:,}"

# ── The competing agencies and their buyers ───────────────────────────────────
AGENTS = [
    {"agency":"Knight Frank Belgravia", "name":"Marcus Chen",    "email":"marcus.chen@kf.example",
     "date":"2026-06-22","time":"10:00",
     "buyer":"Dr Anneke Visser","btype":"cash","chain":"no_chain","nat":"Dutch",
     "interest":"hot","budget":"8.0-8.5m","comment":"Relocating from Geneva. Loved the light. Wants to proceed quickly.",
     "offer":{"amount":8250000,"method":"cash","cash":100,"mort":0,"provider":"UBS Switzerland AG"}},
    {"agency":"Savills Sloane Street", "name":"Olivia Bennett", "email":"olivia.bennett@savills.example",
     "date":"2026-06-22","time":"12:00",
     "buyer":"Mr & Mrs Hargreaves","btype":"mortgage","chain":"no_chain","nat":"British",
     "interest":"warm","budget":"7.5-8.0m","comment":"Upsizing locally. Keen but want a second viewing with their architect.",
     "offer":{"amount":7900000,"method":"mortgage","cash":25,"mort":75,"provider":"Coutts & Co"}},
    {"agency":"Hamptons Mayfair", "name":"Raj Patel", "email":"raj.patel@hamptons.example",
     "date":"2026-06-23","time":"11:00",
     "buyer":"Sterling Family Office","btype":"cash","chain":"no_chain","nat":"British",
     "interest":"hot","budget":"8.2-8.6m","comment":"Acquiring as a London base. Cash, no chain, can exchange in 3 weeks.",
     "offer":{"amount":8400000,"method":"cash","cash":100,"mort":0,"provider":"Sterling FO treasury"}},
    {"agency":"Foxtons Chelsea", "name":"Chloe Martin", "email":"chloe.martin@foxtons.example",
     "date":"2026-06-24","time":"14:00",
     "buyer":"Daniel Brooks","btype":"mortgage","chain":"in_chain","nat":"British",
     "interest":"cold","budget":"7.0-7.5m","comment":"Felt the refurb budget was too high for them. Unlikely to proceed.",
     "offer":None},
    {"agency":"Strutt & Parker", "name":"Tom Wright", "email":"tom.wright@struttparker.example",
     "date":"2026-06-25","time":"15:00",
     "buyer":"Helena Rossi","btype":"cash","chain":"no_chain","nat":"Italian",
     "interest":"warm","budget":"~8.0m","comment":"Pied-a-terre buyer. Considering against one other property.",
     "offer":{"amount":8100000,"method":"cash","cash":100,"mort":0,"provider":"Private cash"}},
]

# ── Broker sets the stage ─────────────────────────────────────────────────────
section("BROKER PREPARES THE LISTING")
broker = call("POST","/auth/login",body={"email":"david@inhous.com","password":"inhous2026"})[0]["token"]
print("   Logged in as broker David Johnson")
pid = call("POST","/properties",broker,{
    "address_line1":"14 Eaton Square","address_line2":"Belgravia","city":"London","postcode":"SW1W 9DA",
    "tenure":"Freehold","guide_price":8500000,"bedrooms":5,"floor_area_sqft":4120,"sale_mode":"managed"
},label="create listing 14 Eaton Square @ "+money(8500000))[0]["id"]
# Weekdays default to 'instant', so agent bookings auto-confirm.

# ── Each agency runs its own mini-journey ─────────────────────────────────────
for a in AGENTS:
    section(f"AGENCY: {a['agency']}  —  negotiator {a['name']}")
    itoken = call("POST",f"/properties/{pid}/invite",broker,
                  {"email":a["email"],"role":"agent","agency_name":a["agency"]},
                  label="broker invites agency")[0]["token"]
    tok = call("POST","/auth/register-invite",
               body={"token":itoken,"password":"Agent-Pass2026","full_name":a["name"],"phone":"+44 7700 900000"},
               label="agent accepts invite & creates account")[0]["token"]
    a["token"] = tok

    # 1. Book a viewing (instant weekday -> confirmed)
    bk, _ = call("POST",f"/properties/{pid}/viewings",tok,{
        "requested_date":a["date"],"requested_time":a["time"],
        "buyer_reference":a["buyer"],"buyer_notes":"Registered applicant"
    },label=f"books viewing {a['date']} {a['time']}")
    a["vid"] = bk["id"]
    print(f"         viewing #{a['vid']} -> {bk['status'].upper()}")

    # 2. Carry out the viewing -> lodge buyer details + upload feedback
    call("POST",f"/properties/{pid}/viewings/{a['vid']}/feedback",tok,{
        "interest_level":a["interest"],"buyer_type":a["btype"],"chain_status":a["chain"],
        "budget_range":a["budget"],"follow_up_likelihood":("very_likely" if a["interest"]=="hot" else "possible" if a["interest"]=="warm" else "unlikely"),
        "comments":a["comment"]
    },label=f"viewing done -> feedback ({a['interest'].upper()} interest, buyer: {a['buyer']})")

    # 3. Maybe submit an offer
    if a["offer"]:
        o = a["offer"]
        call("POST",f"/properties/{pid}/offers",tok,{
            "amount":o["amount"],"buyer_full_name":a["buyer"],"buyer_type":a["btype"],
            "buyer_nationality":a["nat"],"purchase_method":o["method"],
            "cash_percent":o["cash"],"mortgage_percent":o["mort"],"financial_provider":o["provider"],
            "proof_of_funds_status":("confirmed" if a["btype"]=="cash" else "received"),
            "chain_status":a["chain"],"proposed_exchange":"2026-07-20","proposed_completion":"2026-08-18",
            "conditions":"Subject to survey","valid_until":"2026-07-04"
        },label=f"SUBMITS OFFER {money(o['amount'])} ({o['method']})")
    else:
        print("         no offer (buyer not proceeding)")

# ── Role isolation check: an agent sees only their own offer ───────────────────
section("ROLE ISOLATION CHECK")
mine,_ = call("GET",f"/properties/{pid}/offers",AGENTS[0]["token"],label="Marcus Chen (agent) lists offers",quiet=True)
print(f"   Agent Marcus sees {len(mine)} offer (only his own).")
allo,_ = call("GET",f"/properties/{pid}/offers",broker,label="Broker lists offers",quiet=True)
print(f"   Broker sees {len(allo)} offers (all agencies).")

# ── Broker's consolidated view ────────────────────────────────────────────────
section("BROKER CONSOLIDATED VIEW")
views,_ = call("GET",f"/properties/{pid}/viewings",broker,quiet=True)
print(f"   VIEWINGS BOOKED: {len(views)}")
for v in sorted(views,key=lambda x:(x['requested_date'],x['requested_time'])):
    print(f"     - {v['requested_date']} {v['requested_time']}  {v['status']:9s}  {v['agency_name']}")

fb,_ = call("GET",f"/properties/{pid}/feedback",broker,quiet=True)
print(f"\n   FEEDBACK RECEIVED: {len(fb)}")
order={"hot":0,"warm":1,"cold":2,"not_proceeding":3}
for f in sorted(fb,key=lambda x:order.get(x['interest_level'],9)):
    print(f"     - {(f['interest_level'] or '').upper():5s} | {f['agency_name']:24s} | {f['buyer_type'] or '?':8s} | {f['budget_range'] or ''}")

print(f"\n   OFFERS (ranked high -> low):")
for o in allo:
    pof = o.get('proof_of_funds_status','')
    print(f"     - {money(o['amount']):>14s} | {o['agency_name']:24s} | {o['buyer_full_name']:22s} | {o['purchase_method']} | PoF:{pof}")

# ── Broker accepts the best offer ─────────────────────────────────────────────
section("BROKER ACCEPTS THE WINNING OFFER")
best = allo[0]
print(f"   Best offer: {money(best['amount'])} from {best['agency_name']} ({best['buyer_full_name']})")
call("POST",f"/properties/{pid}/offers/{best['id']}/action",broker,{"action":"accept"},
     label="broker accepts top offer (fires post-acceptance workflow)")
# Decline the rest
for o in allo[1:]:
    call("POST",f"/properties/{pid}/offers/{o['id']}/action",broker,
         {"action":"decline","reason":"A higher offer was accepted"},
         label=f"declines {money(o['amount'])} ({o['agency_name']})")

prop,_ = call("GET",f"/properties/{pid}",broker,quiet=True)
print(f"\n   Property status now: {prop['status'].upper()}")
print(f"{'='*72}\n  DONE — {len(AGENTS)} agencies, {len(views)} viewings, {len(fb)} feedbacks, {len(allo)} offers, 1 accepted\n{'='*72}")
