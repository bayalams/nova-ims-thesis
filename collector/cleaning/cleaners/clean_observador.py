
import re
from datetime import datetime, timedelta
from .utils import trim_header_by_title, remove_inline_noise

MAX_AGE_DAYS = 90

def clean_observador(text, meta):
    """
    Cleaner for Observador (Portuguese News).
    Strategy:
    1. Trim Header: IE warnings, Dark Mode, Hyundai ads, Presidenciais polls.
    2. Trim Footer: Subscription prompts, share modals, offer dialogs.
    3. Inline: Remove audio player, navigation, sidebar widgets.
    """
    
    # 00a. Freshness Filter (90 days)
    raw_date = meta.get('date') or meta.get('published') or meta.get('updated', '')
    if raw_date:
        try:
            from email.utils import parsedate_to_datetime
            article_date = parsedate_to_datetime(raw_date)
            cutoff = datetime.now(article_date.tzinfo) - timedelta(days=MAX_AGE_DAYS)
            if article_date < cutoff:
                return ""
        except (ValueError, TypeError):
            pass
    
    # 00b. Filter out Podcasts/Radio/Newsletter content
    tags = meta.get('tags') or []
    if any('Rádio Observador' in t or 'Observador Lab' in t or 'Newsletter' in t for t in tags):
        return ""
    
    # 00c. Filter out podcast/program URLs (these lack proper article content)
    link = meta.get('link', '')
    if '/programas/' in link:
        return ""
    
    # 00b. Tag Extraction from URL
    link = meta.get('link', '')
    if link and not meta.get('tags'):
        # observador.pt/2026/01/12/economia/... -> Economia
        url_match = re.search(r'observador\.pt/\d{4}/\d{2}/\d{2}/([^/]+)/', link)
        if url_match:
            section = url_match.group(1)
            tag = section.replace('-', ' ').title()
            meta['tags'] = [tag]
    
    # 0. Header Trim (Title based)
    title = meta.get('title', '')
    if title:
        text = trim_header_by_title(text, title)

    lines = text.split('\n')
    clean_lines = []
    
    # Footer Triggers (Hard Stop)
    footer_triggers = [
        "Assine o Observador",
        "assine o Observador",
        "Veja aqui as suas opções",
        "Partilhe os seus artigos",
        "Quem recebe só precisa",
        "Este artigo foi-lhe oferecido",
        "Atingiu o limite de artigos",
        "Já ofereceu  artigos",
        "Voltar ao artigo",
        "Aconteceu um erro",
        "Por favor tente mais tarde",
        "Fechar",
        "Atenção",
        "Para ler este artigo grátis",
        "Registar-me",
        "Caso já tenha uma conta",
        "Escolher saber é saber escolher",
        "Até Portugal escolher",
        "Proponha uma correção",
        "observador+lusa@observador.pt",
        "Oferecer",
        "Clips",
        "Recomendamos",
        "Populares",
        "Últimas",
        "Ofereça este artigo",
        "A enviar artigo",
        "Artigo oferecido com sucesso",
    ]
    
    skip_patterns = [
        "O Observador já não suporta",
        "Internet Explorer 11",
        "Confirmar",
        "Apoio a Cliente",
        "kWh poupados",
        "A opção Dark Mode",
        "Reduza a sua pegada ecológica",
        "Junte-se à mobilidade do futuro",
        "Presidenciais 2026",
        "Radar das Sondagens",
        "Votómetro",
        "árvore genealógi",
        "Audio Player",
        "00:00",
        "Continuar",
        "Mute",
        "Sobre",
        "Seguir",
        "A seguir",
        "Guardar",
        "Guardado",
        "Copiar ligação",
        "Copiado",
        "De hora a hora",
        "Seguro",
        "Ventura",
        "Cotrim",
        "Gouveia",
        "Mendes",
        "20,2%",
        "19,8%",
        "19,1%",
        "17,5%",
        "15,6%",
        # Header emoji lines
        "💶 As declarações",
        "⌛ A atualidade",
        "🎯 Oiça a Caça",
        "🎧 No domingo",
        "📈 Resultados ao segundo",
        "Descubra o nosso conteúdo",
        "Todo o conteúdo exclusivo",
        "Receba os alertas",
        "Com os nossos alertas",
        # App/Site promo noise
        "Jogue ao Abrapalavra",
        "Uma palavra cinco letras",
        "Instale a App do Observador",
        "A nossa aplicação está disponível",
        "Siga-nos no Instagram",
        "Siga o Observador no Instagram",
        "Subscreva os nossos podcasts",
        "Debates, comentários, entrevistas",
        "Siga-nos no X",
        "Siga o Observador no X",
        "Guarde artigos para ler",
        "Pode guardar artigos",
        "Descubra o melhor da nossa opinião",
        "Toda a opinião, independente",
        "Receba a próxima edição",
        "Enquanto dormia, preparámos",
    ]
    
    for line in lines:
        sline = line.strip()
        
        # Footer Check
        if any(trig in sline for trig in footer_triggers):
            break
            
        # Skip noise lines
        if any(pat in sline for pat in skip_patterns):
            continue
            
        # Skip empty lines with just symbols
        if sline in ['####', '---', '===', '*', '-', 'i', '00:', '00']:
            continue
        
        # Skip emoji bullet lines (header navigation)
        if sline.startswith('* 💶') or sline.startswith('* 🎯') or sline.startswith('* ⌛') or sline.startswith('* 🎧') or sline.startswith('* 📈') or sline.startswith('* 🤔') or sline.startswith('* 🧬'):
            continue
            
        # Skip standalone percentage lines
        if re.match(r'^\d{1,2},\d%$', sline):
            continue
        
        # Skip image markdown
        if sline.startswith('![') and sline.endswith(')'):
            continue
            
        # Skip lines that are just links
        if sline.startswith('[') and sline.endswith(')') and '](' in sline:
            continue
        
        # Skip lines with just markdown headings that are horizontal rules
        if re.match(r'^[=\-]{3,}$', sline):
            continue
            
        clean_lines.append(line)

    text = '\n'.join(clean_lines)
    
    # Post-processing
    text = remove_inline_noise(text)
    
    # Strip Markdown Links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Strip image markdown that leaked
    text = re.sub(r'\]\(https?://[^\)]+\)', '', text)
    
    # Remove horizontal rule markers
    text = re.sub(r'^[=\-]{3,}$', '', text, flags=re.MULTILINE)
    
    # Remove date stamps like "12/1/2026, 15:16"
    text = re.sub(r'^\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}\s*$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    text = text.strip()
    
    # 00d. Post-cleaning sanity check: filter if result is mostly podcast UI noise
    # This catches podcast pages that slipped through other filters
    if 'Mais episódios' in text and 'Visualizado' in text:
        # Count meaningful content vs noise
        noise_count = text.count('Visualizado')
        if noise_count > 3 and len(text) < 500:
            return ""
    
    return text
