"""Walk every page in the panel (Dashboard -> Admin) and complete a journey in each.
Reports PASS/FAIL per check against the live API."""
import json, urllib.request, urllib.error

BASE = "http://localhost:5001/api"
PASS = 0; FAIL = 0; FAILED = []

def api(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method)
    req.add_header("Content-Type","application/json")
    if token: req.add_header("Authorization","Bearer "+token)
    def parse(raw):
        try: return json.loads(raw or "{}")
        except json.JSONDecodeError: return {"_raw": (raw or "")[:160]}
    try:
        with urllib.request.urlopen(req) as r: return r.status, parse(r.read().decode())
    except urllib.error.HTTPError as e: return e.code, parse(e.read().decode())

def upload(path, token, filename, content, doc_type):
    b = "----INHOUSb0undaryX7"
    body = (
        f"--{b}\r\nContent-Disposition: form-data; name=\"doc_type\"\r\n\r\n{doc_type}\r\n"
        f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(BASE+path, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={b}")
    req.add_header("Authorization","Bearer "+token)
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read().decode() or "{}")

def check(cond, label):
    global PASS, FAIL
    print(f"      [{'PASS' if cond else 'FAIL'}] {label}")
    if cond: PASS += 1
    else: FAIL += 1; FAILED.append(label)

def section(t): print(f"\n{'='*72}\n  {t}\n{'='*72}")

broker = api("POST","/auth/login",body={"email":"david@inhous.com","password":"inhous2026"})[1]["token"]

# ── 1. DASHBOARD ──────────────────────────────────────────────────────────────
section("1. DASHBOARD  (GET /properties — stats + listing)")
code, props = api("GET","/properties",broker)
check(code==200 and isinstance(props,list), f"loads properties for stats ({len(props)} found)")

# ── 2. PROPERTIES ─────────────────────────────────────────────────────────────
section("2. PROPERTIES  (create listing)")
code, r = api("POST","/properties",broker,{
    "address_line1":"1 Panel Test Square","city":"London","state_region":"Greater London",
    "postcode":"sw1a 1aa","country":"United Kingdom","guide_price":4500000,"tenure":"Freehold","bedrooms":4})
check(code==201 and "id" in r, "create property")
pid = r.get("id")
code, lst = api("GET","/properties",broker)
check(any(p["id"]==pid for p in lst), "new property appears in list")

# ── 3. PROPERTY DETAIL  (view, edit/price change, parties, invite) ────────────
section("3. PROPERTY DETAIL  (GET, PATCH price, access, invite party)")
code, p = api("GET",f"/properties/{pid}",broker)
check(code==200 and p["currency"]=="GBP" and p["postcode"]=="SW1A 1AA", "GET detail (currency + normalised postcode)")
code, _ = api("PATCH",f"/properties/{pid}",broker,{"guide_price":4300000,"price_notes":"Test reduction"})
check(code==200, "PATCH price reduction")
code, p2 = api("GET",f"/properties/{pid}",broker)
check(any(pl["event_type"]=="reduction" for pl in p2.get("price_log",[])), "price_log records the reduction")
code, acc = api("GET",f"/properties/{pid}/access",broker)
check(code==200, "GET parties/access list")
code, inv = api("POST",f"/properties/{pid}/invite",broker,{"email":"agent.panel@demo.example","role":"agent","agency_name":"Panel Realty"})
check(code==200 and "token" in inv, "invite a party (agent)")
agent = api("POST","/auth/register-invite",body={"token":inv["token"],"password":"Agent-Pass2026","full_name":"Panel Agent","phone":"+000"})[1]["token"]
check(bool(agent), "invited agent registers + gets access")

# ── 4. VIEWINGS  (availability, slots, book, confirm) ─────────────────────────
section("4. VIEWINGS  (availability -> slots -> book -> confirm)")
code, _ = api("PATCH",f"/properties/{pid}/availability",broker,{"viewing_duration_mins":45,"buffer_mins":30,"date_override":{"date":"2026-06-23","mode":"confirm"}})
check(code==200, "PATCH availability (set 23 Jun to 'confirm')")
code, av = api("GET",f"/properties/{pid}/availability",broker)
check(code==200 and "by_day_of_week" in av, "GET availability")
code, slots = api("GET",f"/properties/{pid}/available-slots?date=2026-06-23",agent)
check(code==200 and slots.get("mode")=="confirm", "GET available-slots (mode=confirm)")
code, bk = api("POST",f"/properties/{pid}/viewings",agent,{"requested_date":"2026-06-23","requested_time":"11:00","buyer_reference":"Test Buyer"})
check(code==201 and bk.get("status")=="pending", "agent books -> pending (confirm mode)")
vid = bk.get("id")
code, _ = api("POST",f"/properties/{pid}/viewings/{vid}/confirm",broker,{"action":"confirm"})
check(code==200, "broker confirms viewing")
code, vs = api("GET",f"/properties/{pid}/viewings",broker)
check(any(v["id"]==vid and v["status"]=="confirmed" for v in vs), "viewing now confirmed in list")

# ── 5. FEEDBACK  (submit + read) ──────────────────────────────────────────────
section("5. FEEDBACK  (submit after viewing)")
code, _ = api("POST",f"/properties/{pid}/viewings/{vid}/feedback",agent,{"interest_level":"hot","buyer_type":"cash","chain_status":"no_chain","budget_range":"4.3m","comments":"Very keen"})
check(code==201, "agent submits feedback")
code, fb = api("GET",f"/properties/{pid}/feedback",broker)
check(code==200 and len(fb)>=1, f"broker reads feedback ({len(fb)})")

# ── 6. OFFERS  (submit, isolation, accept) ────────────────────────────────────
section("6. OFFERS  (submit -> isolation -> accept)")
code, of = api("POST",f"/properties/{pid}/offers",agent,{"amount":4250000,"buyer_full_name":"Test Buyer","buyer_type":"cash","purchase_method":"cash","cash_percent":100,"proof_of_funds_status":"confirmed","chain_status":"no_chain"})
check(code==201 and "id" in of, "agent submits offer")
oid = of.get("id")
code, amine = api("GET",f"/properties/{pid}/offers",agent)
code, aall = api("GET",f"/properties/{pid}/offers",broker)
check(len(amine)==1 and len(aall)>=1, f"role isolation (agent sees {len(amine)}, broker sees {len(aall)})")
code, _ = api("POST",f"/properties/{pid}/offers/{oid}/action",broker,{"action":"accept"})
check(code==200, "broker accepts offer (fires post-acceptance workflow)")
code, p3 = api("GET",f"/properties/{pid}",broker)
check(p3["status"]=="under_offer", "property status -> under_offer")

# ── 7. DOCUMENTS  (upload + list) ─────────────────────────────────────────────
section("7. DOCUMENTS  (file upload -> list)")
code, up = upload(f"/properties/{pid}/documents", broker, "memo_of_sale.txt", b"INHOUS memo of sale - test document", "memo_of_sale")
check(code==201 and "id" in up, "broker uploads a document (multipart)")
code, docs = api("GET",f"/properties/{pid}/documents",broker)
check(code==200 and any(d["doc_type"]=="memo_of_sale" for d in docs), f"document appears in vault ({len(docs)})")

# ── 8. AML / KYC  (create + certify + read) ───────────────────────────────────
section("8. AML / KYC  (create -> certify)")
code, aml = api("POST",f"/properties/{pid}/aml",broker,{"party_type":"vendor","person_name":"Test Vendor","nationality":"British"})
check(code==201 and "id" in aml, "create AML record")
code, badreq = api("POST",f"/properties/{pid}/aml",broker,{"party_type":"nonsense"})
check(badreq and code==400, "invalid AML rejected with 400 (was a 500 before)")
amlid = aml.get("id")
code, _ = api("POST",f"/properties/{pid}/aml/{amlid}/certify",broker)
check(code==200, "certify AML record")
code, recs = api("GET",f"/properties/{pid}/aml",broker)
check(any(r["id"]==amlid and r["status"]=="certified" for r in recs), "AML shows certified")

# ── 9. PHOTOGRAPHY  (book the shoot) ──────────────────────────────────────────
section("9. PHOTOGRAPHY  (set preferred date)")
code, ph = api("GET",f"/properties/{pid}/photography",broker)
check(code==200 and len(ph)>=1, "GET photography bookings")
photo_id = [b for b in ph if b["booking_type"]=="photography"][0]["id"]
code, _ = api("PATCH",f"/properties/{pid}/photography/{photo_id}",broker,{"preferred_date":"2026-07-01","preferred_time":"10:00","photographer_firm":"Lens & Light"})
check(code==200, "PATCH preferred date (save & confirm)")
code, ph2 = api("GET",f"/properties/{pid}/photography",broker)
check(any(b["id"]==photo_id and b["status"]=="date_selected" for b in ph2), "booking status -> date_selected")

# ── 10. NOTIFICATIONS  (read + mark-read) ─────────────────────────────────────
section("10. NOTIFICATIONS  (list + mark read)")
code, ns = api("GET","/notifications",broker)
check(code==200 and len(ns)>=1, f"GET notifications ({len(ns)})")
code, _ = api("POST","/notifications/mark-read",broker)
check(code==200, "mark all read")
code, ns2 = api("GET","/notifications",broker)
check(all(n["is_read"]==1 for n in ns2), "all notifications now marked read")

# ── 11. ADMIN  (create user + send invite) ────────────────────────────────────
section("11. ADMIN  (create user + send invite)")
code, u = api("POST","/users",broker,{"email":"paneltest.user@demo.example","password":"Test-Pass2026","full_name":"Panel Admin User","role":"agent","agency_name":"Admin Test"})
check(code==201 and "id" in u, "create user account")
code, dup = api("POST","/users",broker,{"email":"paneltest.user@demo.example","password":"Test-Pass2026","full_name":"Dup","role":"agent"})
check(code==400, "duplicate email rejected (400)")
code, inv2 = api("POST",f"/properties/{pid}/invite",broker,{"email":"buyer.panel@demo.example","role":"buyer_solicitor","agency_name":"Test Law"})
check(code==200 and "invite_url" in inv2, "send invite link")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print(f"\n{'='*72}\n  RESULT: {PASS} passed, {FAIL} failed  (across all 11 panel sections)\n{'='*72}")
if FAILED:
    print("  FAILURES:")
    for f in FAILED: print("   -", f)
else:
    print("  Every panel page completed its journey end-to-end.")
