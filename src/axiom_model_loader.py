"""Load the NLP model for both env and PyInstaller."""


def load_nlp_model():
    """Safely load the spaCy `en_core_web_sm` model"""
    model_name = "en_core_web_sm"

    try:
        # First, rely on the model package itself. This works well with
        # PyInstaller when the package is included via hidden-import.
        import en_core_web_sm  # type: ignore

        return en_core_web_sm.load()
    except Exception as e1:
        try:
            import spacy  # type: ignore

            return spacy.load(model_name)
        except Exception as e2:
            print(
                f"CRITICAL ERROR: Could not load NLP model '{model_name}': {e1} / {e2}",
            )
            return None
