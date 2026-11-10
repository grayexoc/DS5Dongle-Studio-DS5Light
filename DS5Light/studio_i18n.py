"""Translate fixed UI text, preserving Korean text and user data."""
import localization
def text(value):
    return localization.tr(value) if localization.LANGUAGE=="en" else value
