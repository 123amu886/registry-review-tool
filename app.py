import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final with FDA, Pipeline, ClinicalTrials, Google/PubMed Links)")

# -------------------------------
# 1. Load CGT and Infant mappings
# -------------------------------
@st.cache_data
def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)

cgt_map = load_json("cgt_mapping.json")
age_map = load_json("infant_mapping.json")

# -------------------------------
# 2. Load FDA approved therapies + optional pipeline Phase I data
# -------------------------------
@st.cache_data
def load_fda_and_pipeline():
    therapies = {}
    url = "https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/approved-cellular-and-gene-therapy-products"
    r = requests.get(url, timeout=10)
    soup = BeautifulSoup(r.text, 'html.parser')
    table = soup.find("table")
    if table:
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 4:
                therapy_name = cols[0].get_text(strip=True).lower()
                indication = cols[1].get_text(strip=True).lower()
                sponsor = cols[2].get_text(strip=True)
                approval_date = cols[3].get_text(strip=True)
                therapy_type = "gene or cell therapy"
                if "car-t" in therapy_name or "car t" in indication:
                    therapy_type = "CAR-T cell therapy"
                elif "gene therapy" in indication or "gene therapy" in therapy_name:
                    therapy_type = "Gene therapy"
                therapies[therapy_name] = {
                    "condition": indication,
                    "approval_status": "FDA approved",
                    "type": therapy_type,
                    "developer": sponsor,
                    "approval_date": approval_date,
                    "age_group": "unknown"
                }
    try:
        pipeline_df = pd.read_csv('pipeline_phase1.csv')
        for _, row in pipeline_df.iterrows():
            therapies[row['therapy_name'].lower()] = {
                "condition": row['condition'].lower(),
                "approval_status": row['phase'],
                "type": row['therapy_type'],
                "developer": row['developer'],
                "approval_date": "N/A",
                "age_group": row.get('age_group', 'unknown')
            }
    except Exception as e:
        print(f"⚠️ Pipeline CSV integration skipped or errored: {e}")
    return therapies

fda_approved_map = load_fda_and_pipeline()

# -------------------------------
# 3. Infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    include_patterns = [r"from\s*0", r"starting at birth", r"newborn", r"infants?", r"less than\s*(12|18|24)\s*months?", r"<\s*(12|18|24)\s*months?", r"<\s*(1|2)\s*years?", r"up to\s*18\s*months?", r"up to\s*2\s*years?", r"0[-\s]*2\s*years?", r"0[-\s]*24\s*months?", r"from\s*1\s*year", r"from\s*12\s*months", r">\s*12\s*months", r">\s*18\s*months", r">\s*1\s*year"]
    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"
    if "up to" in text_lower:
        return "Likely to include infants"
    likely_patterns = [r"0\s*to", r"6\s*months?\s*to", r"12\s*months?\s*to", r"1\s*year\s*to", r"18\s*months?\s*to"]
    for pattern in likely_patterns:
        if re.search(pattern, text_lower):
            return "Likely to include infants"
    over_two_years = re.search(r"(>\s*2\s*years?|>\s*24\s*months?)", text_lower)
    age_3_or_more = re.search(r"(from|starting at|minimum age)\s*(3|4|5|\d{2,})\s*(years?)", text_lower)
    if over_two_years or age_3_or_more:
        return "Does not include infants"
    return "Does not include infants"

# -------------------------------
# 4. ClinicalTrials.gov API check
# -------------------------------
def check_clinicaltrials_gov(condition):
    try:
        search_url = "https://clinicaltrials.gov/a
