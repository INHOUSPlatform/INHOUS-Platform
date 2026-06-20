"""Seed a rich, deterministic demo dataset: Fintans + international listings,
each with a local agent on an international phone number. Leaves the DB populated."""
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
def reg(it,name,pw,phone): return api("POST","/auth/register-invite",b={"token":it,"password":pw,"full_name":name,"phone":phone})[1].get("token")

broker=api("POST","/auth/login",b={"email":"david@inhous.com","password":"inhous2026"})[1]["token"]
SYM={"GBP":"GBP","EUR":"EUR","USD":"USD","CHF":"CHF","AED":"AED"}

# ── FINTANS (populated) ───────────────────────────────────────────────────────
fin=api("POST","/properties",broker,{"address_line1":"Fintans, Shrewsbury Road","city":"Dublin","state_region":"Leinster","postcode":"d04 vw80","country":"Ireland","tenure":"Freehold","guide_price":7500000,"bedrooms":6,"floor_area_sqft":7400,"epc_rating":"C"})[1]["id"]
vt=api("POST",f"/properties/{fin}/invite",broker,{"email":"fintan.vendor@example.com","role":"vendor"})[1]["token"]
reg(vt,"Fintan O'Sullivan","Vendor-Pass2026","+353 1 555 0100")
av=api("POST",f"/properties/{fin}/aml",broker,{"party_type":"vendor","person_name":"Fintan O'Sullivan","dob":"1968-03-12","nationality":"Irish"})[1]["id"]
api("POST",f"/properties/{fin}/aml/{av}/certify",broker)
for nm,ag,ph,val in [("Aoife Ryan","Sherry FitzGerald","+353 1 555 0123",7500000),("Marcus Chen","Knight Frank","+44 20 7861 1080",7650000)]:
    it=api("POST",f"/properties/{fin}/invite",broker,{"email":nm.split()[0].lower()+".fin@example.com","role":"agent","agency_name":ag})[1]["token"]
    at=reg(it,nm,"Agent-Pass2026",ph)
    api("POST",f"/properties/{fin}/valuations",at,{"valuation_amount":val,"suggested_asking_price":val+200000,"recommended_fee":"1.25% + VAT","estimated_timeframe":"8-12 weeks","comments":"Strong D4 demand"})
print(f"Fintans created (property {fin}) with vendor + 2 agents + valuations")

# ── INTERNATIONAL LISTINGS ────────────────────────────────────────────────────
COUNTRIES=[
 ("Spain","Ibiza","Can Furnet villa, Carrer de Sa Talaia","07819",3200000,"EUR","Lucas Fox Ibiza","Marc Tur","+34 971 391 234"),
 ("Ireland","Dublin","18 Raglan Road, Ballsbridge","d04 r1f2",4500000,"EUR","Sherry FitzGerald","Niamh Byrne","+353 1 555 0188"),
 ("United Arab Emirates","Dubai","Villa 7, Emirates Hills","00000",6500000,"AED","Knight Frank Dubai","Omar Haddad","+971 50 123 4567"),
 ("France","Paris","12 Avenue Montaigne","75008",8900000,"EUR","Barnes Paris","Camille Laurent","+33 1 42 56 78 90"),
 ("Italy","Milan","Via Montenapoleone 8","20121",5400000,"EUR","Engel & Voelkers Milano","Giulia Romano","+39 02 1234 5678"),
 ("Greece","Athens","Irodou Attikou 14, Kolonaki","106 74",3100000,"EUR","Greece Sotheby's","Nikos Papas","+30 21 0123 4567"),
 ("United States","New York","740 Park Avenue, Apt 12A","10021",12500000,"USD","Douglas Elliman","Sarah Klein","+1 212 555 0142"),
]
print(f"\n  {'Country':<22}{'Postcode (typed -> stored)':<34}{'Cur':<5}{'Agent phone'}")
print("  "+"-"*86)
ok=0
for country,city,addr,pc,price,expcur,agency,agent,phone in COUNTRIES:
    pid=api("POST","/properties",broker,{"address_line1":addr,"city":city,"postcode":pc.lower(),"country":country,"guide_price":price,"tenure":"Freehold","bedrooms":5})[1]["id"]
    prop=api("GET",f"/properties/{pid}",broker)[1]
    it=api("POST",f"/properties/{pid}/invite",broker,{"email":agent.split()[0].lower()+"."+country[:2].lower()+"@example.com","role":"agent","agency_name":agency})[1]["token"]
    reg(it,agent,"Agent-Pass2026",phone)
    curok = "OK" if prop["currency"]==expcur else f"!!{prop['currency']}"
    pcok = "OK" if prop["postcode"]==pc.upper() else f"!!{prop['postcode']}"
    if curok=="OK" and pcok=="OK": ok+=1
    print(f"  {country:<22}{pc.lower()+' -> '+prop['postcode']:<34}{prop['currency']:<5}{phone}   [cur {curok}, pc {pcok}]")

props=api("GET","/properties",broker)[1]
print(f"\n  Total properties now visible: {len(props)}")
print(f"  Country listings correct: {ok}/{len(COUNTRIES)}")
print("  Refresh the app — Fintans + all international listings are now present.")
