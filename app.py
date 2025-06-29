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
        "0-2
