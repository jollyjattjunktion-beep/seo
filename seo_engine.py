"""SEO text generation and transparent checklist scoring for Preet Sports."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "at", "by",
    "with", "from", "is", "are", "was", "were", "be", "this", "that", "it", "as",
    "how", "what", "why", "when", "where", "who", "your", "you", "we", "our",
    "live", "video", "official", "full", "new", "today", "vs", "v", "match",
}

CRICKET_TERMS = [
    "cricket live", "live cricket", "live score", "ball by ball commentary",
    "Hindi commentary", "cricket commentary", "live match", "cricket today",
    "match reaction", "live discussion", "scorecard", "T20 live", "ODI live",
]


def clean_text(value: Any) -> str:
    """Normalize a UI/API value to a safe, single-line string."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique_casefold(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        value = clean_text(value).strip(" ,\t\n")
        if not value:
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def fit_title(title: str, limit: int = 100) -> str:
    title = clean_text(title).replace("<", "").replace(">", "")
    if len(title) <= limit:
        return title
    return title[: limit - 1].rstrip() + "…"


def _make_hashtags(values: Iterable[str], limit: int = 5) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        words = re.findall(r"[\w]+", clean_text(value), flags=re.UNICODE)
        candidate = "#" + "".join(words)
        if len(candidate) <= 1 or candidate.casefold() in seen:
            continue
        seen.add(candidate.casefold())
        tags.append(candidate)
        if len(tags) >= limit:
            break
    return tags


def build_tags(topic: str, mode: str, match: dict[str, str], competitors: list[dict] | None = None,
               preferences: dict[str, Any] | None = None) -> list[str]:
    preferences = preferences or {}
    competitors = competitors or []
    team_a = clean_text(match.get("team_a"))
    team_b = clean_text(match.get("team_b"))
    match_phrase = f"{team_a} vs {team_b}".strip(" vs") if team_a and team_b else clean_text(topic)

    if mode == "Cricket match / live score":
        candidates = [
            match_phrase, f"{team_a} vs {team_b} live", f"{team_a} vs {team_b} live score",
            f"{team_a} {team_b} live match", f"{team_a} vs {team_b} Hindi commentary",
            f"{team_a} vs {team_b} ball by ball", f"{team_a} vs {team_b} today",
            "cricket live", "live cricket score", "ball by ball commentary", "Hindi cricket commentary",
            "cricket live score", "live match discussion", "Preet Sports",
        ]
        candidates.extend(CRICKET_TERMS)
    else:
        candidates = [topic, f"{topic} tutorial", f"{topic} guide", f"{topic} explained",
                      f"{topic} tips", f"{topic} for beginners", f"best {topic}"]

    # Add words/phrases found in competitor metadata only when they are relevant to this query.
    topic_words = set(re.findall(r"[a-z0-9]+", topic.casefold()))
    competitor_terms: list[str] = []
    for video in competitors:
        for candidate in [video.get("title", ""), *(video.get("tags", []) or [])]:
            text = clean_text(candidate)
            tokens = set(re.findall(r"[a-z0-9]+", text.casefold()))
            if text and (tokens & topic_words or mode == "Cricket match / live score"):
                competitor_terms.append(text)
    candidates.extend(competitor_terms[:20])
    candidates.extend([x.strip() for x in clean_text(preferences.get("default_tags", "")).split(",")])

    # YouTube's overall tag field has a 500-character combined limit; commas count.
    output: list[str] = []
    budget = 500
    for tag in _unique_casefold(candidates):
        if len(tag) > 100:
            continue
        cost = len(tag) + (1 if output else 0)
        if cost <= budget:
            output.append(tag)
            budget -= cost
        if len(output) >= 30:
            break
    return output


def build_hashtags(topic: str, mode: str, match: dict[str, str], preferences: dict[str, Any] | None = None) -> list[str]:
    preferences = preferences or {}
    team_a = clean_text(match.get("team_a"))
    team_b = clean_text(match.get("team_b"))
    if mode == "Cricket match / live score":
        terms = [f"{team_a} vs {team_b}", "CricketLive", "LiveScore", "PreetSports"]
    else:
        terms = [topic, "YouTubeTips", clean_text(preferences.get("channel_name", "Preet Sports"))]
    terms.extend(clean_text(preferences.get("default_hashtags", "")).replace("#", "").split())
    hashtags = _make_hashtags(terms, 5)
    return hashtags or ["#PreetSports"]


