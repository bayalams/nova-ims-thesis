import re
from .utils import get_best_date, get_tags, trim_header_by_title, remove_inline_noise, normalize_tags

# Specialized Cleaners Imports
# Using try/except to allow partial failures but logging warnings
try:
    from .clean_abc import clean_abc_espana, extract_abc_tags
except ImportError:
    print("[WARNING] Could not import clean_abc")
    clean_abc_espana = None

try:
    from .clean_aljazeera import clean_aljazeera
except ImportError:
    print("[WARNING] Could not import clean_aljazeera")
    clean_aljazeera = None

try:
    from .clean_ambitur import clean_ambitur
except ImportError:
    print("[WARNING] Could not import clean_ambitur")
    clean_ambitur = None

try:
    from .clean_ansa import clean_ansa
except ImportError:
    print("[WARNING] Could not import clean_ansa")
    clean_ansa = None

try:
    from .clean_bbc import clean_bbc
except ImportError:
    print("[WARNING] Could not import clean_bbc")
    clean_bbc = None

try:
    from .clean_cnbc import clean_cnbc
except ImportError:
    print("[WARNING] Could not import clean_cnbc")
    clean_cnbc = None

try:
    from .clean_cnn import clean_cnn
except ImportError:
    print("[WARNING] Could not import clean_cnn")
    clean_cnn = None

try:
    from .clean_conde import clean_conde_nast
except ImportError:
    print("[WARNING] Could not import clean_conde")
    clean_conde_nast = None

try:
    from .clean_zeit import clean_die_zeit, extract_zeit_tags
except ImportError:
    print("[WARNING] Could not import clean_zeit")
    clean_die_zeit = None
    extract_zeit_tags = None

try:
    from .clean_elmundo import clean_elmundo
except ImportError:
    print("[WARNING] Could not import clean_elmundo")
    clean_elmundo = None
try:
    from .clean_elpais import clean_elpais
except ImportError:
    print("[WARNING] Could not import clean_elpais")
    clean_elpais = None

try:
    from .clean_euronews import clean_euronews, extract_euronews_tags
except ImportError:
    print("[WARNING] Could not import clean_euronews")
    clean_euronews = None
try:
    from .clean_expresso import clean_expresso
except ImportError:
    print("[WARNING] Could not import clean_expresso")
    clean_expresso = None

try:
    from .clean_faz import clean_faz
except ImportError:
    print("[WARNING] Could not import clean_faz")
    clean_faz = None

try:
    from .clean_guardian import clean_guardian
except ImportError:
    print("[WARNING] Could not import clean_guardian")
    clean_guardian = None

try:
    from .clean_hosteltur import clean_hosteltur
except ImportError:
    print("[WARNING] Could not import clean_hosteltur")
    clean_hosteltur = None

try:
    from .clean_le_figaro import clean_le_figaro
except ImportError:
    print("[WARNING] Could not import clean_le_figaro")
    clean_le_figaro = None

try:
    from .clean_le_monde import clean_le_monde
except ImportError:
    print("[WARNING] Could not import clean_le_monde")
    clean_le_monde = None

try:
    from .clean_lecho_touristique import clean_lecho_touristique
except ImportError:
    print("[WARNING] Could not import clean_lecho_touristique")
    clean_lecho_touristique = None

try:
    from .clean_observador import clean_observador
except ImportError:
    print("[WARNING] Could not import clean_observador")
    clean_observador = None

try:
    from .clean_portugal_news import clean_portugal_news
except ImportError:
    print("[WARNING] Could not import clean_portugal_news")
    clean_portugal_news = None

try:
    from .clean_portugal_resident import clean_portugal_resident
except ImportError:
    print("[WARNING] Could not import clean_portugal_resident")
    clean_portugal_resident = None

try:
    from .clean_jornal_negocios import clean_jornal_negocios
except ImportError:
    print("[WARNING] Could not import clean_jornal_negocios")
    clean_jornal_negocios = None

try:
    from .clean_jornal_economico import clean_jornal_economico
except ImportError:
    print("[WARNING] Could not import clean_jornal_economico")
    clean_jornal_economico = None

try:
    from .clean_diario_noticias import clean_diario_noticias
except ImportError:
    print("[WARNING] Could not import clean_diario_noticias")
    clean_diario_noticias = None

try:
    from .clean_dw_news import clean_dw_news
except ImportError:
    print("[WARNING] Could not import clean_dw_news")
    clean_dw_news = None

