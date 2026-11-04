import re
from .utils import remove_inline_noise

def clean_portugal_news(text, meta):
    """
    Cleaner for The Portugal News (English news about Portugal).
    Strategy:
    1. Header Trim: Find title heading (skip the nav link version).
    2. Body: Keep article content between title and footer.
    3. Footer Trim: Remove sponsored content, recommendations, ads, tracking pixels.
    """
    
    title = meta.get('title', '')
    
    # Custom header trim for Portugal News
    # Title appears twice: first as nav link [Title](/url), then as heading
    if title and len(title) > 10:
        title_lower = title.lower()
        first_idx = text.lower().find(title_lower)
        if first_idx != -1 and first_idx < 8000:
            # Look for second occurrence (the heading)
            second_idx = text.lower().find(title_lower, first_idx + len(title))
            if second_idx != -1 and second_idx < 10000:
                text = text[second_idx:]
            else:
                # Fallback to first occurrence
                text = text[first_idx:]
    
    # --- Metadata Extraction Enhancement ---
    # TPN often has metadata in the body: "in [Section] ·", "DD MMM YYYY, HH:MM"
    if not meta.get('tags'):
        tag_match = re.search(r'in ([^·\n]+) ·', text)
        if tag_match:
            tag = tag_match.group(1).strip()
            # Split by comma if multiple: "News, Madeira & Azores"
            meta['tags'] = [t.strip() for t in tag.split(',')]
            
    if not (meta.get('published') or meta.get('date')):
        # Match "15 Jan 2026, 13:59"
        date_match = re.search(r'(\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2})', text)
        if date_match:
            meta['published'] = date_match.group(1)
    # ----------------------------------------
    
    lines = text.split('\n')
    clean_lines = []
    
    # Footer triggers (hard stop)
    footer_triggers = [
        "### More in",
        "← Return to previous page",
        "[Sponsored]",
        "Sponsored",
        "You May Like",
        "Related Articles",
        "taboola.com",
        "© 2026 The Portugal News",
        "© 2025 The Portugal News",
        "Established 1977",
        "![](https://sync",
        "![](https://router",
        "![](https://ib.adnxs",
        "![](https://ap.lijit",
        "![](https://image8.pubmatic",
        "![](https://ssum-sec",
        "![](https://onetag",
        "![](https://cs.media",
        "![](https://cms.quantserve",
        "![](https://p.rfihub",
        "![](https://ssp.disqus",
        "![](https://ssc-cms",
        "![](https://user-sync",
        "Share this article:",
    ]
    
    # Skip patterns (noise lines)
    skip_patterns = [
        "Print Edition",
        "Classifieds",
        "propertiesinportugal.com",
        "[Newsletter]",
        "/newsletter?cid=",
        "[Careers]",
        "[Contacts]",
        "[Advertise]",
        "[Latest]",
        "[Distribution]",
        "db6izv6031456.cloudfront.net",  # TPN CDN images
        "The Portugal News logo",
        "![Search]",
        "![Globe]",
        "![Angle down]",
        "![Facebook]",
        "![Twitter]",
        "![Linkedin]",
        "![Instagram]",
        "![Whatsapp]",
        "![X]",
        "/epaper/",
        "[Home](/)",
        "[GAMES]",
        "games.theportugalnews.com",
        "share-facebook.svg",
        "share-twitter",
        "share-linkedin",
        "share-whatsapp",
        "### This week's issue",
        "· [0 Comments]",
        "· [1 Comment]",
        "· [",  # Comments link
        # Navigation sections
        "* [News](/news",
        "* [Portugal](/news/portugal",
        "* [World](/news/world",
        "* [Business](/news/business",
        "* [Invest](/news/invest",
        "* [Lifestyle](/news/lifestyle",
        "* [Sport](/news/sport",
        "* [Travel](/news/travel",
        "* [Culture](/news/culture",
        "* [Tech](/news/tech",
        "* [Crypto](/news/crypto",
        "* [Golden Visa](",
        "* [Portugal Visas](",
        "* [Residency by Investment](",
        "* [Exclusives](",
        "* [Latest News](",
        "* [Events](",
        "+ [All](",
        "+ [Algarve](",
        "+ [Lisbon](",
        "+ [Porto",
        "+ [Alentejo](",
        "+ [Central](",
        "+ [Madeira",
        "+ [Europe](",
        "+ [Ireland](",
        "+ [United Kingdom](",
        "+ [North America](",
        "+ [South America](",
        "+ [Asia](",
        "+ [Africa](",
        "+ [Economy](",
        "+ [Company News](",
        "+ [Finance](",
        "+ [Consumer Rights](",
    ]
    
    for line in lines:
        sline = line.strip()
        
        # Skip empty
        if not sline:
            continue
        
        # Footer check
        if any(trig in sline for trig in footer_triggers):
            break
        
        # Skip noise
        if any(pat in sline for pat in skip_patterns):
            continue
        
        # Skip navigation bullet lists (common pattern)
        if sline.startswith('* [') and '](' in sline and sline.endswith(')'):
            continue
        
        # Skip sub-navigation
        if sline.startswith('+ [') and '](' in sline and sline.endswith(')'):
            continue
        
        # Skip markdown images (ads, logos)
        if sline.startswith('![') and sline.endswith(')'):
            continue
        
        # Skip lines that are just "---" or "==="
        if re.match(r'^[=\-]{3,}$', sline):
            continue
        
        # Skip "Share" standalone
        if sline == "Share":
            continue
            
        # Skip TPN metadata lines (Author, Section, Date, Credits)
        if sline.startswith('By ') and sline.endswith(','):
            continue
        if sline.startswith('in ') and sline.endswith(' ·'):
            continue
        if re.match(r'^\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}$', sline):
            continue
        if sline.startswith('Credits: ') or sline.startswith('Author: '):
            continue
        
        clean_lines.append(line)
    
    text = '\n'.join(clean_lines)
    
    # Post-processing
    text = remove_inline_noise(text)
    
    # Strip Markdown Links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove tracking pixels that leaked
    text = re.sub(r'!\[\]\(https?://[^\)]+\)', '', text)
    
    # Remove horizontal rules
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^===+$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

