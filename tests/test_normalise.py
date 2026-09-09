"""§7.1-7.2 — normalise() and matches(). No provider/key required."""
from app.normalise import matches, normalise


def test_abbreviation_expansion():
    # What matters is that an abbreviation and its expansion normalise to the
    # SAME string (so they match), not that the string is prettily stemmed.
    assert normalise("HTN") == normalise("hypertension")
    assert normalise("SOB") == normalise("shortness of breath")
    assert normalise("T2DM") == normalise("type 2 diabetes mellitus")


def test_stopwords_and_plurals_dropped():
    assert normalise("shortness of breath") == "shortness breath"
    assert normalise("symptoms") == "symptom"


def test_exact_and_fuzzy_match():
    assert matches("hypertension", "HTN") is True
    assert matches("chest pain", "chest pain") is True


def test_clear_nonmatch():
    assert matches("chest pain", "headache") is False
