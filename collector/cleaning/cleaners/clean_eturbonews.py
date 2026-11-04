"""
eTurboNews Cleaner
==================

Cleans articles from ETURBONEWS source.

These articles have a heavy template that includes:
- Site header banner ("eTN is published from Berlin...")
- Social media link list
- Audio player controls (GSpeech)
- Language selector (~40 languages)
- Language flag links (huge single-line block with [![xx]() Lang](url) patterns)
- Table-of-contents bullet list
- Author bios, promotional blocks, and footer widgets
"""

import re


# Known social-media / nav items that appear as bullet-list items
_SOCIAL_NAV = {
    "Facebook Group", "Facebook Page", "Twitter", "Linkedin", "YOUTUBE",
    "Instagram", "Telegram", "TikTok", "WhatsApp", "RSS",
}

# Known language names used in the "Select YOUR LANGUAGE" dropdown
_LANGUAGES = {
    "Albanian", "Arabic", "Armenian", "Bosnian", "Bulgarian", "Catalan",
    "Cantonese", "Chinese", "Croatian", "Czech", "Danish", "Dutch",
    "English", "Filipino", "Finnish", "French", "Georgian", "German",
    "Greek", "Hebrew", "Hindi", "Hungarian", "Icelandic", "Indonesian",
    "Italian", "Japanese", "Kannada", "Korean", "Latvian", "Lithuanian",
    "Macedonian", "Mongolian", "Nepali", "Norwegian", "Persian", "Polish",
    "Portuguese", "Romanian", "Russian", "Serbian", "Sinhala", "Slovak",
    "Slovenian", "Spanish", "Swahili", "Swedish", "Tamil", "Thai",
    "Turkish", "Vietnamese",
}

# Playback-speed values that appear as bullet items
_PLAYBACK_SPEEDS = {
    "0.5", "0.6", "0.7", "0.8", "0.9", "1", "1.1", "1.2", "1.3", "1.5", "2",
}


def clean_eturbonews(text, meta):
    """
    Cleaner for ETURBONEWS articles.
    """
    if not text:
        return ""

    # ── Phase 0: regex-based bulk removals ──────────────────────────

    # Remove the giant language-flag-link lines:  [![sq]() Albanian](url)...
    text = re.sub(
        r'\[!\[[a-zA-Z\-]{2,5}\]\(\)\s+\w[^\]]*\]\(https?://[^\)]+\)',
        '', text
    )

    # Remove empty markdown links:  [](url)
    text = re.sub(r'\[\]\(https?://[^\)]+\)', '', text)

    # Remove markdown images:  ![alt](url)
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)

    # Flatten remaining links:  [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remove orphaned title-attribute fragments: "Albanian") etc.
    text = re.sub(r'"\w+"\)', '', text)

    # Remove lines that are just punctuation residue
    text = re.sub(r'^\s*["\)\(]{1,4}\s*$', '', text, flags=re.MULTILINE)

    # ── Phase 1: line-by-line filtering ─────────────────────────────

    lines = text.split('\n')
    filtered = []
    in_toc = False

    for line in lines:
        sline = line.strip()

        # Blank lines: keep (collapsed later)
        if not sline:
            in_toc = False
            filtered.append(line)
            continue

        # ── Header / banner noise ──
        if "eTN** is published from" in sline:
            continue
        if sline == "the City of Freedom":
            continue

        # ── Social-media bullet list ──
        bare = sline.lstrip("* ").strip()
        if bare in _SOCIAL_NAV:
            continue

        # ── Audio player controls ──
        if sline in ("Press play to listen to this content",
                      "Playback Speed", "Open text",
                      "Download audioDownloaded:0",
                      "Powered By GSpeech"):
            continue
        if sline in ("0:00", "-:--", "1x"):
            continue
        if bare in _PLAYBACK_SPEEDS:
            continue

        # ── Language selector ──
        if sline == "Select YOUR LANGUAGE":
            continue
        if bare in _LANGUAGES:
            continue
        # Standalone " English" after language-flag block
        if sline == "English" and not filtered:
            continue
        if sline == "English" and filtered:
            # Only skip if the previous non-blank line was also noise
            prev_content = [f for f in filtered if f.strip()]
            if not prev_content or prev_content[-1].strip() in _LANGUAGES:
                continue

        # ── Separator lines ──
        if re.match(r'^-{3,}$', sline):
            continue

        # ── Promotional CTAs ──
        if "Register here and now" in sline:
            continue
        if "Still need tickets for" in sline:
            continue
        if "Click here" in sline and ("news to share" in sline or "tickets" in sline.lower()):
            continue

        # ── Author byline ──
        if sline.startswith("Written by "):
            continue

        # ── Image courtesy lines ──
        if sline.lower().startswith("image courtesy of"):
            continue

        # ── Table of contents (bullet list of section headings before body) ──
        # right after language-block cleanup and before the first paragraph.
        # This is handled implicitly: the ToC items are kept as-is since they
        # also appear as section headers in the article body.

        filtered.append(line)

    text = '\n'.join(filtered)

    # ── Phase 2: footer trimming ────────────────────────────────────

    footer_markers = [
        "\n### You may also like",
        "\n### About the author",
        "\n### Leave a Comment",
        "\n#### Podcast",
        "\n#### Share",
        "\n#### Join us!",
        "\n#### Amazing Travel Awards",
        "\n#### Featured Posts",
        "\nCopy link",
        "\nFind any service",
    ]

    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    text = text[:first_idx]

    # ── Phase 3: final cleanup ──────────────────────────────────────

    # Remove "Destinations International Home" standalone lines
    text = re.sub(r'^Destinations International Home$', '', text, flags=re.MULTILINE)

    # Remove quoted related article links: > [Article Title](url)
    text = re.sub(r'^\s*>\s*\[.*?\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)

    # Collapse multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)

    return text.strip()
