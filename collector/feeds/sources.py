"""
RSS source configuration.

This file stores the RSS feeds used by the collector.

The source list is copied from the previous thesis repo:
    /Volumes/Samsung_T5/thesis/src/00__rss_feeds.py

The CLI accepts lowercase versions of these names. For example:
    PUBLICO      -> publico
    AL_JAZEERA   -> al_jazeera
    BBC_TRAVEL   -> bbc_travel
"""


RSS_SOURCES = [
    {"name": "PUBLICO", "url": "https://feeds.feedburner.com/PublicoRSS", "enabled": True},
    {"name": "EXPRESSO", "url": "https://feeds.feedburner.com/expresso-geral", "enabled": True},
    {"name": "DIARIO_NOTICIAS", "url": "https://www.dn.pt/feed", "enabled": True},
    {"name": "JORNAL_NOTICIAS", "url": "https://feeds.feedburner.com/jn-ultimas", "enabled": True},
    {"name": "OBSERVADOR", "url": "https://observador.pt/feed/", "enabled": True},
    {"name": "RTP_NOTICIAS", "url": "https://www.rtp.pt/noticias/rss", "enabled": True},
    {"name": "PORTUGAL_NEWS", "url": "https://www.theportugalnews.com/rss", "enabled": True},
    {"name": "PORTUGAL_RESIDENT", "url": "https://www.portugalresident.com/feed/", "enabled": True},
    {"name": "ECO_SAPO", "url": "https://eco.sapo.pt/rss", "enabled": True},
    {"name": "JORNAL_NEGOCIOS", "url": "https://www.jornaldenegocios.pt/rss", "enabled": True},
    {"name": "JORNAL_ECONOMICO", "url": "https://jornaleconomico.pt/rss", "enabled": True},
    {"name": "SAPO_VIAGENS", "url": "https://travelmagg.sapo.pt/rss", "enabled": True},
    {"name": "AMBITUR", "url": "https://www.ambitur.pt/feed", "enabled": True},
    {"name": "EL_PAIS_GENERAL", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "enabled": True},
    {"name": "EL_PAIS_VIAJERO", "url": "https://feeds.elpais.com/mrss-s/list/ep/site/elpais.com/section/elviajero", "enabled": True},
    {"name": "EL_PAIS_ECONOMIA", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/economia/portada", "enabled": True},
    {"name": "EL_PAIS_ESPANA", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/espana/portada", "enabled": True},
    {"name": "EL_PAIS_INTERNACIONAL", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada", "enabled": True},
    {"name": "EL_MUNDO", "url": "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml", "enabled": True},
    {"name": "ABC_ESPANA", "url": "https://www.abc.es/rss/2.0/viajar/", "enabled": True},
    {"name": "HOSTELTUR", "url": "https://www.hosteltur.com/feed", "enabled": True},
    {"name": "BBC", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "enabled": True},
    {"name": "BBC_TRAVEL", "url": "https://www.bbc.com/travel/feed.rss", "enabled": True},
    {"name": "GUARDIAN_GENERAL", "url": "https://www.theguardian.com/uk/rss", "enabled": True},
    {"name": "GUARDIAN_TRAVEL", "url": "https://www.theguardian.com/uk/travel/rss", "enabled": True},
    {"name": "HUFFPOST_WORLD_NEWS", "url": "https://www.huffpost.com/news/world-news/feed", "enabled": True},
    {"name": "HUFFPOST_TRAVEL", "url": "https://www.huffpost.com/section/travel/feed", "enabled": True},
    {"name": "SPIEGEL_REISE", "url": "https://www.spiegel.de/reise/index.rss", "enabled": True},
    {"name": "SUEDDEUTSCHE_REISE", "url": "https://rss.sueddeutsche.de/rss/Reise", "enabled": True},
    {"name": "DIE_ZEIT", "url": "https://newsfeed.zeit.de/index", "enabled": True},
    {"name": "FAZ", "url": "https://www.faz.net/rss/aktuell/", "enabled": True},
    {"name": "TOURISTIK_AKTUELL", "url": "https://www.touristik-aktuell.de/rss/news.xml", "enabled": True},
    {"name": "LE_MONDE", "url": "https://www.lemonde.fr/rss/une.xml", "enabled": True},
    {"name": "LE_FIGARO_GENERAL", "url": "https://www.lefigaro.fr/rss/figaro_actualites.xml", "enabled": True},
    {"name": "LE_FIGARO_VOYAGES", "url": "https://www.lefigaro.fr/rss/figaro_voyages.xml", "enabled": True},
    {"name": "TOURMAG", "url": "https://www.tourmag.com/xml/syndication.rss", "enabled": True},
    {"name": "LECHO_TOURISTIQUE", "url": "https://www.lechotouristique.com/feed", "enabled": True},
    {"name": "ANSA_VIAGGI", "url": "https://www.ansa.it/canale_viaggi/notizie/viaggiart_rss.xml", "enabled": True},
    {"name": "CNN_TRAVEL", "url": "http://rss.cnn.com/rss/edition_travel.rss", "enabled": True},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "enabled": True},
    {"name": "CNBC_TRAVEL", "url": "https://www.cnbc.com/id/10000739/device/rss/rss.html", "enabled": True},
    {"name": "WASHINGTON_POST", "url": "https://feeds.washingtonpost.com/rss/world", "enabled": True},
    {"name": "CONDE_NAST_TRAVELER", "url": "https://www.cntraveler.com/feed/rss", "enabled": True},
    {"name": "TRAVEL_LEISURE", "url": "https://feeds-api.dotdashmeredith.com/v1/rss/google/bee1a82b-9ca0-42a2-b07a-12eed31f7ec3", "enabled": True},
    {"name": "SKIFT", "url": "https://skift.com/feed/", "enabled": True},
    {"name": "AL_JAZEERA", "url": "https://www.aljazeera.com/xml/rss/all.xml", "enabled": True},
    {"name": "EURONEWS_NEWS", "url": "https://pt.euronews.com/rss?format=mrss&level=theme&name=news", "enabled": True},
    {"name": "EURONEWS_TRAVEL", "url": "https://pt.euronews.com/rss?format=mrss&level=vertical&name=travel", "enabled": True},
    {"name": "FRANCE24", "url": "https://www.france24.com/en/rss", "enabled": True},
    {"name": "DW_NEWS", "url": "https://rss.dw.com/rdf/rss-en-all", "enabled": True},
    {"name": "SIMPLE_FLYING", "url": "https://simpleflying.com/feed/", "enabled": True},
    {"name": "BREAKING_TRAVEL_NEWS", "url": "https://feeds.feedburner.com/breakingtravelnews", "enabled": True},
    {"name": "ETURBONEWS", "url": "https://www.eturbonews.com/feed/", "enabled": True},
    {"name": "TRAVELPULSE", "url": "https://www.travelpulse.com/rss", "enabled": True},
    {"name": "AIR_CURRENT", "url": "https://theaircurrent.com/feed/", "enabled": True},
    {"name": "FVW", "url": "https://www.fvw.de/feed", "enabled": True},
    {"name": "INDEPENDENT_TRAVEL", "url": "https://www.independent.co.uk/travel/rss", "enabled": True},
]


def get_cli_name(source_name):
    """
    Convert a canonical source name into the name users type in commands.

    PARAMETERS:
    - source_name: The uppercase source name, such as "AL_JAZEERA"

    RETURNS:
    - The lowercase command name, such as "al_jazeera"
    """
    return source_name.lower()


def get_enabled_sources():
    """
    Return every source that is currently enabled.

    PARAMETERS:
    - None

    RETURNS:
    - A list of source dictionaries where enabled is True
    """
    enabled_sources = []

    for source in RSS_SOURCES:
        if source["enabled"]:
            enabled_sources.append(source)

    return enabled_sources


def get_source_by_cli_name(cli_name):
    """
    Find one enabled source from the lowercase command name.

    PARAMETERS:
    - cli_name: A lowercase source name, such as "publico"

    RETURNS:
    - The matching source dictionary

    RAISES:
    - ValueError if the source is not known or not enabled
    """
    for source in get_enabled_sources():
        if get_cli_name(source["name"]) == cli_name:
            return source

    raise ValueError(f"Unknown source: {cli_name}")


def select_sources(source_arguments):
    """
    Convert command-line source arguments into source dictionaries.

    PARAMETERS:
    - source_arguments: A list like ["all"] or ["bbc", "publico"]

    RETURNS:
    - A list of selected source dictionaries

    RAISES:
    - ValueError if the user mixes all with source names
    - ValueError if any source name is unknown
    """
    if len(source_arguments) == 0:
        raise ValueError("Please choose 'all' or at least one source name.")

    if "all" in source_arguments and len(source_arguments) > 1:
        raise ValueError("Use either 'all' or specific source names, not both.")

    if source_arguments[0] == "all":
        return get_enabled_sources()

    selected_sources = []

    for source_argument in source_arguments:
        selected_source = get_source_by_cli_name(source_argument)
        selected_sources.append(selected_source)

    return selected_sources
