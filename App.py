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

# Email extractor
def extract_email(url):
    try:
        r = requests.get(url, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        mail = soup.select_one("a[href^=mailto]")
        return mail['href'].replace('mailto:', '') if mail else ""
    except:
        return ""

# ClinicalTrials.gov gene therapy relevance checker
def search_gene_therapy(condition):
    base_url = "https://clinicaltrials.gov/ct2/results"
    try:
        r = requests.get(base_url, params={"cond": condition, "term": "gene therapy"}, timeout=8)
        if "No Studies found" in r.text:
            return "Not Relevant"
        elif re.search(r"\d+\s+Study", r.text):
            return "Relevant"
        else:
            return "Likely Relevant"
    except:
        return "Unsure"

uploaded_file = st.file_uploader("📂 Upload your registry Excel file", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")

    reviewer_name = st.text_input("Enter your name (Column F)", "Reseum")
    df_filtered = df[df["F"] == reviewer_name].copy()

    condition_query = st.text_input("Optional: Filter by condition name (Column D)").strip()
    if condition_query:
        df_filtered = df_filtered[df_filtered["D"].str.contains(condition_query, case=False, na=False)]

    show_incomplete = st.checkbox("Show only incomplete (missing G or I)", value=True)
    if show_incomplete:
        df_filtered = df_filtered[df_filtered["G"].isna() | df_filtered["I"].isna()]

    if df_filtered.empty:
        st.success("🎉 All caught up! No matching rows found.")
    else:
        record_index = st.number_input("Select record", 0, len(df_filtered) - 1, step=1)
        record = df_filtered.iloc[record_index]
        condition = record["D"]

        st.subheader("🔎 Record Details")
        st.markdown(f"**Condition:** `{condition}`")
        st.markdown(f"[📄 Open Registry Link]({record['C']})")

        # Suggested infant inclusion
        suggested_infant = age_map.get(condition, "Uncertain")
        st.caption(f"🧒 Suggested Infant Inclusion: **{suggested_infant}**")

        email = st.text_input("📧 Contact Email (Column E)", extract_email(record["C"]))

        pop_choice = st.radio("🧒 Infant Population (Column G)", [
            "Include infants",
            "Likely to include infants",
            "Unlikely to include infants but possible",
            "Does not include infants",
            "Uncertain"
        ], index=0 if pd.isna(record['G']) else 0)

        comments = st.text_area("🗒 Reviewer Comments (Column H)", value=record.get("H", ""))

        cg_choice = st.radio("🧬 Cell/Gene Therapy Relevance (Column I)", [
            "Relevant",
            "Likely Relevant",
            "Unlikely Relevant",
            "Not Relevant",
            "Unsure"
        ], index=0 if pd.isna(record['I']) else 0)

        if st.button("🔍 Auto-check C&GT relevance from clinicaltrials.gov"):
            cg_auto = search_gene_therapy(condition)
            st.success(f"Gene therapy relevance: **{cg_auto}**")
            cg_choice = cg_auto

        if st.button("💾 Save This Record"):
            df_filtered.at[record_index, "E"] = email
            df_filtered.at[record_index, "G"] = pop_choice
            df_filtered.at[record_index, "H"] = comments
            df_filtered.at[record_index, "I"] = cg_choice
            st.success("✅ Record updated.")

        if st.button("📤 Export Updated Excel"):
            df.update(df_filtered)
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