def _title_options(topic: str, mode: str, match: dict[str, str], preferences: dict[str, Any]) -> list[str]:
    channel = clean_text(preferences.get("channel_name", "Preet Sports")) or "Preet Sports"
    language = clean_text(preferences.get("language", "Hindi")) or "Hindi"
    if mode == "Cricket match / live score":
        a = clean_text(match.get("team_a")) or "Team A"
        b = clean_text(match.get("team_b")) or "Team B"
        match_no = clean_text(match.get("match_number"))
        tournament = clean_text(match.get("tournament"))
        year = clean_text(match.get("year"))
        shorthand = clean_text(match.get("team_shorthand"))
        if not shorthand:
            def short_name(name: str) -> str:
                bits = re.findall(r"[A-Za-z0-9]+", name)
                return "".join(bit[0] for bit in bits[:3]).upper() or name[:3].upper()
            shorthand = f"{short_name(a)} vs {short_name(b)}"
        suffix_bits = [match_no, shorthand, year]
        suffix = " | ".join(x for x in suffix_bits if x)
        title1 = f"🔴 {a} vs {b} Live Match | Live Score & Ball-by-Ball {language} Commentary"
        title2 = f"{a} vs {b} Live Match Reaction & Live Discussion" + (f" | {suffix}" if suffix else "")
        title3 = f"{a} vs {b} Live Score Today | {language} Commentary" + (f" | {match_no}" if match_no else "")
        # Add tournament/channel only when there's room, keeping the search phrase first.
        if tournament and len(title2) < 78:
            title2 += f" | {tournament}"
        if channel.casefold() not in title1.casefold() and len(title1) + len(f" | {channel}") <= 100:
            title1 += f" | {channel}"
        if channel.casefold() not in title3.casefold() and len(title3) + len(f" | {channel}") <= 100:
            title3 += f" | {channel}"
        options = [title1, title2, title3]
    else:
        topic = clean_text(topic) or "YouTube video"
        options = [
            f"{topic}: Complete Guide, Key Tips & What to Know",
            f"How {topic} Works | Practical Guide for Beginners",
            f"{topic} Explained: Important Details, Tips & Examples",
        ]
    options = [fit_title(x) for x in options]
    # Avoid duplicate options after length trimming.
    return _unique_casefold(options)[:3]


def _build_description(topic: str, mode: str, match: dict[str, str], hashtags: list[str],
                       preferences: dict[str, Any], extra: str = "") -> str:
    channel = clean_text(preferences.get("channel_name", "Preet Sports")) or "Preet Sports"
    cta = clean_text(preferences.get("subscribe_cta", "Subscribe to Preet Sports for more cricket live updates and match discussions."))
    custom_intro = clean_text(preferences.get("description_intro", "Welcome to Preet Sports!"))
    extra = clean_text(extra)
    if mode == "Cricket match / live score":
        a = clean_text(match.get("team_a")) or "Team A"
        b = clean_text(match.get("team_b")) or "Team B"
        match_no = clean_text(match.get("match_number")) or "Not specified"
        tournament = clean_text(match.get("tournament")) or "Not specified"
        year = clean_text(match.get("year")) or ""
        language = clean_text(preferences.get("language", "Hindi")) or "Hindi"
        lead = f"🔴 {a} vs {b} Live Match | {a} vs {b} Live Score & {language} Commentary | {channel}"
        sections = [
            lead,
            f"{custom_intro} Join this live match discussion for {a} vs {b}. Follow score updates, ball-by-ball commentary, key moments, and fan discussion in one place.",
            f"🏏 MATCH DETAILS\nTeams: {a} vs {b}\nMatch: {match_no}\nTournament/Series: {tournament}" + (f"\nSeason/Year: {year}" if year else ""),
            f"📣 WHAT YOU'LL FIND\n• Live score discussion and match updates\n• Ball-by-ball cricket commentary in {language}, where available\n• Wickets, boundaries, partnerships, and turning points\n• Respectful discussion with fellow cricket fans",
            cta,
            "💬 Join the discussion: Which team do you think will win? Share your match thoughts in the chat.",
        ]
    else:
        lead = f"{topic} | Tips, Explanation & Guide | {channel}"
        sections = [lead, f"{custom_intro} This video covers {topic} with practical context and clearly organized information.",
                    f"In this video, we look at the main ideas behind {topic}, useful details to keep in mind, and answers to common questions. The goal is to make the subject easier to understand and act on.",
                    cta, f"💬 Tell us what you'd like to see next about {topic}."]
    if extra:
        sections.append(f"📌 ADDITIONAL DETAILS\n{extra}")
    if hashtags:
        sections.append(" ".join(hashtags[:5]))
    description = "\n\n".join(sections).strip()
    # API text fields reject angle brackets; keep within YouTube's 5,000-character help-center limit.
    return description.replace("<", "").replace(">", "")[:4900].strip()


