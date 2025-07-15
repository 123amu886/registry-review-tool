import streamlit as st
import pandas as pd
import requests
import json
import re

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Final Corrected)")

# -------------------------------
# 1. Load mappings
# -------------------------------
@st.cache_data
def load_json(file):
    with open(file, "r") as f:
        return json.load(f)

cgt_map = load_json("cgt_mapping.json")
pipeline_cgt = load_json("pipeline_cgt_conditions.json")
age_map = load_json("infant_mapping.json")

# -------------------------------
# 2. Infant inclusion logic
# -------------------------------
def assess_infant_inclusion(text, condition):
    text_lower = text.lower() if pd.notna(text) else ""
    min_age, max_age = extract_min_max_age(text_lower)

    # 1. Explicit mention patterns
    include_patterns = [
        r"(from|starting at|age)\s*0",
        r"(from|starting at)\s*birth",
        r"newborn",
        r"infants?",
        r"less than\s*(12|18|24)\s*months",
        r"<\s*(12|18|24)\s*months",
        r"<\s*(1|2)\s*years?",
        r"up to\s*18\s*months",
        r"up to\s*2\s*years",
        r"0[-\s]*2\s*years",
        r"0[-\s]*24\s*months",
    ]
    for pattern in include_patterns:
        if re.search(pattern, text_lower):
            return "Include infants"

    # 2. Min age logic
    if min_age is not None and min_age <= 24:
        return "Include infants"

    # 3. Condition onset mapping
    onset = age_map.get(condition.lower(), "").lower()
    if any(x in onset for x in ["birth", "infant", "neonate", "0-2 years"]):
        return "Likely to include infants"

    # 4. Unlikely but possible
    if min_age in [24, 25]:
        return "Unlikely to include infants but possible"

    # 5. Does not include
    if min_age is not None and min_age > 24:
        return "Does not include infants"

    return "Uncertain"

def extract_min_max_age(text):
    min_age = None
    max_age = None

    min_patterns = [
        r"minimum age\s*[:=]?\s*(\d+)\s*(year|month)",
        r"from\s*(\d+)\s*(year|month)",
        r"starting at\s*(\d+)\s*(year|month)",
        r"age\s*[>≥]\s*(\d+)\s*(year|month)",
    ]

    max_patterns = [
        r"maximum age\s*[:=]?\s*(\d+)\s*(year|month)",
        r"up to\s*(\d+)\s*(year|month)",
        r"<\s*(\d+)\s*(year|month)",
        r"less than\s*(\d+)\s*(year|month)",
    ]

    for pattern in min_patterns:
        for m in re.finditer(pattern, text, flags=re.I):
            val, unit = int(m.group(1)), m.group(2).lower()
            months = val * 12 if "year" in unit else val
            if min_age is None or months < min_age:
                min_age = months

    for pattern in max_patterns:
        for m in re.finditer(pattern, text, flags=re.I):
            val, unit = int(m.group(1)), m.group(2).lower()
            months = val * 12 if "year" in unit else val
            if max_age is None or months > max_age:
                max_age = months

    return min_age, max_age

# -------------------------------
# 3. CGT relevance logic
# -------------------------------
def assess_cgt_relevance(condition, text):
    condition_lower = condition.lower()
    links = []

    # 1. Check approved CGT
    if cgt_map.get(condition_lower) == "approved":
        relevance = "Relevant"

    # 2. Check pipeline CGT
    elif pipeline_cgt.get(condition_lower) == "phase_i_or_preclinical":
        relevance = "Likely Relevant"

    # 3. Fallback to keyword detection
    else:
        keywords = ["gene therapy", "cell therapy", "crispr", "car-t"]
        if any(k in text.lower() for k in keywords):
            relevance = "Likely Relevant"
        else:
            relevance = "Unsure"

    # 4. Add Google & PubMed links always
    google = f"https://www.google.com/search?q=is+there+a+gene+therapy+for+{condition.replace(' ','+')}"
    pubmed = f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ','+')}+gene+therapy"
    links.append({"title": "Google Search", "link": google})
    links.append({"title": "PubMed Search", "link": pubmed})

    return relevance, links

# -------------------------------
# 4. Streamlit app
# -------------------------------
uploaded = st.file_uploader("📂 Upload registry Excel", type=["xlsx"])

if uploaded:
    df = pd.read_excel(uploaded, engine="openpyxl")
    reviewer = st.text_input("Your name (Column F)", "")
    filtered = df[df["Reviewer"].str.strip().str.lower() == reviewer.strip().lower()].copy()

    if filtered.empty:
        st.success("🎉 All done.")
    else:
        idx = st.number_input("Select row", 0, len(filtered)-1, step=1)
        row = filtered.iloc[idx]
        condition = row["Conditions"]

        st.subheader("🔎 Record Details")
        st.markdown(f"**Condition:** {condition}")

        # Assessments
        text = " ".join([str(row.get(c, "")) for c in df.columns])
        infant_suggestion = assess_infant_inclusion(text, condition)
        cgt_relevance, links = assess_cgt_relevance(condition, text)

        st.caption(f"🧒 Suggested infant inclusion: **{infant_suggestion}**")
        st.caption(f"🧬 Suggested CGT relevance: **{cgt_relevance}**")

        # Reviewer comments restored
        comments = st.text_area("Reviewer Comments", value=row.get("Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)", ""))

        # Display links
        if links:
            st.markdown("🔗 **Database Links:**")
            for l in links:
                st.markdown(f"- [{l['title']}]({l['link']})")

        # Save button
        if st.button("💾 Save"):
            df.at[filtered.index[idx], "Population (use drop down list)"] = infant_suggestion
            df.at[filtered.index[idx], "Relevance to C&GT"] = cgt_relevance
            df.at[filtered.index[idx], "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            st.success("✅ Saved!")

        # Export updated file
        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("Download Updated File", f, file_name="updated_registry_review.xlsx")