try:
    from .clean_france24 import clean_france24
except ImportError:
    print("[WARNING] Could not import clean_france24")
    clean_france24 = None

try:
    from .clean_breaking_travel_news import clean_breaking_travel_news
except ImportError:
    print("[WARNING] Could not import clean_breaking_travel_news")
    clean_breaking_travel_news = None

try:
    from .clean_independent_travel import clean_independent_travel
except ImportError:
    print("[WARNING] Could not import clean_independent_travel")
    clean_independent_travel = None

try:
    from .clean_ap_news import clean_ap_news
except ImportError:
    print("[WARNING] Could not import clean_ap_news")
    clean_ap_news = None

try:
    from .clean_eturbonews import clean_eturbonews
except ImportError:
    print("[WARNING] Could not import clean_eturbonews")
    clean_eturbonews = None

try:
    from .clean_air_current import clean_air_current
except ImportError:
    print("[WARNING] Could not import clean_air_current")
    clean_air_current = None

try:
    from .clean_eco import clean_eco
except ImportError:
    print("[WARNING] Could not import clean_eco")
    clean_eco = None

try:
    from .clean_huffpost import clean_huffpost
except ImportError:
    print("[WARNING] Could not import clean_huffpost")
    clean_huffpost = None

try:
    from .clean_jornal_noticias import clean_jornal_noticias
except ImportError:
    print("[WARNING] Could not import clean_jornal_noticias")
    clean_jornal_noticias = None

try:
    from .clean_travelpulse import clean_travelpulse
except ImportError:
    print("[WARNING] Could not import clean_travelpulse")
    clean_travelpulse = None

try:
    from .clean_fvw import clean_fvw
except ImportError:
    print("[WARNING] Could not import clean_fvw")
    clean_fvw = None


# ==============================================================================
#                           SOURCE SPECIFIC CLEANERS (INLINE)
# ==============================================================================

try:
    from .clean_rtp import clean_rtp
except ImportError:
    print("[WARNING] Could not import clean_rtp")
    clean_rtp = None

try:
    from .clean_sapo import clean_sapo
except ImportError:
    print("[WARNING] Could not import clean_sapo")
    clean_sapo = None

try:
    from .clean_simple_flying import clean_simple_flying
except ImportError:
    print("[WARNING] Could not import clean_simple_flying")
    clean_simple_flying = None

try:
    from .clean_skift import clean_skift
except ImportError:
    print("[WARNING] Could not import clean_skift")
    clean_skift = None

try:
    from .clean_spiegel import clean_spiegel
except ImportError:
    print("[WARNING] Could not import clean_spiegel")
    clean_spiegel = None

try:
    from .clean_sueddeutsche import clean_sueddeutsche
except ImportError:
    print("[WARNING] Could not import clean_sueddeutsche")
    clean_sueddeutsche = None

try:
    from .clean_touristik_aktuell import clean_touristik_aktuell
except ImportError:
    print("[WARNING] Could not import clean_touristik_aktuell")
    clean_touristik_aktuell = None

try:
    from .clean_tourmag import clean_tourmag
except ImportError:
    print("[WARNING] Could not import clean_tourmag")
    clean_tourmag = None

try:
    from .clean_travel_leisure import clean_travel_leisure
except ImportError:
    print("[WARNING] Could not import clean_travel_leisure")
    clean_travel_leisure = None

try:
    from .clean_washington_post import clean_washington_post
except ImportError:
    print("[WARNING] Could not import clean_washington_post")
    clean_washington_post = None



def clean_obs(text, meta):
    # OBSERVADOR
    text = trim_header_by_title(text, meta.get('title'))
    text = remove_inline_noise(text)
    return text

def clean_generic(text, meta):
    text = trim_header_by_title(text, meta.get('title'))
    text = remove_inline_noise(text)
    return text

# ==============================================================================
#                               MAIN DISPATCHER
# ==============================================================================

