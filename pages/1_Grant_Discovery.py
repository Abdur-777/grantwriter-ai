import os, re, json, hashlib
from urllib.parse import urlparse
from dateutil import parser as dparser
import requests, feedparser
from bs4 import BeautifulSoup
import streamlit as st

# Optional GPT relevance / fields
USE_GPT = True
try:
    from openai import OpenAI
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY",""))
except Exception:
    USE_GPT = False

COUNCIL_NAME = os.getenv("COUNCIL_NAME", "Your Council")
DEFAULT_FEEDS = [u.strip() for u in os.getenv("GRANT_FEEDS","").split(",") if u.strip()]
KEYWORDS = [k.strip().lower() for k in os.getenv("DISCOVERY_KEYWORDS","").split(",") if k.strip()]
REGION_TERMS = [k.strip().lower() for k in os.getenv("DISCOVERY_REGION_TERMS","").split(",") if k.strip()]
SLACK_WEBHOOK = os.getenv("ALERT_SLACK_WEBHOOK","").strip()

DATA_DIR = "data"; os.makedirs(DATA_DIR, exist_ok=True)
SEEN_PATH = os.path.join(DATA_DIR, "seen_grants.json")

st.set_page_config(page_title=f"Grant Discovery – {COUNCIL_NAME}", page_icon="🔎", layout="wide")
st.markdown("<h2>🔎 Grant Discovery & Alerts</h2>", unsafe_allow_html=True)

def _hash(s:str)->str: return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
def load_seen()->set:
    if os.path.exists(SEEN_PATH):
        try: return set(json.load(open(SEEN_PATH,"r",encoding="utf-8")))
        except Exception: return set()
    return set()
