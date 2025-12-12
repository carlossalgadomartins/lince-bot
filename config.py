import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_PATH = os.getenv("DATABASE_PATH", "lince_transcricoes.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Limites
LIMITES = {
    "max_duracao_audio": 600,
    "max_tamanho_arquivo": 20 * 1024 * 1024,
    "timeout_transcricao": 60
}

# Mensagens do bot
MENSAGENS = {
    "start": """🦁 **LINCE BOT — Transcrição Médica Automatizada**

📱 **Como usar:**
1. Grave um áudio (consulta, evolução, SOAP)
2. Envie para mim
3. Receba a transcrição formatada com categorias

🔍 **Comandos:**
/ajuda - Instruções
/categorias - Ver categorias
/ultimas - Últimas 5 transcrições

✅ Pronto para começar!""",

    "ajuda": """🦁 **LINCE BOT — Guia de Uso**

📱 **Gravação:**
- Grave um áudio no Telegram (até 10 minutos)
- Envie para o bot
- Receba transcrição formatada em segundos

🏷️ **Categorias Automáticas:**
ASMA, SEPSE, GASTROENTERITE, PNEUMONIA, CONVULSÃO, DIABETES, DESIDRATAÇÃO, MENINGITE, BRONQUIOLITE, PICADA_ESCORPIÃO, FEBRE_SEM_FOCO, INFECÇÃO_URINÁRIA, OTITE

🔍 **Comandos:**
/categorias - Listar todas
/ultimas - Últimas 5

✅ Envie um áudio para começar!"""
}

# Busca
BUSCA = {
    "resultados_por_pagina": 10,
    "dias_padrao": 30
}

# Categorias clínicas
CATEGORIAS_CLINICAS = {
    "ASMA": [
        "asma", "crise de asma", "sibilos", "chiado", "broncoespasmo",
        "salbutamol", "corticoide", "dispneia", "tiragem"
    ],
    "SEPSE": [
        "sepse", "choque séptico", "hipotensão", "taquicardia", "prostração severa",
        "antibiótico", "hemocultura", "PCR elevado", "leucocitose"
    ],
    "GASTROENTERITE": [
        "gastroenterite", "diarreia", "vômitos", "desidratação",
        "soro de reidratação", "ondansetrona", "fezes líquidas"
    ],
    "PNEUMONIA": [
        "pneumonia", "tosse produtiva", "febre alta", "estertores",
        "crepitações", "antibiótico", "dispneia"
    ],
    "CONVULSÃO": [
        "convulsão", "crise convulsiva", "epilepsia", "fenobarbital",
        "diazepam", "midazolam", "abalos"
    ],
    "DIABETES": [
        "diabetes", "glicemia", "hiperglicemia", "cetoacidose",
        "insulina", "poliúria", "polidipsia"
    ],
    "DESIDRATAÇÃO": [
        "desidratação", "mucosas secas", "turgor diminuído",
        "fontanela deprimida", "oligúria"
    ],
    "MENINGITE": [
        "meningite", "rigidez de nuca", "fontanela abaulada",
        "petéquias", "punção lombar"
    ],
    "BRONQUIOLITE": [
        "bronquiolite", "lactente", "vírus sincicial respiratório",
        "VSR", "sibilos difusos"
    ],
    "PICADA_ESCORPIÃO": [
        "escorpião", "picada", "soro antiescorpiônico",
        "bradicardia", "sudorese"
    ],
    "FEBRE_SEM_FOCO": [
        "febre sem foco", "febre sem sinais", "FSSL",
        "febre isolada", "investigação febril"
    ],
    "INFECÇÃO_URINÁRIA": [
        "infecção urinária", "ITU", "cistite", "pielonefrite",
        "disúria", "urocultura"
    ],
    "OTITE": [
        "otite", "otite média", "otalgia", "membrana timpânica",
        "supuração", "amoxicilina"
    ],
}

# Prompt médico (Small Max Precision para Pediatria)
PROMPT_MEDICO_PEDIATRICO = """Transcrição precisa de consulta pediátrica. Segmente frases corretamente.
Termos exatos: sibilos, tiragens, fontanela, RHA, BEG, prostração, febre, tosse, chiado, 
dispneia, cianose, taquipneia, tiragem intercostal, batimento de asa nasal, asma (HPP), 
crise de asma (HMA), abdome plano flácido indolor normotenso RHA presentes, mucosas coradas 
hidratadas, orofaringe livre, membranas timpânicas íntegras, murmúrio vesicular, 
bulhas rítmicas normofonéticas, ECG [soma] (AO/RV/RM), soro antiescorpiônico, ondansetrona, 
dexametazona, atropina, insulina regular, glicemia capilar, diabetes mellitus, bradicardia, 
sepse, gastroenterite, desidratação, meningite, bronquiolite, convulsão, febre sem foco.
Omitir parâmetros ausentes. Cada item em linha separada. Sem HF/HS/RS na anamnese."""

# Correções médicas
CORRECOES_MEDICAS = {
    r'soraniscorpionico': 'soro antiescorpiônico',
    r'soro anti-escorpiônico': 'soro antiescorpiônico',
    r'ondancetrona': 'ondansetrona',
    r'ondancentrona': 'ondansetrona',
    r'pirona': 'prometazina',
    r'dextametazona': 'dexametazona',
    r'aoscuta': 'ausculta',
    r'horoscopia': 'oroscopia',
    r'dados digitais': 'dados vitais',
    r'caminhado': 'encaminhado',
    r'diabetes mellis': 'diabetes mellitus',
    r'(\d+)\s*batimentos\s*cardíacos': r'\1 bpm',
    r'(\d+)\s*batimentos\s*por\s*minuto': r'\1 bpm',
    r'escala\s*de\s*coma\s*de\s*glasgow': 'ECG',
    r'ruídos\s*hidro\s*aéreos': 'RHA',
    r'bom\s*estado\s*geral': 'BEG',
    r'regular\s*estado\s*geral': 'REG',
    r'mau\s*estado\s*geral': 'MEG',
    r'normo tenso': 'normotenso',
}
