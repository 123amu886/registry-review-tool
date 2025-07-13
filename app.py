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
    with open("cgt_mapping.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

cgt_map = load_cgt_mapping()
age_map = load_age_mapping()

# -------------------------------
# 2. Infant inclusion logic (final corrected version)
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    condition_lower = condition.lower()
    onset = age_map.get(condition_lower, "").lower()

    print(f"DEBUG: Assessing infant inclusion for condition: {condition}")
    print(f"DEBUG: Text: {text_lower}")

    # 1. Explicit exclusion first
    if "no infants" in text_lower or "does not include infants" in text_lower:
        print("DEBUG: Explicit exclusion found")
        return "Does not include infants"

    # 2. INCLUDE INFANTS patterns
    include_patterns = [
        r"\bfrom\s*0\b",
        r"starting at birth",
        r"\bnewborn\b",
        r"\binfants?\b",
        r"less than\s*(12|18|24)\s*months",
        r"<\s*(12|18|24)\s*months",
        r"<\s*(1|2)\s*years?\b",
        r"up to\s*(18|24)\s*months",
        r"up to\s*2\s*years",
        r"0[-\s]*2\s*years",
        r"0[-\s]*24\s*months",
        r"\b12\s*months\b",
        r"\b18\s*months\b",
        r"(?<!\d)1\s*year(?!\d)"
    ]

    for pat in include_patterns:
        if re.search(pat, text_lower):
            print(f"DEBUG: Include infants matched pattern: {pat}")
            return "Include infants"

    # 3. LIKELY TO INCLUDE INFANTS: "up to" any age (even beyond 2 years)
    if re.search(r"up to\s*\d+\s*(months|years?)", text_lower):
        print("DEBUG: 'Up to' found, Likely to include infants")
        return "Likely to include infants"

    # 4. MINIMUM AGE ≥ 2 years or 24 months → Unlikely to include infants but possible
    age_matches = re.findall(r"\b(\d+)\s*(months|years?)\b", text_lower)
    for age_num_str, age_unit in age_matches:
        age_num = int(age_num_str)
        if (age_unit.startswith("year") and age_num >= 2) or (age_unit.startswith("month") and age_num >= 24):
            print(f"DEBUG: Found minimum age {age_num} {age_unit} >= 2 years threshold")
            return "Unlikely to include infants but possible"

    # 5. Onset mapping fallback
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
        print("DEBUG: Onset mapping indicates Include infants")
        return "Include infants"

    if re.search(r"\b2\s*years?\b", onset) or re.search(r"\b24\s*months\b", onset):
        print("DEBUG: Onset mapping indicates >= 2 years")
        return "Unlikely to include infants but possible"

    # 6. Default
    print("DEBUG: No clear match, returning Uncertain")
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

            study_info.append({
                "nct_id": nct_id,
                "title": title,
                "phase": phase,
                "status": status,
                "link": ct_link,
                "contacts": [],
                "locations": []
            })

        return study_info

    except Exception as e:
        print(f"⚠️ ClinicalTrials.gov API error for {condition}: {e}")
        return []

# -------------------------------
# 4. CGT relevance logic
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    condition_lower = condition.lower()

    relevance = cgt_map.get(condition_lower, None)
    studies = check_clinicaltrials_gov(condition)
    if studies:
        links.extend(studies)

    if relevance in ["Relevant", "Likely Relevant"] and studies:
        return relevance, links

    cgt_keywords = ["cell therapy", "gene therapy", "crispr", "talen", "zfn",
                    "gene editing", "gene correction", "gene silencing", "reprogramming",
                    "cgt", "c&gt", "car-t therapy"]
    text_lower = text.lower() if pd.notna(text) else ""

    if any(k in text_lower for k in cgt_keywords):
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
            st.session_state.df = df
            st.success("✅ Saved!")

        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")