def save_seen(seen:set): json.dump(sorted(list(seen)), open(SEEN_PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def fetch_rss(url:str)->list[dict]:
    try:
        fp = feedparser.parse(url); items=[]
        for e in fp.entries:
            items.append({
                "source": urlparse(url).netloc,
                "title": e.get("title","").strip(),
                "link": e.get("link","").strip(),
                "summary": (e.get("summary") or e.get("description") or "").strip(),
                "published": e.get("published",""),
                "id": e.get("id") or e.get("guid") or e.get("link") or _hash(e.get("title","")),
            })
        return items
    except Exception: return []

def fetch_html(url:str)->str:
    try:
        r = requests.get(url, timeout=20); r.raise_for_status(); return r.text
    except Exception: return ""

def extract_deadline_amount(text:str):
    amount=None; date=None
    m = re.search(r'(\$[0-9][\d,]*(?:\.\d{2})?)', text, re.I)
    if m: amount = m.group(1)
    dm = re.search(r'(?:deadline|close[sd]?|due)\s*[:\-]?\s*(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})', text, re.I)
    if dm:
        try: date = dparser.parse(dm.group(1), dayfirst=False, fuzzy=True).date().isoformat()
        except Exception: date = dm.group(1)
    return date, amount

def gpt_rank(title, summary, url, keywords, region_terms):
    if not USE_GPT:
        txt=(title+" "+summary).lower()
        score = sum(1 for k in keywords if k in txt) + sum(1 for r in region_terms if r in txt)
        dd, amt = extract_deadline_amount(summary)
        return {"relevance": min(score*10,90), "deadline": dd, "amount": amt, "why":"heuristic"}
    try:
        prompt = f"""Rank this grant for {COUNCIL_NAME}.
TITLE: {title}
SUMMARY: {summary}
URL: {url}
KEYWORDS: {keywords}
REGION_TERMS: {region_terms}
Return JSON: {{"relevance":0,"deadline":"","amount":"","why":""}}"""
        r = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":"Output strict JSON only."},{"role":"user","content":prompt}],
            response_format={"type":"json_object"}, temperature=0.0, max_tokens=300
        )
        import json; out=json.loads(r.choices[0].message.content)
        if not out.get("deadline") or not out.get("amount"):
            dd, amt = extract_deadline_amount(title+" "+summary); out.setdefault("deadline", dd); out.setdefault("amount", amt)
        return out
    except Exception:
        dd, amt = extract_deadline_amount(title+" "+summary)
        return {"relevance":50,"deadline":dd,"amount":amt,"why":"fallback"}

def post_slack(webhook:str, blocks:list[dict])->bool:
    try: return requests.post(webhook, json={"blocks":blocks}, timeout=15).status_code in (200,204)
    except Exception: return False

def slack_blocks(grants:list[dict])->list[dict]:
    blocks = [{"type":"header","text":{"type":"plain_text","text":"New Grants"}}]
    for g in grants[:10]:
        line = f"*{g['title']}* — {g.get('amount','N/A')} (due {g.get('deadline','N/A')})\n<{g['link']}|Open>  |  {g.get('why','')}"
        blocks += [{"type":"section","text":{"type":"mrkdwn","text":line}}, {"type":"divider"}]
    return blocks

with st.sidebar:
    st.header("⚙️ Sources & Filters")
    feeds = st.text_area("RSS feeds (one per line)", value="\n".join(DEFAULT_FEEDS), height=140)
    keys = st.text_input("Keywords (comma-separated)", ",".join(KEYWORDS) or "community,youth,transport")
    regions = st.text_input("Region terms (comma-separated)", ",".join(REGION_TERMS) or "Victoria,VIC,Wyndham")
    min_rel = st.slider("Min relevance", 0, 100, 60, 5)
    enable_slack = st.toggle("Enable Slack alerts", value=bool(SLACK_WEBHOOK))
    webhook = st.text_input("Slack webhook URL", value=SLACK_WEBHOOK if enable_slack else "")

st.markdown("### 🔁 Fetch & Rank")
if st.button("Fetch now"):
    FEEDS=[u.strip() for u in feeds.splitlines() if u.strip()]
    K=[k.strip().lower() for k in keys.split(",") if k.strip()]
    R=[r.strip().lower() for r in regions.split(",") if r.strip()]
    seen=load_seen(); rows=[]
    with st.spinner("Fetching feeds…"):
        for u in FEEDS:
            for item in fetch_rss(u):
                uid = item.get("id") or item.get("link") or item.get("title","")
                uid = _hash(uid)
                title=item["title"]; link=item["link"]; summary=item.get("summary",""); pub=item.get("published","")
                page_text=""
                try:
                    html=fetch_html(link)
                    if html:
                        soup=BeautifulSoup(html, "html.parser")
                        page_text=" ".join([t.get_text(" ", strip=True) for t in soup.select("p")])[:6000]
                except Exception: pass
                rel = gpt_rank(title, (summary or page_text)[:2000], link, K, R)
                rows.append({
                    "uid":uid,"title":title,"link":link,"published":pub,
                    "relevance":int(rel.get("relevance",0)),
                    "deadline":rel.get("deadline"),"amount":rel.get("amount"),"why":rel.get("why",""),
                    "new": (uid not in seen)
                })
    if not rows: st.info("No items found."); st.stop()
    import pandas as pd
    df=pd.DataFrame(rows).sort_values(["new","relevance"], ascending=[False,False])
    st.session_state["last_df"]=df
    st.success(f"Fetched {len(df)} items.")
    st.dataframe(df, use_container_width=True)

st.markdown("---")
df=st.session_state.get("last_df")
if df is not None and not df.empty:
    st.markdown("### 📤 Alert / Export")
    new_hits = df[(df["new"]) & (df["relevance"] >= min_rel)].to_dict(orient="records")
    c1,c2,c3=st.columns(3)
    c1.metric("New high-relevance", len(new_hits))
    c2.metric("Min relevance", min_rel)
    c3.metric("Total fetched", len(df))

    if new_hits:
        if webhook and st.button("🔔 Send Slack Alert"):
            ok=post_slack(webhook, slack_blocks(new_hits))
            st.success("Slack alert sent.") if ok else st.error("Slack alert failed.")
    else:
        st.info("No new items over threshold.")

    if st.button("✅ Mark shown as seen"):
        seen=load_seen()
        for r in df.to_dict(orient="records"): seen.add(r["uid"])
        save_seen(seen); st.success("Marked as seen.")

    csv=df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", data=csv, file_name="grants_discovered.csv", mime="text/csv")

    digest = []
    for r in new_hits:
        digest.append(f"- **{r['title']}** — {r.get('amount','N/A')} (due {r.get('deadline','N/A')})  \n  {r['link']}  \n  _{r.get('why','')}_")
    md = "# New Grants Digest\n\n" + ("\n".join(digest) if digest else "_No new high-relevance items._")
    st.download_button("⬇️ Download Digest (MD)", data=md.encode("utf-8"), file_name="grants_digest.md", mime="text/markdown")
else:
    st.info("Click **Fetch now** to see results.")
