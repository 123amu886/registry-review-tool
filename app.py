import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="🧾 Clinical Registry Review Tool (Final Integrated)", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Integrated)")

# -------------------------------
# 1. Load JSON mapping files
# -------------------------------
@st.cache_data
def load_cgt_mapping():
    with open("merged_cgt_mapping.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

# FIXED: Load approved_cgt.json which is a list, convert to dict keyed by lowercase condition
@st.cache_data
def load_approved_cgt():
    with open("approved_cgt.json", "r") as f:
        data = json.load(f)  # list of dicts
    approved_dict = {}
    for entry in data:
        key = entry.get("condition", "").strip().lower()
        if key:
            approved_dict.setdefault(key, []).append(entry)
    return approved_dict

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()
approved_cgt_map = load_approved_cgt()

# -------------------------------
# 3. Infant inclusion logic (example)
# (Your existing code here, unchanged)
# -------------------------------

# -------------------------------
# 5. CGT relevance logic with approved CGT lookup fix
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    condition_lower = condition.lower()

    # Lookup approved CGT products for this condition
    approved_info = approved_cgt_map.get(condition_lower, [])
    
    if approved_info:
        # Add approved products as links/info
        for prod in approved_info:
            title = f"Approved Product: {prod['approved_product']} ({prod['agency']}, {prod['approval_year']})"
            # Example: you can link to FDA or EMA sites if you have URLs, else leave link empty or generic
            link = f"https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/{prod['approved_product'].replace(' ','-')}"
            links.append({
                "title": title,
                "link": link,
                "phase": "Approved",
                "status": "Approved",
                "contacts": [],
                "locations": []
            })

    relevance = cgt_map.get(condition_lower, None)
    found_study = False

    # Existing check for clinicaltrials.gov studies
    studies = check_clinicaltrials_gov(condition)
    if studies:
        found_study = True
        links.extend(studies)

    cgt_keywords = ["cell therapy", "gene therapy", "crispr", "talen", "zfn",
                    "gene editing", "gene correction", "gene silencing", "reprogramming",
                    "cgt", "c&gt", "car-t therapy"]
    text_lower = text.lower() if pd.notna(text) else ""

    if relevance in ["Relevant", "Likely Relevant"] and found_study:
        pass
    elif any(k in text_lower for k in cgt_keywords):
        relevance = "Likely Relevant"
    else:
        relevance = "Unsure"

    # Google & PubMed search links for more info
    google_query = f"https://www.google.com/search?q=is+there+a+gene+therapy+for+{condition.replace(' ','+')}"
    links.append({
        "title": "Google Search: Is there a gene therapy for this condition?",
        "link": google_query,
        "phase": "N/A",
        "status": "N/A",
        "contacts": [],
        "locations": []
    })

    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ','+')}+gene+therapy"
    links.append({
        "title": "PubMed Search",
        "link": pubmed_url,
        "phase": "N/A",
        "status": "N/A",
        "contacts": [],
        "locations": []
    })

    return relevance, links

# -------------------------------
# 6. Your existing ClinicalTrials.gov API, email extraction, infant inclusion logic, etc.
# -------------------------------

# -------------------------------
# 7. Streamlit UI code: file uploader, reviewer inputs, displaying suggested infant inclusion,
# CGT relevance, study links, save and export buttons, etc.
# -------------------------------

# (Keep your existing full app code here, unchanged except for imports and the new approved_cgt_map loading.)

# Example usage in your main flow (inside your Streamlit app logic):

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

        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested: **{suggested_infant}**")

        suggested_cgt, study_links = assess_cgt_relevance_and_links(study_texts, condition)
        st.caption(f"🧬 Suggested: **{suggested_cgt}**")

        if study_links:
            st.markdown("🔗 **Related Studies & Database Links:**")
            for s in study_links:
                st.markdown(f"- **{s['title']}** (Phase: {s['phase']}, Status: {s['status']}) [View Study]({s['link']})")
                if s['contacts']:
                    st.markdown(f"  **Contacts:** {', '.join(s['contacts'])}")
                if s['locations']:
                    st.markdown(f"  **Locations:** {', '.join(s['locations'])}")

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
            st.session_state.df = df.copy()
            st.success("✅ Record saved successfully!")

        if st.button("⬇️ Export Updated Excel"):
            output_filename = "updated_registry_review.xlsx"
            df.to_excel(output_filename, index=False)
            with open(output_filename, "rb") as f:
                st.download_button(
                    label="⬇️ Download Updated Registry",
                    data=f,
                    file_name=output_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
