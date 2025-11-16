#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EMAIL AGENT MARKET - MVP ROBUSTO
Versão corrigida para execução em qualquer sistema operacional
"""

import os
import sys
import time
import sqlite3
import base64
import re
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Verificar dependências críticas
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.auth.transport.requests import Request
except ImportError as e:
    print(f"❌ ERRO CRÍTICO: Biblioteca Google não encontrada: {e}")
    print("💡 Execute: pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

try:
    from ollama import chat
except ImportError as e:
    print(f"❌ ERRO CRÍTICO: Ollama não encontrado: {e}")
    print("💡 Execute: pip install ollama")
    sys.exit(1)

# ==============================
# CONFIGURAÇÃO ROBUSTA
# ==============================
class Config:
    def __init__(self):
        self.BASE_DIR = Path(__file__).parent.absolute()
        self.ensure_directories()
        
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
        self.TOKEN_FILE = self.BASE_DIR / "token.json"
        self.CLIENT_SECRET_FILE = self.BASE_DIR / "credentials.json"
        self.DB_CLIENTES = self.BASE_DIR / "clientes.db"
        self.ARQ_PRODUTOS = self.BASE_DIR / "produtos.txt"
        self.LOG_FILE = self.BASE_DIR / "email_agent.log"
        
        self.COOLDOWN = timedelta(minutes=10)
        self.MAX_EMAILS_PROCESS = 10
        self.CHECK_INTERVAL = 30  # segundos
        
        # Configurar logging
        self.setup_logging()
    
    def ensure_directories(self):
        """Garante que todos os diretórios necessários existam"""
        self.BASE_DIR.mkdir(exist_ok=True)
    
    def setup_logging(self):
        """Configura sistema de logging robusto"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.LOG_FILE, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def validate_environment(self):
        """Valida se o ambiente está pronto para execução"""
        errors = []
        
        # Verificar arquivos necessários
        if not self.CLIENT_SECRET_FILE.exists():
            errors.append(f"Arquivo {self.CLIENT_SECRET_FILE} não encontrado")
        
        if not self.ARQ_PRODUTOS.exists():
            errors.append(f"Arquivo {self.ARQ_PRODUTOS} não encontrado")
        
        # Verificar permissões
        if not os.access(self.BASE_DIR, os.W_OK):
            errors.append(f"Sem permissão de escrita em {self.BASE_DIR}")
        
        if errors:
            self.logger.error("❌ ERROS DE AMBIENTE:")
            for error in errors:
                self.logger.error(f"   - {error}")
            return False
        
        self.logger.info("✅ Ambiente validado com sucesso")
        return True

# Configuração global
config = Config()

