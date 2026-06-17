"""End-to-end demo: a full INHOUS sale journey driven through the live REST API."""
import json, urllib.request, urllib.error

BASE = "http://localhost:5001/api"

def call(method, path, token=None, body=None, label=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    def parse(raw):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"_raw": (raw or "")[:200]}
    try:
        with urllib.request.urlopen(req) as r:
            out = parse(r.read().decode())
            code = r.status
    except urllib.error.HTTPError as e:
        out = parse(e.read().decode())
        code = e.code
    status = "OK " if 200 <= code < 300 else "ERR"
    if label:
        print(f"   [{status} {code}] {label}")
        if code >= 300:
            print("        -> " + json.dumps(out))
    return out, code

def section(n, title):
    print(f"\n{'='*70}\n  STEP {n}: {title}\n{'='*70}")

def money(n):
    return f"£{n:,}"

# ── 1. BROKER LOGS IN ─────────────────────────────────────────────────────────
section(1, "Broker logs in")
res, _ = call("POST", "/auth/login", body={"email": "david@inhous.com", "password": "inhous2026"}, label="login david@inhous.com")
broker = res["token"]
print(f"   Logged in as {res['user']['full_name']} ({res['user']['role']})")

# ── 2. BROKER CREATES A NEW LISTING ───────────────────────────────────────────
section(2, "Broker creates a new listing")
res, _ = call("POST", "/properties", broker, {
    "address_line1": "14 Eaton Square", "address_line2": "Belgravia",
    "city": "London", "postcode": "SW1W 9DA", "tenure": "Freehold",
    "guide_price": 8500000, "bedrooms": 5, "floor_area_sqft": 4120,
    "year_built": 1827, "epc_rating": "D", "sale_mode": "managed",
    "notes": "Grade II listed lateral apartment overlooking the gardens."
}, label="create 14 Eaton Square")
pid = res["id"]
print(f"   Property #{pid} created — guide {money(8500000)}")

# ── 3. BROKER INVITES THE PARTIES ─────────────────────────────────────────────
section(3, "Broker invites vendor, agent and both solicitors")
parties = [
    ("vendor",           "sophia.laurent@example.com",      "Sophia Laurent",  None),
    ("agent",            "marcus.chen@knightfrank.example", "Marcus Chen",     "Knight Frank Belgravia"),
    ("vendor_solicitor", "helen.ward@farrer.example",       "Helen Ward",      "Farrer & Co"),
    ("buyer_solicitor",  "james.okafor@mishcon.example",    "James Okafor",    "Mishcon de Reya"),
]
invites = {}
for role, email, name, agency in parties:
    res, _ = call("POST", f"/properties/{pid}/invite", broker,
                  {"email": email, "role": role, "agency_name": agency},
                  label=f"invite {role}: {email}")
    invites[role] = (res["token"], email, name)

# ── 4. EACH PARTY ACCEPTS THEIR INVITE & CREATES AN ACCOUNT ───────────────────
section(4, "Each party accepts their invite and sets a password")
tokens = {}
for role, (itoken, email, name) in invites.items():
    res, _ = call("GET", f"/invite/{itoken}", label=f"open invite ({role})")
    res, _ = call("POST", "/auth/register-invite",
                  body={"token": itoken, "password": f"{role}-Pass2026", "full_name": name, "phone": "+44 7700 900000"},
                  label=f"register {name}")
    tokens[role] = res["token"]
agent, vendor = tokens["agent"], tokens["vendor"]
vsolic, bsolic = tokens["vendor_solicitor"], tokens["buyer_solicitor"]

# ── 5. PHOTOGRAPHY BOOKING ────────────────────────────────────────────────────
section(5, "Broker schedules the photography shoot")
res, _ = call("GET", f"/properties/{pid}/photography", broker, label="list photography bookings")
photo_id = [b for b in res if b["booking_type"] == "photography"][0]["id"]
call("PATCH", f"/properties/{pid}/photography/{photo_id}", broker, {
    "preferred_date": "2026-06-19", "preferred_time": "10:00",
    "photographer_firm": "Lightroom Studios", "broker_brief": "Twilight exterior + 18 interiors"
}, label="set shoot date 2026-06-19")

# ── 6. VIEWING AVAILABILITY ───────────────────────────────────────────────────
section(6, "Broker configures viewing availability")
call("PATCH", f"/properties/{pid}/availability", broker, {
    "viewing_duration_mins": 45, "buffer_mins": 30, "max_per_day": 6,
    "date_override": {"date": "2026-06-22", "mode": "confirm"}
}, label="Mon 22 Jun set to 'confirm' mode")

# ── 7. AGENT CHECKS SLOTS & BOOKS A VIEWING ───────────────────────────────────
section(7, "Agent checks available slots and requests a viewing")
res, _ = call("GET", f"/properties/{pid}/available-slots?date=2026-06-22", agent, label="GET slots for 2026-06-22")
free = [s["time"] for s in res.get("slots", []) if s["available"]]
print(f"   Available start times: {', '.join(free[:6])}{' ...' if len(free)>6 else ''}")
res, _ = call("POST", f"/properties/{pid}/viewings", agent, {
    "requested_date": "2026-06-22", "requested_time": "11:00",
    "buyer_reference": "Cash buyer, relocating from Geneva", "buyer_notes": "Keen, second viewing likely"
}, label="agent requests 11:00 viewing")
vid = res["id"]
print(f"   Viewing #{vid} -> status '{res['status']}' (awaiting vendor confirmation)")

# ── 8. VENDOR CONFIRMS THE VIEWING ────────────────────────────────────────────
section(8, "Vendor confirms the viewing")
call("POST", f"/properties/{pid}/viewings/{vid}/confirm", vendor, {"action": "confirm"}, label="vendor confirms")

