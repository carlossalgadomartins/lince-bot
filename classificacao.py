"""
Detecção de tipo de documento e classificação clínica
"""

import logging
import json
from config import CATEGORIAS_CLINICAS

logger = logging.getLogger(__name__)


def detectar_tipo_documento(texto: str) -> str:
    """
    Detecta tipo de documento baseado em palavras-chave.
    Retorna: ANAMNESE, SOAP, EVOLUCAO ou EXAME_FISICO
    """
    texto_lower = texto.lower()

    # Marcadores SOAP
    if any(m in texto_lower for m in ['s:', 'o:', 'a:', 'p:', 'soap', 'subjetivo', 'objetivo', 'avaliação', 'plano']):
        logger.info("📋 Tipo detectado: SOAP")
        return "SOAP"

    # Marcadores Anamnese
    if any(m in texto_lower for m in ['admitido', 'queixa principal', 'qp:', 'hma', 'hpp', 
                                       'história da moléstia', 'trazido', 'encaminhado', 'medicamentos em uso']):
        logger.info("📋 Tipo detectado: ANAMNESE")
        return "ANAMNESE"

    # Marcadores Evolução
    if any(m in texto_lower for m in ['evolução', 'dia ', 'hoje ', 'paciente mantém', 
                                       'paciente apresenta', 'paciente evolui']):
        logger.info("📋 Tipo detectado: EVOLUCAO")
        return "EVOLUCAO"

    # Padrão: Exame físico isolado
    logger.info("📋 Tipo detectado: EXAME_FISICO")
    return "EXAME_FISICO"


def classificar_categoria_clinica(texto: str) -> list:
    """
    Classifica categoria clínica baseada em termos-chave.
    Retorna lista de categorias detectadas (pode ser múltiplas).
    """
    texto_lower = texto.lower()
    scores = {}

    # Contar matches para cada categoria
    for categoria, termos in CATEGORIAS_CLINICAS.items():
        score = sum(1 for termo in termos if termo in texto_lower)
        if score > 0:
            scores[categoria] = score

    # Retornar categorias com score >= 2 (pelo menos 2 termos)
    categorias = [cat for cat, score in scores.items() if score >= 2]

    # Se nenhuma categoria forte, retornar a de maior score
    if not categorias and scores:
        categorias = [max(scores, key=scores.get)]

    # Se ainda vazio, categoria genérica
    if not categorias:
        categorias = ["GERAL"]

    logger.info(f"🏷️ Categorias detectadas: {', '.join(categorias)}")
    return categorias


def gerar_rascunho_estruturado(transcricao: str, tipo: str) -> dict:
    """Gera rascunho básico baseado no tipo detectado."""
    rascunho = {}

    if tipo == "ANAMNESE":
        rascunho = {
            "HMA": "[Queixa principal e história da moléstia atual]",
            "HPP": "[Histórico patológico pregresso]",
            "Medicamentos em uso": "[Listar com doses]",
            "Hábitos e Rotina": "[Incluir prostração se mencionado]"
        }

        # Extrair simples (heurística básica)
        if "prostrado" in transcricao.lower():
            rascunho["HMA"] = "[Paciente prostrado - incluir em HMA]"
            rascunho["Hábitos e Rotina"] = "[Prostração observada]"

        if "asma" in transcricao.lower() and "crise" not in transcricao.lower():
            rascunho["HPP"] = "[Asma diagnosticada - incluir em HPP]"

        if "crise de asma" in transcricao.lower():
            rascunho["HMA"] = "[Crise de asma - incluir em HMA]"

    elif tipo == "SOAP":
        rascunho = {
            "Medicamentos em uso": "[Listar com doses]",
            "HPP": "[Histórico patológico pregresso]",
            "S": "[Subjetivo: Sintomas relatados]",
            "O": "[Objetivo: Exame físico]",
            "RL": "[Resultado de exames laboratoriais - após O]",
            "A": "[Avaliação: Diagnóstico]",
            "P": "[Plano: Condutas]"
        }

    elif tipo == "EVOLUCAO":
        rascunho = {
            "Data/Hora": "[Incluir data e hora]",
            "Medicamentos em uso": "[Atualizações]",
            "HPP": "[Se relevante]",
            "Evolução": "[Resumo do dia]",
            "Exame físico": "[Dados vitais + sistemas relevantes]",
            "RL": "[Se novo]",
            "Conduta": "[Próximos passos]"
        }

    logger.info(f"📝 Rascunho estruturado gerado para {tipo}")
    return rascunho
