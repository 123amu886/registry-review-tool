import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import re

st.set_page_config(page_title="Clinical Registry Review", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final with Expanded C&GT Keywords)")

# Load infant population mapping (condition-based onset age)
@st.cache_data
def load_age_mapping():
    try:
        with open("infant_mapping.json", "r") as f:
            return json.load(f)
    except:
        return {}

age_map = load_age_mapping()

# Helper function: assess infant inclusion criteria
def assess_infant_inclusion(text, condition):
    if pd.isna(text):
        text_lower = ""
    else:
        text_lower = text.lower()

    # Patterns indicating inclusion of infants
    include_patterns = [
        r"(from|starting at|age)\s*0",
        r"(from|starting at)\s*birth",
        r"newborn",
        r"infants?",
        r"less than 2 years",
        r"up to 2 years",
        r"0[-\s]*2 years",
        r"0[-\s]*24 months",
        r"from 1 year",
        r"from 12 months"
    ]
    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    # Likely to include infants if inclusion criteria mention age 2 years / 24 months
    likely_patterns = [
        r"(from|starting at|age)\s*2\s*(years|yrs)",
        r"(from|starting at|age)\s*24\s*months?"
    ]
    for pattern in likely_patterns:
        if re.search(pattern, text_lower):
            return "Likely to include infants"

    # Explicit exclusion of infants
    exclude_terms = [
        "does not include infants",
        "excludes infants",
        "not include infants",
        "adults only",
        "children older than 2 years",
        "age 3 years and above"
    ]
    for term in exclude_terms:
        if term in text_lower:
            return "Does not include infants"

    # Condition-based onset age override
    onset = age_map.get(condition, "").lower()
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-24 months"]):
        return "Include infants"
    elif any(x in onset for x in ["toddler", "child", "3 years", "4 years"]):
        return "Likely to include infants"

    # If only upper bound mentioned without lower bound
    upper_only_pattern = re.compile(r"up to\s*\d+\s*(years|yrs)")
    if upper_only_pattern.search(text_lower):
        return "Uncertain"

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

# Function to assess Cell/Gene Therapy Relevance based on keywords in text and Google search fallback
def assess_cgt_relevance(text, condition):
    if pd.isna(text):
        text = ""
    text_lower = text.lower()
    cgt_keywords = [
        "cell therapy",
        "gene therapy",
        "crispr-cas9 system",
        "talen",
        "zfn",
        "gene editing",
        "gene correction",
        "gene silencing",
        "reprogramming",
        "cgt",
        "c&gt",
        "car-t therapy"
    ]
    for kw in cgt_keywords:
        if kw in text_lower:
            return "Relevant"

    # Google search fallback (API-free via requests + regex)
    try:
        search_url = f"https://www.google.com/search?q={condition}+gene+therapy"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(search_url, headers=headers, timeout=10)
        search_text = r.text.lower()
        for kw in cgt_keywords:
            if kw in search_text:
                print(f"✅ Found C&GT keyword via Google search: {kw}")
                return "Relevant"
    except Exception as e:
        print(f"⚠️ Google search error for {condition}: {e}")

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

        # Aggregate study text fields for analysis
        study_texts = " ".join([
            str(record.get("Population (use drop down list)", "")),
            str(record.get("Conditions", "")),
            str(record.get("Study Title", "")),
            str(record.get("Brief Summary", ""))
        ])

        # Assess infant inclusion with condition-based override
        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested Infant Inclusion: **{suggested_infant}**")

        # Assess C&GT relevance from text and Google search
        suggested_cgt = assess_cgt_relevance(study_texts, condition)
        st.caption(f"🧬 Suggested Cell/Gene Therapy Relevance: **{suggested_cgt}**")

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

        if st.button("💾 Save This Record"):
            df_filtered.at[record_index, "contact information"] = email
            df_filtered.at[record_index, "Population (use drop down list)"] = pop_choice if pop_choice != "Uncertain" else suggested_infant
            df_filtered.at[record_index, "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            df_filtered.at[record_index, "Relevance to C&GT"] = cg_choice if cg_choice != "Unsure" else suggested_cgt
            st.success("✅ Record updated.")

        if st.button("📤 Export Updated Excel"):
            df.update(df_filtered)
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
