#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EMAIL AGENT MARKET - MVP COM RAG
Versão com RAG para respostas precisas baseadas nos dados da empresa
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

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from ollama import chat

# ==============================
# CONFIGURAÇÕES
# ==============================
class Config:
    """Classe de configuração centralizado do sistema
       Contém todos os paths, intervalos e os parâmetros do sistema

       Atributos são:
            BASE_DIR (Path): É o diretório base do sistema
            SCOPES (list): Permissões da API do GMAIL
            CHECK_INTERVAL (int): Intervalo entre verificações em segundos (60 * 5 = 300 segundos)
            COOLDOWN (timedelta): Intervalo mínimo entre emails para o mesmo destinatário

    """
    def __init__(self):

        # Inicialização das configurações com seus respectivos valores padrões
        self.BASE_DIR = Path(__file__).parent.absolute()
        self.ensure_directories()
        
        # Configurações da API do GMAIL
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
        self.TOKEN_FILE = self.BASE_DIR / "token.json"
        self.CLIENT_SECRET_FILE = self.BASE_DIR / "credentials.json"
        self.DB_CLIENTES = self.BASE_DIR / "clientes.db"
        
        # ARQUIVOS RAG - A base de conhecimento da empresa
        self.ARQ_PRODUTOS = self.BASE_DIR / "produtos.txt"      # Informações dos produtos
        self.ARQ_POLITICAS = self.BASE_DIR / "politicas.txt"    # Informações políticas
        self.ARQ_FINANCEIRO = self.BASE_DIR / "financeiro.txt"  # Informações da parte financeira
        self.ARQ_ENTREGAS = self.BASE_DIR / "entregas.txt"      # Informações relacionadas a entregas
        
        # CONFIGURAÇÕES DE OPERAÇÕES
        self.LOG_FILE = self.BASE_DIR / "email_agent.log" # Geração do arquivo de logs
        
        self.COOLDOWN = timedelta(minutes=10)   # Evitar spam para o mesmo cliente
        self.CHECK_INTERVAL = 300               # Intervalo entre as checagens de novos emails
        self.MAX_EMAILS_PROCESS = 10            # Máximo de emails checados por ciclo
        
        self.setup_logging()
    
    def ensure_directories(self):

        # Garantia que o diretório base existe
        self.BASE_DIR.mkdir(exist_ok=True)
    
    def setup_logging(self):

        # Configurações do sistema de logs para o monitoramento
        # Os logs sao exibidos no console em tempo real para debugging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
    
    def validate_environment(self):

        """ Válida se o ambiente está pronto para execução
            Return:
                    bool: True se todos os arquivos essencias existem, False caso contrário
        """

        # Verifica apenas arquivos essenciais
        essential_files = [self.CLIENT_SECRET_FILE]
        missing = [f for f in essential_files if not f.exists()]
        
        if missing:
            self.logger.error("❌ Arquivos essenciais faltando:")
            for f in missing:
                self.logger.error(f"   - {f.name}")
            return False
        
        self.logger.info("✅ Ambiente validado")
        return True

# Instância global de configuração
config = Config()

