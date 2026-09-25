from __future__ import annotations

C_RED = "#B4232C"
C_RED_DARK = "#981B25"
C_WHITE = "#FFFFFF"
C_TEXT = "#1F2328"
C_MUTED = "#8A8F98"
C_BORDER = "#ECEDEF"
C_GOLD = "#D9A400"

PROFILE = {
    "P1": {
        "trait": "當沖首選",
        "desc": "當沖優勢明顯，未達標仍具後續延伸性。",
        "target": "+10%",
        "median_days": "約3日",
        "p75_days": "7日內",
        "d15_mean_mfe": "約+17%",
        "daytrade": "⚡ 當沖 +1% 勝率 66.8%",
    },
    "A": {
        "trait": "穩定延伸",
        "desc": "走勢相對穩定，具延伸性，適合中短期持有。",
        "target": "+10%",
        "median_days": "約4日",
        "p75_days": "7日內",
        "d15_mean_mfe": "約+17%",
    },
    "B": {
        "trait": "高延伸",
        "desc": "具較強延伸動能，趨勢持續性佳。",
        "target": "+15%",
        "median_days": "約4日",
        "p75_days": "8日內",
        "d15_mean_mfe": "約+23%",
    },
    "C": {
        "trait": "高爆發・高回吐",
        "desc": "前段爆發力強，但獲利回吐也相對較大，適合積極操作。",
        "target": "+20%",
        "median_days": "約5日",
        "p75_days": "10日內",
        "d15_mean_mfe": "約+21%",
    },
}

def _metric(label, value):
    return {
        "type": "box", "layout": "vertical", "flex": 1,
        "alignItems": "center",
        "contents": [
            {"type": "text", "text": label, "size": "xxs", "color": C_MUTED,
             "align": "center", "wrap": True},
            {"type": "text", "text": value, "size": "sm", "color": C_RED,
             "weight": "bold", "align": "center", "margin": "sm"},
        ],
    }

def abc_buy_flex(event, name=None):
    """Locked production-facing BUY card for P1/A/B/C. Notification layer only."""
    code = str(event.get("stock_id") or event.get("symbol") or "")
    cls = str(event.get("signal_class") or event.get("abc") or "?").upper()
    p = PROFILE.get(cls)
    if p is None:
        raise ValueError(f"unsupported signal class: {cls}")

    stock_name = str(name or event.get("stock_name") or "").strip()
    display_name = stock_name or code
    recognition = str(event.get("recognition_time") or event.get("live_known_time") or "")[:5]

    contents = [
        {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
            {"type": "text", "text": "↗", "size": "lg", "color": C_RED, "weight": "bold", "flex": 0},
            {"type": "text", "text": "BUY SIGNAL", "size": "xs", "color": C_RED,
             "weight": "bold", "margin": "sm", "flex": 0},
            {"type": "text", "text": "│", "size": "xs", "color": C_BORDER, "margin": "md", "flex": 0},
            {"type": "text", "text": "趨勢確認", "size": "xs", "color": C_MUTED, "margin": "md", "flex": 0},
        ]},
        {"type": "text", "text": display_name, "size": "xxl", "weight": "bold",
         "color": C_TEXT, "margin": "xl", "wrap": True},
        {"type": "text", "text": code, "size": "sm", "color": C_MUTED, "margin": "xs"},
        {"type": "box", "layout": "horizontal", "alignItems": "center", "margin": "lg", "contents": [
            {"type": "text", "text": cls, "size": "xl", "weight": "bold", "color": C_RED, "flex": 0},
            {"type": "box", "layout": "vertical", "width": "1px", "height": "24px",
             "backgroundColor": C_RED, "margin": "md", "contents": []},
            {"type": "text", "text": p["trait"], "size": "md", "weight": "bold",
             "color": C_RED, "margin": "md", "flex": 0, "wrap": True},
        ]},
    ]

    if cls == "P1":
        contents.append({"type": "text", "text": p["daytrade"], "size": "sm",
                         "weight": "bold", "color": C_GOLD, "margin": "md"})

    contents += [
        {"type": "text", "text": p["desc"], "size": "sm", "color": "#676C75",
         "wrap": True, "margin": "md"},
        {"type": "separator", "color": C_BORDER, "margin": "xl"},
        {"type": "box", "layout": "horizontal", "margin": "lg", "spacing": "sm", "contents": [
            _metric("目標漲幅", p["target"]),
            _metric("常見達標", p["median_days"]),
            _metric("多數達標", p["p75_days"]),
            _metric("15日最高達", p["d15_mean_mfe"]),
        ]},
        {"type": "box", "layout": "vertical", "backgroundColor": C_RED_DARK,
         "cornerRadius": "lg", "paddingAll": "md", "margin": "xl", "contents": [
            {"type": "text", "text": "▲   立即買進", "size": "md", "weight": "bold",
             "color": C_WHITE, "align": "center"}
        ]},
        {"type": "text", "text": f"◷  趨勢已成立  {recognition}", "size": "sm",
         "color": C_MUTED, "align": "center", "margin": "md"},
        {"type": "separator", "color": C_BORDER, "margin": "xl"},
        {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
            {"type": "text", "text": "歷史統計・僅供參考", "size": "xxs", "color": C_MUTED, "flex": 1},
            {"type": "text", "text": "Trade Smart | Your Edge", "size": "xxs",
             "color": C_MUTED, "align": "end", "flex": 1},
        ]},
    ]

    return {
        "type": "flex",
        "altText": f"BUY SIGNAL｜{display_name} {code}｜{cls} {p['trait']}｜立即買進"[:400],
        "contents": {
            "type": "bubble", "size": "mega",
            "body": {"type": "box", "layout": "vertical", "paddingAll": "xl", "contents": contents},
        },
    }

