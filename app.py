import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import re

st.set_page_config(page_title="Clinical Registry Review", layout="wide")
st.title("🧾 Enhanced Clinical Registry Review Tool")

# Load infant population mapping
@st.cache_data
def load_age_mapping():
    try:
        with open("infant_mapping.json", "r") as f:
            return json.load(f)
    except:
        return {}

age_map = load_age_mapping()

# Helper function: assess inclusion criteria
def assess_infant_inclusion(text):
    if pd.isna(text):
        return "Uncertain"
    text_lower = text.lower()
    inclusion_terms = [
        "up to 2 years",
        "from 0-24 months",
        "0-24 months",
        "from 0-2 years",
        "0-2 years",
        "under 2 years",
        "less than 2 years"
    ]
    for term in inclusion_terms:
        if term in text_lower:
            return "Include infants"
    return "Uncertain"

# Enhanced email extractor with debug logs
def extract_email(url):
    try:
        r = requests.get(url, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        mail = soup.select_one("a[href^=mailto]")
        if mail:
            email = mail['href'].replace('mailto:', '')
            print(f"✅ Found email: {email} for URL: {url}")
            return email
        else:
            # Try alternative parsing if no mailto link is found
            potential_emails = soup.get_text()
            matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}", potential_emails)
            if matches:
                email_found = matches[0]
                print(f"✅ Found email via regex: {email_found} for URL: {url}")
                return email_found
            print(f"❌ No email found for URL: {url}")
            return ""
    except Exception as e:
        print(f"⚠️ Error fetching {url}: {e}")
        return ""

# Function to assess Cell/Gene Therapy Relevance based on keywords
def assess_cgt_relevance(text):
    if pd.isna(text):
        return "Unsure"
    text_lower = text.lower()
    cgt_keywords = [
        "cell therapy",
        "gene therapy",
        "crispr-cas9 system",
        "gene editing",
        "cgt",
        "c&gt"
    ]
    for kw in cgt_keywords:
        if kw in text_lower:
            return "Relevant"
    return "Unsure"

uploaded_file = st.file_uploader("📂 Upload your registry Excel file", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")

    reviewer_name = st.text_input("Enter your name (Column F)", "Reseum")
    df_filtered = df[df["Reviewer"].str.strip().str.lower() == reviewer_name.strip().lower()].copy()

    condition_query = st.text_input("Optional: Filter by condition name (Column D)").strip()
    if condition_query:
        df_filtered = df_filtered[df_filtered["Conditions"].str.contains(condition_query, case=False, na=False)]

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

        # Suggested infant inclusion from age criteria detection
        study_texts = " ".join([
            str(record.get("Population (use drop down list)", "")),
            str(record.get("Conditions", "")),
            str(record.get("Study Title", "")),
            str(record.get("Brief Summary", ""))
        ])
        suggested_infant = assess_infant_inclusion(study_texts)
        st.caption(f"🧒 Suggested Infant Inclusion (based on text scan): **{suggested_infant}**")

        # If age_map has condition-based mapping, override Uncertain
        condition_based = age_map.get(condition, None)
        if condition_based and suggested_infant == "Uncertain":
            suggested_infant = condition_based
            st.caption(f"🧒 Suggested Infant Inclusion (from mapping): **{suggested_infant}**")

        # Assess C&GT relevance based on keyword search
        suggested_cgt = assess_cgt_relevance(study_texts)
        st.caption(f"🧬 Suggested Cell/Gene Therapy Relevance (keyword scan): **{suggested_cgt}**")

        email = st.text_input("📧 Contact Email (Column E)", extract_email(record["Web site"]))

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

        if st.button("🔍 Auto-check C&GT relevance from clinicaltrials.gov"):
            cg_auto = search_gene_therapy(condition)
            st.success(f"Gene therapy relevance: **{cg_auto}**")
            cg_choice = cg_auto

        if st.button("💾 Save This Record"):
            df_filtered.at[record_index, "contact information"] = email
            df_filtered.at[record_index, "Population (use drop down list)"] = pop_choice
            df_filtered.at[record_index, "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            df_filtered.at[record_index, "Relevance to C&GT"] = cg_choice if cg_choice != "Unsure" else suggested_cgt
            st.success("✅ Record updated.")

        if st.button("📤 Export Updated Excel"):
            df.update(df_filtered)
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
