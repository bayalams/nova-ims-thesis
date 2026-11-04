
import re
from datetime import datetime, timedelta
from .utils import trim_header_by_title, remove_inline_noise

MAX_AGE_DAYS = 90

def clean_le_monde(text, meta):
    """
    Cleaner for Le Monde (French News).
    Strategy:
    1. Trim Header: Cookie consent, login prompts.
    2. Trim Footer: Subscription prompts, games section, multi-device warnings.
    3. Inline: Remove consent walls, "Lire plus tard", archive links.
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
    
    # 00b. Tag Extraction from URL
    # Le Monde URLs: lemonde.fr/international/article/... 
    link = meta.get('link', '')
    if link and not meta.get('tags'):
        url_match = re.search(r'lemonde\.fr/([^/]+)/', link)
        if url_match:
            section = url_match.group(1)
            if section not in ['rss', 'article', 'www']:
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
        "S'abonner",
        "Édition du jour",
        "Lire le journal numérique",
        "Cours du soir",
        "Culture générale",
        "#### Jeux",
        "Découvrir",
        "Lecture du *Monde* en cours",
        "Vous pouvez lire *Le Monde*",
        "Pourquoi voyez-vous ce message",
        "Lecture restreinte",
        "Fermer la modale",
        "Offrir cet article",
        "Accéder gratuitement en acceptant",
        "À quoi servent les cookies",
        "Pourquoi le *Monde*",
    ]
    
    skip_patterns = [
        "Cet article vous est offert",
        "Pour lire gratuitement",
        "Se connecter",
        "Inscrivez-vous gratuitement",
        "Lire plus tard",
        "Lire notre archive",
        "Article réservé à nos abonnés",
        "Article réservé aux abonnés",
        "Le Monde avec AFP",
        "Vous n'êtes pas inscrit sur Le Monde",
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
            
        clean_lines.append(line)

    text = '\n'.join(clean_lines)
    
    # Post-processing
    text = remove_inline_noise(text)
    
    # Strip Markdown Links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Strip image markdown that leaked
    text = re.sub(r'\]\(https?://[^\)]+\)', '', text)
    
    # Remove photo credits: "NAME / AGENCY"
    text = re.sub(r'^[A-Z\- ]+ / [A-Z\- ]+\s*$', '', text, flags=re.MULTILINE)
    
    # Remove horizontal rule markers
    text = re.sub(r'^[=\-]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
