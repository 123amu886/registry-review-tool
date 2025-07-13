import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Updated)")

# -------------------------------
# 1. Load JSON mapping files
# -------------------------------
@st.cache_data
def load_cgt_mapping():
    with open("cgt_mapping.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()

# -------------------------------
# 2. Infant inclusion logic with numeric extraction
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""

    # Extract numeric minimum ages
    age_matches = re.findall(r"(\d+)\s*(month|year)", text_lower)
    min_age_months = None
    if age_matches:
        for age, unit in age_matches:
            age = int(age)
            age_in_months = age if unit.startswith("month") else age * 12
            if min_age_months is None or age_in_months < min_age_months:
                min_age_months = age_in_months

    # Patterns for "Include infants"
    include_patterns = [
        r"from\s*0",
        r"starting at birth",
        r"newborn",
        r"infants?",
        r"less than\s*(12|18|24)\s*months",
        r"<\s*(12|18|24)\s*months",
        r"<\s*(1|2)\s*years?",
        r"up to\s*18\s*months",
        r"up to\s*2\s*years",
        r"0[-\s]*2\s*years",
        r"0[-\s]*24\s*months",
        r"from\s*1\s*year",
        r"from\s*12\s*months",
        r"12\s*months",
        r"18\s*months",
        r"1\s*year"
    ]

    if any(re.search(p, text_lower) for p in include_patterns):
        return "Include infants"

    # Patterns for "Likely to include infants"
    likely_patterns = [
        r"from\s*0",
        r"from\s*6\s*months",
        r"from\s*1\s*year",
        r"from\s*12\s*months",
        r"(up to.*months|up to.*years)"
    ]

    if any(re.search(p, text_lower) for p in likely_patterns):
        return "Likely to include infants"

    # Explicit exclusion
    if re.search(r"(no infants|excluding infants)", text_lower):
        return "Does not include infants"

    # Numeric-based classification
    if min_age_months is not None:
        if min_age_months >= 24:
            if min_age_months == 24:
                return "Unlikely to include infants but possible"
            else:
                return "Does not include infants"

    # Fallback
    return "Uncertain"

# -------------------------------
# 3. CGT relevance logic with mapping and keyword parsing
# -------------------------------
def assess_cgt_relevance(condition, text):
    condition_lower = condition.lower()
    relevance = cgt_map.get(condition_lower, None)

    # If mapping states Relevant or Likely Relevant
    if relevance in ["Relevant", "Likely Relevant"]:
        return relevance

    # Keyword detection in text
    cgt_keywords = ["gene therapy", "cell therapy", "crispr", "car-t", "gene replacement"]
    text_lower = text.lower() if pd.notna(text) else ""

    if any(k in text_lower for k in cgt_keywords):
        return "Likely Relevant"

    return "Unsure"

# -------------------------------
# 4. ClinicalTrials.gov and external links check
# -------------------------------
def check_gene_cell_therapy(condition):
    links = []

    # ClinicalTrials.gov gene therapy trials
    try:
        search_url = "https://clinicaltrials.gov/api/query/study_fields"
        search_params = {
            "expr": f"{condition} gene therapy",
            "fields": "NCTId,BriefTitle,OverallStatus",
            "min_rnk": 1,
            "max_rnk": 3,
            "fmt": "json"
        }
        r = requests.get(search_url, params=search_params, timeout=10)
        data = r.json()
        studies = data['StudyFieldsResponse']['StudyFields']
        if studies:
            for s in studies:
                nct_id = s.get("NCTId", ["N/A"])[0]
                title = s.get("BriefTitle", ["N/A"])[0]
                status = s.get("OverallStatus", ["N/A"])[0]
                ct_link = f"https://clinicaltrials.gov/ct2/show/{nct_id}"
                links.append({
                    "title": f"{title} (Status: {status})",
                    "link": ct_link
                })
    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov API error: {e}")

    # Google search fallback
    google_query = f"https://www.google.com/search?q=is+there+a+gene+or+cell+therapy+for+{condition.replace(' ','+')}"
    links.append({
        "title": "Google Search: Is there a gene or cell therapy for this condition?",
        "link": google_query
    })

    # PubMed search fallback
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ','+')}+gene+therapy"
    links.append({
        "title": "PubMed Search",
        "link": pubmed_url
    })

    return links

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

        # Inclusion logic
        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested Infant Inclusion: **{suggested_infant}**")

        # CGT relevance logic
        suggested_cgt = assess_cgt_relevance(condition, study_texts)
        st.caption(f"🧬 Suggested CGT Relevance: **{suggested_cgt}**")

        # Gene/cell therapy existence check
        therapy_links = check_gene_cell_therapy(condition)
        st.markdown("🔗 **Gene/Cell Therapy Existence Links:**")
        for l in therapy_links:
            st.markdown(f"- [{l['title']}]({l['link']})")

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
            st.session_state.df = df
            st.success("✅ Saved!")

        if st.button("⬇️ Export Updated Excel"):
            from io import BytesIO
            output = BytesIO()
            df.to_excel(output, index=False, engine='openpyxl')
            st.download_button("⬇️ Download File", output, file_name="updated_registry_review.xlsx")
