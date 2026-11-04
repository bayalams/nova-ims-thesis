"""
France24 Cleaner
================

Cleans articles from FRANCE24 source.
France24 articles have navigation, related articles, "Most read" sections, and footer noise.
"""

import re


def clean_france24(text, meta):
    """
    Cleaner for FRANCE24 articles.
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
        
        # Skip "Issued on:" timestamp lines
        if sline.startswith("Issued on:"):
            continue
            
        # Skip reading time lines
        if re.match(r'^\d+ min Reading time$', sline):
            continue
        if sline == "Reading time":
            continue
            
        # Skip author line "By:" or "Video by:"
        if sline in ["By:", "Video by:"]:
            continue
            
        # Skip image attribution lines
        if sline.startswith("©") and len(sline) < 150:
            continue
            
        # Skip cookie consent / privacy patterns
        if sline in ["Accept", "Deny", "CustomizeDenyAccept"]:
            continue
        if "Manage my choices" in sline:
            continue
        if "your personal data" in sline.lower():
            continue
        if "your consent" in sline.lower() and len(sline) < 200:
            continue
        if re.match(r'^See our \d+ partners$', sline):
            continue
        if "advertising and content" in sline.lower():
            continue
        if "audience research" in sline.lower():
            continue
            
        # Skip video player messages
        if "browser extensions" in sline.lower() and "video player" in sline.lower():
            continue
        if sline == "Try again":
            continue
        if re.match(r'^\d{2}:\d{2}$', sline):  # Video timestamps like "05:40"
            continue
        if re.match(r'^\d{2}:\d{2} min$', sline):  # "05:40 min"
            continue
        if re.match(r'^Play \(\d{2}:\d{2} min\)$', sline):  # "Play (05:40 min)"
            continue
            
        # Skip section labels that are standalone
        if sline in ["Africa", "Americas", "Europe", "Asia / Pacific", "France", "Sport", 
                     "Middle East", "Business", "Culture", "Environment", "Health", "Technology",
                     "In pictures", "As it happened", "Live", "RUSSIA"]:
            continue
            
        # Skip advertising label and navigation
        if sline in ["Advertising", "All episodes", "Most watched", "On the same topic",
                     "From the show", "Read more", "Read less", "Related keywords"]:
            continue
            
        # Skip show titles / branding
        if "© FRANCE 24" in sline or "© France 24" in sline:
            continue
            
        filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Header Cleaning
    # France24 articles start with title as h1 (====)
    title = meta.get('title', '')
    if title:
        # Try to find title-like header
        title_pattern = re.escape(title[:50]) if len(title) > 50 else re.escape(title)
        match = re.search(title_pattern, text[:1000], re.IGNORECASE)
        if match:
            text = text[match.start():]
    
    # 2. Footer Cleaning - cut at related content
    footer_markers = [
        "\nRead next\n",
        "Read next\n[",
        "\nToday's top stories",
        "\nMost read\n",
        "Most read\n1.",
        "\nKeywords for this article",
        "\nPage not found",
        "The content you requested does not exist",
        "\n*(FRANCE 24",  # Source attribution often at article end
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    
    text = text[:first_idx]
    
    # 3. Clean up specific patterns
    
    # Remove markdown images ![...](...) 
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Remove article card patterns: ### [Title...](/path "Title...")
    text = re.sub(r'###\s*\[[^\]]+\]\([^\)]+\)', '', text)
    
    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove header separator lines (====== or ------)
    text = re.sub(r'^[=]{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-]{3,}$', '', text, flags=re.MULTILINE)
    
    # Remove numbered list patterns for "Most read" etc (1. 2. 3. with brackets)
    text = re.sub(r'^\d+\.\s*\d+$', '', text, flags=re.MULTILINE)
    
    # Remove standalone section headers like "Africa" after links
    text = re.sub(r'^(Africa|Europe|Americas|France|Sport|Middle East)\s*$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
