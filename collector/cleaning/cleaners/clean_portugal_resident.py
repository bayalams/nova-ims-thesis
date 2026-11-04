import re
from .utils import remove_inline_noise

def clean_portugal_resident(text, meta):
    """
    Cleaner for Portugal Resident (English news about Portugal).
    Strategy:
    1. Header Trim: Find title or the PODCASTS menu item to start.
    2. Body: Keep content between header and footer triggers.
    3. Noise Reduction: Skip "Discover more" ad blocks and in-body links.
    4. Footer Trim: Remove social sharing, recidivists ads, and post boilerplate.
    """
    
    title = meta.get('title', '')
    
    print(f"Processing article '{title}'")
    
    # --- Header TrimStrategy ---
    # 1. Try to find the title
    clean_title = re.sub(r'<!\[CDATA\[|\]\]>', '', title).strip()
    # Normalize dashes (en-dash, em-dash to hyphen) for search
    search_title = clean_title.replace('–', '-').replace('—', '-')
    
    start_idx = 0
    
    if clean_title:
        # Try title as heading
        escaped = re.escape(clean_title)
        flexible_title = escaped.replace('-', '.').replace(r'\–', '.') 
        
        t_match = re.search(r'^#{1,3}\s+' + flexible_title, text, re.MULTILINE)
        if t_match:
            # Verify this title isn't too deep (likely a footer/sidebar title)
            if t_match.start() < 3000:
                start_idx = t_match.start()
        else:
            # Try plain find first
            t_idx = text.find(clean_title)
            
            # If failed, try normalized
            if t_idx == -1:
                 norm_text = text.replace('–', '-').replace('—', '-')
                 t_idx = norm_text.find(search_title)
            
            # Limit to 3000 chars to avoid finding title in "Latest News" sidebar at bottom (short articles)
            if t_idx != -1 and t_idx < 3000:
                start_idx = t_idx

    # 2. If title low confidence, use menu triggers
    if start_idx == 0:
        menu_triggers = ["PODCASTS", "Daily TV Guide", "Pet Corner", "Security"]
        temp_idx = 0
        for trig in menu_triggers:
            idx = text.find(trig) 
            # Ensure it's reasonable (e.g. within first 5k chars)
            if idx != -1 and idx < 5000:
                temp_idx = max(temp_idx, idx + len(trig))
        if temp_idx > 0:
            start_idx = temp_idx

    if start_idx > 0:
        text = text[start_idx:]

    lines = text.split('\n')
    clean_lines = []
    
    # Metadata extraction
    extracted_date = None
    
    footer_triggers = [
        "More information here",
        "The post",
        "More News",     # Sidebar start trigger
        "Share this:",
        # "Recaptcha" is good, but "protected by" is safer
        "protected by reCAPTCHA",
        "Newspaper editor at",
        "Journalist for the Portugal Resident",
        "More from Author",
        "Also read:",
        "Daily Newsletter (min. 3 x week)",
        "Weekly Newsletter",
        "Available in",
        "Related News",
        "Latest News",
        "Source: Lusa",
        "Source: LUSA",
        "Source material: LUSA",
        "Sign up for our free newsletters",
        "Country\\*", # Escaped for safety if regex used, but 'in' is string match. 
        "Country*",
    ]
    
    skip_patterns = [
        "Discover more",
        "guide",
        "Subscribe to Our Newsletter",
        "Skip to content",
        "Monday, January", "Tuesday, January", "Wednesday, January",
        "Thursday, January", "Friday, January", "Saturday, January", "Sunday, January",
        "Partly cloudy", "ºC", "Patchy rain", "Sunny", "Cloudy", "Rain", # Weather artifacts
        "googlesyndication.com", "pagead2",
        "Manage Notifications",
        "Your personal notification data",
        "Portugal Resident podcast",
        "PODCAST", "Podcast",
        "Newspaper subscription",
        "city break experiences",
        "retirement living options",
        "language courses",
        "Dual citizenship services",
        "Real estate listings",
        "Telecommunications plans",
        "cooking classes",
        "culture blog",
        "Looking for volunteers",
        "minutes ago", "hours ago", "day ago", "days ago",
        "Search for:",
        "Stay Connected",
        "Contributions",
        "Portugal news updates", "Local news alerts", "Algarve water co",
        "Shop Now", "Click Here", "LinkedIn", "Email", "Business Bytes",
        "U.S. Privacy",
        "Learn More](",
    ]
    
    in_article = True
    
    for line in lines:
        sline = line.strip()
        if not sline: continue
            
        low_sline = sline.lower()
        
        # 1. Metadata Extraction
        if not meta.get('published') and any(day in sline for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
            if any(month in sline for month in ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]):
                 extracted_date = sline
        
        # 2. explicit footer starts (Source/Author)
        # Check for Source/Sources at start of line
        if low_sline.startswith("source:") or low_sline.startswith("sources:"):
            in_article = False
            break
            
        # Check for Author Signature
        # Gather author names
        authors = []
        if meta.get('author'): authors.append(meta['author'])
        if meta.get('authors'):
             for a in meta['authors']:
                 if isinstance(a, dict) and a.get('name'): authors.append(a['name'])
                 elif isinstance(a, str): authors.append(a)
        
        for auth in authors:
             if not auth: continue
             # Check exact match or "By Author"
             if len(sline) < len(auth) + 10:
                 if auth.lower() in low_sline:
                      in_article = False
                      break
        if not in_article: break

        # 3. Footer break
        if any(trig.lower() in low_sline for trig in footer_triggers):
            # Special check for "The post... appeared first on" which is a common pattern
            if "the post" in low_sline and "appeared first on" in low_sline:
                in_article = False; break
            
            in_article = False
            break
                
        if not in_article: break
            
        # 3. Skip noise
        if any(pat.lower() in low_sline for pat in skip_patterns):
            continue

        # 3.1 Specific short noise
        if sline in ["* 0", "* 1", "*", "+", "-"]:
             continue
             
        # 3.2 Remove separator lines (------)
        if re.match(r'^[-=_]{3,}$', sline):
             continue
            
        # 4. Filter navigation lists (Specific Fix for "- Porto & North", etc)
        # These typically look like "* Home", "* News", "+ Portugal", "+ Sport"
        if re.match(r'^[-+\*•]\s+', sline) or sline[0] in ['-', '+', '*']:
             menu_terms = [
                 "Home", "News", "Portugal", "Events", "Food & Drink", "Gardening", 
                 "Health & Beauty", "Leisure", "Motoring", "Nature", "Pet Corner", 
                 "Travel", "Economy & Finance", "Education", "History", 
                 "Science & Technology", "Community", "Business", "Sport", "Politics",
                 "Opinion", "Lifestyle", "Property", "Security", "More", 
                 "Porto & North", "Centre", "Lisbon", "Alentejo", "Algarve", "Azores & Madeira"
             ]
             # Check if any menu term is present in this line
             if any(term in sline for term in menu_terms):
                 continue

        # 5. Link/Podcast scrubbing
        # Remove markdown image/link artifacts like [![Name]()!Name]
        if '[![' in sline and '](' in sline:
             continue
             
        sline = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', sline)
        sline = re.sub(r'\(https?://\S+\)', '', sline)
        sline = re.sub(r'\]\(https?://\S+\)', '', sline)
        sline = re.sub(r'https?://\S+', '', sline)
        
        if sline.startswith('[') and '|' in sline: continue
        if len(sline.split()) <= 1 and (sline in ["Menu", "Home", "News", "Share", "Next", "Close", "Search", "Search for:"] or sline.startswith("!")):
            continue
            
        clean_lines.append(sline)
    
    if extracted_date:
        meta['published'] = extracted_date
    
    text = '\n\n'.join(clean_lines)
    text = re.sub(r'\[\]|\( \)', '', text)
    text = remove_inline_noise(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
