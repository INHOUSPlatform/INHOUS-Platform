"""Full lifecycle case study: onboard a client -> market -> view -> offer ->
accept -> AML -> documents -> completion -> third-party introductions."""
import json, urllib.request, urllib.error

BASE = "http://localhost:5001/api"

def call(method, path, token=None, body=None, label=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method)
    req.add_header("Content-Type","application/json")
    if token: req.add_header("Authorization","Bearer "+token)
    def parse(raw):
        try: return json.loads(raw or "{}")
        except json.JSONDecodeError: return {"_raw": (raw or "")[:140]}
    try:
        with urllib.request.urlopen(req) as r: out,code = parse(r.read().decode()), r.status
    except urllib.error.HTTPError as e: out,code = parse(e.read().decode()), e.code
    if label:
        tag = "OK " if 200 <= code < 300 else "ERR"
        print(f"   [{tag} {code}] {label}")
        if code >= 300: print("        -> "+json.dumps(out))
    return out, code

def upload(path, token, filename, content, doc_type):
    bd="----lifecycle"
    body=(f"--{bd}\r\nContent-Disposition: form-data; name=\"doc_type\"\r\n\r\n{doc_type}\r\n"
          f"--{bd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: text/plain\r\n\r\n").encode()+content+f"\r\n--{bd}--\r\n".encode()
    req=urllib.request.Request(BASE+path,data=body,method="POST")
    req.add_header("Content-Type",f"multipart/form-data; boundary={bd}"); req.add_header("Authorization","Bearer "+token)
    with urllib.request.urlopen(req) as x: return json.loads(x.read().decode())

def section(n,t): print(f"\n{'='*72}\n  STAGE {n}: {t}\n{'='*72}")
def reg(itoken, name, pw):  # accept invite -> token
    return call("POST","/auth/register-invite",body={"token":itoken,"password":pw,"full_name":name,"phone":"+44 7700 900000"})[0]["token"]

# ── 1. ONBOARD CLIENT & PROPERTY ──────────────────────────────────────────────
section(1, "Onboard the client & list the property")
broker = call("POST","/auth/login",body={"email":"david@inhous.com","password":"inhous2026"})[0]["token"]
print("   Broker David Johnson logged in")
pid = call("POST","/properties",broker,{
    "address_line1":"7 Cumberland Terrace","address_line2":"Regent's Park","city":"London",
    "state_region":"Greater London","postcode":"nw1 4hx","country":"United Kingdom","tenure":"Freehold",
    "guide_price":6500000,"bedrooms":5,"floor_area_sqft":4400,"sale_mode":"managed"
},label="create listing 7 Cumberland Terrace @ GBP 6,500,000")[0]["id"]
vtok = call("POST",f"/properties/{pid}/invite",broker,{"email":"vendor.life@example.com","role":"vendor"},label="invite vendor")[0]["token"]
vendor = reg(vtok,"Eleanor Whitmore","Vendor-Pass2026")
print(f"   Vendor onboarded · property #{pid} status = onboarding")

# ── 2. PHOTOGRAPHY & GO LIVE ──────────────────────────────────────────────────
section(2, "Photography, then take the listing live")
photo = [b for b in call("GET",f"/properties/{pid}/photography",broker)[0] if b["booking_type"]=="photography"][0]
call("PATCH",f"/properties/{pid}/photography/{photo['id']}",broker,{"preferred_date":"2026-06-24","preferred_time":"10:00","photographer_firm":"Lightroom Studios"},label="book photography shoot")
call("PATCH",f"/properties/{pid}",broker,{"status":"active"},label="set listing LIVE (active)")
print(f"   Status now: {call('GET',f'/properties/{pid}',broker)[0]['status'].upper()}")

# ── 3. VIEWING & FEEDBACK ─────────────────────────────────────────────────────
section(3, "Agent books a viewing and leaves feedback")
atok = call("POST",f"/properties/{pid}/invite",broker,{"email":"agent.life@example.com","role":"agent","agency_name":"Knight Frank"},label="invite agent")[0]["token"]
agent = reg(atok,"Marcus Chen","Agent-Pass2026")
vid = call("POST",f"/properties/{pid}/viewings",agent,{"requested_date":"2026-06-22","requested_time":"11:00","buyer_reference":"Sterling Family Office"},label="agent books viewing (instant)")[0]["id"]
call("POST",f"/properties/{pid}/viewings/{vid}/feedback",agent,{"interest_level":"hot","buyer_type":"cash","chain_status":"no_chain","budget_range":"6.3-6.6m","comments":"Exceptional. Ready to move quickly."},label="agent submits feedback (HOT)")

