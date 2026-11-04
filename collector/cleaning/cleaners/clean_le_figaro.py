
import re
from datetime import datetime, timedelta
from .utils import trim_header_by_title, remove_inline_noise

MAX_AGE_DAYS = 90

def clean_le_figaro(text, meta):
    """
    Cleaner for Le Figaro (French News & Travel).
    Strategy:
    1. Trim Header: Navigation, breadcrumbs, share links before article.
    2. Trim Footer: Comments, "À lire aussi", "Plus de services", cookie walls.
    3. Inline: Remove share links, "Publicité", image placeholders.
    """
    
    # 00a. Freshness Filter (90 days)
    raw_date = meta.get('date') or meta.get('published') or meta.get('updated', '')
    if raw_date:
        try:
            from email.utils import parsedate_to_datetime
            article_date = parsedate_to_datetime(raw_date)
            cutoff = datetime.now(article_date.tzinfo) - timedelta(days=MAX_AGE_DAYS)
            if article_date < cutoff:
                return ""  # Article too old
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
        "À lire aussi",
        "Plus de services",
        "L'actualité à ne pas manquer",
        "commentaires",
        "Lire les",
        "S'ABONNER",
        "Vous avez choisi de refuser les cookies",
        "Accepter les cookies",
        "Paramétrer les cookies",
    ]
    
    skip_patterns = [
        "Publicité",
        "Passer la publicité",
        "Copier le lien",
        "Lien copié",
        "Partager via",
        "Il y a ",  # Time ago markers
        "Aller au contenu",
        "Fermer",
        "Écouter cet article",
        "00:00/",  # Audio player
        "Afficher plus",
        "Afficher moins",
        "Sommaire",
        "Entrez ici votre recherche",
        "Rechercher",
        "Alerte info",
    ]
    
    # Skip breadcrumb lines
    breadcrumb_pattern = re.compile(r'^[0-9]+\. (Accueil|Voyage|International|Politique|Sports|Football|Flash Actu|Guides|Conseils|Inspiration|Hôtels|Musique|Entreprises|Ligue 1)$')
    
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
            
        # Skip lines that are just links (navigation remnants)
        if sline.startswith('[') and sline.endswith(')') and '](' in sline:
            continue
            
        # Skip share button lines
        if sline in ['Oui', 'Non', 'Mail', 'Facebook', 'X', 'Linkedin', 'Messenger', 'WhatsApp', 'Dossier', 'Sujets', 'Suivre', 'Le direct', 'Faits Essentiels']:
            continue
        
        # Skip breadcrumb lines
        if breadcrumb_pattern.match(sline):
            continue
        
        # Skip time markers (12:58, 07:19, etc.)
        if re.match(r'^[0-9]{1,2}:[0-9]{2}$', sline):
            continue
        
        # Skip "Réservé aux abonnés" markers
        if 'Réservé aux abonnés' in sline:
            continue
            
        clean_lines.append(line)

    text = '\n'.join(clean_lines)
    
    # Post-processing
    text = remove_inline_noise(text)
    
    # Strip Markdown Links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Strip image markdown that leaked
    text = re.sub(r'\]\(https?://[^\)]+\)', '', text)
    
    # Remove horizontal rule markers and heading underlines
    text = re.sub(r'^[=\-]{3,}$', '', text, flags=re.MULTILINE)
    
    # Remove "Par Le Figaro" byline
    text = re.sub(r'^Par Le Figaro\s*$', '', text, flags=re.MULTILINE)
    
    # Remove author bylines: "Par [Name]" or "Par [Name], pour Le Figaro"
    text = re.sub(r'^Par [A-Z][a-zÀ-ÿ\-]+.*$', '', text, flags=re.MULTILINE)
    
    # Remove date lines: "Le 12 janvier 2026 à 12h07"
    text = re.sub(r'^Le \d{1,2} [a-zéû]+ \d{4} à \d{2}h\d{2}$', '', text, flags=re.MULTILINE)
    
    # Remove photo credits: "Name / AGENCY"
    text = re.sub(r'^[A-Za-zÀ-ÿ\- ]+ / [A-Z]+\s*$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
