import streamlit as st
import pandas as pd
import json
from io import BytesIO

st.set_page_config(page_title="CGT Landscape Mapping Tool", layout="wide")
st.title("🧬 Full CGT Landscape Mapping Tool")

# Load Excel and JSON files uploaded by user
uploaded_excel = st.file_uploader("Upload Excel file with CGT mapping data", type=["xlsx"])
uploaded_json = st.file_uploader("Upload merged_cgt_mapping.json", type=["json"])

# Session state to keep comments and data updates persistent
if "reviewer_comments" not in st.session_state:
    st.session_state["reviewer_comments"] = {}

if uploaded_excel and uploaded_json:
    # Load Excel data
    df = pd.read_excel(uploaded_excel)

    # Load JSON mapping
    mapping_json = json.load(uploaded_json)

    # Ensure key columns present
    required_cols = ["Condition", "Subset", "Infant Inclusion", "CGT Relevance", "ClinicalTrials.gov Link"]
    if not all(col in df.columns for col in required_cols):
        st.error(f"Excel missing one or more required columns: {required_cols}")
        st.stop()

    # Filter subsets checkbox
    st.sidebar.header("Filter Subsets")
    subsets = df["Subset"].unique().tolist()
    selected_subsets = st.sidebar.multiselect("Select subsets to display", options=subsets, default=subsets)

    filtered_df = df[df["Subset"].isin(selected_subsets)].reset_index(drop=True)

    # Add Reviewer Comments column from session_state if exists
    def get_comment(cond):
        return st.session_state["reviewer_comments"].get(cond, "")

    filtered_df["Reviewer Comments"] = filtered_df["Condition"].apply(get_comment)

    # Editable table for reviewer comments
    st.write("### CGT Mapping Data Table")
    edited_df = filtered_df.copy()

    # Editable reviewer comments with text_input for each row
    for idx, row in edited_df.iterrows():
        comment = st.text_input(
            label=f"Reviewer comments for {row['Condition']}",
            value=row["Reviewer Comments"],
            key=f"comment_{idx}"
        )
        # Update session state on change
        st.session_state["reviewer_comments"][row["Condition"]] = comment

    # Show dataframe again with updated comments
    edited_df["Reviewer Comments"] = edited_df["Condition"].map(st.session_state["reviewer_comments"])

    # Display final table with clickable ClinicalTrials.gov links
    def make_clickable(url):
        return f'<a href="{url}" target="_blank">Link</a>' if pd.notna(url) and url != "" else ""

    st.markdown(
        edited_df[["Condition", "Subset", "Infant Inclusion", "CGT Relevance"]].to_html(escape=False),
        unsafe_allow_html=True,
    )

    # Download updated Excel with reviewer comments included
    def to_excel(df_to_save):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_to_save.to_excel(writer, index=False, sheet_name='CGT Mapping')
            writer.save()
        processed_data = output.getvalue()
        return processed_data

    st.markdown("---")
    if st.button("Download updated Excel"):
        # Merge comments back into full df for download
        df_with_comments = df.copy()
        df_with_comments["Reviewer Comments"] = df_with_comments["Condition"].map(st.session_state["reviewer_comments"])
        excel_data = to_excel(df_with_comments)
        st.download_button(
            label="Download Excel",
            data=excel_data,
            file_name="updated_cgt_mapping.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # Download updated JSON (can save reviewer comments as well)
    st.markdown("---")
    if st.button("Download updated JSON"):
        # Add comments to JSON structure
        for cond in mapping_json:
            comment = st.session_state["reviewer_comments"].get(cond, "")
            mapping_json[cond]["reviewer_comment"] = comment
        json_str = json.dumps(mapping_json, indent=2)
        st.download_button(
            label="Download JSON",
            data=json_str,
            file_name="updated_merged_cgt_mapping.json",
            mime="application/json"
        )

else:
    st.info("Please upload both Excel and JSON files to begin.")

