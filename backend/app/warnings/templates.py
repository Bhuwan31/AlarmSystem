"""Warning message templates (FR-29). Nepali text needs native-speaker review before launch (TBD-03)."""

TEMPLATES = {
    "WATCH": {
        "en": "FLOOD WATCH – {place}: the river is rising. Prepare: charge your phone, pack essentials and know your nearest shelter.",
        "ne": "बाढी सतर्कता – {place}: नदीको सतह बढ्दैछ। तयारी गर्नुहोस्: फोन चार्ज गर्नुहोस्, आवश्यक सामान तयार राख्नुहोस् र नजिकको सुरक्षित आश्रयस्थल थाहा पाउनुहोस्।",
    },
    "WARNING": {
        "en": "FLOOD WARNING – {place}: flooding is likely. Move people with limited mobility, livestock and valuables to higher ground now and be ready to evacuate.",
        "ne": "बाढी चेतावनी – {place}: बाढी आउने सम्भावना छ। अशक्त व्यक्ति, पशुधन र बहुमूल्य सामान अहिले नै अग्लो स्थानमा सार्नुहोस् र सुरक्षित स्थानमा जान तयार रहनुहोस्।",
    },
    "CRITICAL": {
        "en": "EVACUATE NOW – {place}: flooding is happening or imminent. Go to the nearest safe shelter or high ground. Do not cross flowing water.",
        "ne": "तुरुन्त सुरक्षित स्थानमा जानुहोस् – {place}: बाढी आइसकेको वा तुरुन्तै आउँदैछ। नजिकको सुरक्षित आश्रयस्थल वा अग्लो स्थानमा जानुहोस्। बगिरहेको पानी पार नगर्नुहोस्।",
    },
}
FOOTER = {
    "en": "Issued by {issuer}. Valid until {valid_until}. Confidence: {confidence}. Follow police and local officials on site.",
    "ne": "जारीकर्ता: {issuer}। मान्य अवधि: {valid_until} सम्म। विश्वसनीयता: {confidence}। घटनास्थलमा प्रहरी र स्थानीय अधिकारीको निर्देशन पालना गर्नुहोस्।",
}
EXERCISE = {"en": "EXERCISE – NOT A REAL WARNING. ", "ne": "अभ्यास – वास्तविक चेतावनी होइन। "}
REQUIRED = ("{place}",)


def render(level: str, place: str, issuer: str, valid_until: str, confidence: str, exercise: bool) -> dict[str, str]:
    out = {}
    for lang, body in TEMPLATES[level].items():
        text = body.format(place=place) + " " + FOOTER[lang].format(issuer=issuer, valid_until=valid_until, confidence=confidence)
        out[lang] = (EXERCISE[lang] + text) if exercise else text
    return out


def lint() -> list[str]:
    """Return problems; empty list means every template has every required field (FR-65)."""
    problems = []
    for level, langs in TEMPLATES.items():
        for lang, body in langs.items():
            for ph in REQUIRED:
                if ph not in body:
                    problems.append(f"{level}/{lang} missing {ph}")
    return problems
