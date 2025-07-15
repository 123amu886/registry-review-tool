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
def load_pipeline_cgt():
    with open("pipeline_cgt_conditions.json", "r") as f:
        return json.load(f)

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()
pipeline_cgt_map = load_pipeline_cgt()

# -------------------------------
# 2. Infant inclusion patterns
# -------------------------------
include_patterns = [
    r"(from|starting at|age)\s*0",
    r"(from|starting at)\s*birth",
    r"newborn",
    r"infants?",
    r"less than\s*(12|18|24)\s*months",
    r"<\s*(12|18|24)\s*months",
    r"<\s*(1|2)\s*years?",
    r"up to\s*18\s*months",
    r"up to\s*2\s*years",
    r"0[-\s]*2\s*years",
    r"0[-\s]*24\s*months"
]

# -------------------------------
# 3. Extract min/max age
# -------------------------------
def extract_min_max_age(text):
    min_age = None
    max_age = None

    min_patterns = [
        r"minimum age\s*[:=]?\s*(\d+)\s*(year|month)",
        r"from\s*(\d+)\s*(year|month)",
        r"starting at\s*(\d+)\s*(year|month)",
        r"age\s*[>≥]\s*(\d+)\s*(year|month)",
        r"(\d+)\s*(year|month)s?\s*and older"
    ]

    max_patterns = [
        r"maximum age\s*[:=]?\s*(\d+)\s*(year|month)",
        r"up to\s*(\d+)\s*(year|month)",
        r"<\s*(\d+)\s*(year|month)",
        r"less than\s*(\d+)\s*(year|month)"
    ]

    for pattern in min_patterns:
        for m in re.finditer(pattern, text, flags=re.I):
            val, unit = int(m.group(1)), m.group(2).lower()
            months = val * 12 if "year" in unit else val
            if min_age is None or months < min_age:
                min_age = months

    for pattern in max_patterns:
        for m in re.finditer(pattern, text, flags=re.I):
            val, unit = int(m.group(1)), m.group(2).lower()
            months = val * 12 if "year" in unit else val
            if max_age is None or months > max_age:
                max_age = months

    return min_age, max_age

# -------------------------------
# 4. Infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    min_age, max_age = extract_min_max_age(text_lower)

    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    if min_age is not None and min_age <= 24:
        return "Include infants"

    onset = age_map.get(condition.lower(), "").lower()
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
        return "Likely to include infants"

    if "up to" in text_lower and (min_age is None or min_age <= 18):
        return "Likely to include infants"

    if min_age in [24, 25]:
        return "Unlikely to include infants but possible"

    if min_age is not None and min_age > 24:
        return "Does not include infants"

    if min_age is None and any(x in onset for x in ["child", "adult", "adolescent", "3 years", "4 years", "5 years"]):
        return "Does not include infants"

    return "Uncertain"

# -------------------------------
# 5. ClinicalTrials.gov API
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
                "link": ct_link
            })

        return study_info

    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov API error for {condition}: {e}")
        return []

# -------------------------------
# 6. Improved CGT relevance logic
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    cond = condition.lower()
    info = pipeline_cgt_map.get(cond)

    if info:
        rel = info["relevance"]
        studies = check_clinicaltrials_gov(condition)
        links.extend(studies)
        if rel == "Likely Relevant" and any(s for s in studies if s['phase'].lower().startswith("phase")):
            rel = "Relevant"
        return rel, links

    # Fallback to previous keyword-based logic
    cgt_keywords = ["cell therapy", "gene therapy", "crispr", "talen", "zfn",
                    "gene editing", "gene correction", "gene silencing", "reprogramming",
                    "cgt", "c&gt", "car-t therapy"]
    text_lower = text.lower() if pd.notna(text) else ""

    if any(k in text_lower for k in cgt_keywords):
        relevance = "Likely Relevant"
    else:
        relevance = "Unsure"

    google_query = f"https://www.google.com/search?q=is+there+a+gene+therapy+for+{condition.replace(' ','+')}"
    links.append({
        "title": "Google Search: Is there a gene therapy for this condition?",
        "link": google_query,
        "phase": "N/A",
        "status": "N/A"
    })

    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ','+')}+gene+therapy"
    links.append({
        "title": "PubMed Search",
        "link": pubmed_url,
        "phase": "N/A",
        "status": "N/A"
    })

    return relevance, links

# -------------------------------
# 7. Streamlit app flow
# -------------------------------
uploaded_file = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")
    reviewer_name = st.text_input("Your name (Column F)", "")
    df_filtered = df[df["Reviewer"].str.strip().str.lower() == reviewer_name.strip().lower()].copy()

    if df_filtered.empty:
        st.success("🎉 All done, no incomplete rows.")
    else:
        record_index = st.number_input("Select row", 0, len(df_filtered)-1, step=1)
        record = df_filtered.iloc[record_index]
        condition = record["Conditions"]

        st.subheader("🔎 Record Details")
        st.markdown(f"**Condition:** {condition}")

        study_texts = " ".join([str(record.get(col, "")) for col in df.columns])

        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested: **{suggested_infant}**")

        suggested_cgt, study_links = assess_cgt_relevance_and_links(study_texts, condition)
        st.caption(f"🧬 Suggested: **{suggested_cgt}**")

        if study_links:
            st.markdown("🔗 **Related Studies & Database Links:**")
            for s in study_links:
                st.markdown(f"- **{s['title']}** (Phase: {s['phase']}, Status: {s['status']}) [View Study]({s['link']})")

        if st.button("💾 Save"):
            df.at[df_filtered.index[record_index], "Population (use drop down list)"] = suggested_infant
            df.at[df_filtered.index[record_index], "Relevance to C&GT"] = suggested_cgt
            st.success("✅ Saved!")

        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
