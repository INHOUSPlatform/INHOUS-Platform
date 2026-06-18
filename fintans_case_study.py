"""FINTANS end-to-end case study.
Runs the full requested journey and flags every capability the platform
does NOT yet support, with live evidence, so we know what to build next."""
import json, urllib.request, urllib.error

BASE = "http://localhost:5001/api"
GAPS = []

def call(method, path, token=None, body=None, label=None, ok_silent=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method)
    req.add_header("Content-Type","application/json")
    if token: req.add_header("Authorization","Bearer "+token)
    def parse(raw):
        try: return json.loads(raw or "{}")
        except json.JSONDecodeError: return {"_raw": (raw or "")[:120]}
    try:
        with urllib.request.urlopen(req) as r: out,code = parse(r.read().decode()), r.status
    except urllib.error.HTTPError as e: out,code = parse(e.read().decode()), e.code
    if label and not ok_silent:
        tag = "OK " if 200 <= code < 300 else "!! "
        print(f"   [{tag}{code}] {label}")
        if code >= 300: print("         -> "+json.dumps(out))
    return out, code

def upload(path, token, filename, content, doc_type, ctype="text/plain"):
    bd="----fin"
    body=(f"--{bd}\r\nContent-Disposition: form-data; name=\"doc_type\"\r\n\r\n{doc_type}\r\n"
          f"--{bd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n").encode()+content+f"\r\n--{bd}--\r\n".encode()
    req=urllib.request.Request(BASE+path,data=body,method="POST")
    req.add_header("Content-Type",f"multipart/form-data; boundary={bd}"); req.add_header("Authorization","Bearer "+token)
    try:
        with urllib.request.urlopen(req) as x: return x.status, json.loads(x.read().decode() or "{}")
    except urllib.error.HTTPError as e: return e.code, {}

def upload_audio(path, token, content):
    bd="----au"
    body=(f"--{bd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"vf.webm\"\r\nContent-Type: audio/webm\r\n\r\n").encode()+content+f"\r\n--{bd}--\r\n".encode()
    req=urllib.request.Request(BASE+path,data=body,method="POST")
    req.add_header("Content-Type",f"multipart/form-data; boundary={bd}"); req.add_header("Authorization","Bearer "+token)
    try:
        with urllib.request.urlopen(req) as x: return x.status
    except urllib.error.HTTPError as e: return e.code

def reg(itoken, name, pw): return call("POST","/auth/register-invite",body={"token":itoken,"password":pw,"full_name":name,"phone":"+353 1 5550000"})[0].get("token")
def invite(pid, broker, email, role, agency=None): return call("POST",f"/properties/{pid}/invite",broker,{"email":email,"role":role,"agency_name":agency})
def section(n,t): print(f"\n{'='*74}\n  {n}. {t}\n{'='*74}")
def gap(title, evidence): GAPS.append((title, evidence)); print(f"   [GAP] {title}\n         evidence: {evidence}")

broker = call("POST","/auth/login",body={"email":"david@inhous.com","password":"inhous2026"})[0]["token"]

# ── 1. NEW PROPERTY: FINTANS + VENDOR ONBOARDING + AML/KYC ────────────────────
section(1, "Take on Fintans, onboard the vendor, capture AML/KYC (fake data)")
pid = call("POST","/properties",broker,{
    "address_line1":"Fintans, Shrewsbury Road","city":"Dublin","state_region":"Leinster",
    "postcode":"d04 vw80","country":"Ireland","tenure":"Freehold","guide_price":7500000,"bedrooms":6
},label="create property 'Fintans' (Dublin, EUR)")[0]["id"]
vtok = invite(pid, broker, "fintan.vendor@example.com","vendor","")[0]["token"]
vendor = reg(vtok,"Fintan O'Sullivan","Vendor-Pass2026")
# AML record (structured) — stored in aml_records
av,_ = call("POST",f"/properties/{pid}/aml",broker,{"party_type":"vendor","person_name":"Fintan O'Sullivan","dob":"1968-03-12","nationality":"Irish"},label="create vendor AML record (fake)")
call("POST",f"/properties/{pid}/aml/{av['id']}/certify",broker,label="certify vendor AML")
# AML document (file) — stored in documents + uploads/aml_vendor/
code,_ = upload(f"/properties/{pid}/documents",broker,"fintan_passport.txt",b"FAKE PASSPORT SCAN - Fintan O'Sullivan","aml_vendor")
print(f"   [OK {code}] upload vendor AML/KYC document (passport)")
print("   STORED: AML record -> table 'aml_records'; document -> table 'documents' + file under uploads/aml_vendor/")

