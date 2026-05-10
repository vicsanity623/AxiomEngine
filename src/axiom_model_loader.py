"""Load the NLP model for both env and PyInstaller."""

from spacy.language import Language

def load_nlp_model() -> Language:
    try:
        import en_core_web_sm
        return en_core_web_sm.load()
    except ImportError:
        pass
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except Exception as e:
        raise RuntimeError(
            "Could not load spaCy model 'en_core_web_sm'. "
            "Run: python -m spacy download en_core_web_sm"
        ) from e
