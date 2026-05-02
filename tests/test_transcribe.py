from unittest.mock import MagicMock
from app.transcribe import transcribe_voice

def test_transcribe(tmp_path):
    audio = tmp_path / "v.ogg"
    audio.write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="Привет")
    text = transcribe_voice(mock_client, str(audio))
    assert text == "Привет"