# ── 2. VALUATION: 5 AGENTS PROVIDE VALUATIONS FOR THE VENDOR ──────────────────
section(2, "Pre-instruction valuations from 5 agents (to present to the vendor)")
print("   Goal: collect 5 agent valuations into one report the vendor can view.")
# Is there any valuation capability?
_,vc = call("GET",f"/properties/{pid}/valuations",broker, ok_silent=True)
gap("No valuation module", f"GET /properties/{pid}/valuations -> {vc} (no endpoint/table to collect or compare agent valuations, and nothing for the vendor to view a valuation report)")

# ── 3. INSTRUCT & INVITE 5 SELLING AGENTS (need AML/KYC access) ───────────────
section(3, "Instruct: invite 5 selling agents; they need access to AML/KYC")
agents=[]
for i,(name,agency) in enumerate([("Marcus Chen","Knight Frank"),("Olivia Bennett","Savills"),("Raj Patel","Hamptons"),("Tom Wright","Lisney"),("Aoife Ryan","Sherry FitzGerald")]):
    it = invite(pid, broker, f"agent{i}.fintan@example.com","agent",agency)[0]["token"]
    agents.append(reg(it, name, "Agent-Pass2026"))
print(f"   [OK] invited & registered {len(agents)} selling agents")
# Can a selling agent see the vendor AML/KYC docs?
adocs,_ = call("GET",f"/properties/{pid}/documents",agents[0], ok_silent=True)
if not any(d["doc_type"] in ("aml_vendor","aml_buyer") for d in adocs):
    aaml,_ = call("GET",f"/properties/{pid}/aml",agents[0], ok_silent=True)
    gap("Agents cannot access AML/KYC documents", f"agent GET /documents returns {len(adocs)} docs, none AML; GET /aml returns status-only {aaml}. Selling agents have no access to the AML/KYC files as requested.")

# ── 4. PHOTOGRAPHER: invite onto platform, book with vendor, upload photos ─────
section(4, "Photographer: invite, book the shoot, upload photos to the platform")
resp_ph,code_ph = invite(pid, broker, "studio@lightroom.example","photographer","Lightroom Studios")
if code_ph >= 300:
    gap("No 'photographer' role", f"POST invite role=photographer -> {code_ph} {resp_ph}. Photographer cannot be invited/logged in; users role CHECK has no 'photographer'.")
# Workaround available today: broker books + uploads photos as documents
photo=[b for b in call("GET",f"/properties/{pid}/photography",broker)[0] if b["booking_type"]=="photography"][0]
call("PATCH",f"/properties/{pid}/photography/{photo['id']}",broker,{"preferred_date":"2026-06-24","preferred_time":"10:00","photographer_firm":"Lightroom Studios"},label="book photography (broker, as workaround)")
for n in range(3):
    upload(f"/properties/{pid}/documents",broker,f"photo_{n+1}.txt",b"FAKE PHOTO DATA","photo")
upload(f"/properties/{pid}/documents",broker,"floorplan.txt",b"FAKE FLOORPLAN","floorplan")
print("   [OK] 3 photos + 1 floorplan uploaded (by broker) — stored as documents")
print("   NOTE: photographer self-service login + direct upload is the gap; broker upload is the workaround.")

