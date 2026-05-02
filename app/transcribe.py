def transcribe_voice(client, audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="ru",
        )
    return resp.text.strip()
