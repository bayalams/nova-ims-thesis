
import re
from datetime import datetime, timedelta
from .utils import trim_header_by_title, remove_inline_noise

MAX_AGE_DAYS = 90

def clean_lecho_touristique(text, meta):
    """
    Cleaner for L'Echo Touristique (French B2B Travel).
    Strategy:
    1. Trim Header: Navigation, logo, sidebar links.
    2. Trim Footer: Related articles, comments, ads, newsletter.
    3. Inline: Remove share buttons, author bylines, paywall prompts.
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
    
    # 0. Header Trim (Title based)
    title = meta.get('title', '')
    if title:
        text = trim_header_by_title(text, title)

    lines = text.split('\n')
    clean_lines = []
    
    # Footer Triggers (Hard Stop)
    footer_triggers = [
        "Laisser votre commentaire",
        "Annuler la réponse",
        "Ce site utilise Akismet",
        "Précédent",
        "Prochain",
        "Dans la même rubrique",
        "Publi-communiqués",
        "Appels d'offres",
        "Articles récents",
        "Articles les plus lus",
        "Restez Connecté",
        "S'identifier",
        "Newsletter gratuit",
        "Identifiez-vous",
        "Récupérez votre mot de passe",
        "À lire aussi",
        "A lire aussi",
        "### A lire aussi",
        "### À lire aussi",
        "Sur le même sujet",
    ]
    
    skip_patterns = [
        "Publicité",
        "- Publicité -",
        "Share",
        "Facebook",
        "Twitter",
        "Linkedin",
        "Parcourir les articles",
        "La suite est réservée aux abonnés",
        "veuillez vous identifier",
        "abonnez-vous",
        "© Adobe Stock",
        "photo d'illustration",
    ]
    
    for line in lines:
        sline = line.strip()
        
        # Footer Check
        if any(trig in sline for trig in footer_triggers):
            break
            
        # Skip noise lines
        if any(pat in sline for pat in skip_patterns):
            continue
            
        # Skip empty image markdown
        if sline.startswith('![') and sline.endswith(')'):
            continue
            
        # Skip lines that are just links
        if sline.startswith('[') and sline.endswith(')') and '](' in sline:
            continue
        
        # Skip date/author bylines like "Le **Jan 12, 2026**"
        if sline.startswith('Le **') and '202' in sline:
            continue
        
        # Skip "Par **Author**" lines
        if sline.startswith('Par **') or sline.startswith('[Par **'):
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
    
    # Remove standalone category tags like [Premium][Destinations]
    text = re.sub(r'^\[Premium\].*$', '', text, flags=re.MULTILINE)
    
    # Remove duplicate title (appears twice after header trim)
    title = meta.get('title', '')
    if title:
        # Remove second occurrence of title if it appears at start
        lines = text.split('\n')
        if len(lines) >= 2 and lines[0].strip() == title and lines[1].strip() == title:
            lines = lines[1:]  # Remove first duplicate
        text = '\n'.join(lines)
    
    # Remove standalone date lines (Jan 9, 2026, Déc 22, 2025, etc.)
    text = re.sub(r'^(Jan|Fév|Mar|Avr|Mai|Juin|Juil|Août|Sep|Oct|Nov|Déc|Dec) \d{1,2}, \d{4}\s*$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
