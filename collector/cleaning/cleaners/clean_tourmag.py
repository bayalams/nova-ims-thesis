import re

def clean_tourmag(text, meta):
    """
    Cleaner for TourMag articles.
    Removes massive navigation header, sidebar content, and footer noise.
    """
    
    # 1. FIND ARTICLE START - Use title to skip header navigation
    title = meta.get('title', '').strip()
    if title:
        idx = text.find(title)
        if idx > 0:
            text = text[idx:]
    
    # 2. CUT FOOTER - Find these markers and cut everything after
    footer_markers = [
        "* Nos médias",
        "Site certifié",
        "[BROCHURES EN LIGNE]", 
        "Dans la même rubrique :",
        "1 2 3 4 5 Notez",
        "Notez  Dans la même rubrique",
        "Nouveau commentaire :",
        "Lu 0 fois",  # View count variants
    ]
    
    # Also cut at "Lu X fois" pattern using regex
    lu_match = re.search(r'Lu \d+ fois', text)
    if lu_match:
        text = text[:lu_match.start()]
    
    for marker in footer_markers:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
            
    # 3. LINE-BY-LINE CLEANING
    lines = text.split('\n')
    cleaned_lines = []
    
    skip_patterns = [
        r'^\* \[',           # Navigation menu items: * [Link](url)
        r'^---$',            # Horizontal rules
        r'^\|.*\|$',         # Table rows
        r'^!\[\]\(',         # Empty images
        r'^Rédigé par \[',   # Author line with link
        r'^Lu \d+ fois',     # View count
        r'^Publié par ',     # Author byline: "Publié par Amelia Brille"
        r'^Voir tous les articles',  # "Voir tous les articles d'..."
        r'^\* picto ',       # Social icons: "* picto Linkedin"
        r'^Ajoutez TourMaG', # Google Actualités promo
        r'^Google Actualités icône',
        r'^Image not found:', # Broken image placeholders
        r'^- / \d+',         # Image gallery counter: "- / 6"
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
            
        # Skip ad images: [![...](url)
        if s_line.startswith("[![") and "](http" in s_line:
            continue
            
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # 4. STRIP REMAINING LINK SYNTAX
    # Remove markdown image syntax
    text = re.sub(r'!\[.*?\]\([^)]*\)', '', text)
    # Keep text from links but remove URL: [text](url) -> text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    
    # 5. REMOVE INLINE NOISE PATTERNS
    # Author bylines: "Publié par Name Rédactrice TourMaG.com"
    text = re.sub(r'Publié par [^*]+Rédactrice? TourMaG\.com', '', text)
    # "Voir tous les articles d'..."
    text = re.sub(r"Voir tous les articles d'[^*]+", '', text)
    # Social icons
    text = re.sub(r'\* picto (Linkedin|email)', '', text)
    # Google Actualités promo
    text = re.sub(r'Ajoutez TourMaG à votre flux Google Actualités\s*Google Actualités icône', '', text)
    # Image not found placeholders
    text = re.sub(r'Image not found: https?://[^\s]+', '', text)
    # Image gallery counter: "- / 6"
    text = re.sub(r'- / \d+', '', text)
    # Brand news footers: "| | | | --- Autres articles..."
    text = re.sub(r'\| \| \| \| ---\s*Autres articles.*$', '', text, flags=re.DOTALL)
    # Also simpler variant: "--- Autres articles..."
    text = re.sub(r'---\s*Autres articles.*$', '', text, flags=re.DOTALL)
    # Paywall blocks: "TourMaG.compremium Pour..."
    text = re.sub(r'TourMaG\.compremium.*$', '', text, flags=re.DOTALL)
    # Social share blocks with | separators
    text = re.sub(r'\| facebook \| twitter \| youtube \|', '', text)
    text = re.sub(r'\| --- \| --- \| --- \|', '', text)
    # Standalone author name at end (common: "Author Name" as last line)
    # Strip trailing author byline: "AuthorName Rédacteur/Rédactrice"
    text = re.sub(r'\s+[A-Z][a-zéèêë]+ [A-Z][a-zéèêë]+\s*$', '', text)
    
    # 6. CLEAN UP
    # Remove multiple consecutive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove multiple consecutive spaces
    text = re.sub(r'  +', ' ', text)
    # Remove trailing table fragments: "www.site.fr | | | |"
    text = re.sub(r'\s*\|\s*(\|\s*)+$', '', text)
    
    return text.strip()
