"""Offer case studies: multiple offers, cash vs mortgage, counter-with-conditions,
decline, improved re-offer, accept, role isolation and alert levels."""
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
def upload(pid,t,fn,dt):
    bd="----o"; body=(f"--{bd}\r\nContent-Disposition: form-data; name=\"doc_type\"\r\n\r\n{dt}\r\n--{bd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fn}\"\r\nContent-Type: text/plain\r\n\r\n").encode()+b"DATA"+f"\r\n--{bd}--\r\n".encode()
    r=urllib.request.Request(BASE+f"/properties/{pid}/documents",data=body,method="POST"); r.add_header("Content-Type",f"multipart/form-data; boundary={bd}"); r.add_header("Authorization","Bearer "+t)
    try: urllib.request.urlopen(r); return True
    except: return False
def reg(it,name): return api("POST","/auth/register-invite",b={"token":it,"password":"Agent-Pass2026","full_name":name})[1].get("token")
def notif(t): return api("GET","/notifications",t)[1]
def lvl(t,sub):
    for n in notif(t):
        if sub.lower() in n.get("title","").lower(): return n.get("level")
    return None
P=F=0
def ck(c,l):
    global P,F; print(f"  [{'PASS' if c else 'FAIL'}] {l}"); P+=c; F+=(not c)
def sect(t): print(f"\n=== {t} ===")

broker=api("POST","/auth/login",b={"email":"david@inhous.com","password":"inhous2026"})[1]["token"]
pid=api("POST","/properties",broker,{"address_line1":"Offer Scenarios House","city":"London","postcode":"SW1 9OF","country":"United Kingdom","guide_price":5000000})[1]["id"]
api("PATCH",f"/properties/{pid}",broker,{"status":"active"})
vtok=api("POST",f"/properties/{pid}/invite",broker,{"email":"v.ocs@demo.example","role":"vendor"})[1]["token"]; vendor=reg(vtok,"Vendor OCS")
a1=reg(api("POST",f"/properties/{pid}/invite",broker,{"email":"a1.ocs@demo.example","role":"agent","agency_name":"Knight Frank"})[1]["token"],"Agent One")
a2=reg(api("POST",f"/properties/{pid}/invite",broker,{"email":"a2.ocs@demo.example","role":"agent","agency_name":"Savills"})[1]["token"],"Agent Two")
a3=reg(api("POST",f"/properties/{pid}/invite",broker,{"email":"a3.ocs@demo.example","role":"agent","agency_name":"Foxtons"})[1]["token"],"Agent Three")

sect("Scenario 1 — rich cash offer + buyer documents")
o1=api("POST",f"/properties/{pid}/offers",a1,{"offer_date":"2026-06-24","amount":4800000,"buyer_full_name":"Dr Anneke Visser","reason_for_purchase":"Family home","properties_viewed":"5-7","property_to_sell":"No","purchase_method":"cash","financial_provider":"UBS — cash, not conditional on finance","proof_of_funds_status":"confirmed","chain_status":"no_chain","proposed_exchange":"Flexible","proposed_completion":"October","buyer_solicitor_firm":"Mishcon de Reya","conditions":"Subject to survey","agent_notes":"Very strong cash buyer"})
ck(o1[0]==201,"agent 1 submits a detailed cash offer EUR 4,800,000")
o1id=o1[1]["id"]
ck(upload(pid,a1,"pof1.txt","proof_of_funds") and upload(pid,a1,"aml1.txt","aml_buyer"),"agent 1 uploads proof of funds + buyer AML")

sect("Scenario 2 — mortgage offer from a second agent")
o2=api("POST",f"/properties/{pid}/offers",a2,{"amount":4650000,"buyer_full_name":"Hargreaves Family","purchase_method":"mortgage","cash_percent":25,"mortgage_percent":75,"financial_provider":"Coutts","chain_status":"property_to_sell_uo"})
ck(o2[0]==201,"agent 2 submits a mortgage offer EUR 4,650,000")
o2id=o2[1]["id"]

sect("Scenario 3 — low offer is declined")
o3=api("POST",f"/properties/{pid}/offers",a3,{"amount":4200000,"buyer_full_name":"Lowball Ltd","purchase_method":"cash"})[1]["id"]
ck(api("POST",f"/properties/{pid}/offers/{o3}/action",broker,{"action":"decline","reason":"Below the vendor's expectations"})[0]==200,"broker declines the low offer")
ck(lvl(a3,"offer declined")=="red","agent 3 gets a RED 'offer declined' alert")

sect("Scenario 4 — broker counters with a figure + conditions")
ck(api("POST",f"/properties/{pid}/offers/{o1id}/action",broker,{"action":"counter","counter_amount":4950000,"counter_notes":"Vendor will accept 4.95m for an early exchange and inclusion of the AV equipment."})[0]==200,"broker counters offer 1 at EUR 4,950,000 with conditions")
c1=[x for x in api("GET",f"/properties/{pid}/offers",broker)[1] if x["id"]==o1id][0]
ck(c1["status"]=="countered" and c1.get("counter_amount")==4950000 and "early exchange" in (c1.get("counter_notes") or ""),"counter amount + conditions stored")
ck(lvl(a1,"offer countered")=="amber","agent 1 gets an AMBER 'offer countered' alert")

sect("Scenario 5 — buyer accepts the counter via an improved offer, broker accepts")
o4=api("POST",f"/properties/{pid}/offers",a1,{"amount":4950000,"buyer_full_name":"Dr Anneke Visser","purchase_method":"cash","proof_of_funds_status":"confirmed","conditions":"Agreed at counter figure incl. AV equipment","agent_notes":"Accepting the counter"})[1]["id"]
ck(api("POST",f"/properties/{pid}/offers/{o4}/action",broker,{"action":"accept"})[0]==200,"broker accepts the improved EUR 4,950,000 offer")
ck(api("GET",f"/properties/{pid}",broker)[1]["status"]=="under_offer","property is now UNDER OFFER")
ck(lvl(a1,"offer accepted")=="green","agent 1 gets a GREEN 'offer accepted' alert")

sect("Scenario 6 — visibility & isolation")
mine2=api("GET",f"/properties/{pid}/offers",a2)[1]
ck(len(mine2)==1 and mine2[0]["id"]==o2id,"agent 2 sees ONLY their own offer")
allbro=api("GET",f"/properties/{pid}/offers",broker)[1]
ck(len(allbro)>=4,f"broker sees all offers ({len(allbro)})")
ven=api("GET",f"/properties/{pid}/offers",vendor)[1]
ck(len(ven)>=4 and all('negotiator_name' not in o for o in ven),"vendor sees all offers but NOT negotiator contact")
ck(any(n['title'].startswith('New offer') for n in notif(vendor)),"vendor was alerted to new offers")
ck(any(n['title'].startswith('New offer') for n in notif(broker)),"broker was alerted to new offers")

print(f"\nRESULT: {P} passed, {F} failed")
