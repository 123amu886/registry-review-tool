import streamlit as st
import pandas as pd
import json

st.set_page_config(page_title="🧬 CGT Registry Review", layout="wide")
st.title("🧬 CGT Registry Relevance Review Tool")

# Load mappings
@st.cache_data
def load_json(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

cgt_map = load_json("cgt_mapping.json")
pipeline_map = load_json("pipeline_cgt_mapping.json")
synonyms_map = load_json("synonyms_mapping.json")
infant_map = load_json("infant_mapping.json")

# Function to get relevance
def get_cgt_relevance(condition):
    condition_lower = condition.lower()
    standard_condition = synonyms_map.get(condition_lower, condition_lower)

    links = []

    # Approved therapies
    relevance = cgt_map.get(standard_condition)
    if relevance:
        links.append(f"Approved gene/cell therapy for {standard_condition}")
        return relevance, links

    # Pipeline therapies
    relevance = pipeline_map.get(standard_condition)
    if relevance:
        links.append(f"Pipeline CGT exists for {standard_condition}")
        return "Likely Relevant", links

    # Keyword-based detection
    keywords = ["gene therapy", "cell therapy", "car t", "crispr"]
    for kw in keywords:
        if kw in condition_lower:
            return "Likely Relevant", [f"Detected keyword: {kw}"]

    return "Unsure", []

# Function to check infant inclusion criteria
def check_infant_inclusion(condition):
    condition_lower = condition.lower()
    standard_condition = synonyms_map.get(condition_lower, condition_lower)
    return infant_map.get(standard_condition, "Unknown")

# Upload input file
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.write("### Input Data Preview", df.head())

    # Add relevance and infant inclusion columns
    df["CGT Relevance"] = df["Condition"].apply(lambda x: get_cgt_relevance(str(x))[0])
    df["Infant Inclusion"] = df["Condition"].apply(lambda x: check_infant_inclusion(str(x)))

    st.write("### Processed Output", df)

    # Download final processed data
    st.download_button(label="Download Processed Data as CSV",
                       data=df.to_csv(index=False).encode("utf-8"),
                       file_name="processed_registry.csv",
                       mime="text/csv")

# Reviewer comments section
st.write("### 💬 Reviewer Comments")
reviewer_comment = st.text_area("Add your review comments here")
if st.button("Submit Comment"):
    st.success("✅ Comment submitted successfully.")
