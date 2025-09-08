import os, json
import streamlit as st

DATA_DIR = "data"
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
ASSETS_DIR = "assets"
LOGO_PATH = os.path.join(ASSETS_DIR, "council_logo.png")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# ---------- access gate ----------
ACCESS_CODE = os.getenv("ACCESS_CODE", "").strip()
if ACCESS_CODE:
    if not st.session_state.get("auth_ok"):
        st.title("🔒 Admin Settings")
        code = st.text_input("Access code", type="password")
        if st.button("Unlock"):
            if code == ACCESS_CODE:
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Wrong code.")
        st.stop()

st.set_page_config(page_title="Admin Settings", page_icon="⚙️", layout="centered")

# ---------- load/save ----------
def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # defaults from env
    return {
        "feeds": [u.strip() for u in os.getenv("GRANT_FEEDS","").split(",") if u.strip()],
        "keywords": [k.strip() for k in os.getenv("DISCOVERY_KEYWORDS","").split(",") if k.strip()],
        "regions": [r.strip() for r in os.getenv("DISCOVERY_REGION_TERMS","").split(",") if r.strip()],
        "slack": os.getenv("ALERT_SLACK_WEBHOOK","").strip(),
        "contact": {
            "name": os.getenv("ORG_CONTACT_NAME",""),
            "title": os.getenv("ORG_CONTACT_TITLE",""),
            "email": os.getenv("ORG_CONTACT_EMAIL",""),
            "phone": os.getenv("ORG_CONTACT_PHONE","")
        }
    }

def save_settings(data: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

st.title("⚙️ Admin Settings")

cfg = load_settings()

st.subheader("Grant Discovery Defaults")
feeds_txt = st.text_area("RSS feeds (one per line)", value="\n".join(cfg.get("feeds", [])), height=130)
keywords = st.text_input("Keywords (comma-separated)", ",".join(cfg.get("keywords", [])))
regions = st.text_input("Region terms (comma-separated)", ",".join(cfg.get("regions", [])))
slack = st.text_input("Slack Incoming Webhook (optional)", cfg.get("slack", ""))

st.subheader("Organisation Contact (for cover letters)")
c = cfg.get("contact", {})
c["name"] = st.text_input("Contact Name", c.get("name",""))
c["title"] = st.text_input("Contact Title/Team", c.get("title",""))
c["email"] = st.text_input("Contact Email", c.get("email",""))
c["phone"] = st.text_input("Contact Phone", c.get("phone",""))

st.subheader("Branding")
logo_file = st.file_uploader("Upload logo (PNG)", type=["png"])
if logo_file is not None:
    with open(LOGO_PATH, "wb") as f:
        f.write(logo_file.read())
    st.success("Logo saved to assets/council_logo.png")

if st.button("💾 Save settings", type="primary"):
    cfg["feeds"] = [u.strip() for u in feeds_txt.splitlines() if u.strip()]
    cfg["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
    cfg["regions"] = [r.strip() for r in regions.split(",") if r.strip()]
    cfg["slack"] = slack.strip()
    cfg["contact"] = c
    save_settings(cfg)
    st.success("Saved.")
