"""
Jornal de Notícias Cleaner
============================

Cleans articles from JORNAL_NOTICIAS source.
Portuguese general news, often paywalled. Articles have navigation headers,
premium markers, recommendation blocks, and comment sections.
"""

import re


def clean_jornal_noticias(text, meta):
    """
    Cleaner for JORNAL_NOTICIAS articles.
    """
    if not text:
        return ""
    
    # 0. Pre-processing: Remove known garbage lines
    lines = text.split('\n')
    filtered_lines = []
    skip_until_content = True  # Skip header noise until real content
    
    for line in lines:
        sline = line.strip()
        
        # Skip empty lines at the start
        if skip_until_content and not sline:
            continue
        
        # Skip navigation menu items (Portuguese)
        if sline in ["Últimas", "País", "Mundo", "Desporto", "Economia", "Opinião",
                      "Cultura", "Tecnologia", "Saúde", "Justiça", "Sociedade",
                      "Nacional", "Local", "JN Direto", "Vídeo",
                      "Classificados", "Mais", "Menu", "Pesquisar",
                      "Entrar", "Assinar", "Newsletters"]:
            continue
            
        # Skip premium/paywall markers
        if sline in ["Exclusivo Assinantes", "Exclusivo assinantes",
                      "Conteúdo reservado a assinantes",
                      "Assine o JN", "Já é assinante? Inicie sessão"]:
            continue
        if "Assine o JN" in sline:
            continue
        if "Exclusivo Assinantes" in sline or "exclusivo assinantes" in sline:
            continue
            
        # Skip social sharing
        if sline in ["Partilhar", "Partilhar artigo"]:
            continue
        if "partilhe este artigo" in sline.lower():
            continue
            
        # Skip author photo alt text
        if sline.startswith("Foto de") and len(sline) < 50:
            continue
            
        # Skip separator lines
        if re.match(r'^-{3,}$', sline):
            continue
            
        if skip_until_content and len(sline) > 50:
            skip_until_content = False
            
        if not skip_until_content:
            filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Footer Cleaning - cut at footer sections
    footer_markers = [
        "\nLeia também",
        "\nVeja também",
        "\nNotícias relacionadas",
        "\nMais Lidas",
        "\n### Mais Lidas",
        "\nComentários",
        "\n### Comentários",
        "\nSiga-nos",
        "\nReceba as principais notícias",
        "\nNewsletter",
        "\n### Newsletter",
        "\n### Últimas",
        "\nPUB",
        "\nPublicidade",
        "\nConteúdo patrocinado",
        "\nMais sobre",
        "\n### Mais sobre",
        "\nPremium",
        "\nClassificados",
        "\n© Jornal de Notícias",
        "\nTodos os direitos reservados",
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    
    text = text[:first_idx]
    
    # 2. Post-processing cleanup
    
    # Remove markdown images ![...](...) 
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    
    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove PUB/ad markers inline
    text = re.sub(r'^\s*PUB\s*$', '', text, flags=re.MULTILINE)
    
    # Remove breadcrumbs: "JN > País > Artigo"
    text = re.sub(r'^.*JN\s*>\s*\w+.*$', '', text, flags=re.MULTILINE)
    
    # Remove header separator lines (------ or ======)
    text = re.sub(r'^[-=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
