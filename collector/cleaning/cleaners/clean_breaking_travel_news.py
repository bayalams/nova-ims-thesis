"""
Breaking Travel News Cleaner
=============================

Cleans articles from BREAKING_TRAVEL_NEWS source.
These articles have navigation headers, sidebars, and footer content.
"""

import re


def clean_breaking_travel_news(text, meta):
    """
    Cleaner for BREAKING_TRAVEL_NEWS articles.
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
        
        # Skip navigation header lines
        if sline in ["Top Navigation", "Main Navigation", "Mobile Navigation",
                     "Latest", "Sidebar", "Footer"]:
            continue
        if sline == "### Latest":
            continue
            
        # Skip separator lines that are just dashes
        if re.match(r'^-{3,}$', sline):
            continue
            
        # Skip "Older" / "Newer" navigation
        if sline in ["Older", "Newer"]:
            continue
            
        # Skip sidebar sections
        if sline.startswith("### Follow Breaking Travel News"):
            continue
        if sline == "### Latest & Popular News":
            continue
        if sline == "#### Latest News":
            continue
        if sline == "#### Popular News":
            continue
            
        if skip_until_content and len(sline) > 50:
            skip_until_content = False
            
        if not skip_until_content:
            filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Footer Cleaning - cut at navigation/sidebar sections
    footer_markers = [
        "\nOlder\n",
        "\n### Follow Breaking Travel News",
        "\nSidebar\n",
        "\n### Latest & Popular News",
        "\n#### Latest News\n",
        "\n* ![",  # Start of article list with images
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    
    text = text[:first_idx]
    
    # 2. Post-processing cleanup
    
    # Remove markdown images ![...](...) 
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    
    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove header separator lines (------ or ======)
    text = re.sub(r'^[-=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
