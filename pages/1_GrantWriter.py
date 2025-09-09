import os, sys, json, re
from typing import Dict, List
import streamlit as st

# --- Ensure we can import from project root (for `utils/`)
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# --- Import helper module
try:
    from utils.grantwriter_modules import build_rubric, assess_project, export_docx
except Exception as e:
    st.error("Couldn't import utils.grantwriter_modules. Make sure utils/grantwriter_modules.py exists.")
    st.exception(e)
    st.stop()

# --- Folders
os.makedirs(os.path.join(PROJECT_ROOT, "exports"), exist_ok=True)

# =====================
# Utility functions
# =====================

def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def smart_trim(text: str, max_words: int = 150) -> str:
    """Trim text to ~max_words, preserving sentence boundaries when possible."""
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    # Try sentence-preserving trim
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    acc = []
    total = 0
    for s in sentences:
        w = len(s.split())
        if total + w <= max_words:
            acc.append(s)
            total += w
        else:
            break
    if acc:
        return " ".join(acc).strip()
    # Fallback to hard cut
    return " ".join(words[:max_words]).strip()


def text_area_with_counter(label: str, key: str, help: str = "", height: int = 160, show_shrink: bool = True, shrink_to: int = 150):
    """Render a text area with a word counter and optional shrink button."""
    val = st.text_area(label, key=key, help=help, height=height)
    wc = word_count(val)
    col_a, col_b = st.columns([4, 1])
    with col_a:
        st.caption(f"Words: {wc}")
    with col_b:
        if show_shrink and wc > shrink_to:
            if st.button(f"Shrink to {shrink_to}", key=f"shrink_{key}"):
                st.session_state[key] = smart_trim(val, shrink_to)
                st.experimental_rerun()
    return st.session_state.get(key, val)


