"""
Independent Travel Cleaner
===========================

Cleans articles from INDEPENDENT_TRAVEL source.
These articles have notification prompts, newsletter signups, and footer noise.
"""

import re


def clean_independent_travel(text, meta):
    """
    Cleaner for INDEPENDENT_TRAVEL articles.
    """
    if not text:
        return ""
    
    # 0. Pre-processing: Remove known garbage lines
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        sline = line.strip()
        if not sline:
            filtered_lines.append(line)
            continue
        
        # Skip notification prompts
        if "Stay up to date with notifications from The Independent" in sline:
            continue
        if "Notifications can be managed in browser preferences" in sline:
            continue
        if sline in ["Not nowYes please", "Not now", "Yes please"]:
            continue
            
        # Skip swipe navigation
        if sline == "Swipe for next article":
            continue
            
        # Skip newsletter signup (including ### prefixed versions)
        if "Simon Calder" in sline:
            continue
        if sline.startswith("Email\\*") or sline == "Email*":
            continue
        if "I would like to be emailed about offers" in sline:
            continue
            
        # Skip separator lines
        if re.match(r'^-{3,}$', sline):
            continue
            
        filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Footer Cleaning - cut at footer sections
    footer_markers = [
        "\n### More about\n",
        "\nJoin our commenting forum",
        "\n### Most popular",
        "\n### Popular videos",
        "\n### Bulletin",
        "\n### Read next",
        "\n### Thank you for registering",
        "\nPlease refresh the page",
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
    
    # Remove "Read more:" callouts that link to other articles
    text = re.sub(r'\*\*Read more:\*\*\s*\*\*[^\*]+\*\*', '', text)
    
    # Remove header separator lines (------ or ======)
    text = re.sub(r'^[-=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
