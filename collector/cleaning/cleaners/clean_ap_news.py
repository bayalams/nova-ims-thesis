"""
AP News Cleaner
===============

AP pages contain heavy repeated chrome (menus/share/privacy/ad blocks), plus
source-specific formats like LIVE updates and image galleries.
"""

from collections import Counter
import re

from .utils import trim_header_by_title

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s(?:AM|PM)\sGMT$")
_LIVE_HINT_RE = re.compile(r"^\d{1,2}:\d{2}\s(?:AM|PM)\sGMT$", re.MULTILINE)
_SETEXT_LINE_RE = re.compile(r"^[=\-]{4,}$")
_DATELINE_RE = re.compile(r"\(AP\)\s+—")
_MIN_READ_RE = re.compile(r"^\d+\s+MIN READ$", re.IGNORECASE)
_GALLERY_RE = re.compile(r"^\d+\s+of\s+\d+\s*\|?$", re.IGNORECASE)
_DATE_RE = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}$")
_UPDATED_RE = re.compile(
    r"^Updated\s+\d{1,2}:\d{2}\s(?:AM|PM)\sGMT,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}$"
)

_JUNK_EXACT = {
    "Menu",
    "SECTIONS",
    "TOP STORIES",
    "Newsletters",
    "AP QUIZZES",
    "MORE",
    "DONATE",
    "Search Query",
    "Submit Search",
    "Show Search",
    "Submit",
    "Or use",
    "Read More",
    "Read more",
    "Share",
    "Link copied",
    "Cookie Settings",
    "Back Button",
    "Search Icon",
    "Filter Icon",
    "Clear",
    "Apply Cancel",
    "Consent Leg.Interest",
    "Most read",
    "Ad Content",
    "sponsored",
    "Keep on reading",
    "About Your Privacy",
    "By",
    "Edited By",
    "Leer en español",
    "'",
}

_JUNK_PREFIXES = (
    "[The Morning Wire",
    "[The Afternoon Wire",
    "[Ground Game",
    "[AP Top 25 Poll",
    "[The Sports Wire",
    "[AP Entertainment Wire",
    "[The World in Pictures",
    "[World of Faith",
    "##### Login or register to continue",
    "List of Third-Party Partners",
    "List of IAB Vendors",
    "### Manage Privacy Choices",
    "### Vendors List",
    "#### Strictly Necessary Tracking Technologies",
    "#### Performance Tracking Technologies",
    "#### Functional Tracking Technologies",
    "#### Social Media Tracking Technologies",
    "#### Targeting Tracking Technologies",
    "#### Store and/or access information on a device",
    "#### Personalised advertising and content, advertising and content measurement, audience research and services development",
    "#### Use precise geolocation data",
    "#### Actively scan device characteristics for identification",
    "### Related",
)

_JUNK_CONTAINS = (
    "add ap news on google",
    "as your preferred source to see more of our stories on google",
    "the associated press is an independent global news organization",
    "from ap news",
    "cookie settings",
    "do not sell or share my personal information",
    "manage privacy choices",
    "see purposes and manage privacy choices",
    "your opt out preference signal is honored",
    "we care about your privacy",
    "our partners process data to provide",
    "strictly necessary tracking technologies",
    "allow sale of my personal information",
    "i reject all",
    "i accept all",
    "view illustrations",
    "view vendor details",
    "confirm my choices",
    "switch label",
    "checkbox label",
    "newsletters?id=",
    "get email alerts",
    "newsletter delivering",
    "sent directly to your inbox",
    "exclusive insights and key stories",
    "your home base for in-depth reporting",
    "comprehensive global coverage of how religion",
    "get caught up on what you may have missed",
    "undo",
)

_SOCIAL_LINES = {
    "facebook",
    "email",
    "x",
    "linkedin",
    "bluesky",
    "flipboard",
    "pinterest",
    "reddit",
    "twitter",
    "instagram",
}

_GENERIC_NAV_LABELS = {
    "world",
    "u.s.",
    "politics",
    "sports",
    "entertainment",
    "business",
    "science",
    "fact check",
    "oddities",
    "be well",
    "newsletters",
    "photography",
    "climate",
    "health",
    "tech",
    "lifestyle",
    "religion",
    "español",
    "sign in",
}

_FOOTER_STARTS = (
    "Most read",
    "Ad Content",
    "We Care About Your Privacy",
    "Your Opt Out Preference Signal is Honored",
    "Do Not Sell or Share My Personal Information",
    "About Your Privacy",
    "### Manage Privacy Choices",
    "### Vendors List",
    "Cookie List",
    "Keep on reading",
    "sponsored",
    "Copyright ",
    "About",
    "Contact Us",
    "Accessibility Statement",
    "Terms of Use",
    "Privacy Policy",
    "ap.org",
    "Careers",
    "Advertise with us",
)

