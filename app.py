import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Production)")

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
# 2. Refined infant inclusion logic
# -------------------------------
import re

def extract_ages(text):
    """
    Extract min and max age (in months) from text.
    Returns tuple (min_age_months, max_age_months), either can be None if not found.
    """
    min_age = None
    max_age = None

    # Patterns for min age (e.g. "minimum age 14 years", "age >= 2 years", "from 6 months", "14 years and older")
    min_patterns = [
        r"minimum age\s*[:=]?\s*(\d+)\s*(year|month)s?",
        r"age\s*[>≥]\s*(\d+)\s*(year|month)s?",
        r"from\s*(\d+)\s*(year|month)s?",
        r"(\d+)\s*(year|month)s?\s*and older",
        r"starting at\s*(\d+)\s*(year|month)s?"
    ]

    # Patterns for max age (e.g. "up to 18 months", "< 2 years", "less than 24 months")
    max_patterns = [
        r"up to\s*(\d+)\s*(year|month)s?",
        r"<\s*(\d+)\s*(year|month)s?",
        r"less than\s*(\d+)\s*(year|month)s?"
    ]

    for pattern in min_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            val, unit = int(match.group(1)), match.group(2).lower()
            months = val * 12 if unit.startswith("year") else val
            if (min_age is None) or (months < min_age):
                min_age = months

    for pattern in max_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            val, unit = int(match.group(1)), match.group(2).lower()
            months = val * 12 if unit.startswith("year") else val
            if (max_age is None) or (months > max_age):
                max_age = months

    return min_age, max_age

def assess_infant_inclusion(text, condition, age_map):
    """
    Determines infant inclusion category based on eligibility text and condition.
    """

    text_lower = text.lower() if text else ""

    # Check explicit exclusions first
    exclusion_phrases = [
        r"no infants",
        r"excluding infants",
        r"infants excluded",
        r"does not include infants"
    ]
    if any(re.search(p, text_lower) for p in exclusion_phrases):
        return "Does not include infants"

    min_age, max_age = extract_ages(text_lower)

    # Direct infant inclusion phrases
    infant_phrases = [
        r"\bfrom 0\b",
        r"starting at birth",
        r"newborn",
        r"\binfants?\b",
        r"less than (12|18|24) months",
        r"<(12|18|24) months",
        r"<(1|2) years",
        r"up to 18 months",
        r"up to 2 years",
        r"0[-\s]*2 years",
        r"0[-\s]*18 months",
        r"0[-\s]*24 months",
        r"from 1 year",
        r"from 12 months",
        r"\b12 months\b",
        r"\b18 months\b",
        r"\b1 year\b"
    ]

    # If any infant phrase AND min age ≤ 18 months or unknown min age
    if any(re.search(p, text_lower) for p in infant_phrases):
        if min_age is None or min_age <= 18:
            return "Include infants"

    # If "up to" present and min age unknown or ≤ 18 months -> Likely include infants
    if "up to" in text_lower:
        if min_age is None or min_age <= 18:
            return "Likely to include infants"

    # Use onset info for likely inclusion
    onset = age_map.get(condition.lower(), "").lower() if age_map else ""
    likely_terms = ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]
    if any(term in onset for term in likely_terms):
        return "Likely to include infants"

    # Unlikely if min age == 24 months (2 years)
    if min_age == 24:
        return "Unlikely to include infants but possible"

    # Does not include if min age > 24 months
    if min_age is not None and min_age > 24:
        return "Does not include infants"

    # Otherwise, uncertain
    return "Uncertain"

# -------------------------------
# 3. CGT relevance logic
# -------------------------------
def assess_cgt_relevance(condition, text):
    condition_lower = condition.lower()
    relevance = cgt_map.get(condition_lower, None)

    if relevance in ["Relevant", "Likely Relevant"]:
        return relevance

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

    google_query = f"https://www.google.com/search?q=is+there+a+gene+or+cell+therapy+for+{condition.replace(' ','+')}"
    links.append({
        "title": "Google Search: Is there a gene or cell therapy for this condition?",
        "link": google_query
    })

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

        suggested_infant = assess_infant_inclusion(study_texts, condition)
        st.caption(f"🧒 Suggested Infant Inclusion: **{suggested_infant}**")

        suggested_cgt = assess_cgt_relevance(condition, study_texts)
        st.caption(f"🧬 Suggested CGT Relevance: **{suggested_cgt}**")

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
