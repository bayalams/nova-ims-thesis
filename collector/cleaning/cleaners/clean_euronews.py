
import re

def extract_euronews_tags(text):
    """
    Extracts tags from the footer area of Euronews articles.
    Pattern: * [Tag Name](/tag/...)
    """
    tags = []
    # Regex to find: * [Tag Name](URL)
    matches = re.findall(r'^\s*\*\s*\[([^\]]+)\]\(([^\)]+)\)\s*$', text, re.MULTILINE)
    
    for tag_name, url in matches:
        t = tag_name.strip()
        # Tags usually have /tag/ or /t/ in the URL
        if "/tag/" in url or "/etiqueta/" in url or "/topic/" in url:
             if t and "Ir para" not in t: 
                 tags.append(t)
            
    return tags

def clean_euronews(text, meta):
    """
    Cleaner for EURONEWS_NEWS.
    """
    # 0. Video Skip
    if '/video/' in meta.get('url', ''):
        return None
    
    # 0. Inline Cleanup (PRE-PROCESSING)
    
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        sline = line.strip()
        if not sline:
            filtered_lines.append(line)
            continue
            
        # Navigation (Handle raw markdown links: * [Ir para...)
        if "Ir para" in sline and sline.startswith("*"):
             continue
        if sline.startswith("Ir para"):
             continue
             
        # UI / Social Buttons
        # Use substring check for robustness
        social_garbage = ["Flipboard", "Send", "Linkedin", "Messenger", "Bluesky", "Telegram", "Threads", "Partilhar", "Publicidade", "Comentários"]
        if any(bad in sline for bad in social_garbage) and len(sline) < 30:
            continue
        if sline in ["Facebook", "Twitter", "Whatsapp"]:
             continue
            
        # Image artifacts
        if sline.startswith("!Logótipo") or sline.startswith("!Close Button"):
            continue
            
        # Metadata / Byline to Remove (User Request)
        # Author lines: "De Malek Fouda", "De Euronews", "De\xa0Escarlata..."
        # Regex: Start with De, followed by space/nbsp/bracket
        if re.search(r'^De[\s\xa0\[]', sline):
             continue
             
        # Timestamp: "05/01/2026 - 7:44 GMT+1"
        if re.match(r'^\d{2}/\d{2}/\d{4}\s*-\s*\d{1,2}:\d{2}\s*GMT', sline):
             continue
             
        # Comentários artifacts (often links: [Comentários](...))
        if "Comentários" in sline and (sline == "Comentários" or sline.startswith("[Comentários]")):
             continue

        if "Publicado a" in sline:
            continue
        # Also clean isolated date/time lines that weren't caught by main regex
        if re.match(r'^\d{2}/\d{2}/\d{4}.*GMT', sline):
             continue
        if re.match(r'^\d{1,2}:\d{2}$', sline): # 13:56
            continue
        if "Últimas notícias" in sline:
            continue
            
        # Disclaimer (User Request)
        if "traduzido com a ajuda de inteligência artificial" in sline:
            continue

        # Separator Lines (User Request)
        # Remove lines that are just dashes, equals, underscores (3 or more)
        if re.match(r'^[-=_]{3,}$', sline):
            continue

        filtered_lines.append(line)
        
    text = '\n'.join(filtered_lines)

    # 1. Header Cleaning (Block Cut)
    # --------------------------------------------------------------------------
    
    cut_candidates = []
    
    # 1. "Link copiado!" / Video Embed
    idx = text.find("Link copiado!")
    if idx != -1:
        cut_candidates.append(idx + len("Link copiado!"))
        
    idx = text.find("Copiar/colar o link embed do vídeo:")
    if idx != -1:
        cut_candidates.append(idx + len("Copiar/colar o link embed do vídeo:"))
    
    # 2. Social Media Links
    # Pattern: remove everything up to the last social link closing
    social_patterns = ["!facebook", "!twitter", "!whatsapp", "!linkedin", "!threads", "!bluesky", "!flipboard"]
    last_social_end = -1
    
    # Limit search to first 5000 chars to avoid cutting valid body links
    header_chunk = text[:5000].lower()
    
    for pat in social_patterns:
        # Find LAST occurrence of pattern
        pidx = header_chunk.rfind(pat)
        if pidx != -1:
            # Find the closing ')' for this link
            cidx = header_chunk.find(')', pidx)
            if cidx != -1:
                last_social_end = max(last_social_end, cidx + 1)
                
    if last_social_end != -1:
        cut_candidates.append(last_social_end)
        
    # 3. Separator Line (Fallback if social block is missing but line is there)
    match = re.search(r'^-{5,}$', text[:5000], re.MULTILINE)
    if match:
        cut_candidates.append(match.end())

    if cut_candidates:
        best_cut = max(cut_candidates)
        # But for Euronews video pages, the whole file IS noise.
        text = text[best_cut:]

    # 2. Footer Cleaning
    # --------------------------------------------------------------------------
    
    footer_markers = [
        "Mais vistas\n", 
        "\nMais vistas",
        "Notícias relacionadas\n",
        "\nNotícias relacionadas",
        "A nossa escolha\n",
        "\nA nossa escolha",
        "To use this website, please enable JavaScript",
        "Strictly necessary", 
        "Copyright ©",
        "\nComentários", # Strict newline required to avoid matching header link
        "Ir para os atalhos de acessibilidade",
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
            
    text = text[:first_idx]
    
    # 3. Post-Cleaning Cleanup
    # --------------------------------------------------------------------------
    
    # Remove remaining markdown images ![...](...)
    # This cleans up the social icons if the block cut wasn't perfect
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Remove remaining lines starting with '!'
    text = re.sub(r'^\s*!.*$', '', text, flags=re.MULTILINE)
    
    # Remove lines that are just '[' or ']' or '[]'
    text = re.sub(r'^\s*[\[\]]+\s*$', '', text, flags=re.MULTILINE)
    
    # Remove broken link artifacts starting with ](
    # Matches lines like: ](https://...), ](mailto:...), ](whatsapp:...)
    text = re.sub(r'^\s*\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)

    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Collapse Whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()
