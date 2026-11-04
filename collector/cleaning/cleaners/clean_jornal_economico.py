import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_jornal_economico(text, meta):
    """
    Cleaner for Jornal Económico (Portuguese business news).
    Strategy:
    1. Filter out Opinion, Podcasts, and Multimedia
    2. Remove header junk (weglot, tables, search)
    3. Find article title and extract content after it
    4. Remove footer junk (RELACIONADO, RECOMENDADO)
    """
    
    # 0. Filtering: Opinion and Multimedia
    tags = meta.get('tags', [])
    if not isinstance(tags, list):
        tags = []
    
    # Check tags/keywords
    exclude_keywords = [
        'opinião', 'opiniao', 'podcast', 'multimédia', 'multimedia', 
        'vídeo', 'video', 'fotogaleria'
    ]
    
    # URL checks
    url = meta.get('link', '').lower()
    if any(k in url for k in ['/opiniao/', '/multimedia/', '/podcasts/']):
        return ""

    if tags:
        tags_lower = [t.lower() for t in tags]
        if any(k in t for k in exclude_keywords for t in tags_lower):
             if any(k in t for k in exclude_keywords):
                 return ""
                 
    title = meta.get('title', '').strip().lower()
    if title.startswith('opinião') or 'podcast' in title:
        return ""

    # Tag Enrichment (Keyword-based fallback)
    if not tags:
        new_tags = []
        text_lower = text.lower()
        title_lower = meta.get('title', '').lower()
        content_sample = title_lower + " " + text_lower[:2000] # Check title and first 2k chars
        
        keywords_map = {
            'Economia': ['pib', 'inflação', 'bce', 'juros', 'taxa', 'orçamento', 'fisco', 'impostos', 'dívida', 'banco central'],
            'Mercados': ['bolsa', 'psi', 'psi20', 'ações', 'wall street', 'investidores', 'cotada', 'acionista'],
            'Empresas': ['lucros', 'resultados', 'ceo', 'fusão', 'aquisição', 'volume de negócios', 'empresa'],
            'Política': ['governo', 'ministro', 'parlamento', 'eleições', 'partido', 'deputado', 'primeiro-ministro'],
            'Tecnologia': ['inteligência artificial', 'ia', 'tecnologia', 'digital', 'startup', 'software', 'google', 'apple', 'microsoft'],
            'Imobiliário': ['casas', 'habitação', 'rendas', 'imóveis', 'construção'],
            'Energia': ['petróleo', 'gás', 'eletricidade', 'renováveis', 'galp', 'edp'],
        }
        
        for category, keywords in keywords_map.items():
            for kw in keywords:
                if kw in content_sample:
                    new_tags.append(category)
                    break # One match per category is enough
        
        if new_tags:
            meta['tags'] = new_tags

    # 1. Pre-process: Remove Markdown Images
    text = re.sub(r'!\[.*?\]\([^\)]+\)', '', text)
    
    # Pre-process: Remove ALL links (keep text)
    text = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    
    # 2. Remove specific header/navigation junk lines
    lines = text.split('\n')
    cleaned_lines = []
    
    noise_patterns = [
        r'^\[weglot_switcher\]',
        r'^\|.*\|$',  # Markdown table lines (often used for layout/menu in raw text)
        r'^search$',
        r'^×$',
        r'^Assine$',
        r'^Entrar$',
        r'^Menu$',
    ]
    
    for line in lines:
        sline = line.strip()
        if not sline:
            cleaned_lines.append(line)
            continue
            
        is_noise = False
        for pattern in noise_patterns:
            if re.match(pattern, sline, re.IGNORECASE):
                is_noise = True
                break
        
        if is_noise:
            continue
            
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # 3. Try to find the article content start (after title)
    title = meta.get('title', '')
    if title:
        # Normalize title and text for matching (case insensitive, ignore special chars potentially)
        title_idx = text.find(title)
        if title_idx != -1:
            # Check if title appears more than once? 
            # In the examples, title appears in header, then again at start of body.
            
            # Simple heuristic: Start after the FIRST whitespace-separated title occurrence
            # But the raw text often has title -> === -> body
            
            # In example 2: Title -> === -> Body
            
            after_title = text[title_idx + len(title):]
            
            # Skip separator lines (===)
            after_title = re.sub(r'^[\s=]+', '', after_title, count=1)
            
            if len(after_title.strip()) > 100:
                text = after_title

    # 4. Footer Trimming
    footer_triggers = [
        "RELACIONADO",
        "RECOMENDADO",
        "LEIA TAMBÉM",
        "Partilhe este artigo",
        "Subscreva a nossa newsletter",
        "Siga-nos nas redes sociais",
        "### [", # Links to other articles often start like this in footers
    ]
    
    # Specific logic for RELACIONADO / RECOMENDADO sections which seem common
    
    best_cutoff = len(text)
    for trigger in footer_triggers:
        idx = text.find(trigger)
        if idx != -1 and idx < best_cutoff:
            best_cutoff = idx
            
    text = text[:best_cutoff]
    
    # 5. Clean Inline
    text = remove_inline_noise(text)
    
    # 6. Final cleanup of blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
