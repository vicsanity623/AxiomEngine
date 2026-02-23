import os
import sys

import spacy


def load_nlp_model():
    """Safely loads the en_core_web_sm model,
    handling both standard Python and PyInstaller environments.
    """
    model_name = "en_core_web_sm"

    try:
        if getattr(sys, "frozen", False):
            bundle_dir = sys._MEIPASS
            model_path = os.path.join(bundle_dir, model_name)
            return spacy.load(model_path)
        return spacy.load(model_name)
    except Exception as e:
        print(f"CRITICAL ERROR: Could not load NLP model '{model_name}': {e}")
        return None