# ── 9. AGENT SUBMITS VIEWING FEEDBACK ─────────────────────────────────────────
section(9, "Agent submits feedback after the viewing")
call("POST", f"/properties/{pid}/viewings/{vid}/feedback", agent, {
    "interest_level": "hot", "buyer_type": "cash", "chain_status": "no_chain",
    "budget_range": "8.0-8.5m", "follow_up_likelihood": "very_likely",
    "comments": "Loved the volume and light. Asked about service charge and parking."
}, label="submit feedback (high interest)")

# ── 10. AGENT SUBMITS AN OFFER ────────────────────────────────────────────────
section(10, "Agent submits an offer on behalf of the buyer")
res, _ = call("POST", f"/properties/{pid}/offers", agent, {
    "amount": 8250000, "buyer_full_name": "Dr Anneke Visser", "buyer_type": "cash",
    "buyer_email": "a.visser@example.com", "buyer_phone": "+41 79 555 0102",
    "buyer_nationality": "Dutch", "purchase_method": "cash", "cash_percent": 100,
    "financial_provider": "UBS Switzerland AG", "proof_of_funds_status": "confirmed",
    "chain_status": "no_chain", "proposed_exchange": "2026-07-15", "proposed_completion": "2026-08-12",
    "buyer_solicitor_firm": "Mishcon de Reya", "buyer_solicitor_name": "James Okafor",
    "buyer_solicitor_email": "james.okafor@mishcon.example",
    "conditions": "Subject to survey", "valid_until": "2026-06-30"
}, label="agent submits offer " + money(8250000))
oid = res["id"]

# ── 11. BROKER NEGOTIATES, THEN ACCEPTS ───────────────────────────────────────
section(11, "Broker counters, then accepts")
res, _ = call("GET", f"/properties/{pid}/offers", broker, label="broker reviews offers")
print(f"   Offer on table: {money(res[0]['amount'])} from {res[0]['buyer_full_name']} ({res[0]['agency_name']})")
call("POST", f"/properties/{pid}/offers/{oid}/action", broker,
     {"action": "counter", "counter_amount": 8400000, "counter_notes": "Vendor would do 8.4m for an early exchange"},
     label="broker counters at " + money(8400000))
call("POST", f"/properties/{pid}/offers/{oid}/action", broker,
     {"action": "accept"}, label="buyer agrees -> broker ACCEPTS (fires post-acceptance workflow)")

# ── 12. AML / KYC ─────────────────────────────────────────────────────────────
section(12, "Solicitors run AML / KYC checks")
res, _ = call("POST", f"/properties/{pid}/aml", vsolic,
              {"party_type": "vendor", "person_name": "Sophia Laurent", "nationality": "French"},
              label="vendor solicitor opens vendor AML")
aml_v = res["id"]
call("POST", f"/properties/{pid}/aml/{aml_v}/certify", vsolic, label="certify vendor AML")
res, _ = call("POST", f"/properties/{pid}/aml", bsolic,
              {"party_type": "buyer", "person_name": "Dr Anneke Visser", "nationality": "Dutch"},
              label="buyer solicitor opens buyer AML")
aml_b = res["id"]
call("POST", f"/properties/{pid}/aml/{aml_b}/certify", bsolic, label="certify buyer AML")

# ── 13. REFERRAL PARTNER (removals) ───────────────────────────────────────────
section(13, "Referral partner — removals quote with fee disclosure")
res, _ = call("POST", "/referral-partners", broker, {
    "category": "removal", "company_name": "Whitebox Removals",
    "referral_fee_type": "fixed", "referral_fee_amount": 350,
    "disclosure_text": "INHOUS receives a £350 referral fee from Whitebox Removals."
}, label="broker adds Whitebox Removals")
partner_id = res["id"]
call("POST", f"/properties/{pid}/referrals/acknowledge", vendor,
     {"category": "removal", "partner_id": partner_id}, label="vendor acknowledges fee disclosure")
call("POST", f"/properties/{pid}/referrals/convert", broker,
     {"partner_id": partner_id, "notes": "Vendor booked the move"}, label="broker logs conversion")

# ── 14. FINAL STATE ───────────────────────────────────────────────────────────
section(14, "Final state of the deal")
prop, _ = call("GET", f"/properties/{pid}", broker, label="fetch property")
print(f"   {prop['address_line1']}, {prop['city']} {prop['postcode']}")
print(f"   Status: {prop['status'].upper()}   Guide: {money(prop['guide_price'])}")
print("   Price log:")
for p in prop["price_log"]:
    print(f"     - {p['event_type']:10s} {money(p['price'])}")

offers, _ = call("GET", f"/properties/{pid}/offers", broker, label="fetch offers")
o = offers[0]
print(f"   Accepted offer: {money(o['amount'])} ({o['status']}) from {o['buyer_full_name']}")

aml, _ = call("GET", f"/properties/{pid}/aml", broker, label="fetch AML")
print("   AML:", ", ".join(f"{r['party_type']}={r['status']}" for r in aml))

summ, _ = call("GET", "/referrals/summary", broker, label="referral summary")
print(f"   Referral fees earned: {money(int(summ['total_fees_earned']))}")

notifs, _ = call("GET", "/notifications", broker, label="broker notifications")
print(f"   Broker has {len(notifs)} notifications. Most recent:")
for n in notifs[:6]:
    print(f"     - {n['title']}")

print("\n" + "="*70 + "\n  JOURNEY COMPLETE — listing -> viewing -> offer -> accepted -> AML -> referral\n" + "="*70)