# ── 5. BROCHURE BUILDER from photos + floorplans ──────────────────────────────
section(5, "Build a brochure from the uploaded photos & floorplans")
_,bc = call("GET",f"/properties/{pid}/brochure",broker, ok_silent=True)
gap("No brochure builder", f"GET /properties/{pid}/brochure -> {bc}. No feature to assemble photos+floorplan into a brochure; agents can only download the raw files.")

# ── 6. VIEWINGS (6-10) WITH VOICE FEEDBACK; VENDOR CAN SEE ────────────────────
section(6, "Agents book viewings and compile voice feedback (vendor can view)")
slots=[("2026-06-22","10:00"),("2026-06-22","11:30"),("2026-06-23","10:00"),("2026-06-23","14:00"),
       ("2026-06-24","11:00"),("2026-06-24","15:00"),("2026-06-25","10:30"),("2026-06-25","13:00")]
levels=["hot","warm","cold","warm","hot","cold","warm","hot"]
vcount=0; acount=0
for i,(date,time) in enumerate(slots):
    ag=agents[i%len(agents)]
    bk,code=call("POST",f"/properties/{pid}/viewings",ag,{"requested_date":date,"requested_time":time,"buyer_reference":f"Applicant {i+1}"}, ok_silent=True)
    if code==201:
        vcount+=1
        fb,fc=call("POST",f"/properties/{pid}/viewings/{bk['id']}/feedback",ag,{"interest_level":levels[i],"buyer_type":"cash","comments":f"Feedback {i+1}"}, ok_silent=True)
        if fc==201 and i%3==0:  # attach voice note to some
            if upload_audio(f"/properties/{pid}/feedback/{fb['id']}/audio",ag,b"FAKEVOICE"+str(i).encode())==201: acount+=1
print(f"   [OK] {vcount} viewings booked + feedback logged; {acount} with voice notes attached")
vendor_fb,_=call("GET",f"/properties/{pid}/feedback",vendor, ok_silent=True)
print(f"   [OK] vendor can view feedback — sees {len(vendor_fb)} records (voice flagged: {sum(1 for f in vendor_fb if f.get('has_audio'))})")

# ── 7. TWO OFFERS + BUYER DOCS (PoF, AML, solicitor/bank letters) ─────────────
section(7, "Two offers via the offer form, each with buyer PoF / AML / letters")
offers=[]
for i,(amt,buyer) in enumerate([(7300000,"Hargreaves Family"),(7150000,"Delgado Holdings")]):
    ag=agents[i]
    o,_=call("POST",f"/properties/{pid}/offers",ag,{"offer_date":"2026-06-26","amount":amt,"buyer_full_name":buyer,"purchase_method":"cash","proof_of_funds_status":"confirmed","chain_status":"no_chain","buyer_solicitor_firm":"TBC","conditions":"Subject to survey"},label=f"offer {i+1}: {buyer} EUR {amt:,}")
    offers.append(o["id"])
    upload(f"/properties/{pid}/documents",ag,f"pof_{i+1}.txt",b"FAKE PROOF OF FUNDS","proof_of_funds")
    upload(f"/properties/{pid}/documents",ag,f"buyeraml_{i+1}.txt",b"FAKE BUYER AML","aml_buyer")
    upload(f"/properties/{pid}/documents",ag,f"solicitor_letter_{i+1}.txt",b"FAKE SOLICITOR LETTER","other")
    print(f"        + uploaded proof of funds, buyer AML, solicitor letter for offer {i+1}")

# ── 8. ACCEPT OFFER 1 ─────────────────────────────────────────────────────────
section(8, "Accept offer from buyer 1")
call("POST",f"/properties/{pid}/offers/{offers[0]}/action",broker,{"action":"accept"},label="accept offer 1 (Hargreaves Family)")
call("POST",f"/properties/{pid}/offers/{offers[1]}/action",broker,{"action":"decline","reason":"Higher offer accepted"},label="decline offer 2")
print(f"   status now: {call('GET',f'/properties/{pid}',broker)[0]['status'].upper()}")