def format_buy_text(event, name=None):
    code = str(event.get("stock_id") or event.get("symbol") or "")
    cls = str(event.get("signal_class") or "?").upper()
    p = PROFILE.get(cls, {"trait": "趨勢確認"})
    stock_name = str(name or event.get("stock_name") or "").strip()
    title = f"{stock_name} {code}".strip() if stock_name else code
    return f"{cls}｜{p['trait']}｜{title}"


def indicator_help_flex():
    """Fixed LINE Flex card for the 指標說明 command."""
    def row(label, value, desc):
        return {
            "type": "box", "layout": "vertical", "margin": "md",
            "contents": [
                {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
                    {"type": "text", "text": label, "size": "sm", "weight": "bold",
                     "color": C_TEXT, "flex": 1},
                    {"type": "text", "text": value, "size": "sm", "weight": "bold",
                     "color": C_RED, "align": "end", "flex": 1},
                ]},
                {"type": "text", "text": desc, "size": "xxs", "color": C_MUTED,
                 "wrap": True, "margin": "xs"},
            ],
        }

    intraday = [
        ("+0.5%", "80.9%"), ("+1.0%", "66.0%"), ("+1.5%", "52.6%"),
        ("+2.0%", "42.2%"), ("+2.5%", "33.4%"), ("+3.0%", "25.9%"),
    ]
    intraday_rows = [
        {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
            {"type": "text", "text": gain, "size": "sm", "weight": "bold",
             "color": C_TEXT, "flex": 1},
            {"type": "text", "text": rate, "size": "sm", "weight": "bold",
             "color": "#2563B8", "align": "end", "flex": 1},
        ]}
        for gain, rate in intraday
    ]

    contents = [
        {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
            {"type": "text", "text": "▥", "size": "lg", "color": C_RED,
             "weight": "bold", "flex": 0},
            {"type": "text", "text": "指標說明", "size": "xl", "weight": "bold",
             "color": C_TEXT, "margin": "sm", "flex": 0},
            {"type": "text", "text": "以 P1 為例", "size": "xxs", "color": C_MUTED,
             "align": "end", "flex": 1},
        ]},
        row("目標漲幅", "+10%", "訊號出現後，主要期待漲多少。"),
        row("常見達標", "約3日", "通常大約幾天會漲到目標。"),
        row("多數達標", "7日內", "大多數達標股票會在幾天內完成。"),
        row("15日最高達", "約+17%", "往後15個交易日通常最高漲到多少。"),
        {"type": "separator", "color": C_BORDER, "margin": "lg"},
        {"type": "text", "text": "⚡ P1 當沖表現", "size": "md", "weight": "bold",
         "color": C_TEXT, "margin": "lg"},
        {"type": "text", "text": "當天漲到不同幅度的機率", "size": "xxs",
         "color": C_MUTED, "margin": "xs"},
        {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
            {"type": "text", "text": "當日漲幅", "size": "xxs", "color": C_MUTED, "flex": 1},
            {"type": "text", "text": "達標機率", "size": "xxs", "color": C_MUTED,
             "align": "end", "flex": 1},
        ]},
        *intraday_rows,
        {"type": "separator", "color": C_BORDER, "margin": "lg"},
        {"type": "text", "text": "歷史數據基礎", "size": "md", "weight": "bold",
         "color": C_TEXT, "margin": "lg"},
        {"type": "text", "text": "從大量歷史資料辨識訊號，再統計後續表現。",
         "size": "xxs", "color": C_MUTED, "wrap": True, "margin": "xs"},
        {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
            {"type": "text", "text": "P1", "size": "sm", "weight": "bold",
             "color": C_TEXT, "flex": 0},
            {"type": "text", "text": "676萬+筆  →  4,293組", "size": "xs",
             "color": C_TEXT, "align": "end", "flex": 1},
        ]},
        {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
            {"type": "text", "text": "ABC", "size": "sm", "weight": "bold",
             "color": C_TEXT, "flex": 0},
            {"type": "text", "text": "664萬+筆  →  741組", "size": "xs",
             "color": C_TEXT, "align": "end", "flex": 1, "wrap": True},
        ]},
        {"type": "text", "text": "A   +10%      387 / 646      59.9%", "size": "xs",
         "color": C_TEXT, "margin": "md"},
        {"type": "text", "text": "B   +15%        90 / 162      55.6%", "size": "xs",
         "color": C_TEXT, "margin": "sm"},
        {"type": "text", "text": "C   +20%        55 / 128      43.0%", "size": "xs",
         "color": C_TEXT, "margin": "sm"},
        {"type": "separator", "color": C_BORDER, "margin": "lg"},
        {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
            {"type": "text", "text": "歷史統計・僅供參考", "size": "xxs",
             "color": C_MUTED, "flex": 1},
            {"type": "text", "text": "Trade Smart | Your Edge", "size": "xxs",
             "color": C_MUTED, "align": "end", "flex": 1},
        ]},
    ]
    return {
        "type": "flex",
        "altText": "指標說明｜P1・A・B・C 歷史統計",
        "contents": {
            "type": "bubble", "size": "mega",
            "body": {"type": "box", "layout": "vertical",
                     "paddingAll": "xl", "contents": contents},
        },
    }
