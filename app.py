import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final)")

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

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()

# -------------------------------
# 2. Define infant inclusion patterns
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
    r"0[-\s]*24\s*months",
    r"from\s*1\s*year",
    r"from\s*12\s*months",
    r">\s*12\s*months",
    r">\s*18\s*months",
    r">\s*1\s*year"
]

# -------------------------------
# 3. Define infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    onset = age_map.get(condition.lower(), "").lower()
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
        return "Likely to include infants"
    if any(x in onset for x in ["toddler", "child", "3 years", "4 years"]):
        return "Unlikely to include infants but possible"
    return "Uncertain"

# -------------------------------
# 4. ClinicalTrials.gov API
# -------------------------------
def check_clinicaltrials_gov(condition):
    try:
        url = "https://clinicaltrials.gov/api/query/study_fields"
        params = {
            "expr": f"{condition} gene therapy",
            "fields": "NCTId,Condition,BriefTitle,Phase,OverallStatus",
            "min_rnk": 1,
            "max_rnk": 3,
            "fmt": "json"
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        studies = data['StudyFieldsResponse']['StudyFields']
        links = []
        for s in studies:
            nct_id = s["NCTId"][0]
            ct_link = f"https://clinicaltrials.gov/ct2/show/{nct_id}"
            links.append(ct_link)
        return links
    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov API error: {e}")
        return []

# -------------------------------
# 5. CGT relevance logic
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    condition_lower = condition.lower()

    relevance = cgt_map.get(condition_lower, None)
    if relevance:
        if relevance in ["Relevant", "Likely Relevant"]:
            links += check_clinicaltrials_gov(condition)
        return relevance, links

    cgt_keywords = ["cell therapy", "gene therapy", "crispr", "talen", "zfn",
                    "gene editing", "gene correction", "gene silencing", "reprogramming",
                    "cgt", "c&gt", "car-t therapy"]
    text_lower = text.lower() if pd.notna(text) else ""

    if any(k in text_lower for k in cgt_keywords):
        relevance = "Likely Relevant"
        links += check_clinicaltrials_gov(condition)
    else:
        relevance = "Unlikely Relevant"

    # Always add PubMed fallback
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ','+')}+gene+therapy"
    links.append(pubmed_url)

    return relevance, links

# -------------------------------
# 6. Contact email scraper
# -------------------------------
def extract_email(url):
    try:
        r = requests.get(url, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        mail = soup.select_one("a[href^=mailto]")
        if mail:
            return mail['href'].replace('mailto:', '')
        matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}", soup.get_text())
        return matches[0] if matches else ""
    except Exception as e:
        print(f"⚠️ Email extraction error: {e}")
        return ""

# -------------------------------
# 7. Streamlit app flow
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
            st.markdown("🔗 **Links:**")
            for link in study_links:
                st.markdown(f"- [{link}]({link})")

        email = st.text_input("Contact email", extract_email(record["Web site"]))

        pop_choice = st.radio("Infant Population", [
            "Include infants",
            "Likely to include infants",
            "Unlikely to include infants but possible",
            "Does not include infants",
            "Uncertain"
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
            df.at[original_index, "contact information"] = email
            df.at[original_index, "Population (use drop down list)"] = pop_choice if pop_choice != "Uncertain" else suggested_infant
            df.at[original_index, "Relevance to C&GT"] = cg_choice if cg_choice != "Unsure" else suggested_cgt
            df.at[original_index, "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            st.session_state.df = df
            st.success("✅ Saved!")

        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
