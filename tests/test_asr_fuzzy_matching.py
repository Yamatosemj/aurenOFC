from core.utils import similaridade_nome


def test_gochrome_matches_google_chrome():
    assert similaridade_nome("Gochrome", "Google Chrome") >= 0.78


def test_close_spelling_matches():
    assert similaridade_nome("notepade", "Notepad") >= 0.78
    assert similaridade_nome("discor", "Discord") >= 0.78