def save_project_json(payload: Dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def load_project_into_state(data: Dict):
    # Criteria & rubric
    if "criteria_raw" in data:
        st.session_state["criteria_raw"] = data["criteria_raw"]
    if "rubric" in data and isinstance(data["rubric"], list):
        st.session_state["rubric"] = [
            # keep as plain dicts; the assess function doesn't require dataclass objects
            r for r in data["rubric"]
        ]
    if "assessment" in data:
        st.session_state["assessment"] = data["assessment"]
    # Project fields
    proj = data.get("project", {})
    for k, v in proj.items():
        # map back to session keys used below
        mapping = {
            "Project Title": "project_title",
            "Executive Summary": "short_summary",
            "Problem / Need": "problem_need",
            "Activities & Delivery Plan": "activities_plan",
            "Expected Outcomes (KPIs/metrics)": "outcomes_kpis",
            "Evaluation (how you'll measure)": "evaluation",
            "Target Audience": "target_audience",
            "Budget (summary + justification)": "budget",
            "Objectives (bullets OK)": "objectives",
            "Risks & Mitigation": "risks",
            "High-level Timeline": "timeline",
            "Partners & Governance": "partners",
        }
        skey = mapping.get(k)
        if skey:
            st.session_state[skey] = v
    # Meta
    meta = data.get("meta", {})
    st.session_state["funder_name"] = meta.get("funder", st.session_state.get("funder_name", ""))
    st.session_state["applicant_name"] = meta.get("applicant", st.session_state.get("applicant_name", ""))
    st.session_state["amount_requested"] = meta.get("amount", st.session_state.get("amount_requested", ""))


# =====================
# UI — Sidebar
# =====================
st.set_page_config(page_title="GrantWriter AI", page_icon="📝", layout="wide")

with st.sidebar:
    st.header("Grant Criteria")
    criteria_text = st.text_area("Paste the funder criteria verbatim", height=220, key="criteria_raw")
    cols = st.columns(2)
    with cols[0]:
        if st.button("Build Rubric", help="Parse criteria → weighted rubric"):
            st.session_state["rubric"] = build_rubric(criteria_text)
            st.success("Rubric built ✅")
    with cols[1]:
        if st.button("Reset Rubric"):
            st.session_state.pop("rubric", None)
            st.info("Rubric cleared")

    rubric = st.session_state.get("rubric", [])
    if rubric:
        st.subheader("Weighted criteria")
        for r in rubric:
            # r may be a dataclass or dict depending on load/save; normalize
            crit = r["criterion"] if isinstance(r, dict) else r.criterion
            wt = r["weight"] if isinstance(r, dict) else r.weight
            st.write(f"- {crit} — **{round(float(wt)*100)}%**")

    st.divider()
    st.header("Meta")
    st.text_input("Funder name", key="funder_name")
    st.text_input("Applicant/Org name", key="applicant_name")
    st.text_input("Amount requested", key="amount_requested")

    st.divider()
    st.header("Save / Load Project")
    # Download current state as JSON
    if st.button("Prepare Download JSON"):
        # construct a compatible payload
        project_blob = {
            "Project Title": st.session_state.get("project_title", ""),
            "Executive Summary": st.session_state.get("short_summary", ""),
            "Problem / Need": st.session_state.get("problem_need", ""),
            "Activities & Delivery Plan": st.session_state.get("activities_plan", ""),
            "Expected Outcomes (KPIs/metrics)": st.session_state.get("outcomes_kpis", ""),
            "Evaluation (how you'll measure)": st.session_state.get("evaluation", ""),
            "Target Audience": st.session_state.get("target_audience", ""),
            "Budget (summary + justification)": st.session_state.get("budget", ""),
            "Objectives (bullets OK)": st.session_state.get("objectives", ""),
            "Risks & Mitigation": st.session_state.get("risks", ""),
            "High-level Timeline": st.session_state.get("timeline", ""),
            "Partners & Governance": st.session_state.get("partners", ""),
        }
        payload = {
            "meta": {
                "funder": st.session_state.get("funder_name", ""),
                "applicant": st.session_state.get("applicant_name", ""),
                "amount": st.session_state.get("amount_requested", ""),
                "version": "1.0",
            },
            "criteria_raw": st.session_state.get("criteria_raw", ""),
            "rubric": [r if isinstance(r, dict) else r.__dict__ for r in rubric],
            "project": project_blob,
            "assessment": st.session_state.get("assessment", {}),
        }
        st.session_state["_download_bytes"] = save_project_json(payload)
    if b := st.session_state.get("_download_bytes"):
        st.download_button("Download Project JSON", data=b, file_name="grantwriter_project.json")

    # Upload to load
    up = st.file_uploader("Load from JSON", type=["json"])
    if up is not None:
        try:
            data = json.loads(up.read().decode("utf-8"))
            load_project_into_state(data)
            st.success("Project loaded ✅")
        except Exception as e:
            st.error("Invalid JSON file")
            st.exception(e)


# =====================
# UI — Main content
# =====================
st.title("GrantWriter AI")
st.caption("Draft, assess, and export grant narratives aligned to funder criteria.")

st.header("Project Details")
st.text_input("Project Title", key="project_title")
text_area_with_counter("Short Summary (2–3 sentences)", key="short_summary", height=120, shrink_to=120)
text_area_with_counter("Problem / Need", key="problem_need")
text_area_with_counter("Activities & Delivery Plan", key="activities_plan")
text_area_with_counter("Expected Outcomes (KPIs/metrics)", key="outcomes_kpis")
text_area_with_counter("Evaluation (how you'll measure)", key="evaluation")
text_area_with_counter("Target Audience", key="target_audience")
text_area_with_counter("Budget (summary + justification)", key="budget")
text_area_with_counter("Objectives (bullets OK)", key="objectives")
text_area_with_counter("Risks & Mitigation", key="risks")
st.text_input("High-level Timeline", key="timeline", help="e.g., Q1 design; Q2 procurement; Q3 delivery; Q4 evaluation")
text_area_with_counter("Partners & Governance", key="partners")

st.divider()
colA, colB, colC = st.columns([1,1,2])

with colA:
    if st.button("Run Coverage Check"):
        rubric_list = st.session_state.get("rubric", [])
        if not rubric_list:
            st.warning("Build the rubric in the sidebar first.")
        else:
            # Build a project dict for assessment
            project_for_assess = {
                "Project Title": st.session_state.get("project_title", ""),
                "Executive Summary": st.session_state.get("short_summary", ""),
                "Problem / Need": st.session_state.get("problem_need", ""),
                "Activities & Delivery Plan": st.session_state.get("activities_plan", ""),
                "Expected Outcomes (KPIs/metrics)": st.session_state.get("outcomes_kpis", ""),
                "Evaluation (how you'll measure)": st.session_state.get("evaluation", ""),
                "Target Audience": st.session_state.get("target_audience", ""),
                "Budget (summary + justification)": st.session_state.get("budget", ""),
                "Objectives (bullets OK)": st.session_state.get("objectives", ""),
                "Risks & Mitigation": st.session_state.get("risks", ""),
                "High-level Timeline": st.session_state.get("timeline", ""),
                "Partners & Governance": st.session_state.get("partners", ""),
            }
            # NOTE: assess_project expects a list of RubricItem; if we loaded dicts, it's fine because we only read fields.
            st.session_state["assessment"] = assess_project(project_for_assess, st.session_state["rubric"])  # type: ignore
            st.success("Assessed against criteria ✅")

with colB:
    if st.button("Export DOCX"):
        project_for_export = {
            "Project Title": st.session_state.get("project_title", ""),
            "Executive Summary": st.session_state.get("short_summary", ""),
            "Problem / Need": st.session_state.get("problem_need", ""),
            "Activities & Delivery Plan": st.session_state.get("activities_plan", ""),
            "Expected Outcomes (KPIs/metrics)": st.session_state.get("outcomes_kpis", ""),
            "Evaluation (how you'll measure)": st.session_state.get("evaluation", ""),
            "Target Audience": st.session_state.get("target_audience", ""),
            "Budget (summary + justification)": st.session_state.get("budget", ""),
            "Objectives (bullets OK)": st.session_state.get("objectives", ""),
            "Risks & Mitigation": st.session_state.get("risks", ""),
            "High-level Timeline": st.session_state.get("timeline", ""),
            "Partners & Governance": st.session_state.get("partners", ""),
        }
        meta = {
            "title": project_for_export.get("Project Title") or "Grant Application",
            "funder": st.session_state.get("funder_name", ""),
            "applicant": st.session_state.get("applicant_name", ""),
            "amount": st.session_state.get("amount_requested", ""),
        }
        path = export_docx(
            project_for_export,
            filename=os.path.join(PROJECT_ROOT, "exports", "GrantWriter_Export.docx"),
            meta=meta,
            rubric_result=st.session_state.get("assessment"),
        )
        with open(path, "rb") as f:
            st.download_button("Download DOCX", f, file_name="GrantWriter_Export.docx")

res = st.session_state.get("assessment")
if res:
    st.divider()
    st.subheader("Assessment summary")
    overall = res.get("__overall__", {}).get("score", 0.0)
    st.write(f"**Overall weighted score:** {round(float(overall)*100)}%")

    for crit, v in res.items():
        if crit.startswith("__"):
            continue
        weight = float(v.get("weight", 0))
        coverage = float(v.get("coverage", 0))
        st.write(f"**{crit}** — weight {round(weight*100)}% | coverage {round(coverage*100)}%")
        st.progress(coverage)
        hints = v.get("hints") or []
        if hints:
            st.caption("Hints: " + "; ".join(hints[:3]))

st.info
