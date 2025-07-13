import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Full App)")

# -------------------------------
# 1. Load JSON mappings
# -------------------------------
@st.cache_data
def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)

cgt_map = load_json("cgt_mapping.json")
age_map = load_json("infant_mapping.json")

# -------------------------------
# 2. ClinicalTrials.gov API function
# -------------------------------
def check_clinicaltrials_gov(condition):
    try:
        search_url = "https://clinicaltrials.gov/api/query/study_fields"
        search_params = {
            "expr": f"{condition} gene therapy",
            "fields": "NCTId,BriefTitle,Phase,OverallStatus",
            "min_rnk": 1,
            "max_rnk": 3,
            "fmt": "json"
        }
        search_r = requests.get(search_url, params=search_params, timeout=10)
        search_data = search_r.json()
        studies = search_data['StudyFieldsResponse']['StudyFields']
        study_info = []
        for s in studies:
            nct_id = s["NCTId"][0]
            title = s["BriefTitle"][0]
            phase = s.get("Phase", ["N/A"])[0]
            status = s.get("OverallStatus", ["N/A"])[0]
            ct_link = f"https://clinicaltrials.gov/ct2/show/{nct_id}"
            study_info.append({
                "title": title,
                "link": ct_link,
                "phase": phase,
                "status": status
            })
        return study_info
    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov API error for {condition}: {e}")
        return []

# -------------------------------
# 3. Infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    include_patterns = [r"from\\s*0", r"starting at birth", r"newborn", r"infants?", r"less than\\s*(12|18|24)\\s*months?", r"<\\s*(12|18|24)\\s*months?", r"<\\s*(1|2)\\s*years?", r"up to\\s*18\\s*months?", r"up to\\s*2\\s*years?", r"0[-\\s]*2\\s*years?", r"0[-\\s]*24\\s*months?", r"from\\s*1\\s*year", r"from\\s*12\\s*months", r">\\s*12\\s*months", r">\\s*18\\s*months", r">\\s*1\\s*year"]
    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"
    if "up to" in text_lower:
        return "Likely to include infants"
    likely_patterns = [r"0\\s*to", r"6\\s*months?\\s*to", r"12\\s*months?\\s*to", r"1\\s*year\\s*to", r"18\\s*months?\\s*to"]
    for pattern in likely_patterns:
        if re.search(pattern, text_lower):
            return "Likely to include infants"
    return "Does not include infants"

# -------------------------------
# 4. App flow
# -------------------------------
uploaded_file = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")
    reviewer_name = st.text_input("Your name (Column F)", "")
    df_filtered = df[df["Reviewer"].str.strip().str.lower() == reviewer_name.strip().lower()].copy()
    if df_filtered.empty:
        st.success("🎉 All done, no rows.")
    else:
        record_index = st.number_input("Select row", 0, len(df_filtered)-1, step=1)
        record = df_filtered.iloc[record_index]
        condition = record["Conditions"]
        st.markdown(f"**Condition:** `{condition}`")
        study_texts = " ".join([str(record.get(c, "")) for c in df.columns])
        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested: **{suggested_infant}**")

        # ClinicalTrials.gov links
        studies = check_clinicaltrials_gov(condition)
        if studies:
            st.markdown("🔗 **Related Clinical Trials:**")
            for s in studies:
                st.markdown(f"- **{s['title']}** (Phase: {s['phase']}, Status: {s['status']}) [View Study]({s['link']})")
        else:
            st.markdown("⚠️ No active gene therapy trials found.")

# ✅ Save this as `app.py` for your final deployment.
# Let me know if you want FDA and pipeline integration functions re-added next.
