import streamlit as st
import pandas as pd
import requests
import json
import re

st.set_page_config(page_title="Clinical Registry Review Tool", layout="wide")
st.title("🧾 Clinical Registry Review Tool (Corrected Final)")

# -------------------------------
# 1. Load mappings
# -------------------------------
@st.cache_data
def load_json(file):
    with open(file, "r") as f:
        return json.load(f)

cgt_map = load_json("cgt_mapping.json")
pipeline_cgt = load_json("pipeline_cgt_conditions.json")

# -------------------------------
# 2. CGT relevance logic
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
# 3. Streamlit app
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

        # -------------------------------
        # Assess CGT relevance
        text = " ".join([str(row.get(c, "")) for c in df.columns])
        cgt_relevance, links = assess_cgt_relevance(condition, text)
        st.caption(f"🧬 Suggested CGT relevance: **{cgt_relevance}**")

        # -------------------------------
        # Reviewer comments restored
        comments = st.text_area("Reviewer Comments", value=row.get("Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)", ""))

        # -------------------------------
        # Display links
        if links:
            st.markdown("🔗 **Database Links:**")
            for l in links:
                st.markdown(f"- [{l['title']}]({l['link']})")

        # -------------------------------
        # Save button
        if st.button("💾 Save"):
            df.at[filtered.index[idx], "Relevance to C&GT"] = cgt_relevance
            df.at[filtered.index[idx], "Reviewer Notes (comments to support the relevance to the infant population that needs C&GT)"] = comments
            st.success("✅ Saved!")

        # -------------------------------
        # Export updated file
        if st.button("⬇️ Export Updated Excel"):
            df.to_excel("updated_registry_review.xlsx", index=False)
            with open("updated_registry_review.xlsx", "rb") as f:
                st.download_button("Download Updated File", f, file_name="updated_registry_review.xlsx")
