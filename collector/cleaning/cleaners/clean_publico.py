import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_publico(text, meta):
    """
    Cleaner for Publico (Portuguese news).
    Strategy:
    1. Header Trim: Remove "Com o apoio", "Ouça este artigo" blocks.
    2. Body: Keep content between header and footer.
    3. Reader Wall/Footer Trim: Remove "Para continuar a ler", "Tópicos", "Fórum Público".
    """
    
    # 0. Filtering: Videos and Opinion
    # Check tags and URL for "Opinião" or Video indicators
    tags = meta.get('tags', [])
    if not isinstance(tags, list):
        tags = []
    
    url = meta.get('link', '').lower()
    
    # Check if Opinião, Crónica, or Newsletter
    # Normalized check for tags
    tags_lower = [t.lower() for t in tags]
    
    # Filter keywords in tags
    exclude_tags = ['opinião', 'opiniao', 'crónica', 'cronica', 'newsletter', 'briefing']
    if any(ex in tags_lower for ex in exclude_tags):
        return ""
        
    # Check URL for similar patterns
    url_lower = url.lower()
    if any(x in url_lower for x in ['/opiniao/', '/cronica/', '/newsletter/']):
        return ""
        
    # Check Title for Newsletter indicators (e.g. "Despertador:")
    title = meta.get('title', '').strip()
    if title.startswith("Despertador:") or "newsletter" in title.lower():
        return ""

    # Check if Video (extra safety)
    if any('vídeo' in t for t in tags_lower):
        return ""
        
    # 2. Tag Enrichment (from URL)
    # URL format: .../section/type/...
    # Example: .../fugas/entrevista/...
    try:
        # Extract section from URL
        # Typical: https://www.publico.pt/YYYY/MM/DD/section/...
        # or https://www.publico.pt/section/...
        
        path_parts = [p for p in url.split('/') if p and p not in ['https:', 'http:', 'www.publico.pt']]
        
        # Remove date parts if present
        cleaned_parts = []
        for p in path_parts:
            if not (re.match(r'^\d{4}$', p) or re.match(r'^\d{2}$', p)):
                 cleaned_parts.append(p)
                 
        if cleaned_parts:
            section = cleaned_parts[0].capitalize()
            # Map common ones if needed, or just capitalize
            # e.g. 'Culturaipsilon' -> 'Cultura'
            if 'Cultura' in section or 'Ipsilon' in section:
                section = 'Cultura'
            
            # Update tags: Put new section FIRST
            current_tags = meta.get('tags', [])
            if not isinstance(current_tags, list):
                current_tags = []
                
            # Avoid duplicates
            if section not in current_tags:
                meta['tags'] = [section] + current_tags
    except Exception:
        pass

    # 1. Aggressive Header Trim
    # Publico often starts with "Com o apoio O PÚBLICO..." audio player text.
    
    # Pre-process: Remove Markdown Images first
    text = re.sub(r'!\[.*?\]\([^\)]+\)', '', text)

    # Pre-process: Remove ALL links (keep text)
    # Pattern: [text](url) -> text
    # Changed + to * for empty text [] handling
    text = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    
    lines = text.split('\n')
    start_idx = 0
    
    # Known noise lines at start
    noise_starters = [
        "Com o apoio",
        "O PÚBLICO não é compatível",
        "Por favor, actualize",
        "Ouça este artigo",
        "Exclusivo",
        "Gostaria de Ouvir?",
        "Quer manter-se informado", 
        "Descarregue a aplicação",
        "Acesso gratuito:",
        "Assine já",
        "Ir para o conteúdo",
        "Ir para navegação principal"
    ]
    
    # Skip initial noise lines
    for i, line in enumerate(lines):
        sline = line.strip()
        if not sline: 
            continue
            
        is_noise = False
        for noise in noise_starters:
            if noise in sline:
                is_noise = True
                break
        
        # Audio timestamps (e.g. 00:00, 02:04)
        if re.match(r'^\d{2}:\d{2}$', sline):
            is_noise = True
            
        if not is_noise:
            title = meta.get('title', '')
            if title and title in sline:
                pass 
            else:
                # Potential start. 
                if len(sline) > 50: 
                    start_idx = i
                    break
    
    if start_idx > 0:
        lines = lines[start_idx:]
        text = '\n'.join(lines)

    # 2. Footer Trimming
    footer_triggers = [
        "seguintes tópicos para criar um grupo",
        "**Os leitores são a força e a vida do jornal**",
        "Para continuar a ler este artigo assine o PÚBLICO",
        "### Tópicos",
        "Notificações bloqueadas",
        "### Edição impressa",
        "Continuar a ler",
        "Saiba mais sobre o Fórum Público",
        "Receba notificações quando publicamos",
        "Estes são os autores e tópicos",
        "Mais populares",
        "Os jornalistas do PÚBLICO poderão sempre intervir",
        "Em destaque\n-----------",
        "Em destaque\n-----------", # Markdown underline style
        "##### Lazer",
        "##### Televisão",
        "##### Fotogaleria", 
        "##### Não há comentários",
        "* Aprovados",
        "* Pendentes" 
    ]
    
    best_cutoff = len(text)
    
    for trigger in footer_triggers:
        idx = text.find(trigger)
        if idx != -1 and idx < best_cutoff:
            best_cutoff = idx
            
    # Markdown footer section headers (### ...)
    # Sometimes "### Tópicos" or "### Últimas" are headers
    # Regex for specific footer headers
    footer_regex = [
        r'###\s+Tópicos',
        r'###\s+Últimas',
        r'###\s+Notificações',
        r'\* \[Aprovados\]\(#comments',
        r'Em destaque\s+\-+',
        r'#####\s+' # Catch all Level 5 headers as they seem to be used for footer lists in Publico
    ]
    
    for pat in footer_regex:
        match = re.search(pat, text)
        if match and match.start() < best_cutoff:
            best_cutoff = match.start()

    text = text[:best_cutoff]

    # 3. Clean Inline
    text = remove_inline_noise(text)
    
    # Remove separation markers (lines with just =, -, _)
    # e.g. "========", "-------"
    text = re.sub(r'^\s*[-=_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    return text.strip()
