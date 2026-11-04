import re

def clean_touristik_aktuell(text, meta):
    """
    Cleaner for Touristik Aktuell articles.
    Removes "Suche"/"Anzeige" headers, timestamp metadata, and footer noise/sidebars.
    """
    
    # 1. TRIM HEADER
    # Content typically starts with the Title.
    
    # 0. REMOVE LAYOUT TAGS
    # Users identified these as irrelevant: 'top-teaser', 'top-news'
    tags = meta.get('tags', [])
    if tags:
        meta['tags'] = [t for t in tags if t not in ['top-teaser', 'top-news']]
        
    title = meta.get('title', '').strip()
    if title:
        # Try exact match first
        idx = text.find(title)
        if idx != -1:
            text = text[idx:]
        else:
            # Try fuzzy match (sometimes title has different whitespace)
            # Normalize whitespace in both
            norm_title = ' '.join(title.split())
            norm_text = ' '.join(text.split())
            if norm_title in norm_text:
                # This is expensive to map back to original index, so fallback to regex
                # Try to find the title line roughly
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if len(line.strip()) > 10 and line.strip() in title:
                        # Start from this line
                        text = '\n'.join(lines[i:])
                        break
    
    # 2. TRIM FOOTER
    # Common artifacts identifying the end of the article:
    # - "terstützer hat – viele fürchten deutliche Nachteile..." (Sidebar artifact)
    # - "### [Link Title](url)" (Related articles block)
    # - "#### Newsletter"
    # - Carousel arrows
    
    footer_patterns = [
        r"terstützer hat – viele fürchten",
        r"### \[.*\]\(.*touristik-aktuell\.de.*\)", 
        r"#### Newsletter",
        r"\n×\n",
        r"\n❮\n",
        r"Vorheriger Artikel",
        r"Nächster Artikel",
        r"\[Copy URL\]",
        r"#### Verwandte Themen",
        r"\[Facebook\]\(https://www\.facebook\.com/sharer",
        r"\[Email\]\(mailto:",
        r"\nTeilen\n",
        r"\*\*Special in touristik aktuell\*\*",
        r"Mehr Beiträge, Updates und Infos zu den Angeboten",
    ]
    
    for pattern in footer_patterns:
        match = re.search(pattern, text)
        if match:
            text = text[:match.start()]
            
    # 3. START AFTER DATE (Remove Author/Image noise at top)
    # The clean article usually has Title -> Image -> Author -> Date -> Category -> Content
    # Look for Date line: DD.MM.YYYY
    date_match = re.search(r'\n(\d{2}\.\d{2}\.\d{4})\s*\n', text)
    if date_match:
        # Check if this date is in the first 1000 chars (likely the header date)
        if date_match.start() < 1000:
            # Cut everything before and including the date
            # But wait, there might be a category link after date.
            text = text[date_match.end():]
            
            # Also remove the next line if it's a category link like [Category](url)
            # Pattern: ^\[.*\]\(.*\)$
            lines = text.split('\n')
            if lines and re.match(r'^\s*\[.*\]\(.*\)\s*$', lines[0]):
                text = '\n'.join(lines[1:])
                
            # If the next line is empty, skip it
            text = text.lstrip()

    # 4. ADDITIONAL NOISE REMOVAL
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        s_line = line.strip()
        
        # Skip "Suche", "Anzeige", "Suchbegriff"
        if s_line in ["Suche", "Anzeige", "Suchbegriff", "Menü"]:
            continue
            
        # Skip inline promotional links
        if re.search(r"Link anmelden|mailworx|bit\.ly", s_line, re.IGNORECASE):
            continue

        # Skip known repetitive sidebar artifacts if they weren't caught by footer
        if "Mietwagen: Starcar steht vor dem Aus" in s_line:
            continue
            
        cleaned_lines.append(line)
        
    text = '\n'.join(cleaned_lines)
    
    # 5. STRIP ALL LINKS
    # Remove images first: ![alt](url) -> empty
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Convert [text](url) to just text
    # Use NON-GREEDY match for the content in brackets to avoid over-matching
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    
    return text.strip()