def score_metadata(title: str, description: str, tags: list[str], hashtags: list[str], topic: str) -> tuple[int, list[str], list[str]]:
    """Return a heuristic checklist score, with explicit improvement notes."""
    score = 0
    wins: list[str] = []
    issues: list[str] = []
    topic_norm = clean_text(topic).casefold()
    title_len = len(title)
    desc_len = len(description)
    tag_chars = len(",".join(tags))
    title_has_topic = bool(topic_norm and topic_norm in title.casefold())
    desc_has_topic = bool(topic_norm and topic_norm in description[:250].casefold())

    if title_len <= 100:
        score += 10
        wins.append(f"Title is within the 100-character limit ({title_len}/100).")
    else:
        issues.append("Shorten the title to 100 characters or fewer.")
    if 35 <= title_len <= 75:
        score += 10
        wins.append("Title length is reasonably compact for many surfaces.")
    else:
        issues.append("Consider making the title more concise and keeping the main phrase early.")
    if title_has_topic:
        score += 20
        wins.append("Main query/phrase appears in the title.")
    else:
        issues.append("Include the main search phrase naturally in the title.")
    if desc_len >= 250:
        score += 10
        wins.append(f"Description provides context ({desc_len} characters).")
    else:
        issues.append("Add useful, specific context to the description.")
    if desc_has_topic:
        score += 15
        wins.append("Main query/phrase appears near the start of the description.")
    else:
        issues.append("Move the main search phrase into the first lines of the description.")
    if 3 <= len(hashtags) <= 5:
        score += 10
        wins.append(f"Hashtag count is focused ({len(hashtags)}).")
    elif len(hashtags) > 5:
        score += 5
        issues.append("Use a smaller set of highly relevant hashtags.")
    else:
        issues.append("Add 3–5 relevant hashtags if they fit the video.")
    if tags and tag_chars <= 500:
        score += 10
        wins.append(f"Tags fit the 500-character combined budget ({tag_chars}/500).")
    else:
        issues.append("Add relevant tags and keep the combined comma-separated text under 500 characters.")
    if len(tags) >= 5:
        score += 5
        wins.append("Several topic-related tags are included.")
    else:
        issues.append("Consider a few more precise related tags, without stuffing unrelated terms.")
    if re.search(r"subscribe|comment|share|join|tell us|discussion", description, flags=re.I):
        score += 5
        wins.append("Description includes a viewer action or engagement prompt.")
    else:
        issues.append("Add a natural call to action when appropriate.")
    return min(100, score), wins, issues


def generate_package(topic: str, mode: str, match: dict[str, str], competitors: list[dict] | None = None,
                     preferences: dict[str, Any] | None = None, extra_description: str = "") -> list[dict[str, Any]]:
    preferences = preferences or {}
    competitors = competitors or []
    topic = clean_text(topic)
    titles = _title_options(topic, mode, match, preferences)
    tags = build_tags(topic, mode, match, competitors, preferences)
    hashtags = build_hashtags(topic, mode, match, preferences)
    description = _build_description(topic, mode, match, hashtags, preferences, extra_description)

    outputs: list[dict[str, Any]] = []
    for index, title in enumerate(titles, start=1):
        # Title-specific score; all other fields are shared so they're easy to compare.
        score, wins, issues = score_metadata(title, description, tags, hashtags, topic)
        outputs.append({
            "option": index,
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "seo_score": score,
            "score_label": "Heuristic checklist score — not a YouTube ranking prediction",
            "strengths": wins,
            "improvements": issues,
            "tag_characters": len(",".join(tags)),
            "title_characters": len(title),
            "description_characters": len(description),
        })
    return outputs


def extract_title_terms(videos: list[dict], limit: int = 20) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for video in videos:
        title = clean_text(video.get("title", ""))
        tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", title.casefold()) if len(t) > 2 and t not in STOP_WORDS]
        counts.update(tokens)
    return counts.most_common(limit)
