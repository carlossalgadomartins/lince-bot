#!/usr/bin/env python3
import logging
import os
import tempfile
from pathlib import Path
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

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
# 🔒 CONTROLE DE ACESSO PRIVADO
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
    conn = sqlite3.connect("lince_transcricoes.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcricao_id INTEGER,
            tag TEXT,
            data_criacao TEXT,
            FOREIGN KEY (transcricao_id) REFERENCES transcricoes(id)
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Tabela de tags criada/verificada")

async def adicionar_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona tag à última transcrição"""
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    tag = " ".join(context.args).strip()
    if not tag:
        await update.message.reply_text("❌ Use: /tag nome_da_tag")
        return

    conn = sqlite3.connect("lince_transcricoes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM transcricoes
        WHERE telegram_user_id = ?
        ORDER BY criado_em DESC
        LIMIT 1
    """, (update.effective_user.id,))
    resultado = cursor.fetchone()

    if not resultado:
        await update.message.reply_text("❌ Nenhuma transcrição encontrada.")
        conn.close()
        return

    tid = resultado[0]

    cursor.execute("""
        INSERT INTO tags (transcricao_id, tag, data_criacao)
        VALUES (?, ?, ?)
    """, (tid, tag, datetime.now().isoformat()))

    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Tag '{tag}' adicionada à última transcrição!")

async def listar_por_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todas as transcrições com uma tag específica"""
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    tag = " ".join(context.args).strip()
    if not tag:
        await update.message.reply_text("❌ Use: /listar nome_da_tag")
        return

    conn = sqlite3.connect("lince_transcricoes.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.transcricao_formatada, t.criado_em
        FROM transcricoes t
        INNER JOIN tags tg ON t.id = tg.transcricao_id
        WHERE tg.tag = ? AND t.telegram_user_id = ?
        ORDER BY t.criado_em DESC
    """, (tag, update.effective_user.id))
    resultados = cursor.fetchall()
    conn.close()

    if not resultados:
        await update.message.reply_text(f"❌ Nenhum registro com tag '{tag}'.")
        return

    resposta = f"📋 *Transcrições com tag '{tag}':*\n\n"
    botoes = []

    for i, (tid, texto, data) in enumerate(resultados, start=1):
        preview = (
            texto[:75]
            .replace("\n", " ")
            .replace("*", "")
            .replace("_", "")
            .replace("[", "")
            .replace("]", "")
            .strip()
            + "..."
        )
        resposta += f"*{i}. ID {tid}* | {data}\n{preview}\n\n"
        botoes.append([InlineKeyboardButton(f"📍 Ver transcrição {i}", callback_data=f"view_{tid}")])

    botoes.append([InlineKeyboardButton("◀️ Fechar", callback_data="voltar")])

    await update.message.reply_text(
        resposta,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

async def listar_todas_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todas as tags disponíveis"""
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    conn = sqlite3.connect("lince_transcricoes.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tag, COUNT(*)
        FROM tags
        GROUP BY tag
        ORDER BY COUNT(*) DESC
    """)
    dados = cursor.fetchall()
    conn.close()

    if not dados:
        await update.message.reply_text("❌ Nenhuma tag cadastrada.")
        return

    texto = "🏷️ *Tags disponíveis:*\n\n"
    for tag, qtd in dados:
        texto += f"• `{tag}` ({qtd})\n"

    await update.message.reply_text(texto, parse_mode="Markdown")

# ============================================
# LOG & DATABASE
# ============================================

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/lince_bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

try:
    db = DatabaseManager()
except Exception as e:
    logger.error(f"Erro ao iniciar BD: {e}")
    exit(1)

# ============================================
# FUNÇÕES DO BOT
# ============================================

async def start(update: Update, context):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return
    await update.message.reply_text(MENSAGENS["start"], parse_mode="Markdown")

async def ajuda(update: Update, context):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return
    await update.message.reply_text(MENSAGENS["ajuda"], parse_mode="Markdown")

