import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_sapo(text, meta):
    """
    Cleaner for Sapo Notícias and related sub-brands (SAPO_VIAGENS, Magg, etc.).
    """
    
    # 1. Header Trimming (Title Based)
    text = trim_header_by_title(text, meta.get('title'))
    
    # NEW: Aggressive Pre-Trim for "Ler Artigo Completo"
    # This handles the AI summary blocks effectively by cutting everything before the main text start.
    idx_ler = text.find('Ler Artigo Completo', 0, 2000)
    if idx_ler != -1:
        text = text[idx_ler + len('Ler Artigo Completo'):].strip()

    # NEW: ECO Premium Pre-Trim
    # ECO articles often have "Assinar\nA Comissão..." where the real content starts after the last "Assinar"
    last_assinar = -1
    search_region = text[:1500]
    for match in re.finditer(r'\bAssinar\b', search_region):
        last_assinar = match.end()
    if last_assinar > 0:
        text = text[last_assinar:].strip()

    # 3. Aggressive Header Noise Removal (Menu, Login, etc.)
    header_patterns = [
        r'^### Menu\s*$',
        r'^### Mais\s*$',
        r'^\d+\s*$', # Isolated numbers like 1, 2 often found in menus
        r'^Siga-nos:.*?$',
        r'^### Menu\s+Siga-nos:.*?(?=\n\n)',
        r'^Toggle navigation\s+##### Em',
        r'^### Inicie sessão.*?Fale connosco.*?Torne-se premium.*?Escolha a sua assinatura.*?Assinar Eco Premium.*?(?=\n\n)',
        # ECO Premium Banners (backup, should be cut by pre-trim)
        r'\* Aceda a todos os artigos ECO Premium.*?(Assinar\s+)+',
        r'\{\{ calculatePrice.*?\}\}.*?Assinar',
        r'#### Assinar Eco Premium.*?(Assinar\s+)+',
        r'^\* Todas as vantagens ECO Premium\..*?$',
        r'^\* Revista Advocatus em papel\..*?$',
        r'^\* Receba as newsletters exclusivas.*?$',
        r'^\* Pode aceder aos artigos Premium.*?$',
        # Leftover from ECO pre-trim
        r'^por (ano|mês)\s*$',
    ]
    for pat in header_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)

    # 4. Remove AI Summaries / Audio Readers
    # "Ler Resumo", "Ouvir Resumo", "Voz gerada por...", "Este resumo foi criado..."
    summary_patterns = [
        r'(Ler|Ouvir) (Resumo|Artigo).*?(Ler Artigo Completo|Saiba\s+mais\.?|#\))', 
        r'#### Conteúdo.*?(#### Feedback.*?)?funcionalidade!',
        r'#### Feedback.*?funcionalidade!',
        r'#### Conteúdo', 
        r'Este resumo foi criado com recurso a inteligência artificial.*?captar todas as nuances importantes do artigo\.',
        r'Resumo gerado por inteligência artificial.*?Saiba\s+mais.*?',
        r'Pode ouvir este artigo.*?Siga o podcast.*?(?=\n\n)',
        r'SAPO\]\(#\)',
        r'Voz gerada por inteligência artificial.*?\(#audio-disclaimer\)',
    ]
    
    for pat in summary_patterns:
        # Using DOTALL to span multiple lines
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)

    # 4. Footer Trimming
    footer_triggers = [
        "### Tópicos",
        "#### Continua a fazer scroll para ver mais artigos",
        "TAMBÉM PODE GOSTAR",
        "### Relacionados Playlist",
        "#### ÚLTIMAS",
        "###### Últimas Notícias",
        "### Mais Recentes",
        "Notificações\n------------\nQueremos estar sempre consigo",
        "Notícias relacionadas",
        "EDIÇÃO NAS BANCAS!",
        "Comentários\n",
        "Comentários (",
        "Veja também\nFechar",
        "###### O seu browser está desatualizado!",
        "Mais Recentes\n-------------\n[###", # Executive Digest
        # ECO Related Articles (usually at the end with links and dates)
        "* [2.º Fórum",  # ECO event links
        "* [5ª edição",
        "Saiba Mais](https://eco.sapo.pt/eventos/",
    ]
    
    best_cutoff = len(text)
    for trigger in footer_triggers:
        idx = text.find(trigger)
        if idx != -1 and idx < best_cutoff:
            best_cutoff = idx
            
    text = text[:best_cutoff]
    
    # 5. Remove Video Player / Modal Artifacts
    video_patterns = [
        r'Beginning of dialog window\..*?End of dialog window\.',
        r'This is a modal window\..*?activating the close button\.',
    ]
    for pat in video_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)

    # 6. Inline Noise
    text = remove_inline_noise(text)
    
    # Remove "Partilha" (share buttons)
    text = re.sub(r'^\s*Partilha\s*$', '', text, flags=re.MULTILINE)

    # Remove repeated lines like "Entrar", "Pagar", "Ler", "Marketeer"
    text = re.sub(r'^\s*(Entrar|Pagar|Ler|Marketeer)\s*$', '', text, flags=re.MULTILINE)
    
    # Remove Executive Digest dates: "Janeiro 8, 2026" or "12 Janeiro 2026"
    text = re.sub(r'^[A-Z][a-z]+ \d{1,2}, \d{4}\s*\d{2}:\d{2}$', '', text, flags=re.MULTILINE) # Janeiro 8, 2026...
    
    # Remove Sapo dates: "11 dez 2025 12:30"
    text = re.sub(r'^\d{1,2} [a-z]{3} \d{4} \d{2}:\d{2}$', '', text, flags=re.MULTILINE)

    # Remove numeric dates: "2026/01/05" or "12/01/2026"
    text = re.sub(r'^\s*\d{4}/\d{2}/\d{2}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d{2}/\d{2}/\d{2,4}\s*(\d{2}:\d{2})?\s*$', '', text, flags=re.MULTILINE)

    # Remove ECO related article links: "* [Title\n12 Janeiro 2026](url)"
    text = re.sub(r'\* \[.*?\n\d{1,2} [A-Za-z]+ \d{4}\]\(https?://[^\)]+\)', '', text, flags=re.DOTALL)
    # Also: "* [Title\nSaiba Mais](url)"
    text = re.sub(r'\* \[.*?\nSaiba Mais\]\(https?://[^\)]+\)', '', text, flags=re.DOTALL)


    # Remove separation markers
    text = re.sub(r'^-+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^=+$', '', text, flags=re.MULTILINE)

    return text.strip()
