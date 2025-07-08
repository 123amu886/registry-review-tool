import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final)")

# -------------------------------
# Load mapping files
# -------------------------------
@st.cache_data
def load_cgt_mapping():
    with open("fda_approved_gene_therapies.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()

# -------------------------------
# Function to extract contacts and locations by NCT ID
# -------------------------------
def extract_ctgov_contacts_locations(nct_id):
    try:
        detail_url = "https://clinicaltrials.gov/api/query/full_studies"
        detail_params = {"expr": nct_id, "fmt": "json"}
        detail_r = requests.get(detail_url, params=detail_params, timeout=10)
        detail_data = detail_r.json()

        contacts = []
        locations = []

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

        return contacts, locations

    except Exception as e:
        print(f"⚠️ Contact/location parsing error for {nct_id}: {e}")
        return ["No contact data found."], ["No location data found."]

# -------------------------------
# Infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""

    include_patterns = [
        r"from\s*0", r"starting at birth", r"newborn", r"infants?",
        r"less than\s*(12|18|24)\s*months", r"<\s*(12|18|24)\s*months",
        r"<\s*(1|2)\s*years?", r"up to\s*18\s*months", r"up to\s*2\s*years",
        r"0[-\s]*2\s*years", r"0[-\s]*24\s*months", r"from\s*1\s*year",
        r"from\s*12\s*months", r">\s*12\s*months", r">\s*18\s*months", r">\s*1\s*year"
    ]

    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    if any(phrase in text_lower for phrase in ["from 0", "from 6 months", "from 1 year", "from 12 months", "up to"]):
        return "Likely to include infants"

    age_months_match = re.search(r"(\d+)\s*(month|months)", text_lower)
    if age_months_match:
        min_age_months = int(age_months_match.group(1))
        if min_age_months == 24:
            return "Unlikely to include infants but possible"
        elif min_age_months > 24:
            return "Does not include infants"

    age_years_match = re.search(r"(\d+)\s*(year|years)", text_lower)
    if age_years_match:
        min_age_years = int(age_years_match.group(1))
        if min_age_years == 2:
            return "Unlikely to include infants but possible"
        elif min_age_years >= 3:
            return "Does not include infants"

    onset = age_map.get(condition.lower(), "").lower()
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
        return "Likely to include infants"
    if any(x in onset for x in ["toddler", "child", "3 years", "4 years"]):
        return "Unlikely to include infants but possible"

    return "Uncertain"

# -------------------------------
# Streamlit app flow
# -------------------------------
uploaded_file = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")
    st.session_state.df = df.copy()

    st.subheader("🔍 Extracting ClinicalTrials.gov Contacts and Locations")
    if "NCT number" in df.columns:
        nct_ids = df["NCT number"].dropna().unique()
        ct_contacts = []
        ct_locations = []

        for nct in nct_ids:
            contacts, locations = extract_ctgov_contacts_locations(nct)
            ct_contacts.append("; ".join(contacts))
            ct_locations.append("; ".join(locations))

        df["CT_Contacts"] = ct_contacts
        df["CT_Locations"] = ct_locations
        st.success(f"✅ Extracted contacts and locations for {len(nct_ids)} studies.")

    else:
        st.error("❌ 'NCT number' column not found in your Excel. Please check column naming.")

    if st.button("⬇️ Export Updated Excel"):
        df.to_excel("updated_registry_review_with_contacts.xlsx", index=False)
        with open("updated_registry_review_with_contacts.xlsx", "rb") as f:
            st.download_button("⬇️ Download File", f, file_name="updated_registry_review_with_contacts.xlsx")
