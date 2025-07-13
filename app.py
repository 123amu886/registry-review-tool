import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json

# -------------------------------
# Page setup
# -------------------------------
st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Merged Final)")

# -------------------------------
# Load mapping files
# -------------------------------
@st.cache_data
def load_fda_mapping():
    with open("fda_approved_gene_therapies.json", "r") as f:
        return json.load(f)

@st.cache_data
def load_age_mapping():
    with open("infant_mapping.json", "r") as f:
        return json.load(f)

fda_map = load_fda_mapping()
age_map = load_age_mapping()

# -------------------------------
# Infant inclusion function (merged July 1st + refined logic)
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

    likely_patterns = [
        r"from\s*0", r"from\s*6\s*months", r"from\s*1\s*year",
        r"from\s*12\s*months", r"up to"
    ]

    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    for pattern in likely_patterns:
        if re.search(pattern, text_lower):
            return "Likely to include infants"

    if re.search(r"(2\s*years?|24\s*months?)", text_lower):
        return "Unlikely to include infants but possible"

    if re.search(r"(from|starting at|minimum age)\s*(3|4|5|\d{2,})\s*(years?)", text_lower):
        return "Does not include infants"

    onset = age_map.get(condition.lower(), "").lower()
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years", "0-12 months", "0-24 months"]):
        return "Likely to include infants"
    if any(x in onset for x in ["toddler", "child", "3 years", "4 years"]):
        return "Unlikely to include infants but possible"

    return "Uncertain"

# -------------------------------
# CGT relevance function (FDA, Phase III, filtered PubMed, override)
# -------------------------------
def assess_cgt_relevance_and_links(text, condition):
    links = []
    condition_lower = condition.lower()

    # A. FDA approved therapies
    for therapy, data in fda_map.items():
        if condition_lower in data['condition'].lower():
            links.append({
                "title": f"{therapy.capitalize()} (FDA Approved)",
                "link": f"https://www.google.com/search?q={therapy}+{condition.replace(' ','+')}",
                "phase": "Approved",
                "status": "FDA approved"
            })
            return "Relevant (FDA Approved)", links

    # B. ClinicalTrials.gov Phase III check
    try:
        url = "https://clinicaltrials.gov/api/query/study_fields"
        params = {
            "expr": f"{condition} gene therapy",
            "fields": "NCTId,BriefTitle,Phase,OverallStatus",
            "min_rnk": 1,
            "max_rnk": 10,
            "fmt": "json"
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        studies = data['StudyFieldsResponse']['StudyFields']

        for s in studies:
            phase = s.get("Phase", ["N/A"])[0]
            if "Phase 3" in phase or "Phase III" in phase:
                links.append({
                    "nct_id": s["NCTId"][0],
                    "title": f"{s['BriefTitle'][0]} (Near Approval)",
                    "phase": phase,
                    "status": s.get("OverallStatus", ["N/A"])[0],
                    "link": f"https://clinicaltrials.gov/ct2/show/{s['NCTId'][0]}"
                })
                return "Likely Relevant (Phase III / Near Approval)", links

        if studies:
            for s in studies:
                links.append({
                    "nct_id": s["NCTId"][0],
                    "title": s["BriefTitle"][0],
                    "phase": s.get("Phase", ["N/A"])[0],
                    "status": s.get("OverallStatus", ["N/A"])[0],
                    "link": f"https://clinicaltrials.gov/ct2/show/{s['NCTId'][0]}"
                })
            return "Relevant (Clinical Trials)", links

    except:
        pass

    # C. Filtered PubMed preclinical pipeline
    try:
        query = f"{condition} gene therapy preclinical OR animal model OR in vivo"
        url = f"https://pubmed.ncbi.nlm.nih.gov/?term={query.replace(' ', '+')}"
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')

        for article in soup.select('.docsum-content'):
            title = article.select_one('.docsum-title').get_text(strip=True)
            link = "https://pubmed.ncbi.nlm.nih.gov" + article.select_one('.docsum-title')['href']

            if any(kw in title.lower() for kw in ["preclinical", "animal model", "gene therapy", "vector", "in vivo", "functional rescue", "treatment"]):
                links.append({"title": title, "link": link})

        if links:
            return "Likely Relevant (Preclinical)", links

    except:
        pass

    # D. Keyword fallback
    cgt_keywords = ["cell therapy", "gene therapy", "crispr", "talen", "zfn",
                    "gene editing", "gene correction", "gene silencing", "reprogramming",
                    "cgt", "c&gt", "car-t therapy"]
    text_lower = text.lower() if pd.notna(text) else ""
    if any(k in text_lower for k in cgt_keywords):
        return "Likely Relevant", links

    # E. Google fallback
    google_query = f"https://www.google.com/search?q=is+there+a+gene+therapy+for+{condition.replace(' ','+')}"
    links.append({"title": "Google Search: Is there a gene therapy for this condition?", "link": google_query})
    return "Unsure", links

# -------------------------------
# Streamlit app flow
# -------------------------------
uploaded_file = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")
    reviewer_name = st.text_input("👤 Enter your reviewer name to filter rows:")

    if reviewer_name:
        if "Reviewer" in df.columns:
            df_filtered = df[df["Reviewer"].str.contains(reviewer_name, case=False, na=False)]
            st.write(f"✅ {len(df_filtered)} rows found for reviewer '{reviewer_name}'.")

            for i, row in df_filtered.iterrows():
                st.markdown("---")
                condition = row.get("Conditions", "")
                study_texts = " ".join([
                    str(row.get("Population (use drop down list)", "")),
                    str(row.get("Conditions", "")),
                    str(row.get("Study Title", "")),
                    str(row.get("Brief Summary", ""))
                ])

                st.markdown(f"### **Condition:** {condition}")

                infant_inclusion = assess_infant_inclusion(study_texts, condition)
                cgt_relevance, links = assess_cgt_relevance_and_links(study_texts, condition)

                st.write(f"🧒 **Infant Inclusion:** {infant_inclusion}")
                st.write(f"🧬 **CGT Relevance:** {cgt_relevance}")

                if links:
                    st.markdown("🔗 **Related Links:**")
                    for l in links:
                        st.markdown(f"- [{l['title']}]({l['link']})")

                note = st.text_area(f"📝 Add reviewer note for row {i}:", value=row.get("Reviewer Notes", ""))

                override_relevance = st.selectbox(
                    f"🔧 Override CGT relevance for row {i} if needed:",
                    ["No change", "Relevant", "Likely Relevant", "Unlikely Relevant", "Not Relevant", "Unsure"]
                )

                if st.button(f"💾 Save note and assessments for row {i}"):
                    df.loc[i, "Reviewer Notes"] = note
                    df.loc[i, "Infant Inclusion"] = infant_inclusion
                    if override_relevance != "No change":
                        df.loc[i, "CGT Relevance"] = override_relevance
                    else:
                        df.loc[i, "CGT Relevance"] = cgt_relevance
                    st.success(f"✅ Saved note and assessments for row {i}.")

            # Download updated Excel
            if st.button("⬇️ Download Updated Excel"):
                df.to_excel("updated_registry_review.xlsx", index=False)
                with open("updated_registry_review.xlsx", "rb") as f:
                    st.download_button("⬇️ Download File", f, file_name="updated_registry_review.xlsx")

        else:
            st.error("❌ 'Reviewer' column not found in your Excel.")