_RELATED_HEADERS = {"Related Stories", "Related stories"}


def _normalize(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


def _looks_like_junk_line(line: str) -> bool:
    sline = line.strip()
    if not sline:
        return False

    if sline in _JUNK_EXACT:
        return True

    if any(sline.startswith(prefix) for prefix in _JUNK_PREFIXES):
        return True

    lower = sline.lower()
    if any(token in lower for token in _JUNK_CONTAINS):
        return True

    bullet_stripped = re.sub(r"^[\*\+\-]\s*", "", sline).strip().lower()
    if bullet_stripped in _SOCIAL_LINES:
        return True
    if bullet_stripped in _GENERIC_NAV_LABELS:
        return True
    if lower in _GENERIC_NAV_LABELS:
        return True

    if re.match(r"^\*\s*\+\s*\[", sline):
        return True
    if re.match(r"^[\*\-\+]\s*(Copy|Print)$", sline):
        return True
    if re.match(r"^[\*\-\+]\s+[A-Za-z][A-Za-z0-9\.\-’'& ]{1,35}$", sline):
        # Compact bullet nav labels (e.g., "- Weather", "+ Most watched videos").
        return True
    if re.match(r"^\*+\s*$", sline):
        return True
    if re.match(r"^\[\s*\]\(https?://", sline):
        return True
    if re.match(r"^\+ The Associated Press$", sline):
        return True
    if re.match(r"^\* From AP News$", sline):
        return True

    return False


def _is_gallery_line(line: str) -> bool:
    sline = line.strip()
    if not sline:
        return False
    if _GALLERY_RE.match(sline):
        return True
    if "(AP Photo/" in sline or "(AP Photo," in sline:
        return True
    if "via AP)" in sline and len(sline) < 280:
        return True
    return False


def _is_footer_start(line: str) -> bool:
    sline = line.strip()
    if not sline:
        return False
    return any(sline.startswith(marker) for marker in _FOOTER_STARTS)


def _is_live_article(raw_text: str) -> bool:
    ts_count = len(_LIVE_HINT_RE.findall(raw_text))
    return ts_count >= 3 and "live" in raw_text.lower()


def _cleanup_markup(text: str) -> str:
    # Remove markdown images before line filtering.
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Flatten markdown links.
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def _find_setext_heading_start(lines: list[str]) -> int:
    for i in range(len(lines) - 1):
        current = lines[i].strip()
        nxt = lines[i + 1].strip()
        if not current or not nxt:
            continue
        if not re.match(r"^={4,}$", nxt):
            continue
        if len(current) < 20:
            continue
        if _looks_like_junk_line(current):
            continue
        if current.lower() in _GENERIC_NAV_LABELS:
            continue
        return i
    return -1


def _find_first_idx(lines: list[str], predicate) -> int:
    for i, ln in enumerate(lines):
        if predicate(ln.strip()):
            return i
    return -1


def _trim_to_probable_article_start(text: str, is_live: bool) -> str:
    lines = text.split("\n")
    if not lines:
        return text

    heading_idx = _find_setext_heading_start(lines)
    dateline_idx = _find_first_idx(lines, lambda s: bool(_DATELINE_RE.search(s)))
    updated_idx = _find_first_idx(lines, lambda s: bool(_UPDATED_RE.match(s)))

    # Prefer explicit setext title when available. Otherwise fall back to updated/dateline.
    candidates = [idx for idx in (heading_idx, updated_idx, dateline_idx) if idx != -1]
    if not candidates:
        return text

    start_idx = min(candidates)

    if dateline_idx != -1 and start_idx > dateline_idx:
        start_idx = max(0, dateline_idx - 8)

    # Avoid trimming to very early false positives in chrome.
    if start_idx < 8:
        return text

    trimmed = "\n".join(lines[start_idx:])

    # Live pages often include a "latest headlines list" before the real setext title.
    if is_live:
        lines2 = trimmed.split("\n")
        h2 = _find_setext_heading_start(lines2)
        if h2 > 0:
            trimmed = "\n".join(lines2[h2:])

    return trimmed


def _filter_ap_lines(lines: list[str], is_live: bool) -> list[str]:
    filtered: list[str] = []
    seen_live_marker = False
    in_related = False
    kept_content_lines = 0

    for line in lines:
        sline = line.strip()
        if not sline:
            if filtered and filtered[-1] != "":
                filtered.append("")
            continue

        if _is_footer_start(sline) and kept_content_lines >= 20:
            break

        if sline in _RELATED_HEADERS:
            in_related = True
            continue

        if in_related:
            if _MIN_READ_RE.match(sline) or _looks_like_junk_line(sline):
                continue
            # End related stories block when real text resumes.
            if len(sline) > 80 or _DATELINE_RE.search(sline):
                in_related = False
            else:
                continue

        if is_live:
            if sline == "LIVE":
                seen_live_marker = True
                continue
            if not seen_live_marker and (_TIME_RE.match(sline) or _DATE_RE.match(sline)):
                continue
            if sline in {"ALL", "breaking news updates"}:
                continue

        if _looks_like_junk_line(sline):
            continue
        if _is_gallery_line(sline):
            continue

        if sline.startswith("By ") and len(sline) <= 120:
            continue
        if sline.startswith("Updated [hour]:[minute]"):
            continue

        # Remove setext underline noise if previous line is empty or also underline.
        if _SETEXT_LINE_RE.match(sline):
            # Keep '=' title underlines. Drop long '-' separators as noise.
            if re.match(r"^-{4,}$", sline):
                continue
            if not filtered or filtered[-1] == "" or _SETEXT_LINE_RE.match(filtered[-1]):
                continue

        filtered.append(sline)
        kept_content_lines += 1

    return filtered


def _dedupe_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen = Counter()

    for line in lines:
        sline = line.strip()
        if not sline:
            if deduped and deduped[-1] != "":
                deduped.append("")
            continue

        norm = _normalize(sline)
        seen[norm] += 1

        # Keep first occurrence only for repeated lines.
        if seen[norm] > 1:
            continue

        deduped.append(sline)

    return deduped


def _looks_like_byline(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s in {"By", "Edited By"}:
        return True
    # Uppercase "THE ASSOCIATED PRESS" or names like "WAFAA SHURAFA and SAM METZ".
    if len(s) <= 120 and re.fullmatch(r"[A-ZÀ-ÖØ-Ý'`\.\- ,&]+", s):
        return True
    if s.startswith("Updated "):
        return True
    return False


def _prune_prelude_before_dateline(lines: list[str], is_live: bool) -> list[str]:
    if is_live:
        return lines

    dateline_idx = next((i for i, ln in enumerate(lines) if _DATELINE_RE.search(ln)), -1)
    if dateline_idx == -1 or dateline_idx < 4:
        return lines

    prefix = lines[:dateline_idx]
    suffix = lines[dateline_idx:]

    keep_prefix: list[str] = []
    for i, ln in enumerate(prefix):
        s = ln.strip()
        if not s:
            if keep_prefix and keep_prefix[-1] != "":
                keep_prefix.append("")
            continue

        # Keep title + title underline at very top.
        if i <= 1:
            keep_prefix.append(s)
            continue

        # Keep byline/updated metadata only, drop teaser/caption lines.
        if _looks_like_byline(s):
            keep_prefix.append(s)
            continue

    merged = keep_prefix + ([""] if keep_prefix and keep_prefix[-1] != "" else []) + suffix
    return merged


def _compute_metrics(raw_text: str, cleaned_text: str) -> dict:
    raw_lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    clean_lines = [ln.strip() for ln in cleaned_text.splitlines() if ln.strip()]

    clean_count = len(clean_lines)
    raw_count = len(raw_lines)

    remaining_noise = sum(1 for ln in clean_lines if _looks_like_junk_line(ln))
    noise_ratio = (remaining_noise / clean_count) if clean_count else 0.0

    if clean_count:
        normalized = [_normalize(ln) for ln in clean_lines]
        dup_ratio = (len(normalized) - len(set(normalized))) / len(normalized)
    else:
        dup_ratio = 0.0

    dateline_idx = next((i for i, ln in enumerate(clean_lines) if _DATELINE_RE.search(ln)), -1)
    body_lines_after_dateline = max(0, clean_count - dateline_idx - 1) if dateline_idx != -1 else 0

    return {
        "raw_non_empty_lines": raw_count,
        "clean_non_empty_lines": clean_count,
        "retained_line_ratio": round((clean_count / raw_count), 4) if raw_count else 0.0,
        "noise_ratio": round(noise_ratio, 4),
        "dup_ratio": round(dup_ratio, 4),
        "body_lines_after_dateline": body_lines_after_dateline,
    }


def clean_ap_news(text, meta):
    """
    Cleaner for AP_NEWS articles.
    """
    if not text:
        return ""

    raw_text = text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _cleanup_markup(text)
    text = trim_header_by_title(text, (meta or {}).get("title"))
    is_live = _is_live_article(raw_text)
    text = _trim_to_probable_article_start(text, is_live=is_live)

    lines = text.split("\n")
    lines = _filter_ap_lines(lines, is_live=is_live)
    lines = _dedupe_lines(lines)
    lines = _prune_prelude_before_dateline(lines, is_live=is_live)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if isinstance(meta, dict):
        meta["cleaner_metrics"] = _compute_metrics(raw_text, cleaned)

    return cleaned
