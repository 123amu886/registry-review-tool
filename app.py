import streamlit as st
import pandas as pd
import json
from io import BytesIO

st.set_page_config(page_title="CGT Landscape Mapping Tool", layout="wide")
st.title("🧬 Full CGT Landscape Mapping Tool with Auto JSON Generation")

# Session state for reviewer comments
if "reviewer_comments" not in st.session_state:
    st.session_state["reviewer_comments"] = {}

# Functions for link generation
def generate_ctgov_link(condition):
    return f"https://clinicaltrials.gov/search?cond={condition.replace(' ', '+')}"

def generate_pubmed_link(condition):
    return f"https://pubmed.ncbi.nlm.nih.gov/?term={condition.replace(' ', '+')}"

# Function to save Excel as bytes for download
def to_excel(df_to_save):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_to_save.to_excel(writer, index=False, sheet_name='CGT Mapping')
        writer.save()
    processed_data = output.getvalue()
    return processed_data

# Upload Excel file
uploaded_excel = st.file_uploader("Upload Excel file with CGT mapping data", type=["xlsx"])

if uploaded_excel:
    df = pd.read_excel(uploaded_excel)

    # Ensure key columns
    required_cols = ["Condition", "Subset", "Infant Inclusion", "CGT Relevance"]
    for col in required_cols:
        if col not in df.columns:
            st.error(f"Excel missing required column: {col}")
            st.stop()

    # Generate CT.gov and PubMed links if not present
    if "ClinicalTrials.gov Link" not in df.columns:
        df["ClinicalTrials.gov Link"] = df["Condition"].apply(generate_ctgov_link)
    if "PubMed Link" not in df.columns:
        df["PubMed Link"] = df["Condition"].apply(generate_pubmed_link)

    # Initialize Reviewer Comments column
    if "Reviewer Comments" not in df.columns:
        df["Reviewer Comments"] = ""

    # Filter by subset
    st.sidebar.header("Filter Subsets")
    subsets = df["Subset"].unique().tolist()
    selected_subsets = st.sidebar.multiselect("Select subsets to display", options=subsets, default=subsets)

    filtered_df = df[df["Subset"].isin(selected_subsets)].reset_index(drop=True)

    # Load reviewer comments from session state
    def get_comment(cond):
        return st.session_state["reviewer_comments"].get(cond, "")

    filtered_df["Reviewer Comments"] = filtered_df["Condition"].apply(get_comment)

    # Editable reviewer comments
    st.write("### CGT Mapping Data Table with Reviewer Comments")
    edited_df = filtered_df.copy()
    for idx, row in edited_df.iterrows():
        comment = st.text_input(
            label=f"Reviewer comments for {row['Condition']}",
            value=row["Reviewer Comments"],
            key=f"comment_{idx}"
        )
        st.session_state["reviewer_comments"][row["Condition"]] = comment

    # Update comments in dataframe
    edited_df["Reviewer Comments"] = edited_df["Condition"].map(st.session_state["reviewer_comments"])

    # Display table with clickable CT.gov links
    def make_clickable(url):
        return f'<a href="{url}" target="_blank">Link</a>' if pd.notna(url) and url != "" else ""

    display_df = edited_df.copy()
    display_df["ClinicalTrials.gov Link"] = display_df["ClinicalTrials.gov Link"].apply(make_clickable)
    display_df["PubMed Link"] = display_df["PubMed Link"].apply(make_clickable)

    st.markdown(
        display_df.to_html(escape=False, index=False),
        unsafe_allow_html=True,
    )

    # Download updated Excel
    st.markdown("---")
    if st.button("Download updated Excel"):
        df_with_comments = df.copy()
        df_with_comments["Reviewer Comments"] = df_with_comments["Condition"].map(st.session_state["reviewer_comments"])
        excel_data = to_excel(df_with_comments)
        st.download_button(
            label="Download Excel",
            data=excel_data,
            file_name="updated_cgt_mapping.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # Auto-generate merged_cgt_mapping.json from current dataframe
    st.markdown("---")
    if st.button("Download auto-generated JSON"):
        merged_json = {}
        for _, row in df.iterrows():
            merged_json[row["Condition"]] = {
                "subset": row["Subset"],
                "infant_inclusion": row["Infant Inclusion"],
                "cgt_relevance": row["CGT Relevance"],
                "clinicaltrials_link": row["ClinicalTrials.gov Link"],
                "pubmed_link": row["PubMed Link"],
                "reviewer_comment": st.session_state["reviewer_comments"].get(row["Condition"], "")
            }
        json_str = json.dumps(merged_json, indent=2)
        st.download_button(
            label="Download merged_cgt_mapping.json",
            data=json_str,
            file_name="merged_cgt_mapping.json",
            mime="application/json"
        )

else:
    st.info("Please upload your Excel file to begin.")

