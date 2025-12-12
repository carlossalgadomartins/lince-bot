"""
Gerenciamento de banco de dados SQLite com indexação
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.conn = None
        self.conectar()
        self.criar_tabelas()

    def conectar(self):
        """Conecta ao banco de dados."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"✅ Conectado ao banco: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Erro ao conectar ao banco: {e}")
            raise

    def criar_tabelas(self):
        """Cria tabelas se não existirem."""
        cursor = self.conn.cursor()

        # Tabela principal
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcricoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_message_id INTEGER UNIQUE,
                telegram_user_id INTEGER,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                audio_file_id TEXT,
                audio_duracao INTEGER,
                transcricao_raw TEXT,
                transcricao_formatada TEXT,
                tipo_documento TEXT,
                categorias TEXT,
                paciente_nome TEXT,
                tags_adicionais TEXT,
                editado BOOLEAN DEFAULT 0,
                enviado_hf BOOLEAN DEFAULT 0,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Índices para busca rápida
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_categorias ON transcricoes(categorias)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_data ON transcricoes(data_hora)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tipo ON transcricoes(tipo_documento)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user ON transcricoes(telegram_user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_paciente ON transcricoes(paciente_nome)")

        self.conn.commit()
        logger.info("✅ Tabelas criadas/verificadas")

    def salvar_transcricao(self, message_id, user_id, audio_file_id, duracao,
                          transcricao_raw, transcricao_formatada, tipo, categorias,
                          paciente_nome=None):
        """Salva transcrição no banco."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO transcricoes 
                (telegram_message_id, telegram_user_id, audio_file_id, audio_duracao,
                 transcricao_raw, transcricao_formatada, tipo_documento, categorias, paciente_nome)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (message_id, user_id, audio_file_id, duracao, transcricao_raw,
                  transcricao_formatada, tipo, json.dumps(categorias), paciente_nome))
            self.conn.commit()
            logger.info(f"✅ Transcrição salva (ID: {cursor.lastrowid})")
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Erro ao salvar: {e}")
            raise

    def buscar_por_categoria(self, categoria, limite=10, offset=0):
        """Busca transcrições por categoria."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, data_hora, tipo_documento, categorias, transcricao_formatada
                FROM transcricoes
                WHERE categorias LIKE ?
                ORDER BY data_hora DESC
                LIMIT ? OFFSET ?
            """, (f'%"{categoria}"%', limite, offset))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Erro ao buscar: {e}")
            return []

    def buscar_por_periodo(self, dias=7, limite=10):
        """Busca transcrições dos últimos N dias."""
        try:
            cursor = self.conn.cursor()
            data_inicio = datetime.now() - timedelta(days=dias)
            cursor.execute("""
                SELECT id, data_hora, tipo_documento, categorias
                FROM transcricoes
                WHERE data_hora >= ?
                ORDER BY data_hora DESC
                LIMIT ?
            """, (data_inicio.isoformat(), limite))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Erro ao buscar por período: {e}")
            return []

    def buscar_ultimas(self, limite=5):
        """Retorna as últimas N transcrições."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, data_hora, tipo_documento, categorias, transcricao_formatada
                FROM transcricoes
                ORDER BY data_hora DESC
                LIMIT ?
            """, (limite,))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Erro ao buscar últimas: {e}")
            return []

    def buscar_por_id(self, transcricao_id):
        """Busca transcrição específica por ID."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM transcricoes WHERE id = ?
            """, (transcricao_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"❌ Erro ao buscar por ID: {e}")
            return None

    def editar_categoria(self, transcricao_id, novas_categorias):
        """Edita categorias de uma transcrição."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE transcricoes
                SET categorias = ?, editado = 1
                WHERE id = ?
            """, (json.dumps(novas_categorias), transcricao_id))
            self.conn.commit()
            logger.info(f"✅ Categoria editada (ID: {transcricao_id})")
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao editar: {e}")
            return False

    def marcar_enviado_hf(self, transcricao_id):
        """Marca transcrição como enviada para HF."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE transcricoes
                SET enviado_hf = 1
                WHERE id = ?
            """, (transcricao_id,))
            self.conn.commit()
            logger.info(f"✅ Marcado como enviado (ID: {transcricao_id})")
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao marcar: {e}")
            return False

    def estatisticas_categorias(self):
        """Retorna estatísticas por categoria."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT categorias, COUNT(*) as total
                FROM transcricoes
                GROUP BY categorias
                ORDER BY total DESC
            """)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Erro ao gerar estatísticas: {e}")
            return []

    def estatisticas_tipos(self):
        """Retorna estatísticas por tipo de documento."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT tipo_documento, COUNT(*) as total
                FROM transcricoes
                GROUP BY tipo_documento
                ORDER BY total DESC
            """)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Erro ao gerar estatísticas: {e}")
            return []

    def fechar(self):
        """Fecha conexão com banco."""
        if self.conn:
            self.conn.close()
            logger.info("✅ Banco de dados fechado")
