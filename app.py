import streamlit as st
import pandas as pd
import json
import re

st.set_page_config(page_title="CGT Registry Review Tool", layout="wide")
st.title("🧬 Comprehensive CGT Registry Review Tool")

# Load mappings
@st.cache_data
def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)

cgt_map = load_json("cgt_mapping.json")
pipeline_map = load_json("pipeline_cgt_mapping.json")
infant_map = load_json("infant_mapping.json")
synonyms_map = load_json("synonyms_mapping.json")

# Helper functions
def get_synonym(condition):
    condition_lower = condition.lower()
    for canonical, synonyms in synonyms_map.items():
        if condition_lower == canonical or condition_lower in [s.lower() for s in synonyms]:
            return canonical
    return condition  # Return original if no synonym match found

def get_cgt_relevance(condition):
    condition = get_synonym(condition)
    cond_lower = condition.lower()
    if cond_lower in [c.lower() for c in cgt_map.get("approved_conditions", [])]:
        return "Approved CGT"
    elif cond_lower in [c.lower() for c in pipeline_map.get("pipeline_conditions", [])]:
        return "Likely Relevant (Pipeline)"
    else:
        return "Unsure"

def get_infant_inclusion(condition):
    condition = get_synonym(condition)
    return infant_map.get(condition, "Unknown")

def get_ctgov_link(condition):
    query = re.sub(r"\s+", "+", condition)
    return f"https://clinicaltrials.gov/search?cond={query}"

def get_pubmed_link(condition):
    query = re.sub(r"\s+", "+", condition)
    return f"https://pubmed.ncbi.nlm.nih.gov/?term={query}"

# Upload data
uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    if "Condition" not in df.columns:
        st.error("No 'Condition' column found in uploaded file.")
    else:
        # Process mappings
        df["Synonym/Canonical"] = df["Condition"].apply(get_synonym)
        df["Infant Inclusion"] = df["Condition"].apply(get_infant_inclusion)
        df["CGT Relevance"] = df["Condition"].apply(get_cgt_relevance)
        df["ClinicalTrials.gov Link"] = df["Condition"].apply(get_ctgov_link)
        df["PubMed Link"] = df["Condition"].apply(get_pubmed_link)

        # Reviewer Comments
        if "Reviewer Comments" not in df.columns:
            df["Reviewer Comments"] = ""

        st.write("### Processed Registry Data")
        st.dataframe(df)

        # Filter options
        st.write("### Filter Options")
        relevance_filter = st.multiselect("Select CGT Relevance to Display", options=df["CGT Relevance"].unique(), default=df["CGT Relevance"].unique())
        filtered_df = df[df["CGT Relevance"].isin(relevance_filter)]

        st.write("### Filtered Data")
        st.dataframe(filtered_df)

        # Download buttons
        @st.cache_data
        def convert_df_to_csv(df):
            return df.to_csv(index=False).encode('utf-8')

        st.download_button("Download Filtered CSV", data=convert_df_to_csv(filtered_df), file_name="filtered_registry.csv", mime="text/csv")

        # Reviewer comments input
        st.write("### Update Reviewer Comments")
        selected_row = st.number_input("Select row index to add comment", min_value=0, max_value=len(df)-1, step=1)
        comment = st.text_input("Enter comment")
        if st.button("Save Comment"):
            df.at[selected_row, "Reviewer Comments"] = comment
            st.success(f"Comment saved for row {selected_row}.")

        # Download updated Excel
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("Download Updated Excel", data=output.getvalue(), file_name="updated_registry.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
