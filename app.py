from __future__ import annotations

import io
import json
import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from preferences import DEFAULTS, load_preferences, save_preferences
from seo_engine import extract_title_terms, generate_package
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


def current_topic_and_match() -> tuple[str, str, dict[str, str], str]:
    return (st.session_state.get("topic", ""), st.session_state.get("mode", "Cricket match / live score"),
            st.session_state.get("match", {}), st.session_state.get("extra_description", ""))

if page == "Generate SEO":
    st.markdown('<div class="ps-hero"><b>Generate metadata for a specific cricket match or any video topic.</b><br><span class="ps-muted">You can generate metadata without an API key. Competitor-derived suggestions require a working YouTube Data API key.</span></div>', unsafe_allow_html=True)
    with st.form("generation_form"):
        mode = st.radio("Video type", ["Cricket match / live score", "General YouTube video"], horizontal=True)
        match: dict[str, str] = {}
        if mode == "Cricket match / live score":
            c1, c2, c3 = st.columns(3)
            with c1:
                team_a = st.text_input("Team 1", placeholder="India")
            with c2:
                team_b = st.text_input("Team 2", placeholder="Australia")
            with c3:
                match_number = st.text_input("Match number / stage", placeholder="3rd T20I")
            c4, c5, c6 = st.columns(3)
            with c4:
                tournament = st.text_input("Tournament / series", placeholder="India tour of Australia")
            with c5:
                year = st.text_input("Year", value=str(date.today().year))
            with c6:
                shorthand = st.text_input("Team shorthand (optional)", placeholder="IND vs AUS")
            topic_default = f"{team_a} vs {team_b}".strip() if team_a and team_b else ""
            topic = st.text_input("Main search phrase", value=topic_default, placeholder="India vs Australia live match")
            match = {"team_a": team_a, "team_b": team_b, "match_number": match_number,
                     "tournament": tournament, "year": year, "team_shorthand": shorthand}
            search_query = st.text_input("Competitor search query", value=f"{topic} cricket live".strip(), help="Used only when you click research or generate-with-competitors.")
        else:
            topic = st.text_input("Main topic / exact video subject", placeholder="How to improve cricket live stream audio")
            search_query = st.text_input("Competitor search query", value=topic, help="An exact topic helps produce more relevant competitor patterns.")
        extra_description = st.text_area("Additional accurate details to include", placeholder="Venue, start time, players, links, sponsor disclosures, or details specific to this video.", height=100)
        use_competitors = st.checkbox("Use previously fetched competitor research", value=bool(st.session_state.competitor_results))
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
            packages = generate_package(topic, mode, match, competitors, prefs, extra_description)
            st.session_state.generated_packages = packages
            st.session_state.topic = topic
            st.session_state.mode = mode
            st.session_state.match = match
            st.session_state.extra_description = extra_description
            st.success("SEO package generated.")

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

        st.markdown("#### Title")
        st.code(package["title"], language=None)
        st.markdown("#### Description")
        st.code(package["description"], language=None)
        col_tags, col_hash = st.columns(2)
        with col_tags:
            st.markdown("#### Tags — comma separated")
            st.code(", ".join(package["tags"]), language=None)
        with col_hash:
            st.markdown("#### Hashtags")
            st.code(" ".join(package["hashtags"]), language=None)
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
