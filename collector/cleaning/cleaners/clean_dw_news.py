"""
DW News (Deutsche Welle) Cleaner
================================

Cleans articles from DW_NEWS source.
DW articles in markdown format have navigation, related articles, and footer noise.
"""

import re


def clean_dw_news(text, meta):
    """
    Cleaner for DW_NEWS articles.
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
        
        # Skip navigation lines
        if sline.startswith("1. [Skip to") or sline.startswith("2. [Skip to") or sline.startswith("3. [Skip to"):
            continue
        if "Skip to content" in sline or "Skip to main menu" in sline or "Skip to more DW sites" in sline:
            continue
            
        # Skip header navigation sections
        if sline in ["Regions", "Topics", "Categories", "In focus"]:
            continue
            
        # Skip social/share buttons
        if sline in ["Copy link", "Share"]:
            continue
        if "https://p.dw.com/p/" in sline and len(sline) < 50:
            continue
            
        # Skip "You need to enable JavaScript" message
        if "You need to enable JavaScript" in sline:
            continue
            
        # Skip image captions that are just photo credits
        if sline.startswith("Image:") and len(sline) < 150:
            continue
            
        # Skip "Edited by:" lines
        if sline.startswith("*Edited by:"):
            continue
        if sline.startswith("Edited by:"):
            continue
            
        filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Header Cleaning
    # Cut from title (if present in meta)
    title = meta.get('title', '')
    if title and title in text:
        idx = text.find(title)
        if idx != -1 and idx < 500:
            text = text[idx:]
    
    # 2. Footer Cleaning - cut at related articles section
    footer_markers = [
        "\nExplore more\n",
        "Explore more\n------------",
        "\nShow more stories",
        "\nRelated topics",
        "Related topics\n--------------",
        "\n### [",  # Start of related article cards
        "Show more stories",
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    
    text = text[:first_idx]
    
    # 3. Post-processing cleanup
    
    # Remove video embeds inside links: [![To view this video...](data:...)](url)
    # Pattern: [![...](data:image...)](/url) 
    text = re.sub(r'\[!\[.*?enable JavaScript.*?\]\(data:image[^\)]+\)\]\([^\)]+\)', '', text, flags=re.DOTALL)
    text = re.sub(r'\[!\[.*?supports HTML5 video.*?\]\([^\)]+\)\]\([^\)]+\)', '', text, flags=re.DOTALL)
    
    # Also remove standalone video embeds: ![...](data:image...)
    text = re.sub(r'!\[.*?enable JavaScript.*?\]\(data:image[^\)]+\)', '', text, flags=re.DOTALL)
    
    # Remove markdown images ![...](...) 
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    
    # Remove standalone video timestamps like "10:51" or "05:30"
    text = re.sub(r'^\s*\d{1,2}:\d{2}\s*$', '', text, flags=re.MULTILINE)
    
    # Remove orphaned empty links like [](https://...)
    text = re.sub(r'\[\s*\]\([^\)]+\)', '', text)
    
    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove header separator lines (------ or ======)
    text = re.sub(r'^[-=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
