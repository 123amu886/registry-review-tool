import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import re

st.set_page_config(page_title="Clinical Registry Review", layout="wide")
st.title("🧾 Enhanced Clinical Registry Review Tool (Revised Inclusion Logic)")

# Load infant population mapping
@st.cache_data
def load_age_mapping():
    try:
        with open("infant_mapping.json", "r") as f:
            return json.load(f)
    except:
        return {}

age_map = load_age_mapping()

# Helper function: assess infant inclusion criteria
def assess_infant_inclusion(text):
    if pd.isna(text):
        return "Uncertain"
    text_lower = text.lower()

    # Include infants if explicit terms are present
    include_terms = [
        "up to 2 years",
        "from 0-24 months",
        "from 0-2 years"
    ]
    for term in include_terms:
        if term in text_lower:
            return "Include infants"

    # Likely to include infants if inclusion criteria mention age 0, 1 year, 2 years, 12 months, 24 months
    likely_patterns = [
        r"(from|starting at|age)\s*0",
        r"(from|starting at|age)\s*1\s*(year|yr)",
        r"(from|starting at|age)\s*2\s*(years|yrs)",
        r"(from|starting at|age)\s*12\s*months?",
        r"(from|starting at|age)\s*24\s*months?"
    ]
    for pattern in likely_patterns:
        if re.search(pattern, text_lower):
            return "Likely to include infants"

    # Does not include infants if exclusion stated
    exclude_terms = [
        "does not include infants",
        "excludes infants",
        "not include infants"
    ]
    for term in exclude_terms:
        if term in text_lower:
            return "Does not include infants"

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

# Function to assess Cell/Gene Therapy Relevance based on keywords in text and Google search fallback
def assess_cgt_relevance(text, condition):
    if pd.isna(text):
        text = ""
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

        # Assess infant inclusion
        suggested_infant = assess_infant_inclusion(study_texts)
        st.caption(f"🧒 Suggested Infant Inclusion: **{suggested_infant}**")

        # If age_map has condition-based mapping, override Uncertain
        condition_based =_
