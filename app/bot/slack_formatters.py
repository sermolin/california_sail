"""Slack message formatters for California Sail bot.

Each public function accepts a JSON-safe dict (as returned by app/mcp/tools.py)
and returns a Slack mrkdwn string ready to pass to say() or respond().

Slack mrkdwn differs from Telegram MarkdownV2:
- Bold:   *text*   (no backslash escaping required)
- Italic: _text_
- Code:   `code`
- No special characters need escaping for normal text.
- Max recommended block length: ~3000 characters.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


_MAX_LEN = 3000  # Slack block text limit


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _bold(text: str) -> str:
    return f"*{text}*"


def _code(text: str) -> str:
    return f"`{text}`"


def _score_emoji(score: float | None) -> str:
    if score is None:
        return "❓"
    if score >= 75:
        return "🟢"
    if score >= 50:
        return "🟡"
    if score >= 25:
        return "🟠"
    return "🔴"


def _verdict_line(verdict: str | None, score: float | None) -> str:
    emoji = _score_emoji(score)
    score_str = f"{score:.0f}/100" if score is not None else "—"
    return f"{emoji} *{verdict or 'Unknown'}* ({score_str})"


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime("%b %d %H:%M")
    except Exception:
        return str(iso)[:16]


def _warnings_block(warnings: list[dict]) -> str:
    if not warnings:
        return ""
    severity_emoji = {
        "extreme": "🚨", "severe": "🔴", "moderate": "🟠", "minor": "🟡",
    }
    lines = ["\n⚠️ *Active warnings:*"]
    for w in warnings:
        sev = str(w.get("severity", "")).lower()
        icon = severity_emoji.get(sev, "⚠️")
        event = w.get("event", "Warning")
        headline = w.get("headline", "")
        lines.append(f"{icon} *{event}*")
        if headline:
            lines.append(f"  {headline}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public formatters
# ---------------------------------------------------------------------------

def format_regions(regions: list[dict]) -> str:
    """Format list_regions output."""
    if not regions:
        return "No regions found."
    lines = [_bold("Sailing regions:"), ""]
    for r in regions:
        rid = _code(r.get("id", ""))
        name = r.get("name", "")
        country = r.get("country", "")
        n = r.get("n_zones", 0)
        lines.append(f"• {name} ({country}) — {n} zones")
        lines.append(f"  Use: /compare {rid}")
    return "\n".join(lines)


def format_zones(zones: list[dict], region_id: str) -> str:
    """Format list_zones output."""
    if not zones:
        return "No zones found."
    lines = [_bold(f"Zones in {region_id}:"), ""]
    for z in zones:
        zid = _code(z.get("id", ""))
        name = z.get("name", "")
        exp = z.get("exposure", "")
        hazards = z.get("hazards", [])
        hazard_str = ", ".join(hazards) if hazards else "none"
        lines.append(f"• {name} ({exp})")
        lines.append(f"  Hazards: {hazard_str}")
        lines.append(f"  Forecast: /forecast {zid}")
    return "\n".join(lines)


def format_profiles(profiles: list[dict]) -> str:
    """Format list_profiles output."""
    if not profiles:
        return "No profiles found."
    lines = [_bold("Sailor profiles:"), ""]
    for p in profiles:
        pid = _code(p.get("id", ""))
        name = p.get("name", "")
        emoji = p.get("emoji", "⛵")
        wind = p.get("ideal_wind_kt", [])
        gust = p.get("max_gust_kt", "?")
        wave = p.get("max_wave_m", "?")
        wind_str = f"{wind[0]:.0f}–{wind[1]:.0f} kt" if len(wind) == 2 else "?"
        lines.append(f"{emoji} {name} — {pid}")
        lines.append(f"  Ideal wind: {wind_str}, max gust: {gust} kt, max wave: {wave} m")
    return "\n".join(lines)


def format_forecast(fc: dict) -> str:
    """Format get_zone_forecast output (summary mode)."""
    zone = fc.get("zone", {})
    region = fc.get("region", {})
    profile = fc.get("profile", {})

    zone_name = zone.get("name", "Unknown zone")
    region_name = region.get("name", "")
    profile_name = profile.get("name", "Cruiser") if profile else "Cruiser"

    score = fc.get("current_sailability")
    verdict = fc.get("verdict", "")
    has_marine = fc.get("has_marine_data", False)
    has_tide = fc.get("has_tide_data", False)

    lines = [
        f"⛵ *{zone_name}* — {region_name}",
        f"Profile: {profile_name}",
        "",
        _verdict_line(verdict, score),
    ]

    sources = []
    if has_marine:
        sources.append("waves")
    if has_tide:
        sources.append("tides")
    lines.append(f"Data: wind + {', '.join(sources)}" if sources else "Data: wind only")

    windows = fc.get("best_sail_windows", [])
    if windows:
        lines.append("")
        lines.append(_bold("Best sailing windows:"))
        for w in windows[:3]:
            start = _fmt_time(w.get("start", ""))
            end = _fmt_time(w.get("end", ""))
            wscore = w.get("score")
            emoji = _score_emoji(wscore)
            score_str = f"{wscore:.0f}" if wscore is not None else "?"
            lines.append(f"{emoji} {start} – {end} ({score_str})")

    daily = fc.get("daily", [])
    if daily:
        lines.append("")
        lines.append(_bold("Daily summary:"))
        for d in daily[:5]:
            date = str(d.get("date", ""))[-5:]
            dscore = d.get("sailability_avg")
            wind = d.get("wind_kt_avg")
            emoji = _score_emoji(dscore)
            score_str = f"{dscore:.0f}" if dscore is not None else "?"
            wind_str = f"{wind:.0f} kt" if wind is not None else "?"
            lines.append(f"{emoji} {date}: score {score_str}, wind {wind_str}")

    warnings_block = _warnings_block(fc.get("warnings", []))
    if warnings_block:
        lines.append(warnings_block)

    return "\n".join(lines)


def format_compare(ranked: list[dict], region_id: str) -> str:
    """Format compare_zones_in_region output."""
    if not ranked:
        return "No zones found."
    lines = [_bold(f"Zone rankings — {region_id}:"), ""]
    for entry in ranked:
        rank = entry.get("rank", "?")
        zid = entry.get("zone_id", "")
        name = entry.get("zone_name", zid)
        score = entry.get("sailability")
        verdict = entry.get("verdict", "")
        wind = entry.get("avg_wind_kt")
        gust = entry.get("max_gust_kt")
        has_warn = entry.get("has_warnings", False)

        emoji = _score_emoji(score)
        score_str = f"{score:.0f}" if score is not None else "?"
        wind_str = f"{wind:.0f}" if wind is not None else "?"
        gust_str = f"{gust:.0f}" if gust is not None else "?"
        warn_flag = " ⚠️" if has_warn else ""
        zid_code = _code(zid)

        lines.append(f"{rank}. {emoji} {name}{warn_flag}")
        lines.append(f"   Score: {score_str} — {verdict}")
        lines.append(f"   Wind avg {wind_str} kt, max gust {gust_str} kt")
        lines.append(f"   Details: /forecast {zid_code}")
    return "\n".join(lines)


def format_windows(windows: list[dict], zone_id: str) -> str:
    """Format best_sail_windows output."""
    if not windows:
        return f"No good windows found for {zone_id} in the forecast period."
    lines = [_bold(f"Best windows — {zone_id}:"), ""]
    for i, w in enumerate(windows, 1):
        start = _fmt_time(w.get("start", ""))
        end = _fmt_time(w.get("end", ""))
        score = w.get("score")
        verdict = w.get("verdict", "")
        emoji = _score_emoji(score)
        score_str = f"{score:.0f}" if score is not None else "?"
        lines.append(f"{i}. {emoji} {start} – {end}")
        lines.append(f"   Score {score_str} — {verdict}")
    return "\n".join(lines)


def format_warnings(warnings: list[dict], region_id: str) -> str:
    """Format get_active_warnings output."""
    if not warnings:
        return f"✅ No active marine warnings for {region_id}."
    lines = [_bold(f"Active warnings — {region_id}:"), ""]
    severity_emoji = {
        "extreme": "🚨", "severe": "🔴", "moderate": "🟠", "minor": "🟡",
    }
    for w in warnings:
        sev = str(w.get("severity", "")).lower()
        icon = severity_emoji.get(sev, "⚠️")
        event = w.get("event", "Warning")
        headline = w.get("headline", "")
        expires = w.get("expires", "")
        lines.append(f"{icon} *{event}*")
        if headline:
            lines.append(f"  {headline}")
        if expires:
            lines.append(f"  Expires: {expires}")
    return "\n".join(lines)


def format_explain(explanation: dict, zone_id: str) -> str:
    """Format explain_score output."""
    hour = _fmt_time(explanation.get("hour", ""))
    score = explanation.get("sailability")
    verdict = explanation.get("verdict", "")
    wind_score = explanation.get("wind_score")
    sea_score = explanation.get("sea_score")
    vis_score = explanation.get("visibility_score")
    gates = explanation.get("gates_passed")
    wat = explanation.get("wat_penalty", 0.0)
    why = explanation.get("why_string", "")
    thresholds = explanation.get("profile_thresholds", {})

    def _fmt(v: float | None) -> str:
        return f"{v:.1f}" if v is not None else "—"

    gates_str = "✅ passed" if gates else "❌ failed (score capped)"
    wat_str = f"-{wat:.0f}" if wat else "0"

    lines = [
        f"🔍 *{zone_id}* — score breakdown at {hour}",
        "",
        _verdict_line(verdict, score),
        "",
        _bold("Components:"),
        f"  Wind score:       {_fmt(wind_score)}/100",
        f"  Sea score:        {_fmt(sea_score)}/100",
        f"  Visibility score: {_fmt(vis_score)}/100",
        f"  WAT penalty:      {wat_str} pts",
        f"  Safety gates:     {gates_str}",
    ]

    if thresholds:
        lines.append("")
        lines.append(_bold("Profile thresholds:"))
        wind_range = thresholds.get("ideal_wind_kt", [])
        if wind_range:
            lines.append(f"  Ideal wind: {wind_range[0]:.0f}–{wind_range[1]:.0f} kt")
        if thresholds.get("max_gust_kt"):
            lines.append(f"  Max gust: {thresholds['max_gust_kt']} kt")
        if thresholds.get("max_wave_m"):
            lines.append(f"  Max wave: {thresholds['max_wave_m']} m")

    if why:
        lines.append("")
        lines.append(_bold("Summary:"))
        lines.append(why)

    return "\n".join(lines)
