import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

# -------------------------------
# Page setup
# -------------------------------
st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Integrated)")

# -------------------------------
# Load mapping files
# -------------------------------
@st.cache_data
def load_fda_mapping():
    with open("fda_approved_gene_therapies.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

fda_map = load_fda_mapping()
age_map = load_age_mapping()

# -------------------------------
# 1. Extract ClinicalTrials.gov contacts & locations
# -------------------------------
def extract_ctgov_contacts_locations(nct_id):
    try:
        detail_url = "https://clinicaltrials.gov/api/query/full_studies"
        params = {"expr": nct_id, "fmt": "json"}
        r = requests.get(detail_url, params=params, timeout=10)
        data = r.json()

        contacts, locations = [], []

        full_study = data['FullStudiesResponse']['FullStudies'][0]['Study']
        protocol = full_study.get('ProtocolSection', {})
        contacts_module = protocol.get('ContactsLocationsModule', {})

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
        print(f"⚠️ Contact/location error for {nct_id}: {e}")
        return ["No contact data found."], ["No location data found."]

# -------------------------------
# 2. Assess infant inclusion
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
# 3. Check ClinicalTrials.gov for active trials
# -------------------------------
def check_clinicaltrials_gov(condition):
    try:
        url = "https://clinicaltrials.gov/api/query/study_fields"
        params = {
            "expr": f"{condition} gene therapy",
            "fields": "NCTId,BriefTitle,Phase,OverallStatus",
            "min_rnk": 1,
            "max_rnk": 3,
            "fmt": "json"
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        studies = data['StudyFieldsResponse']['StudyFields']

        study_info = []
        for s in studies:
            study_info.append({
                "nct_id": s["NCTId"][0],
                "title": s["BriefTitle"][0],
                "phase": s.get("Phase", ["N/A"])[0],
                "status": s.get("OverallStatus", ["N/A"])[0],
                "link": f"https://clinicaltrials.gov/ct2/show/{s['NCTId'][0]}"
            })
        return study_info

    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov error for {condition}: {e}")
        return []

# -------------------------------
# 4. Check preclinical PubMed data
# -------------------------------
def check_preclinical_pubmed(condition):
    try:
        query = f"{condition} gene therapy preclinical OR animal model OR in vitro"
        url = f"https://pubmed.ncbi.nlm.nih.gov/?term={query.replace(' ', '+')}"
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for article in soup.select('.docsum-content'):
            title = article.select_one('.docsum-title').get_text(strip=True)
            link = "https://pubmed.ncbi.nlm.nih.gov" + article.select_one('.docsum-title')['href']
            results.append({"title": title, "link": link})

        return results if results else None

    except Exception as e:
        print(f"⚠️ PubMed preclinical error for {condition}: {e}")
        return None

# -------------------------------
# 5. Assess CGT relevance
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    condition_lower = condition.lower()

    # A. FDA approved therapies
    for therapy, data in fda_map.items():
        if condition_lower in data['condition'].lower():
            links.append({
                "title": f"{therapy.capitalize()} (FDA Approved)",
                "link": f"https://www.google.com/search?q={therapy}+{condition.replace(' ','+')}",
                "phase": "Approved",
                "status": "FDA approved"
            })
            return "Relevant (FDA Approved)", links

    # B. ClinicalTrials.gov
    studies = check_clinicaltrials_gov(condition)
    if studies:
        links.extend(studies)
        return "Relevant (Clinical Trials)", links

    # C. Preclinical pipeline
    preclinical_results = check_preclinical_pubmed(condition)
    if preclinical_results:
        links.extend(preclinical_results)
        return "Likely Relevant (Preclinical)", links

    # D. Keyword-based fallback
    cgt_keywords = ["cell therapy", "gene therapy", "crispr", "talen", "zfn",
                    "gene editing", "gene correction", "gene silencing", "reprogramming",
                    "cgt", "c&gt", "car-t therapy"]
    text_lower = text.lower() if pd.notna(text) else ""
    if any(k in text_lower for k in cgt_keywords):
        return "Likely Relevant", links

    # E. Google fallback
    google_query = f"https://www.google.com/search?q=is+there+a+gene+therapy+for+{condition.replace(' ','+')}"
    links.append({"title": "Google Search: Is there a gene therapy for this condition?", "link": google_query})
    return "Unsure", links

# -------------------------------
# 6. Streamlit App Flow
# -------------------------------
uploaded_file = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")
    df.columns = [col.lower() for col in df.columns]
    nct_col = next((col for col in df.columns if "nct" in col), None)

    if nct_col:
        contacts_all, locations_all = [], []
        for nct_id in df[nct_col].dropna():
            contacts, locations = extract_ctgov_contacts_locations(nct_id)
            contacts_all.append("; ".join(contacts))
            locations_all.append("; ".join(locations))

        df["CT_Contacts"] = contacts_all
        df["CT_Locations"] = locations_all
        st.success(f"✅ Extracted contacts & locations for {len(df[nct_col].dropna())} studies.")

    else:
        st.error("❌ NCT ID column not found in your Excel. Please check column naming.")

    # Save updated file
    if st.button("⬇️ Export Updated Excel"):
        df.to_excel("updated_registry_review_with_contacts.xlsx", index=False)
        with open("updated_registry_review_with_contacts.xlsx", "rb") as f:
            st.download_button("⬇️ Download File", f, file_name="updated_registry_review_with_contacts.xlsx")
