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
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""

    # Extract all ages with positions
    age_pattern = re.compile(r"(\d+)\s*(month|year)s?")
    all_ages = [(int(m.group(1)), m.group(2), m.start()) for m in age_pattern.finditer(text_lower)]

    min_age_months = None
    if all_ages:
        months_list = [age * 12 if unit.startswith("year") else age for age, unit, _ in all_ages]
        min_age_months = min(months_list)

    # 1. Explicit exclusions (highest precedence)
    if re.search(r"(no infants|excluding infants|does not include infants|infants excluded)", text_lower):
        return "Does not include infants"

    # 2. Minimum age logic overrides
    if min_age_months is not None:
        if min_age_months > 24:
            return "Does not include infants"
        elif min_age_months == 24:
            return "Unlikely to include infants but possible"
        # else, min_age_months <=24: continue checks below

    # 3. "up to" phrase handling (Likely include infants if no min age or min_age <= 24)
    if "up to" in text_lower:
        if min_age_months is None or min_age_months <= 24:
            return "Likely to include infants"

    # 4. Include infants phrases with strict word boundaries
    include_patterns = [
        r"\bfrom\s*0\b",
        r"\bfrom\s*6\s*months\b",
        r"\bfrom\s*12\s*months\b",
        r"\bfrom\s*1\s*year\b",
        r"\bstarting at birth\b",
        r"\bnewborn\b",
        r"\binfants?\b",
        r"less than\s*(12|18|24)\s*months",
        r"<\s*(12|18|24)\s*months",
        r"<\s*(1|2)\s*years?",
        r"0[-\s]*2\s*years",
        r"0[-\s]*18\s*months",
        r"0[-\s]*24\s*months",
        r"\b12\s*months\b",
        r"\b18\s*months\b",
        r"\b1\s*year\b"
    ]

    for pattern in include_patterns:
        for match in re.finditer(pattern, text_lower):
            start, end = match.span()
            before = text_lower[start-1] if start > 0 else " "
            after = text_lower[end] if end < len(text_lower) else " "
            if (not before.isdigit()) and (not after.isdigit()):
                return "Include infants"

    # 5. Onset age mapping fallback
    onset = age_map.get(condition.lower(), "").lower()
    likely_phrases = ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]
    if any(x in onset for x in likely_phrases):
        return "Likely to include infants"

    # 6. Default fallback
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
