import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Integrated)")

# -------------------------------
# 1. Load JSON mapping files with lowercase keys
# -------------------------------
@st.cache_data
def load_cgt_mapping():
    with open("cgt_mapping.json", "r") as f:
        raw_map = json.load(f)
        return {k.lower(): v for k, v in raw_map.items()}

@st.cache_data
def load_pipeline_cgt_mapping():
    with open("pipeline_cgt_mapping.json", "r") as f:
        raw_map = json.load(f)
        return {k.lower(): v for k, v in raw_map.items()}

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

cgt_map = load_cgt_mapping()
pipeline_map = load_pipeline_cgt_mapping()
age_map = load_age_mapping()

# -------------------------------
# 2. Infant inclusion patterns and extraction
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

def extract_min_max_age(text):
    min_age, max_age = None, None

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
# 3. CGT relevance assessment
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    condition_lower = condition.lower()
    links = []

    if condition_lower in cgt_map:
        relevance = "Relevant"
    elif condition_lower in pipeline_map:
        relevance = "Likely Relevant"
    else:
        # fallback keyword-based logic
        cgt_keywords = ["cell therapy", "gene therapy", "crispr", "talen", "zfn",
                        "gene editing", "gene correction", "gene silencing", "reprogramming",
                        "cgt", "c&gt", "car-t therapy"]
        text_lower = text.lower() if pd.notna(text) else ""
        if any(k in text_lower for k in cgt_keywords):
            relevance = "Likely Relevant"
        else:
            relevance = "Unsure"

    # Always add Google & PubMed fallback links
    google_query = f"https://www.google.com/search?q=is+there+a+gene+therapy+for+{condition.replace(' ','+')}"
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ','+')}+gene+therapy"

    links.append({"title": "Google Search", "link": google_query})
    links.append({"title": "PubMed Search", "link": pubmed_url})

    return relevance, links

# -------------------------------
# 4. Streamlit app flow
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
        st.markdown(f"**Condition:** {condition}")
        st.markdown(f"**Study Title:** {record['Study Title']}")
        st.markdown(f"[🔗 Open Registry Link]({record['Web site']})")

        study_texts = " ".join([
            str(record.get("Population (use drop down list)", "")),
            str(record.get("Conditions", "")),
            str(record.get("Study Title", "")),
            str(record.get("Brief Summary", ""))
        ])

        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested infant inclusion: **{suggested_infant}**")

        suggested_cgt, study_links = assess_cgt_relevance_and_links(study_texts, condition)
        st.caption(f"🧬 Suggested CGT relevance: **{suggested_cgt}**")

        if study_links:
            st.markdown("🔗 **Related Searches:**")
            for s in study_links:
                st.markdown(f"- [{s['title']}]({s['link']})")

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
            df.at[original_index, "Population (use drop down list)"] = pop_choice if pop_choice != "Uncertain" else suggested_infant
            df.at[original_index, "Relevance to C&GT"] = cg_choice if cg_choice != "Unsure" else suggested_cgt
            df.at[original_index, "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            st.session_state.df = df
            st.success("✅ Saved!")

        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
