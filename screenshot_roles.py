"""Log in as each role and screenshot what they see (dashboard + property view),
so each party's journey can be visualised. Saves PNGs to ./screenshots/."""
import json, urllib.request, time, os
from selenium import webdriver
from selenium.webdriver.edge.options import Options
BASE="http://localhost:5001"
def token(email,pw):
    r=urllib.request.Request(BASE+"/api/auth/login",data=json.dumps({"email":email,"password":pw}).encode(),method="POST")
    r.add_header("Content-Type","application/json")
    with urllib.request.urlopen(r) as x: return json.loads(x.read().decode())["token"]

ROLES=[
 ("0_broker","david@inhous.com","inhous2026"),
 ("1_vendor","vendor.show@inhous.com","Showcase2026"),
 ("2_agent","agent1.show@inhous.com","Showcase2026"),
 ("3_buyer","buyer.show@inhous.com","Showcase2026"),
 ("4_vendor_solicitor","vsol.show@inhous.com","Showcase2026"),
 ("5_buyer_solicitor","bsol.show@inhous.com","Showcase2026"),
 ("6_photographer","photo.show@inhous.com","Showcase2026"),
 ("7_surveyor","survey.show@inhous.com","Showcase2026"),
 ("8_mortgage_broker","mort.show@inhous.com","Showcase2026"),
]
os.makedirs("screenshots", exist_ok=True)
o=Options(); o.add_argument("--headless=new"); o.add_argument("--disable-gpu"); o.add_argument("--no-sandbox"); o.add_argument("--window-size=1440,1024")
d=webdriver.Edge(options=o)
def clickText(text):
    return d.execute_script("""
      const t=arguments[0];
      const el=[...document.querySelectorAll('div.card')].find(e=>e.textContent.includes(t));
      if(el){el.click();return true;} return false;
    """, text)
try:
    for label,em,pw in ROLES:
        tok=token(em,pw)
        d.get(BASE+"/")
        d.execute_script("localStorage.setItem('inhous_token', arguments[0]);", tok)
        d.get(BASE+"/"); time.sleep(4)
        d.save_screenshot(f"screenshots/{label}_dashboard.png")
        if clickText("Showcase Manor"):
            time.sleep(3)
            d.save_screenshot(f"screenshots/{label}_property.png")
        # capture which tabs/sections are visible to this role
        tabs=d.execute_script("return [...document.querySelectorAll('button')].map(b=>b.textContent.trim()).filter(x=>['Overview','Participants','Valuations','Viewings','Feedback','Offers','Documents','AML / KYC','Photography','Brochure','Introductions'].includes(x));")
        print(f"{label:<20} sees sections: {sorted(set(tabs))}")
finally:
    d.quit()
print("\nScreenshots saved to ./screenshots/")
