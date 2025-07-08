def assess_cgt_relevance_and_links(text, condition):
    links = []
    if pd.isna(text):
        text = ""
    text_lower = text.lower()
    condition_lower = condition.lower()

    # Check mapping first
    relevance = cgt_map.get(condition_lower, None)
    if relevance:
        if relevance in ["Relevant", "Likely Relevant"]:
            ct_url = f"https://clinicaltrials.gov/ct2/results?cond={condition}&term=gene+therapy"
            scholar_url = f"https://scholar.google.com/scholar?q={condition}+gene+therapy+preclinical"
            links.extend([ct_url, scholar_url])
        return relevance, links

    # Fallback: keyword detection in text
    cgt_keywords = [
        "cell therapy", "gene therapy", "crispr-cas9 system", "talen", "zfn",
        "gene editing", "gene correction", "gene silencing", "reprogramming",
        "cgt", "c&gt", "car-t therapy"
    ]
    if any(kw in text_lower for kw in cgt_keywords):
        relevance = "Likely Relevant"
        ct_url = f"https://clinicaltrials.gov/ct2/results?cond={condition}&term=gene+therapy"
        scholar_url = f"https://scholar.google.com/scholar?q={condition}+gene+therapy+preclinical"
        links.extend([ct_url, scholar_url])
    else:
        relevance = "Unlikely Relevant"

    return relevance, links