# ==============================
# GERENCIADOR RAG (RETRIEVAL-AUGMENTED GENERATION)
# ==============================
class RAGManager:

    """
    
    Sistema RAG para fornecer contexto preciso ao Ollama
    Os arquivos de conhecimento da empresa são carregados
    as informações relevantes baseado nas intenções detctadas no email.

    Atributos são: 
        context_cache (dict): Cache com conteúdo de todos os arquivos carregados

    """

    def __init__(self):

        # Inicializa o RAGManager para carregar todos os contextos
        self.context_cache = {}
        self.load_all_contexts()
    
    def load_all_contexts(self):
        """ 
        
        Carrega todos os arquivos de contexto uma vez na inicialização
        Os arquivos são mantidos em cache para performance
        Arquivos ausentes são tratados silenciosamente
        
        """
        contexts = {
            'produtos': self.load_file(config.ARQ_PRODUTOS),
            'politicas': self.load_file(config.ARQ_POLITICAS),
            'financeiro': self.load_file(config.ARQ_FINANCEIRO),
            'entregas': self.load_file(config.ARQ_ENTREGAS)
        }
        self.context_cache = contexts
        config.logger.info("✅ Contextos RAG carregados")
    
    def load_file(self, file_path):

        """

        Verifica se o arquivo existe e carrega o conteúdo do arquivo
        
        Args:
            file_path (Path): Caminho do arquivo a ser carregado

        Returns:
            str: Conteúdo do arquivo ou string vazia caso não exista
        
        """
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                config.logger.error(f"❌ Erro ao carregar {file_path.name}: {e}")
        return ""
    

    def get_relevant_context(self, email_corpo, intencoes):
        
        """
        
        Seleciona o contexto relevante com base nas intenções detectadas
        
        Args:
            email_corpo (str): Corpo do emails recebido
            intencoes (list): Lista das intenções detectadas

        Returns:
            str: Contexto relevante concatenado ou string vazia
        """
        contexto_relevante = []
        corpo_lower = email_corpo.lower()
        intencoes_str = [i['intencao'] for i in intencoes]
        
        # PRODUTOS - para pedidos, negociações
        if any(i in intencoes_str for i in ['pedido', 'negociacao']):
            if self.context_cache['produtos']:
                contexto_relevante.append("🎯 CATÁLOGO DE PRODUTOS:\n" + self.context_cache['produtos'])
        
        # POLÍTICAS - para reclamações, trocas, dúvidas
        if any(i in intencoes_str for i in ['reclamacao', 'duvida']):
            if self.context_cache['politicas']:
                contexto_relevante.append("📋 POLÍTICAS DA EMPRESA:\n" + self.context_cache['politicas'])
        
        # FINANCEIRO - para pagamentos, descontos
        if any(i in intencoes_str for i in ['negociacao', 'duvida']) or any(word in corpo_lower for word in ['pagamento', 'desconto', 'preço', 'valor']):
            if self.context_cache['financeiro']:
                contexto_relevante.append("💰 INFORMAÇÕES FINANCEIRAS:\n" + self.context_cache['financeiro'])
        
        # ENTREGAS - para prazos, fretes
        if any(i in intencoes_str for i in ['duvida', 'pedido']) or any(word in corpo_lower for word in ['entrega', 'prazo', 'frete', 'envio']):
            if self.context_cache['entregas']:
                contexto_relevante.append("🚚 INFORMAÇÕES DE ENTREGA:\n" + self.context_cache['entregas'])
        
        return "\n\n".join(contexto_relevante) if contexto_relevante else ""


