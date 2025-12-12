"""
Pós-processamento médico de transcrições
"""

import re
import logging
from config import CORRECOES_MEDICAS

logger = logging.getLogger(__name__)


def corrigir_termos_medicos(texto: str) -> str:
    """Aplica correções de termos médicos comuns."""
    texto_corrigido = texto

    for padrao, correcao in CORRECOES_MEDICAS.items():
        try:
            texto_corrigido = re.sub(padrao, correcao, texto_corrigido, flags=re.IGNORECASE)
        except Exception as e:
            logger.warning(f"⚠️  Erro ao aplicar correção '{padrao}': {e}")

    logger.info("✅ Correções médicas aplicadas")
    return texto_corrigido


def segmentar_linhas(texto: str) -> str:
    """Segmenta texto em linhas para melhor estruturação."""
    # Adiciona quebra de linha antes de seções (palavras capitalizadas seguidas de dois-pontos)
    texto = re.sub(r'([A-Z][a-z]+:)', r'\n\1', texto)

    # Remove linhas vazias duplicadas
    texto = re.sub(r'\n\s*\n', '\n\n', texto)

    return texto.strip()


def normalizar_doses(texto: str) -> str:
    """Padroniza formato de doses medicamentosas."""
    # Ex: "0,7ml" → "0,7 ml"
    texto = re.sub(r'(\d+[,.]?\d*)(ml|mg|g|UI|unidades)', r'\1 \2', texto)

    # Ex: "0,5unidade" → "0,5 unidade"
    texto = re.sub(r'(\d+)\s*(unidade|unidades)', r'\1 \2', texto)

    logger.info("✅ Doses normalizadas")
    return texto


def extrair_comandos_voz(texto: str) -> tuple:
    """
    Extrai comandos de voz do tipo:
    - "Lince, iniciar transcrição"
    - "Lince, parar transcrição"
    - "Lince, marcar importante"
    - "Lince, enviar para HF"

    Retorna: (texto_limpo, lista_de_comandos)
    """
    comandos = []

    padroes = {
        "iniciar": r"(?i)lince,?\s*iniciar\s*transcrição",
        "parar": r"(?i)lince,?\s*parar\s*transcrição",
        "marcar": r"(?i)lince,?\s*marcar\s*importante",
        "enviar_hf": r"(?i)lince,?\s*enviar\s*para\s*hf",
    }

    texto_limpo = texto

    for tipo, padrao in padroes.items():
        matches = list(re.finditer(padrao, texto))
        for match in matches:
            comandos.append({
                "tipo": tipo,
                "texto": match.group(0),
                "posicao": match.start()
            })
            texto_limpo = texto_limpo.replace(match.group(0), "")

    # Limpar espaços extras
    texto_limpo = re.sub(r'\n\s*\n', '\n\n', texto_limpo)
    texto_limpo = texto_limpo.strip()

    logger.info(f"✅ Comandos extraídos: {len(comandos)}")
    return texto_limpo, comandos


def aplicar_pós_processamento(texto: str) -> str:
    """Aplica todos os pós-processamentos em sequência."""
    texto = corrigir_termos_medicos(texto)
    texto = segmentar_linhas(texto)
    texto = normalizar_doses(texto)

    logger.info("✅ Pós-processamento completo")
    return texto
