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

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()

# -------------------------------
# Infant inclusion logic helpers
# -------------------------------
def extract_ages(text):
    """
    Extract min and max age (in months) from text.
    Returns tuple (min_age_months, max_age_months), either can be None if not found.
    """
    min_age = None
    max_age = None

    # Patterns for min age (e.g. "minimum age 14 years", "age >= 2 years", "from 6 months", "14 years and older")
    min_patterns = [
        r"minimum age\s*[:=]?\s*(\d+)\s*(year|month)s?",
        r"age\s*[>≥]\s*(\d+)\s*(year|month)s?",
        r"from\s*(\d+)\s*(year|month)s?",
        r"(\d+)\s*(year|month)s?\s*and older",
        r"starting at\s*(\d+)\s*(year|month)s?"
    ]

    # Patterns for max age (e.g. "up to 18 months", "< 2 years", "less than 24 months")
    max_patterns = [
        r"up to\s*(\d+)\s*(year|month)s?",
        r"<\s*(\d+)\s*(year|month)s?",
        r"less than\s*(\d+)\s*(year|month)s?"
    ]

    for pattern in min_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            val, unit = int(match.group(1)), match.group(2).lower()
            months = val * 12 if unit.startswith("year") else val
            if (min_age is None) or (months < min_age):
                min_age = months

    for pattern in max_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            val, unit = int(match.group(1)), match.group(2).lower()
            months = val * 12 if unit.startswith("year") else val
            if (max_age is None) or (months > max_age):
                max_age = months

    return min_age, max_age

def assess_infant_inclusion(text, condition, age_map):
    """
    Determines infant inclusion category based on eligibility text and condition.
    """

    text_lower = text.lower() if text else ""

    # Check explicit exclusions first
    exclusion_phrases = [
        r"no infants",
        r"excluding infants",
        r"infants excluded",
        r"does not include infants"
    ]
    if any(re.search(p, text_lower) for p in exclusion_phrases):
        return "Does not include infants"

    min_age, max_age = extract_ages(text_lower)

    # Direct infant inclusion phrases
    infant_phrases = [
        r"\bfrom 0\b",
        r"starting at birth",
        r"newborn",
        r"\binfants?\b",
        r"less than (12|18|24) months",
        r"<(12|18|24) months",
        r"<(1|2) years",
        r"up to 18 months",
        r"up to 2 years",
        r"0[-\s]*2 years",
        r"0[-\s]*18 months",
        r"0[-\s]*24 months",
        r"from 1 year",
        r"from 12 months",
        r"\b12 months\b",
        r"\b18 months\b",
        r"\b1 year\b"
    ]

    # If any infant phrase AND min age ≤ 18 months or unknown min age
    if any(re.search(p, text_lower) for p in infant_phrases):
        if min_age is None or min_age <= 18:
            return "Include infants"

    # If "up to" present and min age unknown or ≤ 18 months -> Likely include infants
    if "up to" in text_lower:
        if min_age is None or min_age <= 18:
            return "Likely to include infants"

    # Use onset info for likely inclusion
    onset = age_map.get(condition.lower(), "").lower() if age_map else ""
    likely_terms = ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]
    if any(term in onset for term in likely_terms):
        return "Likely to include infants"

    # Unlikely if min age == 24 months (2 years)
    if min_age == 24:
        return "Unlikely to include infants but possible"

    # Does not include if min age > 24 months
    if min_age is not None and min_age > 24:
        return "Does not include infants"

    # Otherwise, uncertain
    return "Uncertain"

# -------------------------------
# ClinicalTrials.gov API with contacts and locations
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

            detail_url = "https://clinicaltrials.gov/api/query/full_studies"
            detail_params = {"expr": nct_id, "fmt": "json"}
            detail_r = requests.get(detail_url, params=detail_params, timeout=10)
            detail_data = detail_r.json()

            contacts = []
            locations = []

            try:
                full_study = detail_data['FullStudiesResponse']['FullStudies'][0]['Study']
                protocol_section = full_study.get('ProtocolSection', {})
                contacts_module = protocol_section.get('ContactsLocationsModule', {})

                overall_officials = contacts_module.get('OverallOfficialList', {}).get('OverallOfficial', [])
                for contact in overall_officials:
                    name = contact.get('LastName', 'N/A')
                    role = contact.get('Role', 'N/A')
                    contacts.append(f"{name} ({role})")

                location_list = contacts_module.get('LocationList', {}).get('Location', [])
                for loc in location_list:
                    facility = loc.get('LocationFacility', 'N/A')
                    city = loc.get('LocationCity', 'N/A')
                    country = loc.get('LocationCountry', 'N/A')
                    locations.append(f"{facility}, {city}, {country}")

            except Exception as e:
                print(f"⚠️ Detail parsing error for {nct_id}: {e}")
                contacts = ["No contact data found."]
                locations = ["No location data found."]

            study_info.append({
                "nct_id": nct_id,
                "title": title,
                "phase": phase,
                "status": status,
                "link": ct_link,
                "contacts": contacts,
                "locations": locations
            })

        return study_info

    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov API error for {condition}: {e}")
        return []

# -------------------------------
# CGT relevance check (fixed)
# -------------------------------
def assess_cgt_relevance(condition):
    condition_lower = condition.lower()
    relevance = cgt_map.get(condition_lower, "Unsure")  # now directly get string value
    if relevance in ["Relevant", "Likely Relevant"]:
        return relevance

    # fallback: Google search link
    query = f"is there a gene therapy for {condition}"
    google_search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    return f"Check Google: {google_search_url}"

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
