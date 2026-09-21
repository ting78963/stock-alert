from __future__ import annotations

C_RED="#dc2626"
C_WHITE="#ffffff"
C_TEXT="#111827"
C_MUTED="#6b7280"
C_SOFT="#f7f7f8"
C_PINK="#fee2e2"

PROFILE = {
    "A": {
        "trait": "穩定延伸",
        "target": "+10%",
        "median_days": "約 4 個交易日",
        "p75_days": "7 個交易日內",
        "d15_mean_mfe": "約 +17%",
    },
    "B": {
        "trait": "高延伸",
        "target": "+15%",
        "median_days": "約 4 個交易日",
        "p75_days": "8 個交易日內",
        "d15_mean_mfe": "約 +23%",
    },
    "C": {
        "trait": "高爆發・高回吐",
        "target": "+20%",
        "median_days": "約 5 個交易日",
        "p75_days": "10 個交易日內",
        "d15_mean_mfe": "約 +21%",
    },
}

def _metric(icon, label, value):
    return {
        "type": "box",
        "layout": "horizontal",
        "backgroundColor": C_SOFT,
        "cornerRadius": "10px",
        "paddingAll": "10px",
        "margin": "sm",
        "contents": [
            {"type": "text", "text": icon, "size": "lg", "flex": 1, "gravity": "center"},
            {"type": "box", "layout": "vertical", "flex": 6, "contents": [
                {"type": "text", "text": label, "size": "xs", "color": C_MUTED, "weight": "bold"},
                {"type": "text", "text": value, "size": "md", "color": C_TEXT, "weight": "bold", "margin": "xs", "wrap": True},
            ]},
        ],
    }

def abc_buy_flex(event, name=None):
    """Old red buy-card shell, with only production-facing A/B/C information."""
    code = str(event.get("stock_id") or event.get("symbol") or "")
    cls = str(event.get("signal_class") or event.get("abc") or "?").upper()
    profile = PROFILE.get(cls, {
        "trait": "趨勢確認",
        "target": "—",
        "median_days": "—",
        "p75_days": "—",
        "d15_mean_mfe": "—",
    })
    title = f"{name} {code}".strip() if name else code

    return {
        "type": "flex",
        "altText": f"🔥 {cls} 型買進訊號｜{title}",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "0px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": C_RED,
                        "paddingAll": "14px",
                        "contents": [
                            {"type": "text", "text": "🔥 趨勢確認｜買進訊號", "color": C_WHITE, "size": "sm", "weight": "bold", "align": "center"},
                            {"type": "text", "text": title, "color": C_WHITE, "size": "xl", "weight": "bold", "align": "center", "margin": "sm", "wrap": True},
                        ],
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "paddingAll": "12px",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "vertical",
                                "backgroundColor": C_PINK,
                                "cornerRadius": "12px",
                                "paddingAll": "9px",
                                "contents": [
                                    {"type": "text", "text": f"{cls} 型｜{profile['trait']}", "color": "#991b1b", "size": "md", "weight": "bold", "align": "center", "wrap": True}
                                ],
                            },
                            _metric("🎯", "目標漲幅", profile["target"]),
                            _metric("⏱", "常見達標", profile["median_days"]),
                            _metric("📅", "多數達標", profile["p75_days"]),
                            _metric("📈", "15日平均最大延伸", profile["d15_mean_mfe"]),
                        ],
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": C_RED,
                        "paddingAll": "10px",
                        "contents": [
                            {"type": "text", "text": "▲ 買進", "color": C_WHITE, "align": "center", "weight": "bold", "size": "sm"}
                        ],
                    },
                ],
            },
        },
    }

def format_buy_text(event, name=None):
    code = str(event.get("stock_id") or event.get("symbol") or "")
    cls = str(event.get("signal_class") or "?").upper()
    profile = PROFILE.get(cls, {})
    title = f"{name} {code}".strip() if name else code
    trait = profile.get("trait", "趨勢確認")
    return f"🔥 {cls} 型｜{trait}｜{title}"
