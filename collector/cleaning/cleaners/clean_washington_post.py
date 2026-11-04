import re

def clean_washington_post(text, meta):
    """
    Cleaner for Washington Post articles.
    
    Removes:
    - "Democracy Dies in Darkness" header
    - "By [Name]" lines and author bios
    - "Comments" footer and subsequent text
    - "Share" social blocks
    - Inline links
    """
    
    # 1. REMOVE FOOTER (Aggressive cutoff)
    # -------------------------------------------------------------------------
    footer_markers = [
        "**Comments**",
        "**Comments**\n",
        "\nComments\n", 
        "Gift Article", 
        "Share", 
        "HAND CURATED",
        "Sign in to join the conversation",
        "Show more comments"
    ]
    
    for marker in footer_markers:
        if marker in text:
            text = text.split(marker)[0]

    # 2. LINE-BY-LINE CLEANING
    # -------------------------------------------------------------------------
    lines = text.split('\n')
    cleaned_lines = []
    
    skip_patterns = [
        r'^Democracy Dies in Darkness',   # Header slogan
        r'^Listening\.+$',                # Audio player text
        r'^\d+ min$',                     # Reading time
        r'^Share$',                       # Social share button
        r'^Gift Article$',                # Paywall/gift link
        r'^By ',                          # Author bylines
        r'^Updated ',                     # Updated date
        r'^Published ',                   # Published date
        r'^HAND CURATED',                 # Hand curated section
        r'^Sign in to join',              # Comments prompt
        r'^Show more comments',           # Comments prompt
        r'^Accessibility statement',      # Header info
        r'^Skip to main content',         # Header info
        r'^Sign in',                      # Header info
        r'^!\[.*\]\(.*arc-authors.*\)',  # Author bio images (check URL part)
        r'^!\[.*Ask The Post AI.*\]'      # AI prompt
    ]
    
    for line in lines:
        s_line = line.strip()
        if not s_line:
            continue
            
        # Strip markdown links for checking: [Text](url) -> Text
        content_only = re.sub(r'\[([^\]]+)\]\(.*?\)', r'\1', s_line).strip()
        
        # Skip matching patterns
        skip = False
        for pattern in skip_patterns:
            if re.match(pattern, s_line) or re.match(pattern, content_only):
                skip = True
                break
        
        if skip:
            continue
            
        cleaned_lines.append(line)
        
    text = '\n'.join(cleaned_lines)
    
    # 3. INLINE CLEANING
    # -------------------------------------------------------------------------
    # Remove markdown links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