def clean_and_enrich_text(text, meta):
    if not text:
        return ""
    
    # 0. SKIP VIDEOS
    link = meta.get('link', '')
    tags = normalize_tags(meta.get('tags', []))
    meta['tags'] = tags
    title = meta.get('title', '')
    
    # Check for Consent Walls (scraping failures)
    consent_keywords = [
        "CookieConsent", "Responsible use of your data", "Consent Selection", 
        "Necessary cookies help", "distinguish between humans and bots",
        "Privacy trigger icon", "actively scanning it for specific characteristics",
        "This site asks for consent to use your data"
    ]
    if any(k in text for k in consent_keywords):
        return ""

    # Check for video keywords in tags (case-insensitive)
    if tags and any('vídeo' in t.lower() or 'videos' in t.lower() for t in tags):
        return ""
        
    # Check for video URL patterns
    video_patterns = ['/video/', '/videos/', '/cmtv/', 'www.nytimes.com/video']
    if any(pat in link for pat in video_patterns):
        return ""

    source = meta.get('source', '').upper() # Normalized

    # Dispatcher
    try:
        if 'PUBLICO' in source:
            from .clean_publico import clean_publico
            cleaned_body = clean_publico(text, meta)
        elif 'EXPRESSO' in source:
            cleaned_body = clean_expresso(text, meta)
        elif 'FAZ' in source and clean_faz:
            cleaned_body = clean_faz(text, meta)
        elif 'GUARDIAN' in source and clean_guardian:
            cleaned_body = clean_guardian(text, meta)
        elif 'HOSTELTUR' in source and clean_hosteltur:
            cleaned_body = clean_hosteltur(text, meta)
        elif 'LE_FIGARO' in source and clean_le_figaro:
            cleaned_body = clean_le_figaro(text, meta)
        elif 'LE_MONDE' in source and clean_le_monde:
            cleaned_body = clean_le_monde(text, meta)
        elif 'LECHO_TOURISTIQUE' in source and clean_lecho_touristique:
            cleaned_body = clean_lecho_touristique(text, meta)
        elif 'ABC_ESPANA' in source and clean_abc_espana:
            cleaned_body = clean_abc_espana(text, meta)
        elif 'AL_JAZEERA' in source and clean_aljazeera:
            cleaned_body = clean_aljazeera(text, meta)
        elif 'AMBITUR' in source and clean_ambitur:
            cleaned_body = clean_ambitur(text, meta)
        elif 'OBSERVADOR' in source and clean_observador:
            cleaned_body = clean_observador(text, meta)
        elif 'PORTUGAL_NEWS' in source and clean_portugal_news:
            cleaned_body = clean_portugal_news(text, meta)
        elif 'PORTUGAL_RESIDENT' in source and clean_portugal_resident:
            cleaned_body = clean_portugal_resident(text, meta)
        elif 'JORNAL_NEGOCIOS' in source and clean_jornal_negocios:
            cleaned_body = clean_jornal_negocios(text, meta)
        elif 'JORNAL_ECONOMICO' in source and clean_jornal_economico:
            cleaned_body = clean_jornal_economico(text, meta)
        elif 'DIARIO_NOTICIAS' in source and clean_diario_noticias:
            cleaned_body = clean_diario_noticias(text, meta)
        elif 'DW_NEWS' in source and clean_dw_news:
            cleaned_body = clean_dw_news(text, meta)
        elif 'FRANCE24' in source and clean_france24:
            cleaned_body = clean_france24(text, meta)
        elif 'BREAKING_TRAVEL_NEWS' in source and clean_breaking_travel_news:
            cleaned_body = clean_breaking_travel_news(text, meta)
        elif 'INDEPENDENT_TRAVEL' in source and clean_independent_travel:
            cleaned_body = clean_independent_travel(text, meta)
        elif 'AP_NEWS' in source and clean_ap_news:
            cleaned_body = clean_ap_news(text, meta)
        elif 'ETURBONEWS' in source and clean_eturbonews:
            cleaned_body = clean_eturbonews(text, meta)
        elif 'AIR_CURRENT' in source and clean_air_current:
            cleaned_body = clean_air_current(text, meta)
        elif 'ECO_SAPO' in source and clean_eco:
            cleaned_body = clean_eco(text, meta)
        elif 'HUFFPOST' in source and clean_huffpost:
            cleaned_body = clean_huffpost(text, meta)
        elif 'JORNAL_NOTICIAS' in source and clean_jornal_noticias:
            cleaned_body = clean_jornal_noticias(text, meta)
        elif 'TRAVELPULSE' in source and clean_travelpulse:
            cleaned_body = clean_travelpulse(text, meta)
        elif 'FVW' in source and clean_fvw:
            cleaned_body = clean_fvw(text, meta)
        elif 'RTP_NOTICIAS' in source and clean_rtp:
            cleaned_body = clean_rtp(text, meta)
        elif 'SAPO' in source and clean_sapo:
            cleaned_body = clean_sapo(text, meta)
        elif 'SIMPLE_FLYING' in source and clean_simple_flying:
            cleaned_body = clean_simple_flying(text, meta)
        elif 'SKIFT' in source and clean_skift:
            cleaned_body = clean_skift(text, meta)
        elif 'SPIEGEL' in source and clean_spiegel:
            cleaned_body = clean_spiegel(text, meta)
        elif 'SUEDDEUTSCHE' in source and clean_sueddeutsche:
            cleaned_body = clean_sueddeutsche(text, meta)
        elif 'TOURISTIK_AKTUELL' in source and clean_touristik_aktuell:
            cleaned_body = clean_touristik_aktuell(text, meta)
        elif 'TOURMAG' in source and clean_tourmag:
            cleaned_body = clean_tourmag(text, meta)
        elif 'TRAVEL_LEISURE' in source and clean_travel_leisure:
            cleaned_body = clean_travel_leisure(text, meta)
        elif 'WASHINGTON_POST' in source and clean_washington_post:
            cleaned_body = clean_washington_post(text, meta)
        elif 'ANSA_VIAGGI' in source and clean_ansa:
            cleaned_body = clean_ansa(text, meta)
        elif ('BBC_TRAVEL' in source or source == 'BBC') and clean_bbc:
            cleaned_body = clean_bbc(text, meta)
        elif ('CNBC_TRAVEL' in source or 'CNBC' in source) and clean_cnbc:
            cleaned_body = clean_cnbc(text, meta)
        elif 'CNN_TRAVEL' in source and clean_cnn:
            cleaned_body = clean_cnn(text, meta)
        elif 'CONDE_NAST_TRAVELER' in source and clean_conde_nast:
            cleaned_body = clean_conde_nast(text, meta)
        elif 'DIE_ZEIT' in source and clean_die_zeit:
            # 1. Extract specific tags before cleaning
            if extract_zeit_tags:
                new_tags = extract_zeit_tags(text)
                if new_tags:
                    current_tags = meta.get('tags', [])
                    # Append unique new tags
                    for t in new_tags:
                        if t not in current_tags:
                            current_tags.append(t)
                    meta['tags'] = current_tags
            # 2. Clean Text
            cleaned_body = clean_die_zeit(text, meta)
        elif 'EL_MUNDO' in source and clean_elmundo:
            cleaned_body = clean_elmundo(text, meta)
        elif 'EL_PAIS' in source and clean_elpais:
            cleaned_body = clean_elpais(text, meta)
        elif ('EURONEWS_NEWS' in source or 'EURONEWS_TRAVEL' in source) and clean_euronews:
             # 1. Extract Tags
             if extract_euronews_tags:
                 new_tags = extract_euronews_tags(text)
                 if new_tags:
                      current = meta.get('tags', []) or []
                      for t in new_tags:
                          if t not in current:
                              current.append(t)
                      meta['tags'] = current
             # 2. Clean
             cleaned_body = clean_euronews(text, meta)


            
        else:
            cleaned_body = clean_generic(text, meta)
            print("NOT CLEANED, RAW DATA")
    except Exception as e:
        print(f"[ERROR] Cleaning error for {source}: {e}")
        cleaned_body = text # Return raw text on error

    # Metadata Processing (kept in meta dict for use as chunk metadata)
    title = meta.get('title', '').strip()
    title = re.sub(r'<!\[CDATA\[|\]\]>', '', title).strip()
    meta['title'] = title  # Update cleaned title back to meta

    # Get best metadata (might have been updated by cleaners)
    date_str = get_best_date({'metadata': meta})
    meta['date'] = date_str  # Store normalized date in meta
    
    tags_list = normalize_tags(meta.get('tags', []))
    meta['tags'] = tags_list
    tags_str = ", ".join(tags_list) if isinstance(tags_list, list) else str(tags_list)

    # Special handling: if ABC and no tags, try extraction
    if 'ABC_ESPANA' in source and not tags_str:
        try:
             if 'extract_abc_tags' in globals() and extract_abc_tags:
                 extracted = extract_abc_tags(text)
                 if extracted:
                     meta['tags'] = extracted
                     tags_str = ", ".join(extracted)
        except Exception:
            pass

    # Return only the cleaned body - metadata is in meta dict for chunk metadata
    return cleaned_body