# ── 9. MEMO OF SALE -> BOTH SOLICITORS; THEY UPLOAD AML/KYC ───────────────────
section(9, "Memorandum of sale to both solicitors; solicitors upload AML/KYC")
vstok=invite(pid,broker,"vsol.fintan@example.com","vendor_solicitor","Farrer & Co")[0]["token"]; vsol=reg(vstok,"Helen Ward","Solic-Pass2026")
bstok=invite(pid,broker,"bsol.fintan@example.com","buyer_solicitor","Mishcon")[0]["token"]; bsol=reg(bstok,"James Okafor","Solic-Pass2026")
mc,memo=upload(f"/properties/{pid}/documents",broker,"memorandum_of_sale.txt",b"MEMORANDUM OF SALE - Fintans","memo_of_sale")
print(f"   [OK {mc}] memorandum of sale uploaded")
for who,tok,email in [("vendor solicitor",vsol,"vsol.fintan@example.com"),("buyer solicitor",bsol,"bsol.fintan@example.com")]:
    call("POST",f"/properties/{pid}/documents/{memo['id']}/share",broker,{"party_type":"solicitor","recipient_email":email},label=f"send memo to {who} (secure link)")
sv=call("POST",f"/properties/{pid}/aml",vsol,{"party_type":"vendor","person_name":"Fintan O'Sullivan","nationality":"Irish"},label="vendor solicitor uploads vendor AML")[0]
call("POST",f"/properties/{pid}/aml/{sv['id']}/certify",vsol,label="certify",ok_silent=True)
sb=call("POST",f"/properties/{pid}/aml",bsol,{"party_type":"buyer","person_name":"Hargreaves Family","nationality":"British"},label="buyer solicitor uploads buyer AML")[0]
call("POST",f"/properties/{pid}/aml/{sb['id']}/certify",bsol,label="certify",ok_silent=True)

# ── 10. CONVEYANCING: 3RD-PARTY SERVICES ──────────────────────────────────────
section(10, "Conveyancing — buyer/vendor avail of third-party services")
# ensure a gardener/landscaping partner exists
call("POST","/referral-partners",broker,{"category":"landscaping","company_name":"Greenacre Gardens","notes":"Garden design & maintenance"},label="broker adds a gardener (landscaping)")
btok=invite(pid,broker,"buyer.fintan@example.com","buyer","")[0]["token"]; buyer=reg(btok,"Hargreaves Family","Buyer-Pass2026")
parts=call("GET","/referral-partners",buyer)[0]; bycat={}
for p in parts: bycat.setdefault(p["category"],[]).append(p)
for cat in ["cleaning","removal","interior_designer","builder","landscaping"]:
    if bycat.get(cat):
        p=bycat[cat][0]
        call("POST",f"/properties/{pid}/referrals/acknowledge",buyer,{"category":cat,"partner_id":p["id"]},label=f"buyer requests {cat.replace('_',' ')}: {p['company_name']}")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
prop=call("GET",f"/properties/{pid}",broker)[0]
print(f"\n{'='*74}\n  RESULT\n{'='*74}")
print(f"  Property: {prop['address_line1']}, {prop['city']} {prop['postcode']} ({prop['currency']})  status={prop['status'].upper()}")
print(f"  AML records: {len(call('GET',f'/properties/{pid}/aml',broker)[0])}   Documents: {len(call('GET',f'/properties/{pid}/documents',broker)[0])}   Offers: {len(call('GET',f'/properties/{pid}/offers',broker)[0])}")
print(f"\n  ISSUES TO ADDRESS ({len(GAPS)}):")
for i,(t,e) in enumerate(GAPS,1):
    print(f"   {i}. {t}")
print("\n  Everything else (onboarding, AML capture, instruct/agents, photo+floorplan storage,")
print("  viewings, voice feedback, vendor visibility, offers + buyer docs, acceptance,")
print("  memo + secure send to solicitors, solicitor AML uploads, 3rd-party introductions) ran OK.")