# ==============================
# GERENCIADOR DE BANCO DE DADOS
# ==============================
class DatabaseManager:

    """

    Gerencia as operações de banco de dados SQLite

    Responsável por manter o histórico de emails processados
    para evitar duplicação de respostas

    """

    def __init__(self, db_path):

        """
        Inicializa o gerenciador de banco de dados

        Args:
            db_path (str): Caminho do arquivo de banco de dados

        """
        self.db_path = db_path
        self.ensure_tables()
    
    def get_connection(self):

        """

        Cria e retorna uma conexão com o banco de dados

        Returns:
            sqlite.Connection: Conexão com o banco
        """
        return sqlite3.connect(self.db_path)
    
    def ensure_tables(self):

        """ 

        Garante que as tabelas necessárias existam no banco

        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Tabela para controle de emails processados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emails_processados (
                id_email TEXT PRIMARY KEY,
                data_processamento TEXT,
                remetente TEXT,
                assunto TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        config.logger.info("✅ Banco de dados pronto")

# ==============================
# GERENCIADOR DE ESTADO
# ==============================
class StateManager:

    """

    Gerencia o estado do sistema e controle de fluxo

    Responsável por rastrear quais email já foram processados e evitar retrabalho
    """

    def __init__(self, db_manager):

        """

        Inicializa o gerenciador de estado

        Args: 
            db.manager (DatabaseManager): Instância do gerenciador de banco
        """
        self.db = db_manager
    
    def is_email_processed(self, email_id):

        """

        Verifica se um email já foi processado

        Args:
            email_id (str): ID único do email no GMAIL

        Returns:
            bool: Truese o email já foi processado. False caso contrário
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM emails_processados WHERE id_email = ?", (email_id,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def mark_email_processed(self, email_id, remetente, assunto):

        """

        Marca o email como processado no banco de dados

        Args: 
            email_id (str): ID único do email
            remetente (str): Email do remetente
            assunto (str): Assunto do email
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO emails_processados (id_email, data_processamento, remetente, assunto) VALUES (?, ?, ?, ?)",
            (email_id, datetime.now().isoformat(), remetente, assunto)
        )
        conn.commit()
        conn.close()

# ==============================
# DETECÇÃO DE INTENÇÕES
# ==============================
class IntentionDetector:

    """

    Detecta as intenções nos emails usando análisando as keywords

    Idnetifica automaticamente o que o cliente precisa baseado em palavras-chave
    no assunto e corpo do email
    """
    def __init__(self):

        # Inicializa o detector com palavras-chave pré-definidas
        self.keywords = {
            'pedido': ['orçamento', 'pedido', 'comprar', 'cotação', 'preço', 'valor', 'quantidade'],
            'duvida': ['dúvida', 'duvida', 'pergunta', 'como funciona', 'informação'],
            'reclamacao': ['reclamação', 'reclamacao', 'problema', 'erro', 'defeito', 'quebrado', 'troc'],
            'negociacao': ['proposta', 'negociar', 'desconto', 'melhor preço', 'condições']
        }
    
    def detect_intentions(self, corpo_email, assunto):

        """

        Analisa o email e detecta intenções presentes

        Args: 
            corpo_email (str): Corpo do email
            assunto (str): Assunto do email

        Returns:
            list: Lista do dicionŕio com intenções detectadas e a confiança
        """
        texto = f"{assunto} {corpo_email}".lower()
        intentions = []
        
        for intent_name, words in self.keywords.items():
            score = sum(1 for word in words if word in texto)
            if score > 0:
                intentions.append({
                    'intencao': intent_name,
                    'score': score,
                    'confianca': min(score / 3.0, 1.0)
                })
        
        # Fallback para emails sem intenções claras
        return intentions if intentions else [{'intencao': 'geral', 'score': 1, 'confianca': 0.5}]

# ==============================
# AGENTE PRINCIPAL DE EMAIL COM RAG
# ==============================
class EmailAgent:

    """

    Agente principal que orquestra todo o processo de resposta a emails

    Coordena a autenticação, detecção de intenções, geração de respostas 
    e o envio de emails

    """
    def __init__(self, db_manager, state_manager, intention_detector, rag_manager):
        
        """

        Inicializa o agente de emails com todas as depedências

        Args:
            db_manager (DatabaseManager): Gerenciador de banco
            state_manager (StateManager): Gerenciador de estado
            intention_detector (IntentionDetector): Detector de intenções
            rag_manager (RAGManager): Gerenciador RAG

        """
        self.db = db_manager
        self.state = state_manager
        self.detector = intention_detector
        self.rag = rag_manager
        self.service = self.authenticate_gmail()
        self.last_sent = {}
    
    def authenticate_gmail(self):

        """

        Autenticação da API do GMAIL

        Returns:
            googleapiclient.discovery.Resource: Serviço Gmail autenticado
        
        """
        creds = None
        
        # Tenta carregar o token existente
        if config.TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), config.SCOPES)
        

        # Caso seja necessário, renova ou cria novas credenciais
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(config.CLIENT_SECRET_FILE), config.SCOPES)
                creds = flow.run_local_server(port=8080)
                with open(config.TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
        
        return build('gmail', 'v1', credentials=creds)
    
    def get_unprocessed_emails(self):

        """

        Busca emails não processados na caixa de entrada

        Return:
            list: Lista de dicionário com dados dos emails não processados
        """
        try:
            result = self.service.users().messages().list(
                userId='me', labelIds=['INBOX'], maxResults=config.MAX_EMAILS_PROCESS
            ).execute()
            
            unprocessed = []
            for msg in result.get('messages', []):
                if not self.state.is_email_processed(msg['id']):
                    email_data = self.extract_email_data(msg['id'])
                    if email_data:
                        unprocessed.append(email_data)
            
            return unprocessed
        except Exception as e:
            config.logger.error(f"❌ Erro ao buscar emails: {e}")
            return []
    
    def extract_email_data(self, message_id):

        """

        Extrai dados relevantes de um email específico

        Args:
            message_id (str): ID do email no Gmail

        Returns: 
            dict: Dicionário com remetente, assunto e corpo ou None em caso de erro        
        """
        try:
            message = self.service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()
            
            headers = message['payload']['headers']
            remetente = assunto = "desconhecido"
            
            # Extração do remetente e assunto dos headers
            for header in headers:
                if header['name'] == 'From':
                    match = re.search(r'<(.+?)>', header['value'])
                    remetente = match.group(1) if match else header['value'].split()[-1]
                elif header['name'] == 'Subject':
                    assunto = header['value'] or "Sem assunto"
            
            # Extração do corpo do email
            corpo = ""
            if 'parts' in message['payload']:
                for part in message['payload']['parts']:
                    if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                        corpo = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
            
            return {'id': message_id, 'remetente': remetente, 'assunto': assunto, 'corpo': corpo}
            
        except Exception as e:
            config.logger.error(f"❌ Erro ao extrair email: {e}")
            return None
    
    def generate_response(self, email_data, intentions):
        """

        Gera respostas usando o Ollama como LLM e contexto de RAG

        Args:
            email_data (dict): Dados do email recebido
            intentions(dict): Intenções detectadas

        Returns:
            str: Resposta gerada pelo Ollama

        """
        
        # Obtém contexto relevante baseado nas intenções
        contexto_rag = self.rag.get_relevant_context(email_data['corpo'], intentions)
        
        intencoes_str = ", ".join([i['intencao'] for i in intentions])
        
        prompt = f"""
# CONTEXTO DA EMPRESA:
{contexto_rag}

