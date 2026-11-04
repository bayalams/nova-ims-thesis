import re

def clean_travel_leisure(text, meta):
    """
    Cleaner for Travel + Leisure articles.
    Removes H1 underlines, author bios, photo credits, GDPR consent banners, and cookie UI.
    """
    
    # 1. CUT FOOTER - Privacy/Cookie consent banners and newsletter
    footer_markers = [
        "We Care About Your Privacy",
        "List of Partners (vendors)",
        "Accept All Reject All Show Purposes",
        "### We and our partners process data",
        "Object to Legitimate Interests",
        "### Cookie List",
        "Confirm My Choices",
        "Newsletter Sign Up",
    ]
    
    for marker in footer_markers:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
    
    # Cut related articles block - starts with image link blocks
    # Pattern: \n\n[![ indicates start of related articles section
    related_idx = text.find('\n\n[![')
    if related_idx > 0:
        text = text[:related_idx]
    
    # 2. FIND ARTICLE START - Use title to skip any header noise
    title = meta.get('title', '').strip()
    if title:
        idx = text.find(title)
        if idx > 0:
            text = text[idx:]
    
    # 3. REMOVE IMAGE MARKDOWN (multiple formats)
    # Format: ![alt:max_bytes(150000):strip_icc():format(webp)/path] or similar
    text = re.sub(r'!\[[^\]]*:max_bytes[^\]]*\](?:\([^)]*\))?', '', text)
    # Standard image markdown: ![alt](url)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    # Broken image refs: ![alt text
    text = re.sub(r'^!\[[^\]]+\n', '', text, flags=re.MULTILINE)
    # Standalone :max_bytes fragments (leftover from broken markdown) - catch all extensions
    text = re.sub(r':max_bytes\([^)]+\):[^\n]+\.(jpg|png|webp|jpeg|JPG|PNG)\)?', '', text)
    # Photographer credits: "Name Name/Getty Images" or "Name/Source"
    text = re.sub(r'^[A-Z][a-zéèêë]+ [A-Z][a-zéèêë]+/[A-Za-z &]+$', '', text, flags=re.MULTILINE)
    # Single word credit sources: "Getty Images"
    text = re.sub(r'^Getty Images$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^Travel \+ Leisure$', '', text, flags=re.MULTILINE)
    
    # 4. LINE-BY-LINE CLEANING
    lines = text.split('\n')
    cleaned_lines = []
    
    skip_patterns = [
        r'^={3,}$',                  # H1 underline: ===
        r'^-{3,}$',                  # H2 underline: --- or horizontal rules
        r'^By$',                     # Standalone "By" line
        r'^Close$',                  # Close button text
        r'^Credit:',                 # Photo credit
        r'^Updated on \w+',          # "Updated on December 12..."
        r'^Published on \w+',        # "Published on December 12..."
        r'^In This Article$',        # Article navigation
        r'^View All$',               # View all link
        r'^\[\d+$',                  # Comment count: "[2"
        r'^Comments\]',              # Comment link
        r'^### Key Takeaway$',       # Summary section header
        r'^\* \[',                   # Table of contents: * [Section]
        r'^\[Leave a Comment\]',     # Comment link
        r'^\[Travel \+ Leisure Editorial', # Editorial guidelines link
        r'^Newsletter Sign Up$',     # Newsletter signup
        r'^Read more:$',             # Read more link
        r'^Comments$',               # Comments section header
        r'^Account$',                # Account section
        r'^All comments are subject', # Comment guidelines
    ]
    
    for line in lines:
        s_line = line.strip()
        if not s_line:
            continue
            
        # Skip matching patterns
        skip = False
        for pattern in skip_patterns:
            if re.match(pattern, s_line):
                skip = True
                break
        if skip:
            continue
        
        # Strip markdown links from line for checking content: [Text](url) -> Text
        # It's safer to just look at the text content for the decision.
        content_only = re.sub(r'\[([^\]]+)\]\(.*?\)', r'\1', s_line).strip()
        
        # Skip author bio lines - check content_only
        bio_indicators = ['writer', 'journalist', 'appeared in', 'contributing author', 
                         'stories have appeared', 'work has appeared', 'freelance',
                         'years of experience', 'editor who']
        if any(ind in content_only.lower() for ind in bio_indicators):
            continue
        
        # Skip photographer credits based on content_only
        if re.match(r'^[A-Z][a-zéèêë]+( [A-Z][a-zéèêë]+)*/[A-Za-z &\+]+$', content_only):
            continue
        
        # Skip standalone author names based on content_only
        if len(content_only) < 40 and len(content_only) > 3:
            words = content_only.split()
            # Allow 2-3 words (First Last, First Middle Last)
            if len(words) in [2, 3] and all(w[0].isupper() for w in words if w):
                # Check it's not a sentence
                if not any(c in content_only for c in '.,;:!?[]()') and content_only.lower() not in ['a', 'the', 'an']:
                    continue
            
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # 5. REMOVE INLINE NOISE
    # Remove markdown links but keep text: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\(/[^)]+\)', r'\1', text)  # Relative URLs
    # Remove standalone URLs
    text = re.sub(r'https://www\.travelandleisure\.com/[^\s\)]+', '', text)
    # Remove empty link brackets: [text]()
    text = re.sub(r'\[([^\]]+)\]\(\)', r'\1', text)
    # Remove GDPR elements
    text = re.sub(r'checkbox label label', '', text)
    text = re.sub(r'Consent Leg\.Interest', '', text)
    
    # 6. CLEAN UP
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    
    return text.strip()
