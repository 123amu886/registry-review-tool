import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re

st.set_page_config(page_title="Clinical Registry Review", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Integrated Version)")

# ✅ Embedded CGT mapping from your approved products, pipeline, and preclinical lists
cgt_map = {
    # Approved therapies (Relevant)
    "rpe65 mutation retinal dystrophy": "Relevant",
    "spinal muscular atrophy": "Relevant",
    "hemophilia a": "Relevant",
    "duchenne muscular dystrophy": "Relevant",
    "cerebral adrenoleukodystrophy": "Relevant",
    "beta-thalassemia": "Relevant",
    "multiple myeloma": "Relevant",
    "b-all": "Relevant",
    "dlbcl": "Relevant",
    "mantle cell lymphoma": "Relevant",
    "large b-cell lymphoma": "Relevant",
    "prostate cancer": "Relevant",
    "perianal fistula crohn's disease": "Relevant",
    # Phase I-III pipeline (Likely Relevant)
    "hemophilia b": "Likely Relevant",
    "sickle cell disease": "Likely Relevant",
    "metastatic prostate cancer": "Likely Relevant",
    "b-cell malignancies": "Likely Relevant",
    "various solid tumors": "Likely Relevant",
    # Preclinical (Likely Relevant)
    "type 1 diabetes": "Likely Relevant",
    "hereditary angioedema": "Likely Relevant",
}

# Helper function: assess CGT relevance and provide study links
def assess_cgt_relevance_and_links(text, condition):
    links = []
    if pd.isna(text):
        text = ""
    text_lower = text.lower()
    condition_lower = condition.lower()

    # Primary: check mapping
    relevance = cgt_map.get(condition_lower, None)
    if relevance:
        if relevance in ["Relevant", "Likely Relevant"]:
            # ClinicalTrials.gov and Scholar links
            ct_url = f"https://clinicaltrials.gov/ct2/results?cond={condition}&term=gene+therapy"
            scholar_url = f"https://scholar.google.com/scholar?q={condition}+gene+therapy+preclinical"
            links.extend([ct_url, scholar_url])
        return relevance, links

    # Secondary: fallback to keyword detection
    cgt_keywords = [
        "cell therapy", "gene therapy", "crispr-cas9 system", "talen", "zfn",
        "gene editing", "gene correction", "gene silencing", "reprogramming",
        "cgt", "c&gt", "car-t therapy"
    ]
    if any(kw in text_lower for kw in cgt_keywords):
        relevance = "Likely Relevant"
        ct_url = f"https://clinicaltrials.gov/ct2/results?cond={condition}&term=gene+therapy"
        scholar_url = f"https://scholar.google.com/scholar?q={condition}+gene+therapy+preclinical"
        links.extend([ct_url, scholar_url])
    else:
        relevance = "Unlikely Relevant"

    return relevance, links

# Load uploaded file and persist with session_state
uploaded_file = st.file_uploader("📂 Upload your registry Excel file", type=["xlsx"])

if uploaded_file:
    if "df" not in st.session_state:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        st.session_state.df = df.copy()
    else:
        df = st.session_state.df

    reviewer_name = st.text_input("Enter your name (Column F)", "Reseum")
    df_filtered = df[df["Reviewer"].str.strip().str.lower() == reviewer_name.strip().lower()].copy()

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

        study_texts = " ".join([
            str(record.get("Population (use drop down list)", "")),
            str(record.get("Conditions", "")),
            str(record.get("Study Title", "")),
            str(record.get("Brief Summary", ""))
        ])

        # Assess CGT relevance and provide links
        suggested_cgt, study_links = assess_cgt_relevance_and_links(study_texts, condition)
        st.caption(f"🧬 Suggested Cell/Gene Therapy Relevance: **{suggested_cgt}**")

        if study_links:
            st.markdown("🔗 **Related Preclinical/Clinical Study Links:**")
            for link in study_links:
                st.markdown(f"- [{link}]({link})")

        # Contact email extraction
        def extract_email(url):
            try:
                r = requests.get(url, timeout=8)
                soup = BeautifulSoup(r.text, 'html.parser')
                mail = soup.select_one("a[href^=mailto]")
                if mail:
                    return mail['href'].replace('mailto:', '')
                else:
                    matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}", soup.get_text())
                    if matches:
                        return matches[0]
                return ""
            except Exception as e:
                print(f"⚠️ Error fetching {url}: {e}")
                return ""

        email = st.text_input("📧 Contact Email (Column E)", extract_email(record["Web site"]))

        # Reviewer inputs
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
            original_index = df_filtered.index[record_index]
            df.at[original_index, "contact information"] = email
            df.at[original_index, "Population (use drop down list)"] = pop_choice
            df.at[original_index, "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            df.at[original_index, "Relevance to C&GT"] = cg_choice if cg_choice != "Unsure" else suggested_cgt

            st.session_state.df = df
            st.success("✅ Record updated and saved.")

        if st.button("📤 Export Updated Excel"):
            st.session_state.df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
