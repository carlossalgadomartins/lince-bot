import os
import logging
import requests
from config import GROQ_API_KEY, PROMPT_MEDICO_PEDIATRICO

logger = logging.getLogger(__name__)

def transcrever_audio_groq(audio_file_path):
    """Transcreve áudio usando Groq Whisper API via REST"""
    try:
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY não configurado")

        logger.info(f"Transcrevendo: {audio_file_path}")

        with open(audio_file_path, "rb") as audio_file:
            files = {"file": ("audio.ogg", audio_file, "audio/ogg")}
            data = {
                "model": "whisper-large-v3",
                "language": "pt",
                "prompt": PROMPT_MEDICO_PEDIATRICO,
                "temperature": "0.0",
                "response_format": "text"
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files=files,
                data=data,
                timeout=60
            )

            if response.status_code == 200:
                texto = response.text
                logger.info(f"Transcrição OK ({len(texto)} chars)")
                return texto
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

    except Exception as e:
        logger.error(f"Erro: {e}")
        raise

def validar_audio(audio_file_path, max_size):
    if not os.path.exists(audio_file_path):
        return False
    tamanho = os.path.getsize(audio_file_path)
    return 200 < tamanho < max_size