# ==============================
# BANCO DE DADOS ROBUSTO
# ==============================
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.ensure_tables()
    
    def get_connection(self):
        """Retorna conexão com tratamento de erro"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            return conn
        except sqlite3.Error as e:
            config.logger.error(f"❌ Erro de banco de dados: {e}")
            raise
    
    def ensure_tables(self):
        """Garante que todas as tabelas existam"""
        tables = [
            # Tabela clientes
            '''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                nome TEXT,
                data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Tabela produtos
            '''
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY,
                descricao TEXT NOT NULL,
                preco_un REAL NOT NULL
            )
            ''',
            # Tabela pedidos
            '''
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_cliente INTEGER,
                data TEXT NOT NULL,
                status TEXT DEFAULT 'pendente',
                id_email TEXT UNIQUE,
                FOREIGN KEY (id_cliente) REFERENCES clientes (id) ON DELETE CASCADE
            )
            ''',
            # Tabela pedidos_produtos
            '''
            CREATE TABLE IF NOT EXISTS pedidos_produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_pedido INTEGER,
                id_produto INTEGER,
                quantidade INTEGER,
                corrigido BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (id_pedido) REFERENCES pedidos (id) ON DELETE CASCADE,
                FOREIGN KEY (id_produto) REFERENCES produtos (id) ON DELETE CASCADE
            )
            ''',
            # Tabela logs_envio
            '''
            CREATE TABLE IF NOT EXISTS logs_envio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_cliente INTEGER,
                email TEXT NOT NULL,
                mensagem_enviada TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                tipo_agente TEXT NOT NULL,
                FOREIGN KEY (id_cliente) REFERENCES clientes (id) ON DELETE SET NULL
            )
            ''',
            # Tabela correcoes
            '''
            CREATE TABLE IF NOT EXISTS correcoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_pedido INTEGER,
                id_produto INTEGER,
                quantidade_original INTEGER,
                quantidade_corrigida INTEGER,
                data_correcao TEXT NOT NULL,
                FOREIGN KEY (id_pedido) REFERENCES pedidos (id) ON DELETE CASCADE,
                FOREIGN KEY (id_produto) REFERENCES produtos (id) ON DELETE CASCADE
            )
            ''',
            # Tabela emails_processados (CRÍTICA - controle de estado)
            '''
            CREATE TABLE IF NOT EXISTS emails_processados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_email TEXT UNIQUE NOT NULL,
                data_processamento TEXT NOT NULL,
                remetente TEXT NOT NULL,
                assunto TEXT NOT NULL
            )
            '''
        ]
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            for table_sql in tables:
                cursor.execute(table_sql)
            conn.commit()
            config.logger.info("✅ Tabelas do banco validadas")
        except sqlite3.Error as e:
            config.logger.error(f"❌ Erro ao criar tabelas: {e}")
            raise
        finally:
            conn.close()

# ==============================
# AUTENTICAÇÃO GMAIL ROBUSTA
# ==============================
class GmailAuthenticator:
    def __init__(self):
        self.service = None
    
    def authenticate(self):
        """Autenticação robusta com fallbacks"""
        creds = None
        
        # Tentar carregar token existente
        if config.TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), config.SCOPES)
                config.logger.info("✅ Token carregado do arquivo")
            except Exception as e:
                config.logger.warning(f"⚠️ Token inválido: {e}")
                # Remover token corrompido
                try:
                    config.TOKEN_FILE.unlink()
                    config.logger.info("🗑️ Token inválido removido")
                except:
                    pass
        
        # Se não tem credenciais válidas, fazer autenticação
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    config.logger.info("✅ Token renovado")
                except Exception as e:
                    config.logger.warning(f"⚠️ Falha ao renovar token: {e}")
                    creds = None
            
            if not creds:
                if not config.CLIENT_SECRET_FILE.exists():
                    config.logger.error(f"❌ Arquivo {config.CLIENT_SECRET_FILE} não encontrado")
                    return None
                
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(config.CLIENT_SECRET_FILE), config.SCOPES
                    )
                    creds = flow.run_local_server(port=8080, open_browser=True)
                    
                    # Salvar token para uso futuro
                    with open(config.TOKEN_FILE, 'w', encoding='utf-8') as token:
                        token.write(creds.to_json())
                    config.logger.info("✅ Nova autenticação concluída")
                    
                except Exception as e:
                    config.logger.error(f"❌ Erro na autenticação: {e}")
                    return None
        
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            # Testar conexão
            self.service.users().getProfile(userId='me').execute()
            config.logger.info("✅ Autenticação Gmail validada")
            return self.service
        except Exception as e:
            config.logger.error(f"❌ Falha na conexão Gmail: {e}")
            return None

# ==============================
# GESTÃO DE PRODUTOS
# ==============================
class ProductManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def update_products(self):
        """Atualiza produtos do arquivo com tratamento robusto"""
        if not config.ARQ_PRODUTOS.exists():
            config.logger.error(f"❌ Arquivo {config.ARQ_PRODUTOS} não encontrado")
            return False
        
        try:
            with open(config.ARQ_PRODUTOS, 'r', encoding='utf-8') as f:
                linhas = f.readlines()
        except Exception as e:
            config.logger.error(f"❌ Erro ao ler arquivo de produtos: {e}")
            return False
        
        produtos_novos = 0
        conn = self.db.get_connection()
        
        try:
            cursor = conn.cursor()
            for num_linha, linha in enumerate(linhas, 1):
                linha = linha.strip()
                if linha.startswith("produto_id") or not linha:
                    continue
                
                try:
                    # Processamento robusto da linha
                    parts = [p.strip().rstrip("),") for p in linha.split(",")]
                    if len(parts) < 3:
                        config.logger.warning(f"⚠️ Linha {num_linha} ignorada: formato inválido")
                        continue
                    
                    produto_id = int(parts[0])
                    descricao = parts[1]
                    preco = float(parts[2])
                    
                    # Verificar se produto já existe
                    cursor.execute("SELECT 1 FROM produtos WHERE id = ?", (produto_id,))
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO produtos (id, descricao, preco_un) VALUES (?, ?, ?)",
                            (produto_id, descricao, preco)
                        )
                        produtos_novos += 1
                        config.logger.info(f"🆕 Produto adicionado: ID {produto_id} | {descricao}")
                        
                except (ValueError, IndexError) as e:
                    config.logger.warning(f"⚠️ Erro na linha {num_linha} '{linha}': {e}")
                    continue
            
            conn.commit()
            
            if produtos_novos == 0:
                config.logger.info("✅ Nenhum produto novo para adicionar")
            else:
                config.logger.info(f"📊 Total de produtos novos: {produtos_novos}")
                
            return True
            
        except Exception as e:
            conn.rollback()
            config.logger.error(f"❌ Erro ao atualizar produtos: {e}")
            return False
        finally:
            conn.close()

# ==============================
# SISTEMA DE CONTROLE DE ESTADO
# ==============================
class StateManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def is_email_processed(self, email_id):
        """Verifica se email já foi processado"""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM emails_processados WHERE id_email = ?", (email_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def mark_email_processed(self, email_id, remetente, assunto):
        """Marca email como processado"""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO emails_processados (id_email, data_processamento, remetente, assunto) VALUES (?, ?, ?, ?)",
                (email_id, datetime.now().isoformat(), remetente, assunto)
            )
            conn.commit()
        except sqlite3.Error as e:
            config.logger.error(f"❌ Erro ao marcar email como processado: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_last_processed_email(self):
        """Obtém último email processado para recovery"""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id_email FROM emails_processados ORDER BY id DESC LIMIT 1")
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

# ==============================
# AGENTE ORQUESTRADOR ROBUSTO
# ==============================
class EmailOrchestrator:
    def __init__(self, db_manager, state_manager):
        self.db = db_manager
        self.state = state_manager
    
    def classify_intention(self, corpo_email, assunto):
        """Classificação robusta de intenção"""
        corpo_lower = corpo_email.lower()
        assunto_lower = assunto.lower()
        
        # Palavras-chave para classificação rápida
        keywords = {
            'reclamacao': ['reclamação', 'reclamacao', 'problema', 'erro', 'faltando', 'quebrado', 'defeito'],
            'negociacao': ['proposta', 'oferta', 'negociar', 'desconto', 'melhor preço', 'contraproposta'],
            'duvida': ['dúvida', 'duvida', 'pergunta', 'como funciona', 'prazo', 'entrega'],
            'pedido': ['orçamento', 'pedido', 'solicitar', 'comprar', 'cotação', 'preço']
        }
        
        for intent, palavras in keywords.items():
            if any(palavra in corpo_lower or palavra in assunto_lower for palavra in palavras):
                return intent
        
        # Fallback para Ollama
        return self.classify_with_ollama(corpo_email, assunto)
    
    def classify_with_ollama(self, corpo_email, assunto):
        """Classificação com Ollama e tratamento de erro"""
        prompt = f"""
        Classifique a intenção em: pedido, duvida, reclamacao, negociacao.
        Assunto: {assunto}
        Corpo: {corpo_email[:300]}
        Responda APENAS com uma palavra.
        """
        
        try:
            resposta = chat(
                model="llama3",
                messages=[
                    {"role": "system", "content": "Classifique intenções de email."},
                    {"role": "user", "content": prompt}
                ],
                options={'timeout': 30}
            )
            return resposta["message"]["content"].strip().lower()
        except Exception as e:
            config.logger.warning(f"⚠️ Ollama não disponível, usando fallback: {e}")
            return "pedido"  # Fallback conservador

# ==============================
# SISTEMA DE EMAIL ROBUSTO
# ==============================
class EmailManager:
    def __init__(self, gmail_service):
        self.service = gmail_service
        self.last_sent = {}
    
    def get_unprocessed_emails(self, max_results=10):
        """Obtém emails não processados de forma robusta"""
        try:
            result = self.service.users().messages().list(
                userId='me',
                labelIds=['INBOX'],
                maxResults=max_results
            ).execute()
            
            messages = result.get('messages', [])
            unprocessed = []
            
            for msg in messages:
                msg_id = msg['id']
                if not state_manager.is_email_processed(msg_id):
                    try:
                        email_data = self.extract_email_data(msg_id)
                        if email_data:
                            unprocessed.append(email_data)
                    except Exception as e:
                        config.logger.error(f"❌ Erro ao extrair email {msg_id}: {e}")
                        continue
            
            return unprocessed
            
        except Exception as e:
            config.logger.error(f"❌ Erro ao listar emails: {e}")
            return []
    
    def extract_email_data(self, message_id):
        """Extrai dados do email com tratamento robusto"""
        try:
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id, 
                format='full'
            ).execute()
            
            headers = message['payload']['headers']
            remetente = assunto = "desconhecido"
            corpo = ""
            
            for header in headers:
                if header['name'] == 'From':
                    remetente = self.extract_email_from_header(header['value'])
                elif header['name'] == 'Subject':
                    assunto = header['value'] or "Sem assunto"
            
            # Extrair corpo
            corpo = self.extract_body(message['payload'])
            
            return {
                'id': message_id,
                'remetente': remetente,
                'assunto': assunto,
                'corpo': corpo
            }
            
        except Exception as e:
            config.logger.error(f"❌ Erro ao processar email {message_id}: {e}")
            return None
    
    def extract_email_from_header(self, from_header):
        """Extrai email do header de forma robusta"""
        try:
            match = re.search(r'<(.+?)>', from_header)
            if match:
                return match.group(1)
            else:
                # Última parte que parece email
                parts = from_header.split()
                for part in reversed(parts):
                    if '@' in part:
                        return part
                return from_header
        except:
            return from_header
    
    def extract_body(self, payload):
        """Extrai corpo do email de forma robusta"""
        try:
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            elif 'data' in payload.get('body', {}):
                return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
            
            return "Corpo não disponível"
        except Exception as e:
            config.logger.warning(f"⚠️ Erro ao extrair corpo: {e}")
            return "Erro ao ler corpo do email"
    
    def send_email(self, destinatario, assunto, mensagem):
        """Envia email com controle de rate limiting"""
        # Rate limiting
        now = datetime.now()
        if destinatario in self.last_sent:
            if now - self.last_sent[destinatario] < config.COOLDOWN:
                config.logger.warning(f"⏳ Rate limit para {destinatario}")
                return False
        
        try:
            mime_message = MIMEText(mensagem, 'plain', 'utf-8')
            mime_message['to'] = destinatario
            mime_message['subject'] = assunto
            
            raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
            
            self.service.users().messages().send(
                userId='me', 
                body={'raw': raw}
            ).execute()
            
            self.last_sent[destinatario] = now
            config.logger.info(f"📤 Email enviado para {destinatario}")
            return True
            
        except Exception as e:
            config.logger.error(f"❌ Erro ao enviar email para {destinatario}: {e}")
            return False

# ==============================
# SISTEMA PRINCIPAL
# ==============================
class EmailAgentSystem:
    def __init__(self):
        self.db = DatabaseManager(config.DB_CLIENTES)
        self.state = StateManager(self.db)
        self.products = ProductManager(self.db)
        self.orchestrator = EmailOrchestrator(self.db, self.state)
        self.gmail_auth = GmailAuthenticator()
        self.email_manager = None
    
    def initialize(self):
        """Inicialização robusta do sistema"""
        config.logger.info("🚀 Inicializando Email Agent Market...")
        
        if not config.validate_environment():
            return False
        
        if not self.products.update_products():
            config.logger.error("❌ Falha ao carregar produtos")
            return False
        
        service = self.gmail_auth.authenticate()
        if not service:
            config.logger.error("❌ Falha na autenticação Gmail")
            return False
        
        self.email_manager = EmailManager(service)
        config.logger.info("✅ Sistema inicializado com sucesso")
        return True
    
    def process_single_email(self, email_data):
        """Processa um único email de forma robusta"""
        try:
            config.logger.info(f"📧 Processando: {email_data['remetente']} - {email_data['assunto'][:50]}...")
            
            intencao = self.orchestrator.classify_intention(
                email_data['corpo'], 
                email_data['assunto']
            )
            
            config.logger.info(f"🎯 Intenção: {intencao}")
            
            # TODO: Implementar lógica dos agentes específicos
            resposta = f"Resposta automática para {intencao}. Email processado com sucesso."
            
            # Enviar resposta
            if self.email_manager.send_email(email_data['remetente'], "Confirmação", resposta):
                self.state.mark_email_processed(
                    email_data['id'],
                    email_data['remetente'],
                    email_data['assunto']
                )
                return True
            
            return False
            
        except Exception as e:
            config.logger.error(f"❌ Erro ao processar email: {e}")
            return False
    
    def run_monitoring_loop(self):
        """Loop principal de monitoramento robusto"""
        config.logger.info("🔍 Iniciando monitoramento de emails...")
        
        last_email = self.state.get_last_processed_email()
        if last_email:
            config.logger.info(f"📧 Recovery: último email processado {last_email[:20]}...")
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while True:
            try:
                emails = self.email_manager.get_unprocessed_emails(config.MAX_EMAILS_PROCESS)
                
                if emails:
                    config.logger.info(f"📨 {len(emails)} email(s) não processado(s)")
                    
                    success_count = 0
                    for email in emails:
                        if self.process_single_email(email):
                            success_count += 1
                    
                    config.logger.info(f"✅ {success_count}/{len(emails)} emails processados")
                    consecutive_errors = 0  # Reset error counter
                else:
                    config.logger.info("⏳ Nenhum email novo")
                
                # Aguardar próximo ciclo
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                config.logger.info("🛑 Interrompido pelo usuário")
                break
            except Exception as e:
                consecutive_errors += 1
                config.logger.error(f"❌ Erro no loop principal ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    config.logger.error("🚨 Muitos erros consecutivos, encerrando...")
                    break
                
                time.sleep(config.CHECK_INTERVAL * 2)  # Backoff em caso de erro

# ==============================
# EXECUÇÃO PRINCIPAL
# ==============================
def main():
    """Função principal com tratamento completo de erro"""
    config.logger.info("=" * 50)
    config.logger.info("EMAIL AGENT MARKET - MVP ROBUSTO")
    config.logger.info("=" * 50)
    
    system = EmailAgentSystem()
    
    try:
        if system.initialize():
            system.run_monitoring_loop()
        else:
            config.logger.error("❌ Falha na inicialização do sistema")
            sys.exit(1)
            
    except Exception as e:
        config.logger.critical(f"💥 ERRO CRÍTICO: {e}")
        sys.exit(1)
    finally:
        config.logger.info("👋 Sistema encerrado")

if __name__ == "__main__":
    main()