import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Integrated with FDA & Pipeline CSV)")

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
    # FDA scraping
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
    # Optional pipeline CSV integration
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
# 3. Infant inclusion logic (any “up to …” phrase = Likely)
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    include_patterns = [
        r"from\s*0", r"starting at birth", r"newborn", r"infants?",
        r"less than\s*(12|18|24)\s*months?", r"<\s*(12|18|24)\s*months?",
        r"<\s*(1|2)\s*years?", r"up to\s*18\s*months?", r"up to\s*2\s*years?",
        r"0[-\s]*2\s*years?", r"0[-\s]*24\s*months?", r"from\s*1\s*year",
        r"from\s*12\s*months", r">\s*12\s*months", r">\s*18\s*months", r">\s*1\s*year"
    ]
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
# 4. FDA approval check
# -------------------------------
def check_fda_approved(condition):
    condition_lower = condition.lower()
    approved_info = []
    for therapy, details in fda_approved_map.items():
        if details["condition"].lower() == condition_lower:
            approved_info.append(details)
    return approved_info

# -------------------------------
# 5. Streamlit app flow
# -------------------------------
uploaded_file = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")
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
        st.markdown(f"**Condition:** `{condition}`")
        suggested_infant = assess_infant_inclusion(" ".join([str(record.get(c, "")) for c in df.columns]), condition)
        st.caption(f"🧒 Suggested: **{suggested_infant}**")
        fda_info = check_fda_approved(condition)
        if fda_info:
            for therapy in fda_info:
                st.markdown(f"✅ **FDA Therapy:** {therapy['type']} by {therapy['developer']} | Status: {therapy['approval_status']}")
        else:
            st.markdown("⚠️ No FDA approved therapy found.")
        pop_choice = st.radio("Infant Population", ["Include infants", "Likely to include infants", "Does not include infants"], index=0)
        cg_choice = st.radio("Cell/Gene Therapy Relevance", ["Relevant", "Likely Relevant", "Unlikely Relevant", "Not Relevant", "Unsure"], index=0)
        comments = st.text_area("Reviewer Comments", value=record.get("Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)", ""))
        if st.button("💾 Save"):
            df.at[df_filtered.index[record_index], "Population (use drop down list)"] = pop_choice
            df.at[df_filtered.index[record_index], "Relevance to C&GT"] = cg_choice
            df.at[df_filtered.index[record_index], "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            st.success("✅ Saved!")
        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")

# ✅ End of final deploy-ready `app.py` for GitHub
# Save this as `app.py` and run with `streamlit run app.py`
# Ensure `pipeline_phase1.csv` is in your working directory for pipeline integration.

# Let me know if you want this packaged with a requirements.txt and deployment YAML next.