# ── 4. OFFER & ACCEPTANCE ─────────────────────────────────────────────────────
section(4, "Offer submitted, negotiated and accepted")
oid = call("POST",f"/properties/{pid}/offers",agent,{
    "offer_date":"2026-06-22","amount":6300000,"buyer_full_name":"Sterling Family Office","reason_for_purchase":"London base",
    "properties_viewed":"4-6","property_to_sell":"No","purchase_method":"cash","financial_provider":"Sterling FO treasury",
    "proof_of_funds_status":"confirmed","chain_status":"no_chain","proposed_exchange":"Flexible","proposed_completion":"September",
    "buyer_solicitor_firm":"Mishcon de Reya","conditions":"Subject to survey","agent_notes":"Strong cash buyer, no chain."
},label="agent submits offer GBP 6,300,000")[0]["id"]
call("POST",f"/properties/{pid}/offers/{oid}/action",broker,{"action":"counter","counter_amount":6450000,"counter_notes":"Vendor would do 6.45m"},label="broker counters at GBP 6,450,000")
call("POST",f"/properties/{pid}/offers/{oid}/action",broker,{"action":"accept"},label="buyer agrees -> broker ACCEPTS")
print(f"   Status now: {call('GET',f'/properties/{pid}',broker)[0]['status'].upper()}  (post-acceptance workflow fired)")

# ── 5. CONVEYANCING: SOLICITORS, AML/KYC, DOCUMENTS ───────────────────────────
section(5, "Conveyancing — solicitors, AML/KYC and documents")
vstok = call("POST",f"/properties/{pid}/invite",broker,{"email":"vsol.life@example.com","role":"vendor_solicitor","agency_name":"Farrer & Co"},label="invite vendor solicitor")[0]["token"]
vsol = reg(vstok,"Helen Ward","Solic-Pass2026")
bstok = call("POST",f"/properties/{pid}/invite",broker,{"email":"bsol.life@example.com","role":"buyer_solicitor","agency_name":"Mishcon de Reya"},label="invite buyer solicitor")[0]["token"]
bsol = reg(bstok,"James Okafor","Solic-Pass2026")
av = call("POST",f"/properties/{pid}/aml",vsol,{"party_type":"vendor","person_name":"Eleanor Whitmore","nationality":"British"},label="vendor solicitor opens vendor AML")[0]["id"]
call("POST",f"/properties/{pid}/aml/{av}/certify",vsol,label="certify vendor AML")
ab = call("POST",f"/properties/{pid}/aml",bsol,{"party_type":"buyer","person_name":"Sterling FO Nominee","nationality":"British"},label="buyer solicitor opens buyer AML")[0]["id"]
call("POST",f"/properties/{pid}/aml/{ab}/certify",bsol,label="certify buyer AML")
doc = upload(f"/properties/{pid}/documents",broker,"memo_of_sale.txt",b"MEMORANDUM OF SALE - 7 Cumberland Terrace","memo_of_sale")
print(f"   Memo of sale uploaded (doc #{doc['id']})")
share = call("POST",f"/properties/{pid}/documents/{doc['id']}/share",broker,{"party_type":"solicitor","recipient_name":"James Okafor","recipient_email":"bsol.life@example.com"},label="share memo with buyer solicitor (secure link)")[0]

# ── 6. COMPLETION ─────────────────────────────────────────────────────────────
section(6, "Completion — mark the sale complete")
call("PATCH",f"/properties/{pid}",broker,{"status":"sold"},label="mark property SOLD")
print(f"   Status now: {call('GET',f'/properties/{pid}',broker)[0]['status'].upper()}")

# ── 7. THIRD-PARTY INTRODUCTIONS ──────────────────────────────────────────────
section(7, "Introduce trusted third parties to the buyer")
btok = call("POST",f"/properties/{pid}/invite",broker,{"email":"buyer.life@example.com","role":"buyer"},label="invite buyer to the portal")[0]["token"]
buyer = reg(btok,"Sterling FO Nominee","Buyer-Pass2026")
partners = call("GET","/referral-partners",buyer)[0]
by_cat = {}
for p in partners: by_cat.setdefault(p["category"],[]).append(p)
for cat in ("interior_designer","builder","removal"):
    if by_cat.get(cat):
        p = by_cat[cat][0]
        call("POST",f"/properties/{pid}/referrals/acknowledge",buyer,{"category":cat,"partner_id":p["id"]},label=f"buyer requests {cat.replace('_',' ')}: {p['company_name']}")
# broker logs a conversion + reviews fees
designer = by_cat["interior_designer"][0]
call("POST",f"/properties/{pid}/referrals/convert",broker,{"partner_id":designer["id"],"fee_earned":1500,"notes":"Buyer engaged the designer"},label="broker logs a conversion (GBP 1,500 fee)")
summ = call("GET","/referrals/summary",broker)[0]

# ── FINAL ─────────────────────────────────────────────────────────────────────
prop = call("GET",f"/properties/{pid}",broker)[0]
section("8", "JOURNEY COMPLETE")
print(f"   Property : {prop['address_line1']}, {prop['city']} {prop['postcode']}")
print(f"   Status   : {prop['status'].upper()}   Guide: GBP {prop['guide_price']:,}")
print(f"   Price log: " + " · ".join(f"{pl['event_type']} GBP {pl['price']:,}" for pl in prop['price_log']))
aml = call("GET",f"/properties/{pid}/aml",broker)[0]
print(f"   AML      : " + ", ".join(f"{r['party_type']}={r['status']}" for r in aml))
print(f"   Referral fees earned to date: GBP {int(summ.get('total_fees_earned',0)):,}")
notifs = call("GET","/notifications",broker)[0]
print(f"   Broker notifications generated: {len(notifs)}")
print(f"\n   onboard -> photography -> live -> viewing -> feedback -> offer -> accept")
print(f"   -> AML -> documents -> SOLD -> introductions   [all stages completed]")
