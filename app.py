import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Integrated)")

# -------------------------------
# 1. Load JSON mapping files
# -------------------------------
@st.cache_data
def load_cgt_mapping():
    with open("cgt_mapping.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_fda_approved():
    with open("fda_approved_gene_therapies.json", "r") as f:
        return json.load(f)

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()
fda_approved_map = load_fda_approved()

# -------------------------------
# 2. Infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""

    include_patterns = [
        r"from\s*0",
        r"starting at birth",
        r"newborn",
        r"infants?",
        r"less than\s*(12|18|24)\s*months?",
        r"<\s*(12|18|24)\s*months?",
        r"<\s*(1|2)\s*years?",
        r"up to\s*18\s*months?",
        r"up to\s*2\s*years?",
        r"0[-\s]*2\s*years?",
        r"0[-\s]*24\s*months?",
        r"from\s*1\s*year",
        r"from\s*12\s*months",
        r">\s*12\s*months",
        r">\s*18\s*months",
        r">\s*1\s*year"
    ]

    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    likely_patterns = [
        r"0\s*to",
        r"6\s*months?\s*to",
        r"12\s*months?\s*to",
        r"1\s*year\s*to",
        r"18\s*months?\s*to",
        r"up to"
    ]

    for pattern in likely_patterns:
        if re.search(pattern, text_lower):
            return "Likely to include infants"

    over_two_years = re.search(r"(>\s*2\s*years?|>\s*24\s*months?)", text_lower)
    age_3_or_more = re.search(r"(from|starting at|minimum age)\s*(3|4|5|\d{2,})\s*(years?)", text_lower)

    if over_two_years or age_3_or_more:
        return "Does not include infants"

    return "Does not include infants"

# -------------------------------
# 3. FDA approved therapy check
# -------------------------------
def check_fda_approved(condition):
    condition_lower = condition.lower()
    approved_info = []
    for therapy, details in fda_approved_map.items():
        if details["condition"].lower() == condition_lower:
            approved_info.append({
                "therapy": therapy,
                "type": details["type"],
                "developer": details["developer"],
                "approval_status": details["approval_status"],
                "age_group": details.get("age_group", "unknown")
            })
    return approved_info

# -------------------------------
# 4. ClinicalTrials.gov API check
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
                "nct_id": nct_id,
                "title": title,
                "phase": phase,
                "status": status,
                "link": ct_link,
                "contacts": [],
                "locations": []
            })

        return study_info

    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov API error for {condition}: {e}")
        return []

# -------------------------------
# 5. CGT relevance assessment
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    
    fda_info = check_fda_approved(condition)
    if fda_info:
        age_group = fda_info[0].get('age_group', 'unknown')
        relevance = "Relevant" if age_group == "pediatric" else "Likely Relevant"
        links.append({
            "title": f"FDA Approved Therapy: {fda_info[0]['therapy']} ({fda_info[0]['type']}, {fda_info[0]['developer']})",
            "link": "N/A",
            "phase": "Approved",
            "status": fda_info[0]['approval_status'],
            "contacts": [],
            "locations": [],
            "age_group": age_group
        })
        return relevance, links

    studies = check_clinicaltrials_gov(condition)
    if studies:
        links.extend(studies)
        return "Likely Relevant", links

    google_query = f"https://www.google.com/search?q=is+there+a+gene+therapy+for+{condition.replace(' ','+')}"
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ','+')}+gene+therapy"

    links.append({
        "title": "Google Search: Is there a gene therapy for this condition?",
        "link": google_query,
        "phase": "N/A",
        "status": "N/A",
        "contacts": [],
        "locations": []
    })

    links.append({
        "title": "PubMed Search",
        "link": pubmed_url,
        "phase": "N/A",
        "status": "N/A",
        "contacts": [],
        "locations": []
    })

    return "Unsure", links

# -------------------------------
# 6. Streamlit app flow
# -------------------------------
uploaded_file = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])

if uploaded_file:
    if "df" not in st.session_state:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        st.session_state.df = df.copy()
    else:
        df = st.session_state.df

    reviewer_name = st.text_input("Your name (Column F)", "")
    df_filtered = df[df["Reviewer"].str.strip().str.lower() == reviewer_name.strip().lower()].copy()

    show_incomplete = st.checkbox("Show only incomplete rows", value=True)
    if show_incomplete:
        df_filtered = df_filtered[df_filtered["Population (use drop down list)"].isna() | df_filtered["Relevance to C&GT"].isna()]

    if df_filtered.empty:
        st.success("🎉 All done, no incomplete rows.")
    else:
        record_index = st.number_input("Select row", 0, len(df_filtered)-1, step=1)
        record = df_filtered.iloc[record_index]
        condition = record["Conditions"]

        st.subheader("🔎 Record Details")
        st.markdown(f"**Condition:** `{condition}`")
        st.markdown(f"**Study Title:** `{record['Study Title']}`")
        st.markdown(f"[🔗 Open Registry Link]({record['Web site']})")

        study_texts = " ".join([
            str(record.get("Population (use drop down list)", "")),
            str(record.get("Conditions", "")),
            str(record.get("Study Title", "")),
            str(record.get("Brief Summary", ""))
        ])

        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested: **{suggested_infant}**")

        suggested_cgt, study_links = assess_cgt_relevance_and_links(study_texts, condition)
        st.caption(f"🧬 Suggested: **{suggested_cgt}**")

        if study_links:
            st.markdown("🔗 **Related Studies & Database Links:**")
            for s in study_links:
                st.markdown(f"- **{s['title']}** (Phase: {s['phase']}, Status: {s['status']}) [View Study]({s['link']})")

        pop_choice = st.radio("Infant Population", [
            "Include infants",
            "Likely to include infants",
            "Does not include infants"
        ], index=0)

        cg_choice = st.radio("Cell/Gene Therapy Relevance", [
            "Relevant",
            "Likely Relevant",
            "Unlikely Relevant",
            "Not Relevant",
            "Unsure"
        ], index=0)

        comments = st.text_area("Reviewer Comments", value=record.get(
            "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)", ""))

        if st.button("💾 Save"):
            original_index = df_filtered.index[record_index]
            df.at[original_index, "Population (use drop down list)"] = pop_choice if pop_choice != "Uncertain" else suggested_infant
            df.at[original_index, "Relevance to C&GT"] = cg_choice if cg_choice != "Unsure" else suggested_cgt
            df.at[original_index, "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            st.session_state.df = df
            st.success("✅ Saved!")

        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")

# ✅ End of final integrated app.py
# Save this file to GitHub as app.py and run with `streamlit run app.py`

# Let me know if you want the FDA auto-update script or testing checklist included next.
