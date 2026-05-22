"""Telegram message formatters for California Sail bot.

Each public function accepts a JSON-safe dict (as returned by app/mcp/tools.py)
and returns a Telegram-flavoured MarkdownV2 string ready to send.

Telegram MarkdownV2 requires escaping these chars outside of formatting marks:
  _ * [ ] ( ) ~ ` > # + - = | { } . !
We escape everything and then deliberately add formatting marks.
"""
from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Escaping helpers
# ---------------------------------------------------------------------------

_ESCAPE_CHARS = r"\_*[]()~`>#+-=|{}.!"
_ESCAPE_RE = re.compile(r"([" + re.escape(_ESCAPE_CHARS) + r"])")


def _esc(text: str) -> str:
    """Escape a plain string for MarkdownV2."""
    return _ESCAPE_RE.sub(r"\\\1", str(text))


def _bold(text: str) -> str:
    return f"*{_esc(text)}*"


def _code(text: str) -> str:
    return f"`{_esc(text)}`"


# ---------------------------------------------------------------------------
# Sailability score → emoji + label
# ---------------------------------------------------------------------------

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
    v = _esc(verdict or "Unknown")
    s = _esc(score_str)
    return f"{emoji} {v} \\({s}\\)"


# ---------------------------------------------------------------------------
# Warnings block
# ---------------------------------------------------------------------------

def _warnings_block(warnings: list[dict]) -> str:
    if not warnings:
        return ""
    lines = ["\n⚠️ *Active warnings:*"]
    severity_emoji = {
        "extreme": "🚨",
        "severe": "🔴",
        "moderate": "🟠",
        "minor": "🟡",
    }
    for w in warnings:
        sev = str(w.get("severity", "")).lower()
        icon = severity_emoji.get(sev, "⚠️")
        event = _esc(w.get("event", "Warning"))
        headline = _esc(w.get("headline", ""))
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
        return _esc("No regions found.")
    lines = [_bold("Sailing regions:"), ""]
    for r in regions:
        rid = _code(r.get("id", ""))
        name = _esc(r.get("name", ""))
        country = _esc(r.get("country", ""))
        n = _esc(str(r.get("n_zones", 0)))
        lines.append(f"• {name} \\({country}\\) — {n} zones")
        lines.append(f"  Use: /compare {rid}")
    return "\n".join(lines)


def format_zones(zones: list[dict], region_id: str) -> str:
    """Format list_zones output."""
    if not zones:
        return _esc("No zones found.")
    lines = [_bold(f"Zones in {region_id}:"), ""]
    for z in zones:
        zid = _code(z.get("id", ""))
        name = _esc(z.get("name", ""))
        exp = _esc(z.get("exposure", ""))
        hazards = z.get("hazards", [])
        hazard_str = _esc(", ".join(hazards)) if hazards else _esc("none")
        lines.append(f"• {name} \\({exp}\\)")
        lines.append(f"  Hazards: {hazard_str}")
        lines.append(f"  Forecast: /forecast {zid}")
    return "\n".join(lines)


def format_profiles(profiles: list[dict]) -> str:
    """Format list_profiles output."""
    if not profiles:
        return _esc("No profiles found.")
    lines = [_bold("Sailor profiles:"), ""]
    for p in profiles:
        pid = _code(p.get("id", ""))
        name = _esc(p.get("name", ""))
        emoji = p.get("emoji", "⛵")
        wind = p.get("ideal_wind_kt", [])
        gust = p.get("max_gust_kt", "?")
        wave = p.get("max_wave_m", "?")
        wind_str = _esc(f"{wind[0]:.0f}–{wind[1]:.0f} kt") if len(wind) == 2 else _esc("?")
        lines.append(f"{emoji} {name} — {pid}")
        lines.append(f"  Ideal wind: {wind_str}, max gust: {_esc(str(gust))} kt, max wave: {_esc(str(wave))} m")
    return "\n".join(lines)


def format_forecast(fc: dict) -> str:
    """Format get_zone_forecast output (summary mode)."""
    zone = fc.get("zone", {})
    region = fc.get("region", {})
    profile = fc.get("profile", {})

    zone_name = _esc(zone.get("name", "Unknown zone"))
    region_name = _esc(region.get("name", ""))
    profile_name = _esc(profile.get("name", "Cruiser") if profile else "Cruiser")

    score = fc.get("current_sailability")
    verdict = fc.get("verdict", "")
    has_marine = fc.get("has_marine_data", False)
    has_tide = fc.get("has_tide_data", False)

    lines = [
        f"⛵ {_bold(zone_name)} — {region_name}",
        f"Profile: {profile_name}",
        "",
        _verdict_line(verdict, score),
    ]

    # Data sources
    sources = []
    if has_marine:
        sources.append("waves")
    if has_tide:
        sources.append("tides")
    if sources:
        lines.append(f"Data: wind \\+ {_esc(', '.join(sources))}")
    else:
        lines.append("Data: wind only")

    # Best windows
    windows = fc.get("best_sail_windows", [])
    if windows:
        lines.append("")
        lines.append(_bold("Best sailing windows:"))
        for w in windows[:3]:
            start = _fmt_time(w.get("start", ""))
            end = _fmt_time(w.get("end", ""))
            wscore = w.get("score")
            emoji = _score_emoji(wscore)
            score_str = _esc(f"{wscore:.0f}" if wscore is not None else "?")
            lines.append(f"{emoji} {start} – {end} \\({score_str}\\)")

    # Daily summary
    daily = fc.get("daily", [])
    if daily:
        lines.append("")
        lines.append(_bold("Daily summary:"))
        for d in daily[:5]:
            date = _esc(d.get("date", "")[-5:])  # MM-DD
            dscore = d.get("sailability_avg")
            wind = d.get("wind_kt_avg")
            emoji = _score_emoji(dscore)
            score_str = _esc(f"{dscore:.0f}" if dscore is not None else "?")
            wind_str = _esc(f"{wind:.0f} kt" if wind is not None else "?")
            lines.append(f"{emoji} {date}: score {score_str}, wind {wind_str}")

    # Warnings
    warnings_block = _warnings_block(fc.get("warnings", []))
    if warnings_block:
        lines.append(warnings_block)

    return "\n".join(lines)


