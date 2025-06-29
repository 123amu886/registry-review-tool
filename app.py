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
    except
