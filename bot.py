#!/usr/bin/env python3
import logging
import os
import tempfile
from pathlib import Path
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

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler('logs/lince_bot.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

try:
    db = DatabaseManager()
except Exception as e:
    logger.error(f"Erro BD: {e}")
    exit(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MENSAGENS["start"], parse_mode='Markdown')

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MENSAGENS["ajuda"], parse_mode='Markdown')

async def processar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    audio_path = None
    try:
        # Aceitar VOICE (gravação interna) ou AUDIO (arquivo enviado)
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

        txt_fmt = f"[TIPO: {tipo}]\n[CATEGORIAS: {', '.join(categorias)}]\n\nLince, iniciar transcrição\n{transcricao}\nLince, parar transcrição"

        tid = db.salvar_transcricao(update.message.message_id, update.message.from_user.id, file_id, duracao, transcricao_raw, txt_fmt, tipo, categorias)

        kb = [[InlineKeyboardButton("Ver texto", callback_data=f"view_{tid}")]]
        await msg.delete()

        prev = (txt_fmt[:250] + "...") if len(txt_fmt) > 250 else txt_fmt
        await update.message.reply_text(f"Transcrição OK\nTipo: {tipo}\nCategorias: {', '.join(categorias)}\nID: {tid}\n\n{prev}", reply_markup=InlineKeyboardMarkup(kb))

        os.remove(audio_path)

    except Exception as e:
        logger.error(f"Erro: {e}")
        await update.message.reply_text("Erro ao processar")
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

async def ultimas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resultados = db.buscar_ultimas(limite=5)
    if not resultados:
        await update.message.reply_text("Nenhuma transcrição")
        return
    msg = "Últimas 5:\n\n"
    for r in resultados:
        msg += f"ID {r['id']} | {r['tipo_documento']}\n"
    await update.message.reply_text(msg)

async def categorias_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "Categorias:\n" + "\n".join([f"• {c}" for c in CATEGORIAS_CLINICAS.keys()])
    await update.message.reply_text(msg)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("view_"):
        tid = int(query.data.split("_")[1])
        trans = db.buscar_por_id(tid)
        if trans:
            await query.message.reply_text(f"Texto:\n\n{trans['transcricao_formatada'][:4000]}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN não configurado")
        return
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("ultimas", ultimas))
    app.add_handler(CommandHandler("categorias", categorias_cmd))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, processar_audio))
    app.add_handler(CallbackQueryHandler(button_callback))
    logger.info("Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()