# INTENÇÕES DETECTADAS NO EMAIL:
{intencoes_str}

# EMAIL DO CLIENTE:
Assunto: {email_data['assunto']}
Mensagem: {email_data['corpo']}

# INSTRUÇÕES:
- Use APENAS as informações do CONTEXTO DA EMPRESA para responder
- Seja preciso, humano e direto
- Não invente informações que não estão no contexto
- Para pedidos, ofereça orçamento baseado nos produtos listados
- Para reclamações, siga as políticas da empresa
- Assine como "Equipe de Atendimento"

RESPOSTA:
"""
        
        try:
            resposta = chat(
                model="llama3",
                messages=[{"role": "user", "content": prompt}],
                options={'timeout': 45}
            )
            return resposta["message"]["content"]
        except Exception as e:
            config.logger.error(f"❌ Erro ao gerar resposta: {e}")
            return "Obrigado pelo seu contato! Nossa equipe responderá em breve."
    
    def send_email(self, destinatario, assunto, mensagem):

        """

        Enviar email com controle de rate limit

        Args:
            destinatario (str): Email do destinatário
            assunto (str): Assunto do email
            mensagem (str): Corpo da mensagem

        Returns: 
            bool: True se email foi enviado, False caso contrário
        """
        now = datetime.now()

        # Verifica rate limit
        if destinatario in self.last_sent and (now - self.last_sent[destinatario]) < config.COOLDOWN:
            config.logger.warning(f"⏳ Rate limit: {destinatario}")
            return False
        
        try:
            mime_message = MIMEText(mensagem, 'plain', 'utf-8')
            mime_message['to'] = destinatario
            mime_message['subject'] = f"Re: {assunto}"
            raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
            
            self.service.users().messages().send(userId='me', body={'raw': raw}).execute()
            self.last_sent[destinatario] = now
            return True
        except Exception as e:
            config.logger.error(f"❌ Erro no envio: {e}")
            return False
    
    def process_emails(self):

        """

        Processa todos os emails não processados

        Return:
            int: Número de emails processados com sucesso
        """
        emails = self.get_unprocessed_emails()
        
        if not emails:
            config.logger.info("⏳ Nenhum email novo")
            return 0
        
        config.logger.info(f"📨 {len(emails)} email(s) para processar")
        processed = 0
        
        for email in emails:

            # Detecta intenções e gera resposta
            intentions = self.detector.detect_intentions(email['corpo'], email['assunto'])
            config.logger.info(f"🎯 Intenções: {[i['intencao'] for i in intentions]}")
            
            resposta = self.generate_response(email, intentions)
            
            # Envia a resposta e marca como processado
            if self.send_email(email['remetente'], email['assunto'], resposta):
                self.state.mark_email_processed(email['id'], email['remetente'], email['assunto'])
                processed += 1
                config.logger.info(f"✅ Respondido: {email['remetente']}")
        
        return processed
    
    def run(self):

        """

        Loop principal de exucução do agente

        Executa as verificações periódicas até ser interrompido
        """
        config.logger.info("🚀 Email Agent com RAG iniciado")
        config.logger.info(f"⏰ Verificando a cada {config.CHECK_INTERVAL/60} minutos")
        
        ciclo = 0
        while True:
            ciclo += 1
            config.logger.info(f"\n🔄 Ciclo #{ciclo} - {datetime.now().strftime('%H:%M:%S')}")
            
            try:
                processed = self.process_emails()
                if processed > 0:
                    config.logger.info(f"📊 {processed} email(s) processado(s) neste ciclo")
                
                config.logger.info(f"⏰ Próxima verificação em {config.CHECK_INTERVAL/60} minutos...")
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                config.logger.info("👋 Encerrado pelo usuário")
                break
            except Exception as e:
                config.logger.error(f"❌ Erro no ciclo: {e}")
                time.sleep(60)

# ==============================
# EXECUÇÃO PRINCIPAL
# ==============================
def main():

    """

    Função principal de inicialização do sistema

    Orquestra a criação de todos os componentes e inicia o loop principal
    """
    config.logger.info("=" * 50)
    config.logger.info("EMAIL AGENT MARKET - MVP COM RAG")
    config.logger.info("=" * 50)
    
    if not config.validate_environment():
        return
    
    # Inicializando componentes
    db = DatabaseManager(config.DB_CLIENTES)
    state = StateManager(db)
    detector = IntentionDetector()
    rag = RAGManager()
    
    # Cria e executa agente
    agent = EmailAgent(db, state, detector, rag)
    agent.run()

if __name__ == "__main__":

    """

    Ponto de entrada do sistema

    Garante que o sistema seja executado apenas quando o script é diretamente chamado,
    não quando importado
    """
    main()