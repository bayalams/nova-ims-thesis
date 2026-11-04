import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_jornal_negocios(text, meta):
    """
    Cleaner for Jornal de Negócios (Portuguese business news).
    Strategy:
    1. Filter out Opinion, Podcasts, and Multimedia
    2. Remove navigation junk (dashes, menus, ads)
    3. Find article title and extract content after it
    4. Remove paywall messages and share forms
    5. Remove footer junk
    """
    
    # 0. Filtering: Opinion and Multimedia
    tags = meta.get('tags', [])
    if not isinstance(tags, list):
        tags = []
    
    # Check tags for exclusion keywords
    exclude_keywords = [
        'opinião', 'opiniao', 'podcast', 'multimédia', 'multimedia', 
        'vídeo', 'video', 'fotogaleria'
    ]
    
    # URL checks
    url = meta.get('link', '').lower() # or 'url' depending on scraper
    if any(k in url for k in ['/opiniao/', '/multimedia/', '/podcasts/']):
        return ""

    if tags:
        tags_lower = [t.lower() for t in tags]
        if any(k in t for k in exclude_keywords for t in tags_lower):
            # Check specifically if the tag contains the keyword
             if any(k in t for k in exclude_keywords):
                 return ""
                 
    # Also check Title for "Opinião:" or similar prefixes
    title = meta.get('title', '').strip().lower()
    if title.startswith('opinião') or 'podcast' in title:
        return ""

    # 0. Pre-process: Remove Markdown Images
    text = re.sub(r'!\[.*?\]\([^\)]+\)', '', text)
    
    # Pre-process: Remove ALL links (keep text)
    text = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    
    # 1. Remove navigation junk lines (lines that are mostly dashes or short menu items)
    lines = text.split('\n')
    cleaned_lines = []
    
    # Noise patterns to skip
    noise_patterns = [
        r'^-{3,}$',  # Lines of just dashes
        r'^={3,}$',  # Lines of just equals
        r'^Search$',
        r'^ASSINE',
        r'^Negócios:',
        r'^Notícias em Destaque',
        r'^Menu$',
        r'^Seguir$',
        r'^Para seguir um autor',
        r'^Caso não esteja registado',
        r'^Funcionalidade exclusiva para assinantes',
        r'^Para poder adicionar esta notícia',
        r'^Enviar o artigo:',
        r'^O meu email$',
        r'^O meu nome$',
        r'^Comentários$',
        r'^Destinatários:',
        r'^Enviar$',
        r'^Olá, envio como oferta',
        r'^\d{2}:\d{2}$',  # Timestamps like 08:00
        r'^\* \.\.\.$',  # Bullet with ellipsis
        r'^×$',  # Close button
    ]
    
    for line in lines:
        sline = line.strip()
        
        # Skip empty lines for now
        if not sline:
            cleaned_lines.append(line)
            continue
        
        # Skip noise patterns
        is_noise = False
        for pattern in noise_patterns:
            if re.match(pattern, sline, re.IGNORECASE):
                is_noise = True
                break
        
        if is_noise:
            continue
        
        # Skip very short navigation-like lines
        if len(sline) < 20 and sline in ['Login', 'Logout', 'Assinar', 'Premium', 'Newsletter']:
            continue
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # 2. Try to find the article content start (after title)
    title = meta.get('title', '')
    if title:
        # Find the title in the text and start after it
        title_idx = text.find(title)
        if title_idx != -1:
            # Start after the title line
            after_title = text[title_idx + len(title):]
            # Also skip any "===" underlines
            after_title = re.sub(r'^[\s=]+', '', after_title, count=1)
            if len(after_title.strip()) > 100:
                text = after_title
    
    # 3. Footer Trimming - remove paywall and share forms
    footer_triggers = [
        "Funcionalidade exclusiva para assinantes",
        "Para poder adicionar esta notícia",
        "Enviar o artigo:",
        "efectue o seu registo gratuito",
        "deverá efectuar login",
        "Olá, envio como oferta",
        "Leia mais em Jornal de Negócios",
        "Mais populares",
        "Mais lidas",
        "Mais Lidas",
        "Noticias Mais Lidas",
        "Notícias Mais Lidas",
        "Últimas notícias",
        "Comentar publicação",
        "Partilhar no Facebook",
        "Partilhar no Twitter",
        "### Relacionadas",
        "### Ver mais",
    ]
    
    # Find earliest footer trigger
    best_cutoff = len(text)
    for trigger in footer_triggers:
        idx = text.find(trigger)
        if idx != -1 and idx < best_cutoff:
            best_cutoff = idx
    
    text = text[:best_cutoff]
    
    # 4. Clean inline noise
    text = remove_inline_noise(text)
    
    # 5. Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 6. Remove remaining separator lines
    text = re.sub(r'^\s*[-=_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    return text.strip()
