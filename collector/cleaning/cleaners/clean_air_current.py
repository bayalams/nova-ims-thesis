"""
The Air Current Cleaner
=======================

Cleans articles from AIR_CURRENT source.
These articles have author avatars, newsletter signups, and WordPress footer noise.
"""

import re


def clean_air_current(text, meta):
    """
    Cleaner for AIR_CURRENT articles.
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
        
        # Skip author avatar images
        if "Avatar photo" in sline:
            continue
            
        # Skip "Share" buttons
        if sline == "Share":
            continue
            
        # Skip newsletter signup
        if "HEAR FROM THE AIR CURRENT" in sline:
            continue
        if "Leave this field empty if you're human" in sline:
            continue
            
        # Skip separator lines
        if re.match(r'^-{3,}$', sline):
            continue
            
        filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Footer Cleaning - cut at footer sections
    footer_markers = [
        "\nOur award-winning aerospace reporting",
        "\nZeen is a next generation WordPress",
        "\nStart typing to see results",
        "\n#### Privacy Overview",
        "\nNecessary\nNecessary",
        "\nSAVE & ACCEPT",
        "\nClose",
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    
    text = text[:first_idx]
    
    # 2. Post-processing cleanup
    
    # Remove author byline pattern: [Author Name](url)·
    text = re.sub(r'\[([^\]]+)\]\(https://theaircurrent\.com/author/[^\)]+\)\s*·', '', text)
    
    # Remove avatar image markdown
    text = re.sub(r'\[!\[Avatar photo\]\([^\)]+\)\]\([^\)]+\)', '', text)
    
    # Remove markdown images ![...](...) 
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    
    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove standalone dates like "·January 22, 2026"
    text = re.sub(r'^\s*·[A-Za-z]+ \d+, \d{4}\s*$', '', text, flags=re.MULTILINE)
    
    # Remove header separator lines (====)
    text = re.sub(r'^[=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
