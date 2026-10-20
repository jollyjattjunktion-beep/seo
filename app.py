from __future__ import annotations

import io
import json
import os
import re
import requests
from html.parser import HTMLParser
from html import unescape
from urllib.parse import urlparse
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from preferences import DEFAULTS, load_preferences, save_preferences
from seo_engine import extract_title_terms, generate_package, score_metadata
from youtube_api import YouTubeAPIError, compact_number, format_published_date, search_videos

load_dotenv()
st.set_page_config(page_title="Preet Sports SEO Generator", page_icon="🏏", layout="wide")

if "preferences" not in st.session_state:
    st.session_state.preferences = load_preferences()
if "competitor_results" not in st.session_state:
    st.session_state.competitor_results = []
if "competitor_query" not in st.session_state:
    st.session_state.competitor_query = ""
if "generated_packages" not in st.session_state:
    st.session_state.generated_packages = []
if "crex_match_prefill" not in st.session_state:
    st.session_state.crex_match_prefill = {}
if "youtube_keyword_opportunities" not in st.session_state:
    st.session_state.youtube_keyword_opportunities = []

prefs = st.session_state.preferences

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1450px;}
.ps-hero {padding: 1.1rem 1.35rem; border: 1px solid rgba(128,128,128,.25); border-radius: 16px; margin-bottom: 1rem;}
.ps-muted {color: #737373; font-size: .9rem;}
</style>
""", unsafe_allow_html=True)

st.title("🏏 Preet Sports — YouTube SEO Generator")
st.caption("Match-aware metadata • public competitor research • transparent SEO checklist")

with st.sidebar:
    st.header("Connection")
    env_key = os.getenv("YOUTUBE_API_KEY", "")
    api_key = st.text_input("YouTube Data API key", value=env_key, type="password", help="Kept in this browser session; the app does not save it to preferences.")
    st.caption("Enable YouTube Data API v3 in Google Cloud. Public competitor search uses this API key.")
    st.divider()
    st.header("Workspace")
    page = st.radio("Open", ["Generate SEO", "Competitor Research", "Preet Sports Defaults", "About & Limits"], label_visibility="collapsed")
    st.divider()
    st.caption("Tags are a minor discovery factor compared with the title, thumbnail and description. The score is a local checklist, not YouTube's ranking score.")



def _clean_field(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fit_title_app(title: str, limit: int = 100) -> str:
    title = _clean_field(title)
    if len(title) <= limit:
        return title
    # Prefer a clean word boundary rather than chopping a word in half.
    shortened = title[:limit].rsplit(" ", 1)[0].rstrip(" |:-")
    return shortened or title[:limit]


def _build_match_titles(topic: str, mode: str, match: dict[str, str],
                        preferences: dict, coverage: str) -> list[str]:
    """Create concise, distinct titles with exact-match wording first."""
    channel = _clean_field(preferences.get("channel_name", "Preet Sports")) or "Preet Sports"
    language = _clean_field(preferences.get("language", "Hindi")) or "Hindi"

    if mode != "Cricket match / live score":
        base = _clean_field(topic) or "YouTube video"
        candidates = [
            f"{base}: Practical Guide & Key Tips",
            f"{base} Explained | Step-by-Step Guide",
            f"{base}: Important Details & Examples",
        ]
    else:
        a = _clean_field(match.get("team_a")) or "Team 1"
        b = _clean_field(match.get("team_b")) or "Team 2"
        stage = _clean_field(match.get("match_number"))
        tournament = _clean_field(match.get("tournament"))
        year = _clean_field(match.get("year"))
        fixture = f"{a} vs {b}"
        match_format = _clean_field(match.get("match_format"))

        # Keep the exact fixture at the beginning. Only use wording that matches
        # the selected coverage type; stage and match format are separate fields.
        if coverage == "Live reaction and discussion":
            candidates = [
                f"{fixture} Live | {stage} | Fan Discussion" if stage else f"{fixture} Live | Fan Discussion",
                f"{fixture} Live Match Reaction & Discussion",
                f"{fixture} | {stage} | Preet Sports Discussion" if stage else f"{fixture} | Preet Sports Discussion",
            ]
        elif coverage == "Live score updates and Hindi commentary":
            candidates = [
                f"{fixture} Live Score | {stage} | {language} Commentary" if stage else f"{fixture} Live Score | {language} Commentary",
                f"{fixture} Live Match | Ball-by-Ball {language} Commentary",
                f"{fixture} Live Score | {match_format}" if match_format else f"{fixture} Live Score Today",
            ]
        elif coverage == "Pre-match analysis":
            candidates = [
                f"{fixture} Preview | {stage} | Match Analysis" if stage else f"{fixture} Preview | Match Analysis",
                f"{fixture} Match Preview & Key Players",
                f"{fixture} | {tournament} Preview" if tournament else f"{fixture} | Match Preview",
            ]
        else:  # Post-match review
            candidates = [
                f"{fixture} Match Review | Key Moments & Analysis",
                f"{fixture} Result & Match Analysis | {stage}" if stage else f"{fixture} Result & Match Analysis",
                f"{fixture} | {tournament} Review" if tournament else f"{fixture} | Match Review",
            ]

        # Add verified context only where it improves distinction and fits.
        context = " | ".join(x for x in [tournament, year] if x)
        if context:
            revised = []
            for title in candidates:
                if len(title) <= 76 and context.casefold() not in title.casefold():
                    revised.append(f"{title} | {context}")
                else:
                    revised.append(title)
            candidates = revised

        # Include the channel name only when the title remains concise.
        if channel:
            candidates = [
                f"{title} | {channel}"
                if len(title) + len(channel) + 3 <= 100 and channel.casefold() not in title.casefold()
                else title
                for title in candidates
            ]

    unique = []
    seen = set()
    for candidate in candidates:
        candidate = _fit_title_app(candidate, 100)
        key = candidate.casefold()
        if candidate and key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique[:3]


def _build_match_description(topic: str, mode: str, match: dict[str, str],
                             preferences: dict, extra: str, coverage: str,
                             hashtags: list[str]) -> str:
    """Build a readable, accurate description with stage and format kept distinct."""
    channel = _clean_field(preferences.get("channel_name", "Preet Sports")) or "Preet Sports"
    language = _clean_field(preferences.get("language", "Hindi")) or "Hindi"
    custom_intro = _clean_field(preferences.get("description_intro", "Welcome to Preet Sports!"))
    cta = _clean_field(preferences.get("subscribe_cta", "Subscribe to Preet Sports for more cricket discussions."))
    extra = _clean_field(extra)

    if mode != "Cricket match / live score":
        sections = [
            f"{_clean_field(topic)} | {channel}",
            f"{custom_intro} This video covers {_clean_field(topic)} with relevant context and practical details.",
            cta,
        ]
    else:
        a = _clean_field(match.get("team_a")) or "Team 1"
        b = _clean_field(match.get("team_b")) or "Team 2"
        fixture = f"{a} vs {b}"
        stage = _clean_field(match.get("match_number"))
        tournament = _clean_field(match.get("tournament"))
        year = _clean_field(match.get("year"))
        match_format = _clean_field(match.get("match_format"))

        coverage_copy = {
            "Live reaction and discussion": (
                "Join the live match reaction and fan discussion. Follow the match conversation, "
                "key moments, wickets, boundaries and turning points discussed on the stream."
            ),
            "Live score updates and Hindi commentary": (
                f"Follow {fixture} live score updates and {language} commentary as provided during the stream, "
                "including key moments, wickets, boundaries and partnerships."
            ),
            "Pre-match analysis": (
                f"Explore the {fixture} match preview, team context, players to watch and pre-match analysis."
            ),
            "Post-match review": (
                f"Review the {fixture} result, key moments, turning points and post-match analysis."
            ),
        }

        # The first two lines lead with the exact fixture and actual coverage.
        first_line_parts = [fixture]
        if stage:
            first_line_parts.append(stage)
        if coverage == "Live score updates and Hindi commentary":
            first_line_parts.append("Live Score")
            first_line_parts.append(f"{language} Commentary")
        elif coverage == "Live reaction and discussion":
            first_line_parts.append("Live Fan Discussion")
        elif coverage == "Pre-match analysis":
            first_line_parts.append("Match Preview")
        else:
            first_line_parts.append("Match Review")
        first_line_parts.append(channel)

        sections = [
            "🔴 " + " | ".join(first_line_parts),
            f"{custom_intro} {coverage_copy.get(coverage, 'Join the match discussion and follow the key moments.')}",
        ]

        details = [f"Teams: {fixture}"]
        if stage:
            details.append(f"Stage: {stage}")
        if match_format:
            details.append(f"Format: {match_format}")
        venue = _clean_field(match.get("venue"))
        start_time = _clean_field(match.get("start_time"))
        if venue:
            details.append(f"Venue: {venue}")
        if start_time:
            details.append(f"Date / Start time (as listed): {start_time}")
        if tournament:
            details.append(f"Tournament / Series: {tournament}")
        if year:
            details.append(f"Season / Year: {year}")
        if details:
            sections.append("🏏 MATCH DETAILS\n" + "\n".join(details))

        if coverage == "Live reaction and discussion":
            sections.append(
                "💬 WHAT YOU CAN EXPECT\n"
                "• Fan reactions and match discussion\n"
                "• Analysis of wickets, boundaries and partnerships\n"
                "• Discussion of important match moments\n"
                "• Respectful conversation with fellow cricket fans"
            )
        elif coverage == "Live score updates and Hindi commentary":
            sections.append(
                f"📣 MATCH COVERAGE\n"
                f"• Live score updates and match situation\n"
                f"• {language} commentary, where provided\n"
                "• Key wickets, boundaries and partnerships"
            )
        elif coverage == "Pre-match analysis":
            sections.append(
                "📋 PRE-MATCH COVERAGE\n"
                "• Match context and team analysis\n"
                "• Players to watch\n"
                "• Match discussion and predictions"
            )
        else:
            sections.append(
                "📊 MATCH REVIEW\n"
                "• Result and key moments\n"
                "• Turning points and partnerships\n"
                "• Post-match analysis"
            )

        sections.append(
            f"💬 JOIN THE DISCUSSION\nWho do you think will win / how do you rate {fixture}? "
            "Share your thoughts respectfully."
        )
        sections.append(cta)

    if extra:
        sections.append("📌 ADDITIONAL VIDEO DETAILS\n" + extra)
    if hashtags:
        # Hashtags belong at the end of the description; keyword tags remain
        # in the separate YouTube Studio Tags field.
        sections.append(" ".join(hashtags[:3]))

    description = "\n\n".join(section for section in sections if _clean_field(section)).strip()
    return description.replace("<", "").replace(">", "")[:4900].strip()


def _apply_editorial_metadata(packages: list[dict], topic: str, mode: str,
                              match: dict[str, str], preferences: dict,
                              extra: str, coverage: str) -> list[dict]:
    """Replace repetitive/overclaiming drafts with content-aligned metadata and rescore."""
    if not packages:
        return packages

    titles = _build_match_titles(topic, mode, match, preferences, coverage)
    hashtags = packages[0].get("hashtags", [])
    tags = packages[0].get("tags", [])
    description = _build_match_description(topic, mode, match, preferences, extra, coverage, hashtags)

    # Keep exactly three options where possible; make a third distinct fallback if needed.
    if mode == "Cricket match / live score":
        a = _clean_field(match.get("team_a")) or "Team 1"
        b = _clean_field(match.get("team_b")) or "Team 2"
        fixture = f"{a} vs {b}"
        fallback = f"{fixture} | {coverage} | Preet Sports"
    else:
        fallback = f"{_clean_field(topic)} | Key Details | Preet Sports"
    while len(titles) < min(3, len(packages)):
        candidate = _fit_title_app(fallback if fallback.casefold() not in {t.casefold() for t in titles} else f"{fallback} Guide")
        if candidate.casefold() in {t.casefold() for t in titles}:
            break
        titles.append(candidate)

    output = []
    for index, original in enumerate(packages):
        title = titles[index] if index < len(titles) else original.get("title", "")
        score, strengths, improvements = score_metadata(title, description, tags, hashtags, topic)
        item = dict(original)
        item.update({
            "option": index + 1,
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "seo_score": score,
            "score_label": "Editorial metadata checklist — not an official YouTube score or ranking prediction",
            "strengths": strengths,
            "improvements": improvements,
            "tag_characters": len(",".join(tags)),
            "title_characters": len(title),
            "description_characters": len(description),
        })
        output.append(item)
    return output




class _CREXParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts, self.text_parts, self.meta = [], [], {}
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"):
                self.meta[key] = unescape(attrs["content"].strip())
    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False
    def handle_data(self, data):
        value = re.sub(r"\s+", " ", data or "").strip()
        if value:
            self.text_parts.append(value)
            if self.in_title:
                self.title_parts.append(value)


class _ClassTextCollector(HTMLParser):
    """Collect readable text from every div containing a requested CSS class."""
    def __init__(self, class_name: str):
        super().__init__(convert_charrefs=True)
        self.class_name = class_name.casefold()
        self.values: list[str] = []
        self._capture_depth: int | None = None
        self._capture_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "div":
            return
        attrs_dict = dict(attrs)
        classes = (attrs_dict.get("class") or "").split()
        if self._capture_depth is not None:
            # Count nested divs so we don't stop at the first inner </div>.
            self._capture_depth += 1
        elif self.class_name in {item.casefold() for item in classes}:
            self._capture_depth = 1
            self._capture_parts = []

    def handle_data(self, data):
        if self._capture_depth is not None and data:
            self._capture_parts.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() == "div" and self._capture_depth is not None:
            self._capture_depth -= 1
            if self._capture_depth == 0:
                value = re.sub(r"\s+", " ", unescape(" ".join(self._capture_parts))).strip()
                if value:
                    self.values.append(value)
                self._capture_depth = None
                self._capture_parts = []


def _extract_class_texts(html: str, class_name: str) -> list[str]:
    """Return text from all matching classed divs, including nested div content."""
    collector = _ClassTextCollector(class_name)
    collector.feed(html or "")
    return collector.values


def _extract_class_text(html: str, class_name: str) -> str:
    """Backward-compatible helper returning the first classed div's text."""
    values = _extract_class_texts(html, class_name)
    return values[0] if values else ""


def _looks_like_date_time(value: str) -> bool:
    """Reject date/time strings accidentally returned as stadium names."""
    value = _clean_field(value)
    has_clock = bool(re.search(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", value, re.I))
    has_weekday = bool(re.search(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", value, re.I))
    has_date = bool(re.search(r"\b\d{1,2}\s+[A-Za-z]{3,9}\b", value, re.I))
    return has_clock and (has_weekday or has_date)


def _looks_like_venue(value: str) -> bool:
    """Accept common cricket-ground names and reject dates/times."""
    value = _clean_field(value)
    if not value or _looks_like_date_time(value):
        return False
    return bool(re.search(r"\b(?:Oval|Stadium|Ground|Cricket Park|Cricket Club|Sports Ground)\b", value, re.I))


def _fetch_crex_match(url: str) -> dict[str, str]:
    """Fetch a CREX match page and extract teams, format, series, venue and time."""
    url = (url or "").strip()
    if not re.match(r"^https?://(www\.)?crex\.com/", url, flags=re.I):
        raise ValueError("Enter a valid https://crex.com match URL.")
    response = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }, timeout=20)
    response.raise_for_status()
    html = response.text
    parser = _CREXParser()
    parser.feed(html)
    visible = " ".join(parser.text_parts)

    # Prefer Open Graph metadata, as CREX often puts the full series name there.
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.title_parts)
    title = unescape(re.sub(r"\s+", " ", title)).strip()
    path = urlparse(url).path.lower()
    combined = f"{title} {visible} {path}"

    # CREX has direct CSS hooks for venue and date/time, for example:
    # <div class="venue">North Sydney Oval</div>
    # <div class="match-date">...<div>Tuesday, 20 October, 1:45 PM</div></div>
    # Some CREX pages include repeated classed blocks (or hidden fixture tiles).
    # Check all of them and never accept a clock/date string as a venue name.
    venue_class_values = _extract_class_texts(html, "venue")
    venue_from_class = next((value for value in venue_class_values if _looks_like_venue(value)), "")
    date_class_values = _extract_class_texts(html, "match-date")
    date_from_class = next((value for value in date_class_values if _looks_like_date_time(value)), "")

    # Extract teams from og:title before the stage/format marker.
    team_a = team_b = ""
    mt = re.search(
        r"^(.+?)\s+vs\s+(.+?)(?=\s+(?:1st|2nd|3rd|\d+(?:st|nd|rd|th)|live score|live match|match info|odi tri|t20|test)\b|$)",
        title, re.I
    )
    if mt:
        team_a, team_b = mt.group(1).strip(" -|"), mt.group(2).strip(" -|")
    abbr = {"eng":"England", "pak":"Pakistan", "ind":"India", "aus":"Australia",
            "sl":"Sri Lanka", "nz":"New Zealand", "wi":"West Indies", "sa":"South Africa",
            "ban":"Bangladesh", "afg":"Afghanistan", "zim":"Zimbabwe", "ire":"Ireland",
            "usa":"USA", "nep":"Nepal", "can":"Canada"}
    if not team_a or not team_b:
        mt = re.search(r"/([a-z]{2,4})-vs-([a-z]{2,4})-", path, re.I)
        if mt:
            team_a = abbr.get(mt.group(1).lower(), mt.group(1).upper())
            team_b = abbr.get(mt.group(2).lower(), mt.group(2).upper())

    fmt = ""
    if re.search(r"\bODI\b|one.day", combined, re.I) or "-odi-" in path:
        fmt = "ODI"
    elif re.search(r"\bT20I\b", combined, re.I) or "-t20i" in path:
        fmt = "T20I"
    elif re.search(r"\bT20\b|twenty20", combined, re.I) or "-t20" in path:
        fmt = "T20"
    elif re.search(r"\bTest\b", combined, re.I):
        fmt = "Test"
    elif re.search(r"\bT10\b", combined, re.I):
        fmt = "T10"

    # Some CREX Open Graph titles use a hyphen, e.g. "2nd-T20".
    title_stage_match = re.search(
        r"\b(1st|2nd|3rd|\d{1,2}(?:st|nd|rd|th))\s*[-– ]\s*(ODI|T20I?|Test|T10)\b",
        title, re.I
    )
    stage = ""
    if title_stage_match:
        stage_format = title_stage_match.group(2)
        stage_format = stage_format.upper() if stage_format.lower() in {"odi", "t20", "t20i", "t10"} else "Test"
        stage = f"{title_stage_match.group(1)} {stage_format}"
    else:
        mt = re.search(
            r"\b(?:1st|2nd|3rd|\d{1,2}(?:st|nd|rd|th))\s+(?:ODI|T20I?|Test|Match|Semi[- ]?Final|Final|Qualifier|Eliminator)\b",
            combined, re.I
        )
        if mt:
            stage = re.sub(r"\s+", " ", mt.group(0)).strip()
        else:
            mt = re.search(r"-(1st|2nd|3rd|\d+(?:st|nd|rd|th))-match-", path, re.I)
            if mt:
                stage = f"{mt.group(1)} {fmt}".strip() if fmt else f"{mt.group(1)} Match"

    # If the OG title has a stage, the text between that stage and "Live Score"
    # is the series/tour name (e.g. "New Zealand Women tour of Australia 2026").
    tournament = ""
    if title_stage_match:
        series_tail = title[title_stage_match.end():]
        series_tail = re.split(
            r"\b(?:Live Score|Live Match|Match Info|Updates|Scorecard|Highlights|News)\b",
            series_tail, maxsplit=1, flags=re.I
        )[0]
        series_tail = re.sub(r"^[\s,|:–-]+|[\s,|:–-]+$", "", series_tail).strip()
        if series_tail and re.search(r"\b(?:tour of|series|league|cup|championship|trophy)\b", series_tail, re.I):
            tournament = series_tail

    if not tournament:
        mt = re.search(
            r"([A-Za-z][A-Za-z &'-]*\s+tour of\s+[A-Za-z][A-Za-z &'-]*\s+20\d{2})",
            title, re.I
        )
        if mt:
            tournament = re.sub(r"\s+", " ", mt.group(1)).strip(" .,-")
        else:
            mt = re.search(
                r"(ODI Tri[- ]Series in [A-Za-z ]+? 20\d{2}|Tri[- ]Series in [A-Za-z ]+? 20\d{2}|[A-Za-z ]+? League 20\d{2})",
                combined, re.I
            )
            if mt:
                tournament = re.sub(r"\s+", " ", mt.group(1)).strip(" .,-")
            elif "tri-series" in path:
                tournament = "ODI Tri-Series in Pakistan"

    venue = venue_from_class
    if not venue:
        # Fall back to recognizable venue names in page text, but don't allow a
        # date/time fragment to leak into the venue field.
        venue_patterns = [
            r"(Rawalpindi Cricket Stadium(?:,\s*Rawalpindi)?)",
            r"(Gaddafi Stadium(?:,\s*Lahore)?)",
            r"([A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*){0,5}\s+(?:Oval|Stadium|Ground))",
            r"Venue\s*[:\-]\s*([^|,]{3,80}(?:Stadium|Ground|Oval)[^|]{0,40})",
            r"at\s+([A-Z][A-Za-z ]+(?:Stadium|Ground|Oval)(?:,\s*[A-Z][A-Za-z ]+)?)",
        ]
        for pattern in venue_patterns:
            mt = re.search(pattern, combined, re.I)
            if mt:
                candidate = re.sub(r"\s+", " ", mt.group(1)).strip(" .,-")
                if _looks_like_venue(candidate):
                    venue = candidate
                    break
    if _looks_like_date_time(venue):
        venue = ""

    # The match-date class is the source of truth when present; preserve its exact text.
    start_time = date_from_class if _looks_like_date_time(date_from_class) else ""
    if not start_time:
        for pattern in [
            r"((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+\d{1,2}\s+[A-Za-z]+,?\s+\d{1,2}:\d{2}\s*(?:AM|PM))",
            r"((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{1,2}:\d{2}\s*(?:AM|PM))",
            r"(\d{1,2}\s+[A-Za-z]+\s+20\d{2},?\s+\d{1,2}:\d{2}\s*(?:AM|PM))",
        ]:
            mt = re.search(pattern, visible, re.I)
            if mt:
                start_time = re.sub(r"\s+", " ", mt.group(1)).strip()
                break

    mt = re.search(r"\b(20\d{2})\b", f"{title} {path} {visible}")
    year = mt.group(1) if mt else ""
    if not team_a or not team_b:
        raise ValueError("Could not reliably extract both teams. CREX may have blocked the request or rendered details dynamically.")
    return {
        "team_a": team_a, "team_b": team_b, "match_number": stage, "match_format": fmt,
        "tournament": tournament, "year": year, "venue": venue, "start_time": start_time,
        "source_url": url, "source_title": title,
    }

def _research_youtube_keyword_ideas(api_key: str, match: dict[str, str]) -> list[dict]:
    """Mine public YouTube result titles for keyword ideas, not search-volume estimates."""
    a, b = match.get("team_a", ""), match.get("team_b", "")
    fixture = f"{a} vs {b}"
    queries = [f"{fixture} live score", f"{fixture} live commentary",
               f"{a} {b} {match.get('match_format') or 'cricket'}"]
    videos = []
    for query in queries:
        videos.extend(dict(v) for v in search_videos(api_key, query, 25, "relevance", "IN", None))
    unique, seen = [], set()
    for video in videos:
        key = video.get("url") or video.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(video)
    terms = extract_title_terms(unique, limit=40) if unique else []
    total = max(1, len(unique))
    rows = []
    for term, count in terms:
        term = str(term).strip()
        if len(term) < 3 or term.casefold() in {"live", "match", "cricket", "today", "video"}:
            continue
        share = int(count) / total
        label = "Less common in this sample" if share <= .30 else ("Moderately common" if share <= .60 else "Very common")
        rows.append({"Keyword idea":term, "Competitor titles using term":int(count),
                     "Sample share":f"{share:.0%}", "Observation":label})
    rows.sort(key=lambda r:(0 if r["Observation"] == "Less common in this sample" else 1,
                            -r["Competitor titles using term"], r["Keyword idea"].casefold()))
    return rows[:20]



def current_topic_and_match() -> tuple[str, str, dict[str, str], str]:
    return (st.session_state.get("topic", ""), st.session_state.get("mode", "Cricket match / live score"),
            st.session_state.get("match", {}), st.session_state.get("extra_description", ""))

if page == "Generate SEO":
    st.markdown('<div class="ps-hero"><b>Generate metadata for a specific cricket match or any video topic.</b><br><span class="ps-muted">Paste a CREX match URL to prefill fixture details. You can generate metadata without an API key; related YouTube keyword research requires a working API key.</span></div>', unsafe_allow_html=True)
    with st.form("crex_fetch_form"):
        crex_url = st.text_input("CREX match URL", value=st.session_state.get("crex_url_input", "https://crex.com/cricket-live-score/eng-vs-pak-2nd-match-odi-tri-series-in-pakistan-2026-match-updates-13NC"), placeholder="https://crex.com/cricket-live-score/...")
        fetch_crex = st.form_submit_button("Fetch match details from CREX", type="primary", use_container_width=True)
    if fetch_crex:
        try:
            with st.spinner("Fetching match details from CREX..."):
                fetched = _fetch_crex_match(crex_url)
                st.session_state.crex_match_prefill = fetched
                st.session_state.crex_url_input = crex_url.strip()

                # Sync form widgets explicitly; Streamlit otherwise keeps their old
                # values after reruns, even when a new CREX URL is fetched.
                st.session_state["team_a_input"] = fetched.get("team_a", "")
                st.session_state["team_b_input"] = fetched.get("team_b", "")
                st.session_state["match_number_input"] = fetched.get("match_number", "")
                allowed_formats = ["", "T20", "T20I", "ODI", "Test", "T10", "The Hundred", "Other"]
                detected_format = fetched.get("match_format", "")
                st.session_state["match_format_input"] = detected_format if detected_format in allowed_formats else ""
                st.session_state["tournament_input"] = fetched.get("tournament", "")
                st.session_state["year_input"] = fetched.get("year", "")
                st.session_state["topic_input"] = f"{fetched.get('team_a', '')} vs {fetched.get('team_b', '')}".strip()
                st.session_state["shorthand_input"] = ""
                st.session_state["venue_input"] = fetched.get("venue", "")
                st.session_state["start_time_input"] = fetched.get("start_time", "")
                st.session_state["cricket_search_query_input"] = f"{fetched.get('team_a', '')} vs {fetched.get('team_b', '')} cricket live".strip()
                st.session_state.generated_packages = []
                st.session_state.youtube_keyword_opportunities = []
            st.success("Match details fetched. Review extracted values before generating metadata.")
        except Exception as exc:
            st.error(f"Could not fetch CREX details automatically: {exc}")
            st.caption("If CREX blocks automated requests or loads details dynamically, enter the missing details manually.")
    crex_data = st.session_state.get("crex_match_prefill", {})
    if crex_data:
        with st.expander("Fetched match details — verify before publishing", expanded=True):
            st.write(f"**Page title:** {crex_data.get('source_title') or 'Not available'}")
            st.write(f"**Teams:** {crex_data.get('team_a')} vs {crex_data.get('team_b')}")
            st.write(f"**Match stage:** {crex_data.get('match_number') or 'Not found'}")
            st.write(f"**Format:** {crex_data.get('match_format') or 'Not found'}")
            st.write(f"**Tournament:** {crex_data.get('tournament') or 'Not found'}")
            st.write(f"**Venue:** {crex_data.get('venue') or 'Not found'}")
            st.write(f"**Date / time as listed:** {crex_data.get('start_time') or 'Not found'}")
            st.caption("Verify the venue, date and time before publishing.")
    with st.form("generation_form"):
        mode = st.radio("Video type", ["Cricket match / live score", "General YouTube video"], horizontal=True)
        coverage = st.selectbox(
            "Actual stream/video format",
            [
                "Live reaction and discussion",
                "Live score updates and Hindi commentary",
                "Pre-match analysis",
                "Post-match review",
            ],
            help="Choose only what viewers will actually receive. This changes the title and description wording.",
        )
        match: dict[str, str] = {}
        if mode == "Cricket match / live score":
            c1, c2, c3 = st.columns(3)
            with c1:
                team_a = st.text_input("Team 1", value=st.session_state.get("crex_match_prefill", {}).get("team_a", ""), placeholder="India", key="team_a_input")
            with c2:
                team_b = st.text_input("Team 2", value=st.session_state.get("crex_match_prefill", {}).get("team_b", ""), placeholder="Australia", key="team_b_input")
            with c3:
                match_number = st.text_input("Match stage / number", value=st.session_state.get("crex_match_prefill", {}).get("match_number", ""), placeholder="2nd Semi-Final or 3rd T20I", key="match_number_input")
            c4, c5, c6 = st.columns(3)
            with c4:
                match_format_options = ["", "T20", "T20I", "ODI", "Test", "T10", "The Hundred", "Other"]
                detected_format = st.session_state.get("crex_match_prefill", {}).get("match_format", "")
                match_format_index = match_format_options.index(detected_format) if detected_format in match_format_options else 0
                match_format = st.selectbox("Match format", match_format_options, index=match_format_index, key="match_format_input")
            with c5:
                tournament = st.text_input("Tournament / series", value=st.session_state.get("crex_match_prefill", {}).get("tournament", ""), placeholder="Tournament / series", key="tournament_input")
            with c6:
                year_default = st.session_state.get("crex_match_prefill", {}).get("year", "") if st.session_state.get("crex_match_prefill") else str(date.today().year)
                year = st.text_input("Season / year (optional)", value=year_default, placeholder="2026", key="year_input")
            topic_default = f"{team_a} vs {team_b}".strip() if team_a and team_b else ""
            topic = st.text_input("Main search phrase", value=topic_default, placeholder="India vs Australia live match", key="topic_input")
            shorthand = st.text_input("Team shorthand (optional)", placeholder="ENG vs PAK", key="shorthand_input")
            c7, c8 = st.columns(2)
            with c7:
                venue = st.text_input("Stadium / venue", value=st.session_state.get("crex_match_prefill", {}).get("venue", ""), placeholder="Rawalpindi Cricket Stadium", key="venue_input")
            with c8:
                start_time = st.text_input("Match date / start time (as listed)", value=st.session_state.get("crex_match_prefill", {}).get("start_time", ""), placeholder="Tuesday, 20 October, 8:00 AM", key="start_time_input")
            match = {"team_a": team_a, "team_b": team_b, "match_number": match_number,
                     "match_format": match_format, "tournament": tournament, "year": year,
                     "venue": venue, "start_time": start_time,
                     "source_url": st.session_state.get("crex_match_prefill", {}).get("source_url", ""),
                     "team_shorthand": shorthand}
            search_query = st.text_input("Competitor search query", value=f"{topic} cricket live".strip(), help="Used only when you click research or generate-with-competitors.", key="cricket_search_query_input")
        else:
            topic = st.text_input("Main topic / exact video subject", placeholder="How to improve cricket live stream audio", key="general_topic_input")
            search_query = st.text_input("Competitor search query", value=topic, help="An exact topic helps produce more relevant competitor patterns.", key="general_search_query_input")
        extra_description = st.text_area("Additional accurate details to include", placeholder="Venue, start time, players, links, sponsor disclosures, or details specific to this video.", height=100)
        use_competitors = st.checkbox("Use previously fetched competitor research", value=bool(st.session_state.competitor_results))
        research_keywords = st.checkbox(
            "Research related YouTube keyword ideas after generation (uses API quota)",
            value=True,
            help="Uses public YouTube title samples. Less common in the sample does not prove low competition or easy ranking.",
        )
        submitted = st.form_submit_button("Generate SEO package", type="primary", use_container_width=True)

    if submitted:
        if not topic.strip():
            st.error("Enter the main search phrase or both team names first.")
        elif mode == "Cricket match / live score" and (not match.get("team_a") or not match.get("team_b")):
            st.error("Add both team names so the generated titles and description are specific to the match.")
        else:
            query_norm = search_query.strip().casefold()
            competitors = st.session_state.competitor_results if use_competitors else []
            if use_competitors and st.session_state.competitor_query.casefold() not in query_norm and st.session_state.competitor_query.casefold() != query_norm:
                st.warning("The saved competitor query may differ from this video. Check the research results before relying on competitor-derived tags.")
            st.session_state.youtube_keyword_opportunities = []
            packages = generate_package(topic, mode, match, competitors, prefs, extra_description)
            packages = _apply_editorial_metadata(
                packages, topic, mode, match, prefs, extra_description, coverage
            )
            st.session_state.generated_packages = packages
            st.session_state.topic = topic
            st.session_state.mode = mode
            st.session_state.match = match
            st.session_state.extra_description = extra_description
            st.session_state.coverage = coverage
            if research_keywords and api_key.strip() and mode == "Cricket match / live score":
                with st.spinner("Searching YouTube for related keyword ideas..."):
                    try:
                        st.session_state.youtube_keyword_opportunities = _research_youtube_keyword_ideas(api_key, match)
                    except Exception as exc:
                        st.warning(f"SEO package generated, but YouTube keyword research failed: {exc}")
            elif research_keywords and not api_key.strip():
                st.info("Add your YouTube Data API key in the sidebar to fetch related YouTube keyword ideas.")
            st.success("SEO package generated with match details and a human-readable description.")

    packages = st.session_state.generated_packages
    if packages:
        st.subheader("Generated metadata")
        selected = st.selectbox("Compare title options", options=list(range(len(packages))), format_func=lambda i: f"Option {i + 1}: {packages[i]['title']}")
        package = packages[selected]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Checklist score", f"{package['seo_score']}/100")
        m2.metric("Title", f"{package['title_characters']}/100 chars")
        m3.metric("Description", f"{package['description_characters']} chars")
        m4.metric("Tags", f"{package['tag_characters']}/500 chars")
        st.caption(package["score_label"])
        st.info("Use the Tags field separately in YouTube Studio. Do not paste the comma-separated tag list into the description. Hashtags are shown separately and placed at the end of the description. Enter the verified match stage separately from the match format.")

        st.markdown("#### Title")
        st.code(package["title"], language=None)
        st.markdown("#### Description")
        st.code(package["description"], language=None)
        col_tags, col_hash = st.columns(2)
        with col_tags:
            st.markdown("#### Tags — paste into YouTube Studio Tags field")
            st.code(", ".join(package["tags"]), language=None)
        with col_hash:
            st.markdown("#### Hashtags")
            st.code(" ".join(package["hashtags"]), language=None)
        keyword_ideas = st.session_state.get("youtube_keyword_opportunities", [])
        if keyword_ideas:
            st.markdown("#### Related YouTube keyword ideas")
            st.caption("Derived from public YouTube search-result titles. ‘Less common’ means less frequent in this sample only; it is not verified search volume or a guarantee of easy ranking.")
            st.dataframe(pd.DataFrame(keyword_ideas), use_container_width=True, hide_index=True)
            keyword_text = "\n".join(f"{row['Keyword idea']} — {row['Observation']}" for row in keyword_ideas)
            st.download_button("Download keyword ideas (.txt)", keyword_text, file_name="preet_sports_keyword_ideas.txt", mime="text/plain")
        st.markdown("#### Checklist feedback")
        good_col, improve_col = st.columns(2)
        with good_col:
            st.markdown("**What is working**")
            if package["strengths"]:
                for item in package["strengths"]:
                    st.write(f"✅ {item}")
            else:
                st.write("No checklist strengths detected yet.")
        with improve_col:
            st.markdown("**Potential improvements**")
            if package["improvements"]:
                for item in package["improvements"]:
                    st.write(f"• {item}")
            else:
                st.write("No basic checklist issues detected.")

        bundle = {
            "channel": prefs.get("channel_name", "Preet Sports"),
            "topic": st.session_state.get("topic", ""),
            "generated_at_local_date": date.today().isoformat(),
            "score_note": package["score_label"],
            "title_options": [p["title"] for p in packages],
            "selected_option": package,
        }
        txt = ("PREET SPORTS — YOUTUBE SEO PACKAGE\n\n" +
               "TITLE OPTIONS\n" + "\n".join(f"{i+1}. {p['title']}" for i, p in enumerate(packages)) +
               "\n\nDESCRIPTION\n" + package["description"] +
               "\n\nTAGS\n" + ", ".join(package["tags"]) +
               "\n\nHASHTAGS\n" + " ".join(package["hashtags"]) +
               f"\n\nCHECKLIST SCORE: {package['seo_score']}/100 (not a ranking prediction)\n")
        dl1, dl2 = st.columns(2)
        dl1.download_button("Download selected package (.txt)", txt, file_name="preet_sports_seo_package.txt", mime="text/plain", use_container_width=True)
        dl2.download_button("Download all options (.json)", json.dumps({"packages": packages, "note": package["score_label"]}, ensure_ascii=False, indent=2), file_name="preet_sports_seo_options.json", mime="application/json", use_container_width=True)

elif page == "Competitor Research":
    st.markdown("Explore public results for a match or video subject. This is a snapshot of search results, not private channel analytics or a promise of ranking.")
    with st.form("research_form"):
        query = st.text_input("Search query", value=st.session_state.competitor_query or "India vs Australia cricket live")
        col1, col2, col3 = st.columns(3)
        with col1:
            count = st.slider("Results", 10, 50, 50, 5)
        with col2:
            order_label = st.selectbox("Sort", ["Most views / live concurrent viewers", "Most relevant", "Newest", "Highest rating"])
            order = {"Most views / live concurrent viewers": "viewCount", "Most relevant": "relevance", "Newest": "date", "Highest rating": "rating"}[order_label]
        with col3:
            region = st.selectbox("Region", ["IN", "US", "GB", "AU", "PK", "NZ", "ALL"], index=0)
        lookback = st.selectbox("Publication window", ["Any time", "Past 7 days", "Past 30 days", "Past 90 days"])
        run_search = st.form_submit_button("Fetch competitor videos", type="primary", use_container_width=True)
    if run_search:
        if not api_key.strip():
            st.error("Add your YouTube Data API key in the sidebar first.")
        elif not query.strip():
            st.error("Enter a competitor search query.")
        else:
            after = None
            if lookback != "Any time":
                days = {"Past 7 days": 7, "Past 30 days": 30, "Past 90 days": 90}[lookback]
                after = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00Z"
            with st.spinner("Fetching public YouTube search results and metadata…"):
                try:
                    results = search_videos(api_key, query, count, order, region, after)
                    st.session_state.competitor_results = results
                    st.session_state.competitor_query = query
                    st.success(f"Fetched {len(results)} public video result(s).")
                except YouTubeAPIError as exc:
                    st.error(str(exc))
    results = st.session_state.competitor_results
    if results:
        views = [v["views"] for v in results if isinstance(v.get("views"), int)]
        st.markdown("#### Snapshot summary")
        a, b, c, d = st.columns(4)
        a.metric("Videos returned", len(results))
        b.metric("Total public views", compact_number(sum(views)) if views else "Not public")
        c.metric("Median public views", compact_number(sorted(views)[len(views)//2]) if views else "Not public")
        d.metric("Search query", st.session_state.competitor_query)

        table_rows = []
        for v in results:
            table_rows.append({
                "Title": v.get("title", ""),
                "Channel": v.get("channel_title", ""),
                "Published": format_published_date(v.get("published_at", "")),
                "Views": v.get("views"),
                "Likes": v.get("likes"),
                "Comments": v.get("comments"),
                "Tags found": len(v.get("tags") or []),
                "URL": v.get("url", ""),
            })
        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={
            "URL": st.column_config.LinkColumn("Video link", display_text="Open video"),
            "Views": st.column_config.NumberColumn("Views", format="localized"),
            "Likes": st.column_config.NumberColumn("Likes", format="localized"),
            "Comments": st.column_config.NumberColumn("Comments", format="localized"),
        })
        terms = extract_title_terms(results, limit=20)
        if terms:
            st.markdown("#### Frequently occurring title terms")
            st.dataframe(pd.DataFrame(terms, columns=["Term", "Videos using term"]), use_container_width=True, hide_index=True)
        st.markdown("#### Common tags from public competitor metadata")
        from collections import Counter
        common = Counter(tag for video in results for tag in (video.get("tags") or []))
        if common:
            st.code(", ".join(tag for tag, _ in common.most_common(30)), language=None)
        else:
            st.info("The returned videos did not expose public tag lists, or tags were unavailable. Use title terms as a pattern, not as proof of search volume.")
        csv_data = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download competitor snapshot (.csv)", csv_data, "youtube_competitor_snapshot.csv", "text/csv")
        st.caption("Public view/like/comment counts are snapshots and can change. Like/comment counts may be hidden by a creator. They are not your channel's YouTube Analytics.")
    else:
        st.info("No research loaded yet. Search a match or topic above to see up to 50 public videos.")

elif page == "Preet Sports Defaults":
    st.subheader("Channel metadata preferences")
    st.write("These defaults are saved to a local JSON file. Do not enter your API key here; it is intentionally kept separate.")
    with st.form("preferences_form"):
        channel_name = st.text_input("Channel name", prefs.get("channel_name", DEFAULTS["channel_name"]))
        language = st.selectbox("Commentary / metadata language", ["Hindi", "English", "Punjabi", "Hinglish", "Urdu", "Bengali", "Other"], index=["Hindi", "English", "Punjabi", "Hinglish", "Urdu", "Bengali", "Other"].index(prefs.get("language", "Hindi")) if prefs.get("language", "Hindi") in ["Hindi", "English", "Punjabi", "Hinglish", "Urdu", "Bengali", "Other"] else 0)
        intro = st.text_area("Default description intro", prefs.get("description_intro", DEFAULTS["description_intro"]))
        cta = st.text_area("Default subscription / engagement CTA", prefs.get("subscribe_cta", DEFAULTS["subscribe_cta"]))
        default_tags = st.text_area("Default comma-separated tags", prefs.get("default_tags", DEFAULTS["default_tags"]))
        default_hashtags = st.text_input("Default hashtags (without # is okay)", prefs.get("default_hashtags", DEFAULTS["default_hashtags"]))
        default_region = st.selectbox("Default competitor region", ["IN", "US", "GB", "AU", "PK", "NZ", "ALL"], index=["IN", "US", "GB", "AU", "PK", "NZ", "ALL"].index(prefs.get("default_region", "IN")) if prefs.get("default_region", "IN") in ["IN", "US", "GB", "AU", "PK", "NZ", "ALL"] else 0)
        default_topic = st.text_input("Default topic shown in competitor research", prefs.get("default_topic", "Cricket"))
        save = st.form_submit_button("Save Preet Sports defaults", type="primary", use_container_width=True)
    if save:
        new_prefs = {"channel_name": channel_name, "language": language, "description_intro": intro,
                     "subscribe_cta": cta, "default_tags": default_tags, "default_hashtags": default_hashtags,
                     "default_region": default_region, "default_topic": default_topic}
        try:
            save_preferences(new_prefs)
            st.session_state.preferences = load_preferences()
            prefs = st.session_state.preferences
            st.success("Preferences saved.")
        except OSError as exc:
            st.error(f"Could not save preferences: {exc}. Check DATA_DIR write permissions.")
    st.caption("Local Windows preferences survive restarts. On Render, attach a persistent disk mounted at /var/data and set DATA_DIR=/var/data; otherwise redeploys/restarts can reset the file.")

else:
    st.subheader("About this app")
    st.markdown("""
**What it does**
- Generates three title options, a topic-aware description, relevant tags, and a small hashtag set.
- Searches up to 50 public YouTube videos and enriches results with available view, like, comment, and tag metadata.
- Stores Preet Sports preferences in a JSON file.
- Exports generated metadata as TXT/JSON and competitor snapshots as CSV.

**Important limitations**
- The score is a transparent local checklist, not an official YouTube score and not a prediction of views, CTR, or ranking.
- Public YouTube Data API search results are not the same as complete YouTube search results. API quota applies.
- Public search statistics are not private channel analytics. To read your own watch time, impressions, CTR, or revenue, a separate OAuth-based YouTube Analytics integration is required.
- Competitor title terms are observed text, not search-volume data. Use only tags that actually describe your video.
- The app does not upload or publish videos automatically.

**Current field limits used by the app**
- Video title: 100 characters.
- Combined tags: 500 characters in the comma-separated tag field.
- Description: kept below 5,000 characters.
""")
    st.markdown("Sources: [YouTube Help — edit video settings](https://support.google.com/youtube/answer/57404) · [YouTube Help — add tags](https://support.google.com/youtube/answer/146402) · [YouTube Data API search.list](https://developers.google.com/youtube/v3/docs/search/list) · [YouTube Data API videos.list](https://developers.google.com/youtube/v3/docs/videos/list)")

st.divider()
st.caption("Preet Sports SEO Generator • generated suggestions should be reviewed for match accuracy before publishing.")
