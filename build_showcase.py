"""Build one fully-populated 'showcase' property with a login for every role,
so each party's journey can be viewed live. Prints a credential table."""
import json, urllib.request, urllib.error
BASE="http://localhost:5001/api"
PW="Showcase2026"
def api(m,p,t=None,b=None):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(BASE+p,data=d,method=m); r.add_header("Content-Type","application/json")
    if t: r.add_header("Authorization","Bearer "+t)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode() or "{}")
        except: return e.code,{}
def upload(pid,t,fn,dt,ct="image/jpeg"):
    bd="----s"; body=(f"--{bd}\r\nContent-Disposition: form-data; name=\"doc_type\"\r\n\r\n{dt}\r\n--{bd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n").encode()+b"DATA"+f"\r\n--{bd}--\r\n".encode()
    r=urllib.request.Request(BASE+f"/properties/{pid}/documents",data=body,method="POST"); r.add_header("Content-Type",f"multipart/form-data; boundary={bd}"); r.add_header("Authorization","Bearer "+t)
    try: urllib.request.urlopen(r)
    except: pass
broker=api("POST","/auth/login",b={"email":"david@inhous.com","password":"inhous2026"})[1]["token"]
pid=api("POST","/properties",broker,{"address_line1":"Showcase Manor","city":"London","state_region":"Greater London","postcode":"SW3 4RT","country":"United Kingdom","tenure":"Freehold","guide_price":4500000,"bedrooms":5,"floor_area_sqft":3800,"epc_rating":"C"})[1]["id"]
ref=api("GET",f"/properties/{pid}",broker)[1]["reference"]
def add(role,email,name,ag=None):
    it=api("POST",f"/properties/{pid}/invite",broker,{"email":email,"role":role,"agency_name":ag})[1].get("token")
    return api("POST","/auth/register-invite",b={"token":it,"password":PW,"full_name":name,"phone":"+44 20 7000 0000"})[1].get("token")
people=[
 ("vendor","vendor.show@inhous.com","Eleanor Vendor",None),
 ("agent","agent1.show@inhous.com","Marcus Agent","Knight Frank"),
 ("agent","agent2.show@inhous.com","Olivia Agent","Savills"),
 ("buyer","buyer.show@inhous.com","Daniel Buyer",None),
 ("vendor_solicitor","vsol.show@inhous.com","Helen VendorSol","Farrer & Co"),
 ("buyer_solicitor","bsol.show@inhous.com","James BuyerSol","Mishcon de Reya"),
 ("photographer","photo.show@inhous.com","Sam Photographer","Lightroom Studios"),
 ("surveyor","survey.show@inhous.com","Priya Surveyor","Carter Walsh"),
 ("mortgage_broker","mort.show@inhous.com","Tom MortgageBroker","Trinity Financial"),
]
tok={}
for role,em,nm,ag in people: tok[em]=add(role,em,nm,ag)
# Populate
for n in range(3): upload(pid,tok["photo.show@inhous.com"],f"photo{n}.jpg","photo")
upload(pid,tok["photo.show@inhous.com"],"floor.jpg","floorplan")
api("PUT",f"/properties/{pid}/brochure",broker,{"headline":"A handsome Chelsea family house","summary":"Beautifully presented over five floors with a west-facing garden.","highlights":"5 bedrooms\nWest-facing garden\nOff-street parking","hero_doc_id":None})
api("PATCH",f"/properties/{pid}",broker,{"status":"active"})
v1=api("POST",f"/properties/{pid}/viewings",tok["agent1.show@inhous.com"],{"requested_date":"2026-06-22","requested_time":"10:00","buyer_reference":"Cash buyer"})[1]["id"]
api("POST",f"/properties/{pid}/viewings/{v1}/feedback",tok["agent1.show@inhous.com"],{"interest_level":"hot","buyer_type":"cash","comments":"Very keen, ready to proceed."})
api("POST",f"/properties/{pid}/viewings",tok["agent2.show@inhous.com"],{"requested_date":"2026-06-23","requested_time":"14:00","buyer_reference":"Family"})
o1=api("POST",f"/properties/{pid}/offers",tok["agent1.show@inhous.com"],{"offer_date":"2026-06-24","amount":4300000,"buyer_full_name":"Cash Buyer Ltd","purchase_method":"cash","proof_of_funds_status":"confirmed","buyer_solicitor_firm":"Mishcon de Reya"})[1]["id"]
api("POST",f"/properties/{pid}/offers",tok["agent2.show@inhous.com"],{"amount":4200000,"buyer_full_name":"Family Buyer","purchase_method":"mortgage"})
api("POST",f"/properties/{pid}/offers/{o1}/action",broker,{"action":"accept"})
av=api("POST",f"/properties/{pid}/aml",tok["vsol.show@inhous.com"],{"party_type":"vendor","person_name":"Eleanor Vendor","nationality":"British"})[1]["id"]
api("POST",f"/properties/{pid}/aml/{av}/certify",tok["vsol.show@inhous.com"])
ab=api("POST",f"/properties/{pid}/aml",tok["bsol.show@inhous.com"],{"party_type":"buyer","person_name":"Daniel Buyer","nationality":"British"})[1]["id"]
api("POST",f"/properties/{pid}/aml/{ab}/certify",tok["bsol.show@inhous.com"])
memo=api("POST",f"/properties/{pid}/documents",broker)  # noop
# buyer introductions
parts=api("GET","/referral-partners",tok["buyer.show@inhous.com"])[1]; bycat={}
for pp in parts: bycat.setdefault(pp["category"],[]).append(pp)
for cat in ["interior_designer","removal","cleaning"]:
    if bycat.get(cat): api("POST",f"/properties/{pid}/referrals/acknowledge",tok["buyer.show@inhous.com"],{"category":cat,"partner_id":bycat[cat][0]["id"]})
api("POST","/notifications/run-reminders",broker)
print(f"SHOWCASE PROPERTY: {ref} — Showcase Manor, Chelsea (property #{pid})")
print(f"All demo logins use password: {PW}\n")
print(f"  {'Role':<18}{'Login email':<28}")
print("  "+"-"*48)
print(f"  {'INHOUS broker':<18}{'david@inhous.com':<28}(pw inhous2026)")
for role,em,nm,ag in people:
    print(f"  {role:<18}{em:<28}")
