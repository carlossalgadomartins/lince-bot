#!/usr/bin/env python3
import logging
import os
import tempfile
from pathlib import Path
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

try:
    from config import TELEGRAM_BOT_TOKEN, LIMITES, MENSAGENS, CATEGORIAS_CLINICAS
    from database import DatabaseManager
    from whisper_api import transcrever_audio_groq, validar_audio
    from processamento import aplicar_pós_processamento
    from classificacao import detectar_tipo_documento, classificar_categoria_clinica
except ImportError as e:
    print(f"Erro: {e}")
    exit(1)

# ============================================
# 🔒 CONFIGURAÇÃO DE ACESSO
# ============================================

raw_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "")
ALLOWED_IDS = {int(i.strip()) for i in raw_ids.split(",") if i.strip()}

def usuario_autorizado(user_id: int) -> bool:
    """Verifica se o usuário está autorizado"""
    return user_id in ALLOWED_IDS

# ============================================
# 🏷️ SISTEMA DE TAGS
# ============================================

def criar_tabela_tags():
    """Cria tabela de tags (executar uma vez)"""
    conn = sqlite3.connect('lince_transcricoes.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcricao_id INTEGER,
            tag TEXT,
            data_criacao TEXT,
            FOREIGN KEY (transcricao_id) REFERENCES transcricoes(id)
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Tabela de tags criada/verificada")

async def adicionar_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona tag à última transcrição"""
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    tag = ' '.join(context.args).strip()

    if not tag:
        await update.message.reply_text("❌ Use: /tag nome_da_tag")
        return

    conn = sqlite3.connect('lince_transcricoes.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM transcricoes
        WHERE telegram_user_id = ?
        ORDER BY criado_em DESC
        LIMIT 1
    ''', (update.effective_user.id,))

    resultado = cursor.fetchone()

    if not resultado:
        await update.message.reply_text("❌ Nenhuma transcrição encontrada.")
        conn.close()
        return

    transcricao_id = resultado[0]

    cursor.execute('''
        INSERT INTO tags (transcricao_id, tag, data_criacao)
        VALUES (?, ?, ?)
    ''', (transcricao_id, tag, datetime.now().isoformat()))

    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Tag '{tag}' adicionada à última transcrição!")

async def listar_por_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todas as transcrições com uma tag específica"""
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    tag = ' '.join(context.args).strip()

    if not tag:
        await update.message.reply_text("❌ Use: /listar nome_da_tag")
        return

    conn = sqlite3.connect('lince_transcricoes.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.transcricao_formatada, t.criado_em
        FROM transcricoes t
        INNER JOIN tags tg ON t.id = tg.transcricao_id
        WHERE tg.tag = ? AND t.telegram_user_id = ?
        ORDER BY t.criado_em DESC
    ''', (tag, update.effective_user.id))

    resultados = cursor.fetchall()
    conn.close()

    if not resultados:
        await update.message.reply_text(f"❌ Nenhuma transcrição encontrada com a tag '{tag}'.")
        return

    resposta = f"📋 *Transcrições com tag '{tag}':*\n\n"

    for i, (texto, data) in enumerate(resultados, 1):
        preview = texto[:150].replace('\n', ' ') + "..."
        resposta += f"*{i}. {data}*\n{preview}\n\n"

    await update.message.reply_text(resposta, parse_mode='Markdown')

async def listar_todas_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todas as tags disponíveis"""
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    conn = sqlite3.connect('lince_transcricoes.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT tag, COUNT(*) as quantidade
        FROM tags
        GROUP BY tag
        ORDER BY quantidade DESC
    ''')

    resultados = cursor.fetchall()
    conn.close()

    if not resultados:
        await update.message.reply_text("❌ Nenhuma tag criada ainda.")
        return

    resposta = "🏷️ *Tags disponíveis:*\n\n"
    for tag, qtd in resultados:
        resposta += f"• `{tag}` ({qtd} transcrição{'s' if qtd > 1 else ''})\n"

    await update.message.reply_text(resposta, parse_mode='Markdown')

# ============================================
# CONFIGURAÇÃO DE LOGGING E BANCO
# ============================================

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler('logs/lince_bot.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

try:
    db = DatabaseManager()
except Exception as e:
    logger.error(f"Erro BD: {e}")
    exit(1)

# ============================================
# HANDLERS EXISTENTES (COM VERIFICAÇÃO DE ACESSO)
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return
    await update.message.reply_text(MENSAGENS["start"], parse_mode='Markdown')

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return
    await update.message.reply_text(MENSAGENS["ajuda"], parse_mode='Markdown')

async def processar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    audio_path = None
    try:
        if update.message.voice:
            audio_obj = update.message.voice
            file_id = audio_obj.file_id
            duracao = audio_obj.duration
            extensao = ".ogg"
        elif update.message.audio:
            audio_obj = update.message.audio
            file_id = audio_obj.file_id
            duracao = audio_obj.duration
            extensao = ".mp3"
        else:
            await update.message.reply_text("Envie um áudio")
            return

        if duracao > LIMITES["max_duracao_audio"]:
            await update.message.reply_text(f"Áudio muito longo ({duracao}s)")
            return

        msg = await update.message.reply_text("Baixando áudio...")
        audio_file = await context.bot.get_file(file_id)

        with tempfile.NamedTemporaryFile(suffix=extensao, delete=False) as tmp:
            audio_path = tmp.name

        await audio_file.download_to_drive(audio_path)

        if not validar_audio(audio_path, LIMITES["max_tamanho_arquivo"]):
            await msg.edit_text("Arquivo inválido")
            os.remove(audio_path)
            return

        await msg.edit_text("Transcrevendo...")
        transcricao_raw = transcrever_audio_groq(audio_path)

        if not transcricao_raw or len(transcricao_raw.strip()) < 10:
            await msg.edit_text("Transcrição vazia")
            os.remove(audio_path)
            return

        transcricao = aplicar_pós_processamento(transcricao_raw)
        tipo = detectar_tipo_documento(transcricao)
        categorias = classificar_categoria_clinica(transcricao)

        # Formatar texto SEM as categorias no topo
        txt_fmt = f"Lince, iniciar transcrição\n{transcricao}\nLince, parar transcrição"

        tid = db.salvar_transcricao(update.message.message_id, update.message.from_user.id, file_id, duracao, transcricao_raw, txt_fmt, tipo, categorias)

        # ============================================
        # CRIAR BOTÕES CLICÁVEIS PARA CATEGORIAS
        # ============================================
        botoes = []

        # Linha 1: Botões de categorias (máximo 3 por linha)
        linha_categorias = []
        for cat in categorias:
            # Sanitizar nome da categoria para callback_data
            cat_sanitizado = cat.replace(" ", "_")
            linha_categorias.append(InlineKeyboardButton(f"🏷️ {cat}", callback_data=f"cat_{cat_sanitizado}"))
            if len(linha_categorias) == 3:
                botoes.append(linha_categorias)
                linha_categorias = []

        # Adicionar categorias restantes
        if linha_categorias:
            botoes.append(linha_categorias)

        # Linha final: Botão "Ver texto completo"
        botoes.append([InlineKeyboardButton("📄 Ver texto completo", callback_data=f"view_{tid}")])

        kb = InlineKeyboardMarkup(botoes)

        await msg.delete()

        # Mensagem formatada
        prev = (txt_fmt[:200] + "...") if len(txt_fmt) > 200 else txt_fmt
        mensagem = f"✅ *Transcrição concluída*\n\n📋 Tipo: `{tipo}`\n🆔 ID: `{tid}`\n\n{prev}"

        await update.message.reply_text(mensagem, reply_markup=kb, parse_mode='Markdown')

        os.remove(audio_path)

    except Exception as e:
        logger.error(f"Erro: {e}")
        await update.message.reply_text("Erro ao processar")
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

async def ultimas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    resultados = db.buscar_ultimas(limite=5)
    if not resultados:
        await update.message.reply_text("Nenhuma transcrição")
        return
    msg = "Últimas 5:\n\n"
    for r in resultados:
        msg += f"ID {r['id']} | {r['tipo_documento']}\n"
    await update.message.reply_text(msg)

async def categorias_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    msg = "Categorias:\n" + "\n".join([f"• {c}" for c in CATEGORIAS_CLINICAS.keys()])
    await update.message.reply_text(msg)

# ============================================
# HANDLER PARA CLIQUES NAS CATEGORIAS
# ============================================

async def listar_por_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE, categoria: str):
    """Lista todas as transcrições de uma categoria específica"""
    query = update.callback_query

    if not usuario_autorizado(query.from_user.id):
        await query.answer("⛔ Acesso negado", show_alert=True)
        return

    conn = sqlite3.connect('lince_transcricoes.db')
    cursor = conn.cursor()

    # Buscar todas as transcrições do usuário
    cursor.execute('''
        SELECT id, tipo_documento, criado_em, transcricao_formatada, categorias
        FROM transcricoes
        WHERE telegram_user_id = ?
        ORDER BY criado_em DESC
    ''', (query.from_user.id,))

    todas = cursor.fetchall()
    conn.close()

    # Filtrar manualmente as que contêm a categoria
    resultados = []
    for tid, tipo, data, texto, cats in todas:
        if cats and categoria.lower() in cats.lower():
            resultados.append((tid, tipo, data, texto))

    if not resultados:
        await query.answer(f"❌ Nenhuma transcrição encontrada na categoria '{categoria}'", show_alert=True)
        return

    resposta = f"🏷️ *Categoria: {categoria}*\n\n"

    for i, (tid, tipo, data, texto) in enumerate(resultados[:10], 1):
        # Remover caracteres especiais do Markdown para evitar erros
        preview = texto[:100].replace('\n', ' ').replace('*', '').replace('_', '').replace('[', '').replace(']', '') + "..."
        resposta += f"*{i}. ID {tid}* | {tipo}\n📅 {data}\n{preview}\n\n"

    # Botão para voltar
    kb = [[InlineKeyboardButton("◀️ Voltar", callback_data="voltar")]]

    await query.message.reply_text(resposta, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    await query.answer()

# ============================================
# HANDLER DE CALLBACKS (BOTÕES CLICÁVEIS)
# ============================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Ver texto completo
    if query.data.startswith("view_"):
        tid = int(query.data.split("_")[1])
        trans = db.buscar_por_id(tid)
        if trans:
            await query.message.reply_text(f"📄 *Texto completo (ID {tid}):*\n\n{trans['transcricao_formatada'][:4000]}", parse_mode='Markdown')

    # Listar por categoria
    elif query.data.startswith("cat_"):
        categoria = query.data.replace("cat_", "").replace("_", " ")
        await listar_por_categoria(update, context, categoria)

    # Voltar (apenas fecha a mensagem)
    elif query.data == "voltar":
        await query.message.delete()

# ============================================
# FUNÇÃO MAIN
# ============================================

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN não configurado")
        return

    # Criar tabela de tags
    criar_tabela_tags()
    print(f"✅ Bot iniciado com restrição de acesso")
    print(f"✅ IDs autorizados: {ALLOWED_IDS}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers de comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("ultimas", ultimas))
    app.add_handler(CommandHandler("categorias", categorias_cmd))

    # Handlers de tags
    app.add_handler(CommandHandler("tag", adicionar_tag))
    app.add_handler(CommandHandler("listar", listar_por_tag))
    app.add_handler(CommandHandler("tags", listar_todas_tags))

    # Handler de áudio
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, processar_audio))

    # Handler de callbacks (botões clicáveis)
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()

