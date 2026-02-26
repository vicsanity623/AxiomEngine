def load_nlp_model():
    """
    Safely load the spaCy `en_core_web_sm` model in both:
    - Regular Python environments
    - PyInstaller one-file frozen binaries

    Strategy (no network, no dynamic downloads):
    1. Prefer the installed `en_core_web_sm` package's own `load()` function.
    2. Fall back to `spacy.load("en_core_web_sm")` if that fails.
    """
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