async def processar_audio(update: Update, context):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    audio_path = None
    try:
        if update.message.voice:
            audio_obj = update.message.voice
            extensao = ".ogg"
        elif update.message.audio:
            audio_obj = update.message.audio
            extensao = ".mp3"
        else:
            await update.message.reply_text("Envie um áudio.")
            return

        file_id = audio_obj.file_id
        duration = audio_obj.duration

        if duration > LIMITES["max_duracao_audio"]:
            await update.message.reply_text("⛔ Áudio muito longo.")
            return

        msg = await update.message.reply_text("Baixando áudio...")
        arquivo = await context.bot.get_file(file_id)

        with tempfile.NamedTemporaryFile(suffix=extensao, delete=False) as tmp:
            audio_path = tmp.name
        await arquivo.download_to_drive(audio_path)

        if not validar_audio(audio_path, LIMITES["max_tamanho_arquivo"]):
            await msg.edit_text("Arquivo inválido")
            os.remove(audio_path)
            return

        await msg.edit_text("Transcrevendo...")
        texto_raw = transcrever_audio_groq(audio_path)

        if not texto_raw or len(texto_raw.strip()) < 10:
            await msg.edit_text("Transcrição vazia")
            os.remove(audio_path)
            return

        texto_fmt = aplicar_pós_processamento(texto_raw)
        tipo_doc = detectar_tipo_documento(texto_fmt)
        categorias = classificar_categoria_clinica(texto_fmt)

        tid = db.salvar_transcricao(
            update.message.message_id,
            update.message.from_user.id,
            file_id,
            duration,
            texto_raw,
            texto_fmt,
            tipo_doc,
            categorias
        )

        botoes = []

        cat_line = []
        for cat in categorias:
            cat_sanit = cat.replace(" ", "_")
            cat_line.append(InlineKeyboardButton(f"🏷️ {cat}", callback_data=f"cat_{cat_sanit}"))
            if len(cat_line) == 3:
                botoes.append(cat_line)
                cat_line = []

        if cat_line:
            botoes.append(cat_line)

        botoes.append([InlineKeyboardButton("📄 Ver texto completo", callback_data=f"view_{tid}")])

        await msg.delete()

        prev = (texto_fmt[:250] + "...") if len(texto_fmt) > 250 else texto_fmt
        await update.message.reply_text(
            f"✅ *Transcrição concluída*\n\n🆔 ID `{tid}`\n📋 Tipo: `{tipo_doc}`\n\n{prev}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(botoes)
        )

        os.remove(audio_path)

    except Exception as e:
        logger.error(f"Erro processando áudio: {e}")
        await update.message.reply_text("Erro ao processar o áudio.")
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

async def ultimas(update: Update, context):
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

async def categorias_cmd(update: Update, context):
    if not usuario_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso negado. Este bot é privado.")
        return

    msg = "Categorias:\n" + "\n".join([f"• {c}" for c in CATEGORIAS_CLINICAS.keys()])
    await update.message.reply_text(msg)

async def listar_por_categoria(update: Update, context, categoria: str):
    """Lista todas as transcrições de uma categoria específica"""
    query = update.callback_query

    if not usuario_autorizado(query.from_user.id):
        await query.answer("⛔ Acesso negado", show_alert=True)
        return

    conn = sqlite3.connect("lince_transcricoes.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, tipo_documento, criado_em, transcricao_formatada, categorias
        FROM transcricoes
        WHERE telegram_user_id = ?
        ORDER BY criado_em DESC
    """, (query.from_user.id,))
    todas = cursor.fetchall()
    conn.close()

    resultados = []
    for tid, tipo, data, texto, cats in todas:
        if cats and categoria.lower() in cats.lower():
            resultados.append((tid, tipo, data, texto))

    if not resultados:
        await query.answer("❌ Nenhum registro nesta categoria.", show_alert=True)
        return

    texto_msg = f"🏷️ *Categoria: {categoria}*\n\n"
    botoes = []

    for i, (tid, tipo, data, texto) in enumerate(resultados, start=1):
        preview = (
            texto[:75]
            .replace("\n", " ")
            .replace("*", "")
            .replace("_", "")
            .replace("[", "")
            .replace("]", "")
            .strip()
            + "..."
        )
        texto_msg += f"*{i}. ID {tid}* | {tipo}\n📅 {data}\n{preview}\n\n"
        botoes.append([InlineKeyboardButton(f"📍 Ver transcrição {i}", callback_data=f"view_{tid}")])

    botoes.append([InlineKeyboardButton("◀️ Fechar", callback_data="voltar")])

    await query.message.reply_text(texto_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))
    await query.answer()

async def button_callback(update: Update, context):
    """Handler de callbacks dos botões"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("view_"):
        tid = int(query.data.split("_")[1])
        registro = db.buscar_por_id(tid)
        if registro:
            texto = registro["transcricao_formatada"]
            await query.message.reply_text(
                f"📄 *Transcrição completa (ID {tid}):*\n\n{texto[:4000]}",
                parse_mode="Markdown"
            )

    elif query.data.startswith("cat_"):
        categoria = query.data.replace("cat_", "").replace("_", " ")
        await listar_por_categoria(update, context, categoria)

    elif query.data == "voltar":
        await query.message.delete()

# ============================================
# MAIN
# ============================================

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN não configurado")
        return

    criar_tabela_tags()
    print(f"✅ Bot iniciado com restrição de acesso")
    print(f"✅ IDs autorizados: {ALLOWED_IDS}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("ultimas", ultimas))
    app.add_handler(CommandHandler("categorias", categorias_cmd))
    app.add_handler(CommandHandler("tag", adicionar_tag))
    app.add_handler(CommandHandler("listar", listar_por_tag))
    app.add_handler(CommandHandler("tags", listar_todas_tags))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, processar_audio))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()

