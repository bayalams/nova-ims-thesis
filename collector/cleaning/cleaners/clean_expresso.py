import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_expresso(text, meta):
    if not text:
        return ""

    # 0. ALLOWLIST FILTER WITH MAPPING
    # User Request: "Focus on Política, Sociedade, Internacional, Boa Cama Boa Mesa"
    # Plus mapping specific topics to these categories.
    
    tags = [t.strip() for t in meta.get('tags', [])]
    
    # 1. Target Categories (The "Keep" list)
    target_categories = {
        "Política",
        "Sociedade", 
        "Internacional",
        "Boa Cama Boa Mesa"
    }

    # 2. Tag Mapping (Specific -> Target)
    # Note: "Obituário" and "Religião" are explicitly excluded from this map per user request.
    tag_map = {
        # Politics
        "Presidenciais 2026": "Política",
        "Governo": "Política",
        "Parlamento": "Política",
        "Partidos": "Política",
        "Justiça": "Política", # Mapped to Politics as it often involves governance/law
        
        # International
        "Venezuela": "Internacional",
        "Guerra na Ucrânia": "Internacional",
        "Médio Oriente": "Internacional",
        "América Latina": "Internacional",
        "União Europeia": "Internacional",
        "EUA": "Internacional",
        "Brasil": "Internacional",
        "Espanha": "Internacional",
        "França": "Internacional",
        "Reino Unido": "Internacional",
        "Mundo": "Internacional",
        "Europa": "Internacional",
        "Guerra Fria": "Internacional",
        
        # Society
        "Saúde": "Sociedade",
        "Transportes": "Sociedade",
        "Meteorologia": "Sociedade",
        "Segurança": "Sociedade",
        "Imobiliário": "Sociedade",
        "Habitação": "Sociedade",
        "Lisboa": "Sociedade",
        # "Obituário": "Sociedade", # EXCLUDED
        # "Religião": "Sociedade",  # EXCLUDED
        
        # Boa Cama Boa Mesa (usually explicit, but added for completeness if sub-tags exist)
        # Assuming no sub-tags for now based on known list.
    }
    
    # Check if article is allowed
    is_allowed = False
    effective_tags = set()
    
    for t in tags:
        # Normalize
        t_clean = t.strip()
        effective_tags.add(t_clean)
        
        # Add mapped category if exists
        if t_clean in tag_map:
            effective_tags.add(tag_map[t_clean])
            
    # Check intersection (Case insensitive logic not strictly needed if map is exact, 
    # but good for robustness against user/source variation)
    for et in effective_tags:
        # Check against target categories
        if any(tc.lower() == et.lower() for tc in target_categories):
            is_allowed = True
            break
            
    if not is_allowed:
        return ""

    # =========================================================================
    # START CLEANING (Only for allowed articles)
    # =========================================================================

    # 1. Link Stripping (User Request)
    text = re.sub(r'!\[[^\]]*\]\([^\)]*\)', '', text)
    text = re.sub(r'(?<!\!)\[([^\]]*)\]\([^\)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)

    # 2. Header Trim
    title = meta.get('title', '')
    if title:
        text = trim_header_by_title(text, title)

    header_patterns = [
        "Últimas Notícias",
        "Clique aqui para ouvir enquanto navega no ExpressoFechar",
        "Conheça os nossos 1005 parceiros"
    ]
    lines = text.split('\n')
    start_idx = 0
    for i, line in enumerate(lines[:50]):
        sline = line.strip()
        if any(p in sline for p in header_patterns):
            start_idx = i + 1
        if sline in ["Jornalista", "Sonoplasta", "Editora de Política", "Correspondente em Madrid", "Fotojornalista", "Por"]:
            start_idx = i + 1
    text = '\n'.join(lines[start_idx:])

    # 3. Paywall & Subscribe Banners
    paywall_markers = [
        "Artigo Exclusivo para subscritores",
        "Aproveite 60% desconto: subscreva por apenas",
        "Comprou o Expresso?Insira o código",
        "Para continuar a ler este artigo assine o PÚBLICO",
        "Não foi possível carregar o Disqus"
    ]
    
    # 4. Footer Trim
    footer_triggers = [
        "* Mais Partilha",
        "Tem dúvidas, sugestões ou críticas?",
        "Subscreva e aceda aos comentários",
        "Relacionados"
    ]
    
    cleaned_lines = []
    lines = text.split('\n')
    for line in lines:
        sline = line.strip()
        if any(trig in sline for trig in footer_triggers):
            break
        if re.match(r'^[-=_*]{3,}$', sline):
            continue
        if any(pm in sline for pm in paywall_markers) or "Subscreva e tenha acesso" in sline:
            continue
        if sline in ["Jornalista", "Sonoplastia", "Sonoplasta", "Bolsa", "Editor Multimédia", "Editora de Política", "Redatora principal", "Editor de Economia", "Coordenadora de Política"]:
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    # 5. Advanced Cleanup
    
    # Remove Audio/Video Player Noise
    audio_noise_patterns = [
        r'^\d+\s+seconds\s+of\s+\d+\s+seconds.*$',
        r'^Press shift question mark.*$',
        r'^Atalhos de Teclado.*$',
        r'^Shortcuts Open/Close.*$',
        r'^Reproduzir/Pausar.*$',
        r'^Tela Cheia/Sair.*$',
        r'^Desativar Som/Ativar.*$',
        r'^Increase Caption.*$',
        r'^Decrease Caption.*$',
        r'^Adiantar %.*$',
        r'^\d+(\.\d+)x.*$',
        r'^Ao Vivo$',
        r'^\d{2}:\d{2}:\d{2}$',
        r'^\d{2}:\d{2}$',
        r'^Volume \d+%$',
        r'^Aumentar o Volume.*$',
        r'^Diminuir o Volume.*$',
        r'^Adiantar.*$',
        r'^Retroceder.*$',
        r'^Legendas Ativar/Desativar.*$'
    ]
    for pat in audio_noise_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.IGNORECASE)

    # Remove Date from Body
    text = re.sub(r'\b\d{1,2}\s+(?:janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+\d{4}\s+\d{1,2}:\d{2}\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*\d{2}:\d{2}\s*$', '', text, flags=re.MULTILINE)

    # Remove Noise Blocks (* Section)
    # e.g. An International article might have a link block to "Blitz".
    noise_sections = [
        "Blitz", "Bolsa e Mercados", "Tendências", "Opinião", "Internacional", "Economia", 
        "Política", "Sociedade", "Cultura", "Mundo", "País", "Desporto", "O CEO é o limite", 
        "França", "Tecnologia", "Energia", "Ataque dos EUA", "Guerra Rússia-Ucrânia", 
        "Repórteres do Mundo", "Antes Pelo Contrário", "No Princípio Era a Bola", "Oferta", 
        "Mais Energia", "Guerra na Ucrânia", "União Europeia", "Venezuela", "Palavras Cruzadas", 
        "Presidente", "Liga dos Inovadores", "Meteorologia", "Contas Poupança", 
        "Contas-Poupança em Podcast", "Presidenciais 2026", "Ataque dos EUA à Venezuela", 
        "Podcasts", "Boa Cama Boa Mesa"
    ]
    for ns in noise_sections:
        pattern = fr'^\*\s+{re.escape(ns)}\s*\n.*$'
        text = re.sub(pattern, '', text, flags=re.MULTILINE | re.IGNORECASE)

    text = re.sub(r'^\+\s+.*$', '', text, flags=re.MULTILINE)

    # Image Credits
    text = re.sub(r'^.*(?:/reuters|/lusa|/getty images|/afp|/epa|/ap).*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^Agência Lusa.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Metadata Roles
    metadata_roles = [
        r'Jornalista', r'Sonoplastia', r'Multimédia', r'Grafismo', r'Redatora principal', 
        r'Editor de multimédia', r'Editora executiva', r'Editora de', r'Editor de',
        r'Web design', r'Ilustração', r'Fotografia', r'Grande repórter', r'Crítico de', r'Edição de vídeo',
        r'Correspondente em Bruxelas'
    ]
    for role in metadata_roles:
        text = re.sub(fr'^{role}.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # Generic
    text = re.sub(r'(^|\n)Leia também:.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'(^|\n)Siga-nos em.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*Relacionados\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'Carregando artigos\.\.\.', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^Últimas Notícias$', '', text, flags=re.MULTILINE)

    text = remove_inline_noise(text)
    
    return text.strip()
