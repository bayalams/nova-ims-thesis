
import re
from datetime import datetime, timedelta
from .utils import trim_header_by_title, remove_inline_noise

MAX_AGE_DAYS = 90

def clean_guardian(text, meta):
    """
    Cleaner for Guardian (General & Travel).
    Strategy:
    1. Trim Header: Find title, cut before. Remove post-title meta (Date, Share).
    2. Trim Footer: 'Explore more on these topics', 'Most viewed', 'Comments', Subscription pleas.
    3. Inline: Remove 'Key events', 'Share' links, caption artifacts.
    """
    
    # 00a. Freshness Filter (90 days)
    raw_date = meta.get('date') or meta.get('updated', '')
    if raw_date:
        try:
            article_date = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
            cutoff = datetime.now(article_date.tzinfo) - timedelta(days=MAX_AGE_DAYS)
            if article_date < cutoff:
                return ""  # Article too old
        except (ValueError, TypeError):
            pass  # If date parsing fails, keep the article
    
    # 00. Content Filtering (News & Travel ONLY)
    # User Request: "Focus on news and travel, nothing else." (Exclude Wellness, Nutrition, Sport, etc.)
    tags = meta.get('tags', [])
    if not tags:
        tags = []
        
    # Categories to EXPLICITLY BLOCK (Strong Filter)
    block_keywords = {
        'Health', 'Wellness', 'Nutrition', 'Food', 'Recipes', 'Life and style', 
        'Fashion', 'Beauty', 'Sport', 'Football', 'Tennis', 'Cricket', 'Rugby', 
        'Culture', 'Music', 'Film', 'Television', 'Books', 'Stage'
    }
    
    # Categories to KEEP (Allowlist)
    # Note: 'Travel' is a strong keep. 'News' variants are strong keeps.
    allow_keywords = {
        'Travel', 'Places', 'Holidays', 'Destinations', # Travel
        'News', 'Politics', 'World', 'UK', 'US', 'Europe', # Core News
        'Environment', 'Science', 'Technology', 'Business', 'Money', # Hard Topics
        'Education', 'Society', 'Law', 'Consumer affairs'
    }
    
    # Check Tags
    # 1. Flatten tags for checking
    flat_tags = " ".join(tags).lower()
    
    # 2. Check overlap
    has_allowed = any(k.lower() in flat_tags for k in allow_keywords)
    has_blocked = any(k.lower() in flat_tags for k in block_keywords)
    
    # Logic: 
    
    if has_allowed:
        pass # Keep! Priority to News/Travel.
    elif has_blocked:
        return "" # Explicitly blocked (Wellness, Sport, etc.) and NOT News/Travel.
    else:
        return ""

    # 0. Header Trim (Title based)
    title = meta.get('title', '')
    if title:
        text = trim_header_by_title(text, title)

    lines = text.split('\n')
    clean_lines = []
    
    # Flags / State
    in_key_events = False
    
    # Footer Triggers (Hard Stop)
    footer_triggers = [
        "Explore more on these topics",
        "Most viewed",
        "Comments (…)", 
        "Sign in or create your Guardian account",
        "Reuse this content",
        "Independent, quality original journalism needs your support",
        "If you already have Guardian Ad-Lite",
        "Personalised advertising", 
        "Please choose an option" # support banner
    ]
    
    skip_exact = {
        "Share", "Live", "Updated", "Show key events only", 
        "Please turn on JavaScript to use this feature", 
        "Close dialogue", "Next image", "Previous image", "Toggle caption"
    }
    
    # Regex for "Mon 12 Jan 2026..." date lines
    # Updated to handle "ESTLast" fusion and varied timezones
    date_line_pattern = re.compile(r'^\w{3} \d{1,2} \w{3} \d{4} \d{2}\.\d{2} \w+')

    for i, line in enumerate(lines):
        sline = line.strip()
        
        # Footer Check
        if any(trig in sline for trig in footer_triggers):
            if "Explore more on these topics" in sline or "Most viewed" in sline:
                break
            break
            
        # Skip noise lines
        if sline in skip_exact:
            continue
            
        # Loose match for "Share" if it's just that word
        if sline == "Share":
            continue

        # Skip Date Lines at the start (context metadata)
        if i < 25 and date_line_pattern.match(sline):
            continue
            
        # Skip "Key events" headers or bullets in Live feeds
        if sline == "Key events" or sline == "Show key events only":
            in_key_events = True
            continue
        
        if in_key_events:
            # If line starts with bullet and link/time, it's a TOC item
            if sline.startswith('* [') and 'ago' in sline:
                continue
            # If line is empty, skip
            if not sline:
                continue
            if len(sline) > 100: 
                 in_key_events = False
            if not sline.startswith('*'):
                 in_key_events = False
        
        # Skip Image Carousel artifacts (Robust check)
        if sline.startswith("Close dialogue") or "Next imagePrevious image" in sline:
            continue

        # Skip [Share](mailto:...) links
        if "[Share](mailto:?" in sline:
            continue
            
        clean_lines.append(line)

    text = '\n'.join(clean_lines)
    
    # Post-processing inline noise
    text = remove_inline_noise(text)
    
    # Strip Markdown Links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove horizontal rule markers (---) and heading underlines (===)
    text = re.sub(r'^[=\-]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text
