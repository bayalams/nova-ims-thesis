"""
HuffPost Cleaner
=================

Cleans articles from HUFFPOST_WORLD_NEWS and HUFFPOST_TRAVEL sources.
These articles have navigation menus, trending sections, newsletter prompts, and inline CTAs.
"""

import re


def clean_huffpost(text, meta):
    """
    Cleaner for HUFFPOST articles (World News + Travel).
    """
    if not text:
        return ""
    
    # 0. Pre-processing: Remove known garbage lines
    lines = text.split('\n')
    filtered_lines = []
    skip_until_content = True  # Skip header noise until real content
    
    for line in lines:
        sline = line.strip()
        
        # Skip empty lines at the start
        if skip_until_content and not sline:
            continue
        
        # Skip navigation menu items
        if sline in ["U.S. News", "World News", "Business", "Environment", 
                      "Health", "Social Justice", "Entertainment", "Culture & Arts",
                      "Media", "HuffPost Personal", "HuffPost Shopping",
                      "Life", "Style", "Beauty", "Food & Drink", "Home & Living",
                      "Parenting", "Travel", "Voices", "Wellness",
                      "News", "Politics", "Opinion", "Video",
                      "FROM OUR PARTNER", "FROM OUR PARTNERS"]:
            continue
            
        # Skip "Suggest a correction" and similar CTAs
        if sline in ["Suggest a correction", "Do you have info to share with HuffPost reporters?",
                      "Suggest a Correction", "Here's how.", "Support HuffPost",
                      "Already contributed? Log in to hide these messages.",
                      "Popular in the Community"]:
            continue
            
        # Skip newsletter signup lines
        if "Sign up for our daily newsletter" in sline:
            continue
        if "Get top stories and blog posts emailed" in sline:
            continue
        if "Successfully Subscribed!" in sline:
            continue
            
        # Skip social sharing buttons
        if sline in ["Share", "Tweet", "Pin"]:
            continue
            
        # Skip "Go To Homepage" navigation
        if sline == "Go To Homepage":
            continue
            
        if skip_until_content and len(sline) > 50:
            skip_until_content = False
            
        if not skip_until_content:
            filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Footer Cleaning - cut at footer sections
    footer_markers = [
        "\nPopular in the Community",
        "\nTrending",
        "\nMore:",
        "\nSuggest a correction",
        "\nDo you have info to share",
        "\nSupport HuffPost",
        "\nBefore You Go",
        "\nHuffPost Shopping's",
        "\nALSO ON HUFFPOST",
        "\nWhat's Hot",
        "\nRelated...",
        "\n## MORE:",
        "\nGo To Homepage",
        "\nNewsletter",
        "\nNEWSLETTER",
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    
    text = text[:first_idx]
    
    # 2. Post-processing cleanup
    
    # Remove "MORE:" and "RELATED:" inline link blocks
    text = re.sub(r'^MORE:.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^RELATED[\s\.:]+.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\*\*MORE:\*\*.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\*\*RELATED.*?\*\*.*$', '', text, flags=re.MULTILINE)
    
    # Remove markdown images ![...](...) 
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    
    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove header separator lines (------ or ======)
    text = re.sub(r'^[-=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
