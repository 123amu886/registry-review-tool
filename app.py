import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Refined)")

# -------------------------------
# Load mappings
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
# Age extraction helper
# -------------------------------
def extract_ages(text):
    min_age, max_age = None, None

    min_patterns = [
        r"minimum age\s*[:=]?\s*(\d+)\s*(year|month)s?",
        r"age\s*[>≥]\s*(\d+)\s*(year|month)s?",
        r"from\s*(\d+)\s*(year|month)s?",
        r"(\d+)\s*(year|month)s?\s*and older",
        r"starting at\s*(\d+)\s*(year|month)s?"
    ]

    max_patterns = [
        r"up to\s*(\d+)\s*(year|month)s?",
        r"<\s*(\d+)\s*(year|month)s?",
        r"less than\s*(\d+)\s*(year|month)s?"
    ]

    for pattern in min_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            val, unit = int(match.group(1)), match.group(2).lower()
            months = val * 12 if unit.startswith("year") else val
            if min_age is None or months < min_age:
                min_age = months

    for pattern in max_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            val, unit = int(match.group(1)), match.group(2).lower()
            months = val * 12 if unit.startswith("year") else val
            if max_age is None or months > max_age:
                max_age = months

    return min_age, max_age

# -------------------------------
# Infant inclusion assessment
# -------------------------------
def assess_infant_inclusion(text, condition, age_map):
    text_lower = text.lower() if text else ""
    min_age, max_age = extract_ages(text_lower)

    # Explicit exclusions
    if any(re.search(p, text_lower) for p in [r"no infants", r"excluding infants", r"infants excluded", r"does not include infants"]):
        return "Does not include infants"

    # Include infants
    if any(re.search(p, text_lower) for p in [r"0-2 years", r"0-24 months", r"starting from 0", r"starting at birth", r"newborn"]):
        return "Include infants"
    if min_age is not None and min_age <= 24:
        return "Include infants"

    # Likely to include infants by mapping or “up to” logic
    onset = age_map.get(condition.lower(), "").lower()
    if any(term in onset for term in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
        return "Likely to include infants"
    if "up to" in text_lower and (min_age is None or min_age <= 18):
        return "Likely to include infants"

    # Unlikely but possible
    if min_age == 24:
        return "Unlikely to include infants but possible"

    # Does not include infants
    if min_age is not None and min_age > 24:
        return "Does not include infants"

    # Uncertain
    return "Uncertain"

# -------------------------------
# CGT relevance check
# -------------------------------
def assess_cgt_relevance(condition):
    condition_lower = condition.lower()
    relevance = cgt_map.get(condition_lower, "Unsure")
    if relevance in ["Relevant", "Likely Relevant"]:
        return relevance
    query = f"is there a gene therapy for {condition}"
    return f"Check Google: https://www.google.com/search?q={query.replace(' ', '+')}"

# -------------------------------
# Contact email scraper
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
# Streamlit app flow
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

        suggested_infant = assess_infant_inclusion(study_texts, condition, age_map)
        st.caption(f"🧒 Suggested infant inclusion: **{suggested_infant}**")

        suggested_cgt = assess_cgt_relevance(condition)
        st.caption(f"🧬 Suggested CGT relevance: **{suggested_cgt}**")

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
