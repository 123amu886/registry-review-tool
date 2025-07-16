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
    with open("merged_cgt_mapping.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_approved_cgt():
    with open("approved_cgt.json", "r") as f:
        return json.load(f)

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()
approved_cgt_list = load_approved_cgt()

# Transform approved_cgt_list to dict by condition (lowercase)
approved_cgt_map = {}
for item in approved_cgt_list:
    cond = item["condition"].lower()
    approved_cgt_map.setdefault(cond, []).append(item)

# -------------------------------
# 2. Infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    if not text:
        return "Uncertain"
    
    text_lower = text.lower()

    include_patterns = [
        r"(from|starting at|age)\s*0",
        r"(from|starting at)\s*birth",
        r"newborn",
        r"infants?",
        r"less than\s*(12|18|24|36)\s*months",
        r"<\s*(12|18|24|36)\s*months",
        r"<\s*(1|2|3)\s*years?",
        r"up to\s*(12|18|24|36)\s*months",
        r"up to\s*(1|2|3)\s*years",
        r"0[-\s]*2\s*years",
        r"0[-\s]*24\s*months",
        r"^0\s*-\s*\d+\s*years",
        r"0\s*to\s*\d+\s*years"
    ]

    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    # Extract age ranges: e.g. "0 to 17 years", "1-50 years"
    age_ranges = re.findall(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(months|years?)", text_lower)
    for low_str, high_str, unit in age_ranges:
        low = int(low_str)
        high = int(high_str)
        if 'month' in unit:
            low_years = low / 12
            high_years = high / 12
        else:
            low_years = low
            high_years = high

        if 0 <= low_years <= 2:
            return "Include infants"
        elif low_years > 2:
            return "Does not include infants"

    onset = age_map.get(condition.lower(), "").lower() if condition else ""
    if onset:
        if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
            return "Likely to include infants"
        if any(x in onset for x in ["toddler", "child", "3 years", "4 years"]):
            return "Unlikely to include infants but possible"
        if any(x in onset for x in ["adolescent", "adult", "teen"]):
            return "Does not include infants"

    return "Uncertain"

# -------------------------------
# 3. ClinicalTrials.gov API with contacts and locations
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
# 4. CGT relevance logic including approved CGT links
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    condition_lower = condition.lower()

    relevance = cgt_map.get(condition_lower, None)
    found_study = False

    studies = check_clinicaltrials_gov(condition)
    if studies:
        found_study = True
        links.extend(studies)

    # Add approved CGT info for condition
    approved_items = approved_cgt_map.get(condition_lower, [])
    for item in approved_items:
        approved_link = f"https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/{item['approved_product'].lower().replace(' ', '-')}"
        links.append({
            "title": f"Approved CGT: {item['approved_product']} ({item['agency']} {item['approval_year']})",
            "link": approved_link,
            "phase": "Approved",
            "status": "Approved",
            "contacts": [],
            "locations": []
        })

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
# 5. Contact email scraper
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
# 6. Streamlit app flow
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
