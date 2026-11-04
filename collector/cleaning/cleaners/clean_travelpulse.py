"""
TravelPulse Cleaner
====================

Cleans articles from TRAVELPULSE source.
US travel trade publication with navigation menus, author bios,
related stories sidebars, and newsletter signup blocks.
"""

import re


def clean_travelpulse(text, meta):
    """
    Cleaner for TRAVELPULSE articles.
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
        if sline in ["Destinations", "Hotels & Resorts", "Airlines", "Cruises",
                      "Tour Operators", "Agents", "Insurance", "Luxury",
                      "Advisor Tips", "Industry", "Technology",
                      "All Destinations", "All Hotels & Resorts", "All Airlines",
                      "All Cruises", "News", "Features", "Reviews",
                      "Subscribe", "Login", "Register", "Menu",
                      "Search", "Close"]:
            continue
            
        # Skip social sharing buttons
        if sline in ["Share", "Tweet", "Email", "Print", "Comments"]:
            continue
            
        # Skip "By [Author]" lines that are just attribution noise at top
        # (Keep author info if it's part of content)
        
        # Skip newsletter prompts
        if "Get the most important travel news" in sline:
            continue
        if "Sign up for our newsletter" in sline:
            continue
        if "Enter your email" in sline and len(sline) < 80:
            continue
            
        # Skip separator lines
        if re.match(r'^-{3,}$', sline):
            continue
            
        if skip_until_content and len(sline) > 50:
            skip_until_content = False
            
        if not skip_until_content:
            filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Footer Cleaning - cut at footer sections
    footer_markers = [
        "\nRelated Stories",
        "\n### Related Stories",
        "\n## Related Stories",
        "\nTrending Stories",
        "\n### Trending",
        "\nRecommended For You",
        "\nMost Popular",
        "\n### Most Popular",
        "\nAbout the Author",
        "\n### About the Author",
        "\nRead Next",
        "\n### Read Next",
        "\nTags:",
        "\n### Tags",
        "\nJoin the Discussion",
        "\nLeave a Comment",
        "\nSign up for our newsletter",
        "\n### Newsletter",
        "\nAdvertisement",
        "\nSponsored Content",
        "\nMore From TravelPulse",
        "\n### More From TravelPulse",
        "\n© TravelPulse",
        "\n© Copyright",
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
    
    # Remove "RELATED:" or "SEE ALSO:" inline callouts
    text = re.sub(r'^\s*(?:RELATED|SEE ALSO|READ MORE)\s*:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Remove header separator lines (------ or ======)
    text = re.sub(r'^[-=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
