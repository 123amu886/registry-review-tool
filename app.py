import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final with Full Inclusion Criteria)")

# ✅ Embedded CGT mapping (simplified example; extend per your mapping file)
cgt_map = {
    "spinal muscular atrophy": "Relevant",
    "duchenne muscular dystrophy": "Relevant",
    "hemophilia a": "Relevant",
    "hemophilia b": "Likely Relevant",
    "sickle cell disease": "Likely Relevant",
    "type 1 diabetes": "Likely Relevant",
    "asthma": "Not Relevant"
}

# ✅ Sample condition onset mapping (extend with your full dataset)
age_map = {
    "spinal muscular atrophy": "birth",
    "duchenne muscular dystrophy": "early childhood",
    "hemophilia a": "infant",
    "hemophilia b": "infant",
    "sickle cell disease": "infant",
    "type 1 diabetes": "childhood",
    "asthma": "childhood"
}

# 🔧 Infant inclusion patterns
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

# 🔧 Infant inclusion assessment function
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    
    # Explicit inclusion criteria check
    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    # Condition-based onset mapping check for Likely
    onset = age_map.get(condition, "").lower()
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
        return "Likely to include infants"

    # Fallback for unlikely inclusion
    if any(x in onset for x in ["toddler", "child", "3 years", "4 years"]):
        return "Unlikely to include infants but possible"

    return "Uncertain"

# 🔧 CGT relevance assessment function
def assess_cgt_relevance_and_links(text, condition):
    links = []
    if pd.isna(text):
        text = ""
    text_lower = text.lower()
    condition_lower = condition.lower()

    relevance = cgt_map.get(condition_lower, None)
    if relevance:
        if relevance in ["Relevant", "Likely Relevant"]:
            ct_url = f"https://clinicaltrials.gov/ct2/results?cond={condition}&term=gene+therapy"
            scholar_url = f"https://scholar.google.com/scholar?q={condition}+gene+therapy+preclinical"
            links.extend([ct_url, scholar_url])
        return relevance, links

    cgt_keywords = [
        "cell therapy", "gene therapy", "crispr-cas9 system", "talen", "zfn",
        "gene editing", "gene correction", "gene silencing", "reprogramming",
        "cgt", "c&gt", "car-t therapy"
    ]
    if any(kw in text_lower for kw in cgt_keywords):
        relevance = "Likely Relevant"
        ct_url = f"https://clinicaltrials.gov/ct2/results?cond={condition}&term=gene+therapy"
        scholar_url = f"https://scholar.google.com/scholar?q={condition}+gene+therapy+preclinical"
        links.extend([ct_url, scholar_url])
    else:
        relevance = "Unlikely Relevant"

    return relevance, links

# 🔧 Contact email extractor
def extract_email(url):
    try:
        r = requests.get(url, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        mail = soup.select_one("a[href^=mailto]")
        if mail:
            return mail['href'].replace('mailto:', '')
        matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}", soup.get_text())
        if matches:
            return matches[0]
        return ""
    except Exception as e:
        print(f"⚠️ Error fetching {url}: {e}")
        return ""

# 🔧 Load uploaded file with session persistence
uploaded_file = st.file_uploader("📂 Upload your registry Excel file", type=["xlsx"])

if uploaded_file:
    if "df" not in st.session_state:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        st.session_state.df = df.copy()
    else:
        df = st.session_state.df

    reviewer_name = st.text_input("Enter your name (Column F)", "Reseum")
    df_filtered = df[df["Reviewer"].str.strip().str.lower() == reviewer_name.strip().lower()].copy()

    show_incomplete = st.checkbox("Show only incomplete (missing Population or Relevance)", value=True)
    if show_incomplete:
        df_filtered = df_filtered[df_filtered["Population (use drop down list)"].isna() | df_filtered["Relevance to C&GT"].isna()]

    if df_filtered.empty:
        st.success("🎉 All caught up! No matching rows found.")
    else:
        record_index = st.number_input("Select record", 0, len(df_filtered) - 1, step=1)
        record = df_filtered.iloc[record_index]
        condition = record["Conditions"]

        st.subheader("🔎 Record Details")
        st.markdown(f"**Condition:** `{condition}`")
        st.markdown(f"**Study Title:** `{record['Study Title']}`")
        st.markdown(f"[📄 Open Registry Link]({record['Web site']})")

        study_texts = " ".join([
            str(record.get("Population (use drop down list)", "")),
            str(record.get("Conditions", "")),
            str(record.get("Study Title", "")),
            str(record.get("Brief Summary", ""))
        ])

        # Infant inclusion assessment
        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested Infant Inclusion: **{suggested_infant}**")

        # CGT relevance assessment
        suggested_cgt, study_links = assess_cgt_relevance_and_links(study_texts, condition)
        st.caption(f"🧬 Suggested Cell/Gene Therapy Relevance: **{suggested_cgt}**")

        if study_links:
            st.markdown("🔗 **Related Preclinical/Clinical Study Links:**")
            for link in study_links:
                st.markdown(f"- [{link}]({link})")

        email = st.text_input("📧 Contact Email (Column E)", extract_email(record["Web site"]))

        # Reviewer inputs
        pop_choice = st.radio("🧒 Infant Population (Column G)", [
            "Include infants",
            "Likely to include infants",
            "Unlikely to include infants but possible",
            "Does not include infants",
            "Uncertain"
        ], index=0 if pd.isna(record['Population (use drop down list)']) else 0)

        comments = st.text_area("🗒 Reviewer Comments (Column H)", value=record.get("Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)", ""))

        cg_choice = st.radio("🧬 Cell/Gene Therapy Relevance (Column I)", [
            "Relevant",
            "Likely Relevant",
            "Unlikely Relevant",
            "Not Relevant",
            "Unsure"
        ], index=0 if pd.isna(record['Relevance to C&GT']) else 0)

        if st.button("💾 Save This Record"):
            original_index = df_filtered.index[record_index]
            df.at[original_index, "contact information"] = email
            df.at[original_index, "Population (use drop down list)"] = pop_choice if pop_choice != "Uncertain" else suggested_infant
            df.at[original_index, "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            df.at[original_index, "Relevance to C&GT"] = cg_choice if cg_choice != "Unsure" else suggested_cgt

            st.session_state.df = df
            st.success("✅ Record updated and saved.")

        if st.button("📤 Export Updated Excel"):
            st.session_state.df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