def format_compare(ranked: list[dict], region_id: str) -> str:
    """Format compare_zones_in_region output."""
    if not ranked:
        return _esc("No zones found.")
    region_esc = _esc(region_id)
    lines = [_bold(f"Zone rankings — {region_id}:"), ""]
    for entry in ranked:
        rank = entry.get("rank", "?")
        zid = entry.get("zone_id", "")
        name = _esc(entry.get("zone_name", zid))
        score = entry.get("sailability")
        verdict = entry.get("verdict", "")
        wind = entry.get("avg_wind_kt")
        gust = entry.get("max_gust_kt")
        has_warn = entry.get("has_warnings", False)

        emoji = _score_emoji(score)
        score_str = _esc(f"{score:.0f}" if score is not None else "?")
        wind_str = _esc(f"{wind:.0f}" if wind is not None else "?")
        gust_str = _esc(f"{gust:.0f}" if gust is not None else "?")
        warn_flag = " ⚠️" if has_warn else ""
        zid_code = _code(zid)

        lines.append(f"{rank}\\. {emoji} {name}{warn_flag}")
        lines.append(f"   Score: {score_str} — {_esc(verdict)}")
        lines.append(f"   Wind avg {wind_str} kt, max gust {gust_str} kt")
        lines.append(f"   Details: /forecast {zid_code}")
    return "\n".join(lines)


def format_windows(windows: list[dict], zone_id: str) -> str:
    """Format best_sail_windows output."""
    if not windows:
        return _esc(f"No good windows found for {zone_id} in the forecast period.")
    lines = [_bold(f"Best windows — {zone_id}:"), ""]
    for i, w in enumerate(windows, 1):
        start = _fmt_time(w.get("start", ""))
        end = _fmt_time(w.get("end", ""))
        score = w.get("score")
        verdict = w.get("verdict", "")
        emoji = _score_emoji(score)
        score_str = _esc(f"{score:.0f}" if score is not None else "?")
        lines.append(f"{i}\\. {emoji} {start} – {end}")
        lines.append(f"   Score {score_str} — {_esc(verdict)}")
    return "\n".join(lines)


def format_warnings(warnings: list[dict], region_id: str) -> str:
    """Format get_active_warnings output."""
    region_esc = _esc(region_id)
    if not warnings:
        return f"✅ No active marine warnings for {region_esc}\\."
    lines = [_bold(f"Active warnings — {region_id}:"), ""]
    severity_emoji = {
        "extreme": "🚨", "severe": "🔴", "moderate": "🟠", "minor": "🟡",
    }
    for w in warnings:
        sev = str(w.get("severity", "")).lower()
        icon = severity_emoji.get(sev, "⚠️")
        event = _esc(w.get("event", "Warning"))
        headline = _esc(w.get("headline", ""))
        expires = _esc(w.get("expires", ""))
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
        return _esc(f"{v:.1f}" if v is not None else "—")

    gates_str = "✅ passed" if gates else "❌ failed \\(score capped\\)"
    wat_str = _esc(f"-{wat:.0f}" if wat else "0")

    lines = [
        f"🔍 {_bold(zone_id)} — score breakdown at {hour}",
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
            lines.append(f"  Ideal wind: {_esc(f'{wind_range[0]:.0f}–{wind_range[1]:.0f} kt')}")
        if thresholds.get("max_gust_kt"):
            lines.append(f"  Max gust: {_esc(str(thresholds['max_gust_kt']))} kt")
        if thresholds.get("max_wave_m"):
            lines.append(f"  Max wave: {_esc(str(thresholds['max_wave_m']))} m")

    if why:
        lines.append("")
        lines.append(_bold("Summary:"))
        lines.append(_esc(why))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Time formatting helper
# ---------------------------------------------------------------------------

def _fmt_time(iso: str | None) -> str:
    """Extract a human-readable date-time from an ISO-8601 string."""
    if not iso:
        return _esc("?")
    # "2026-05-15T14:00:00" → "May 15 14:00"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return _esc(dt.strftime("%b %d %H:%M"))
    except Exception:
        return _esc(str(iso)[:16])
