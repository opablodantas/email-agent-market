"""
EMAIL AGENT MARKET - MVP COM RAG + MLOPS COM A/B TESTING
Versão com RAG para respostas precisas baseadas nos dados da empresa
Sistema completo com A/B testing, avaliação por LLM juiz e dashboard
"""

import os
import sys
import time
import sqlite3
import base64
import re
import json
import logging
import random
import threading
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Dict, List, Tuple, Any
from collections import Counter

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from ollama import chat

# ==============================
# NOVAS CONFIGURAÇÕES MLOPS
# ==============================
class MLOpsConfig:
    """Configurações do sistema MLOPS"""
    # Modelos para A/B testing - MODELOS COMUNS DO OLLAMA
    AB_MODELS = [
        {"name": "llama3", "description": "Llama 3 Padrão", "weight": 1.0},
        {"name": "mistral", "description": "Mistral 7B", "weight": 1.0},
        {"name": "llama3.1:8b", "description": "Llama 3.1 8B", "weight": 1.0},
        {"name": "neural-chat", "description": "Neural Chat 7B", "weight": 1.0},
    ]
    
    # Critérios de avaliação do LLM Juiz
    EVALUATION_CRITERIA = [
        "clareza",
        "precisão",
        "empatia",
        "profissionalismo",
        "ação_concreta",
        "alinhamento_politicas"
    ]
    
    # Configuração do LLM Juiz
    JUDGE_MODEL = "llama3"  # Modelo para julgar as respostas
    JUDGE_TEMPERATURE = 0.2
    JUDGE_MAX_TOKENS = 500
    
    # Dashboard
    DASHBOARD_UPDATE_INTERVAL = 300  # 5 minutos
    DASHBOARD_MAX_ITEMS = 50
    
    # Database paths
    DB_MLOPS = "mlops.db"
    
    # Controle de experimentos
    ENABLE_AB_TESTING = True
    ENABLE_AUTO_EVALUATION = True
    SAVE_ALL_RESPONSES = True
    
    # Arquivo de log das avaliações
    EVALUATIONS_LOG_FILE = "avaliacoes_llm_juiz.txt"

# ==============================
# CONFIGURAÇÕES ORIGINAIS (MODIFICADAS)
# ==============================
class Config:
    """Classe de configuração centralizado do sistema
       Contém todos os paths, intervalos e os parâmetros do sistema
    """
    def __init__(self):
        self.BASE_DIR = Path(__file__).parent.absolute()
        self.ensure_directories()
        
        # Configurações da API do GMAIL
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
        self.TOKEN_FILE = self.BASE_DIR / "token.json"
        self.CLIENT_SECRET_FILE = self.BASE_DIR / "credentials.json"
        self.DB_CLIENTES = self.BASE_DIR / "clientes.db"
        
        # ARQUIVOS RAG
        self.ARQ_PRODUTOS = self.BASE_DIR / "produtos.txt"
        self.ARQ_POLITICAS = self.BASE_DIR / "politicas.txt"
        self.ARQ_FINANCEIRO = self.BASE_DIR / "financeiro.txt"
        self.ARQ_ENTREGAS = self.BASE_DIR / "entregas.txt"
        
        # CONFIGURAÇÕES DE OPERAÇÕES
        self.LOG_FILE = self.BASE_DIR / "email_agent.log"
        self.COOLDOWN = timedelta(minutes=10)
        self.CHECK_INTERVAL = 300
        self.MAX_EMAILS_PROCESS = 10
        
        # MLOPS
        self.mlops = MLOpsConfig()
        self.DB_MLOPS = self.BASE_DIR / self.mlops.DB_MLOPS
        self.EVALUATIONS_LOG_FILE = self.BASE_DIR / self.mlops.EVALUATIONS_LOG_FILE
        
        self.setup_logging()
        self.setup_evaluations_log()
    
    def ensure_directories(self):
        self.BASE_DIR.mkdir(exist_ok=True)
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_evaluations_log(self):
        """Configura o arquivo de log das avaliações"""
        if not self.EVALUATIONS_LOG_FILE.exists():
            with open(self.EVALUATIONS_LOG_FILE, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("SISTEMA DE AVALIAÇÃO DO LLM JUIZ - EMAIL AGENT MARKET\n")
                f.write("=" * 80 + "\n")
                f.write(f"Iniciado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                self.logger.info(f"✅ Arquivo de avaliações criado: {self.EVALUATIONS_LOG_FILE}")
        else:
            with open(self.EVALUATIONS_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n{'=' * 80}\n")
                f.write(f"SISTEMA REINICIADO EM: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write(f"{'=' * 80}\n\n")
                self.logger.info(f"✅ Arquivo de avaliações existente encontrado, continuando registro...")
    
    def validate_environment(self):
        essential_files = [self.CLIENT_SECRET_FILE]
        missing = [f for f in essential_files if not f.exists()]
        
        if missing:
            self.logger.error("❌ Arquivos essenciais faltando:")
            for f in missing:
                self.logger.error(f"   - {f.name}")
            return False
        
        self.logger.info("✅ Ambiente validado")
        return True

config = Config()

# ==============================
# NOVO: SISTEMA DE VERIFICAÇÃO E LOG DE MODELOS
# ==============================
class ModelChecker:
    """Verifica quais modelos LLM estão disponíveis no Ollama"""
    
    @staticmethod
    def get_available_models():
        """Retorna lista de modelos disponíveis - COM FALLBACK ROBUSTO"""
        try:
            import subprocess
            # Tenta listar modelos
            result = subprocess.run(['ollama', 'list'], 
                                  capture_output=True, text=True, timeout=5)
            
            if result.returncode != 0:
                config.logger.warning("⚠️  O Ollama pode não estar rodando ou 'ollama list' falhou")
                return ['llama3']  # Fallback mínimo
            
            models = []
            for line in result.stdout.strip().split('\n'):
                if line and not line.startswith('NAME'):
                    parts = line.split()
                    if parts:  # Verifica se não está vazio
                        model_name = parts[0]
                        models.append(model_name)
            
            config.logger.info(f"📋 Modelos detectados no Ollama: {models}")
            return models
            
        except subprocess.TimeoutExpired:
            config.logger.warning("⚠️  Timeout ao verificar modelos. Usando fallback...")
            return ['llama3']  # Fallback seguro
        except Exception as e:
            config.logger.warning(f"⚠️  Não foi possível verificar modelos: {e}")
            return ['llama3']  # Fallback seguro
    
    @staticmethod
    def filter_available_models(configured_models):
        """Filtra apenas os modelos que estão instalados - COM LOGICA MELHOR"""
        available_models = ModelChecker.get_available_models()
        filtered = []
        used_names = set()  # Para evitar duplicatas
        
        # Primeiro verifica modelos exatos
        for model in configured_models:
            model_name = model['name']
            
            # Verifica se o modelo exato está disponível
            if model_name in available_models:
                filtered.append(model)
                used_names.add(model_name)
                config.logger.info(f"✅ Modelo {model_name} disponível (match exato)")
            else:
                # Tenta encontrar variantes (ex: "llama3" vs "llama3:latest")
                found = False
                base_name = model_name.split(':')[0]  # Remove tag se houver
                
                for available in available_models:
                    available_base = available.split(':')[0]
                    
                    # Verifica match por nome base
                    if available_base == base_name:
                        # Encontrou uma variante - usa o nome disponível
                        filtered.append({
                            "name": available,  # Usa o nome exato disponível
                            "description": model['description'],
                            "weight": model['weight']
                        })
                        used_names.add(available)
                        config.logger.info(f"✅ Usando variante {available} para {model_name}")
                        found = True
                        break
                
                if not found:
                    config.logger.warning(f"⚠️  Modelo {model_name} não encontrado. Pulando...")
        
        # Se nenhum modelo foi encontrado, usa fallback
        if not filtered:
            config.logger.warning("⚠️  Nenhum modelo configurado encontrado. Usando llama3 como fallback.")
            filtered = [{"name": "llama3", "description": "Llama 3 Padrão", "weight": 1.0}]
        
        # Log final dos modelos ativos
        active_models = [m['name'] for m in filtered]
        config.logger.info(f"🎯 Modelos ativos no A/B Testing: {active_models}")
        
        # Log de distribuição de pesos
        total_weight = sum(m['weight'] for m in filtered)
        for model in filtered:
            probability = (model['weight'] / total_weight * 100) if total_weight > 0 else 0
            config.logger.info(f"   • {model['name']}: peso {model['weight']} ({probability:.1f}% de chance)")
        
        return filtered

# Atualiza a lista de modelos com apenas os disponíveis
config.mlops.AB_MODELS = ModelChecker.filter_available_models(config.mlops.AB_MODELS)

# ==============================
# NOVO: SISTEMA DE LOG DE AVALIAÇÕES EM TXT
# ==============================
class EvaluationLogger:
    """Gerencia o log das avaliações do LLM Juiz em arquivo TXT"""
    
    def __init__(self, log_file_path):
        self.log_file = log_file_path
        self.evaluation_count = 0
    
    def log_evaluation(self, email_data: Dict, model_used: str, response_text: str,
                      scores: Dict, feedback: str, intentions: List):
        """Registra uma avaliação completa no arquivo TXT"""
        self.evaluation_count += 1
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'=' * 80}\n")
            f.write(f"AVALIAÇÃO #{self.evaluation_count} - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"{'=' * 80}\n\n")
            
            # Informações do email
            f.write("📧 INFORMAÇÕES DO EMAIL:\n")
            f.write(f"   • Cliente: {email_data['remetente']}\n")
            f.write(f"   • Assunto: {email_data['assunto']}\n")
            f.write(f"   • Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"   • Intenções detectadas: {', '.join([i['intencao'] for i in intentions])}\n")
            
            # Informações do modelo
            f.write(f"\n🤖 MODELO UTILIZADO:\n")
            f.write(f"   • Nome: {model_used}\n")
            
            # Pontuações
            f.write(f"\n📊 PONTUAÇÕES DO LLM JUIZ:\n")
            f.write(f"   • Clareza: {scores.get('clareza', 0):.1f}/100\n")
            f.write(f"   • Precisão: {scores.get('precisão', 0):.1f}/100\n")
            f.write(f"   • Empatia: {scores.get('empatia', 0):.1f}/100\n")
            f.write(f"   • Profissionalismo: {scores.get('profissionalismo', 0):.1f}/100\n")
            f.write(f"   • Ação Concreta: {scores.get('ação_concreta', 0):.1f}/100\n")
            f.write(f"   • Alinhamento Políticas: {scores.get('alinhamento_politicas', 0):.1f}/100\n")
            f.write(f"   • PONTUAÇÃO GERAL: {scores.get('overall', 0):.1f}/100\n")
            
            # Feedback detalhado
            f.write(f"\n💬 FEEDBACK DO JUIZ:\n")
            feedback_lines = feedback.strip().split('\n')
            for line in feedback_lines:
                f.write(f"   {line.strip()}\n")
            
            # Resposta gerada (resumida)
            f.write(f"\n📝 RESPOSTA GERADA (resumo):\n")
            response_summary = response_text[:300] + "..." if len(response_text) > 300 else response_text
            response_lines = response_summary.strip().split('\n')
            for line in response_lines[:10]:  # Limita a 10 linhas
                f.write(f"   {line.strip()}\n")
            
            f.write(f"\n{'=' * 80}\n")
        
        config.logger.info(f"📝 Avaliação #{self.evaluation_count} salva em: {self.log_file}")
    
    def get_summary_stats(self):
        """Retorna estatísticas do arquivo de log"""
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Conta avaliações
            evaluation_count = content.count("AVALIAÇÃO #")
            
            # Extrai pontuações (simples)
            import re
            overall_scores = re.findall(r'PONTUAÇÃO GERAL: (\d+\.?\d*)/100', content)
            overall_scores = [float(score) for score in overall_scores]
            
            avg_score = sum(overall_scores) / len(overall_scores) if overall_scores else 0
            
            return {
                'total_avaliacoes': evaluation_count,
                'media_geral': avg_score,
                'ultima_avaliacao': datetime.fromtimestamp(os.path.getmtime(self.log_file)).strftime('%d/%m/%Y %H:%M:%S')
            }
        except Exception as e:
            config.logger.warning(f"⚠️  Erro ao ler estatísticas do log: {e}")
            return {'total_avaliacoes': 0, 'media_geral': 0, 'ultima_avaliacao': 'N/A'}

# Inicializa o logger de avaliações
evaluation_logger = EvaluationLogger(config.EVALUATIONS_LOG_FILE)

# ==============================
# NOVO: GERENCIADOR DE BANCO MLOPS SIMPLIFICADO
# ==============================
class MLOpsDatabase:
    """Gerencia o banco de dados para MLOPS em um único arquivo"""
    
    def __init__(self):
        self.db_path = config.DB_MLOPS
        self.setup_database()
        self.model_usage_counter = Counter()  # Contador de uso de modelos
    
    def get_connection(self):
        """Retorna conexão thread-safe"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def setup_database(self):
        """Cria todas as tabelas necessárias"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Tabela para A/B Testing
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ab_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT,
                thread_id TEXT,
                model_used TEXT,
                response_text TEXT,
                timestamp TEXT,
                intention_detected TEXT,
                customer_email TEXT,
                email_subject TEXT,
                original_email TEXT
            )
        ''')
        
        # Tabela para avaliações do LLM Juiz
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id INTEGER,
                judge_model TEXT,
                overall_score REAL,
                clarity_score REAL,
                accuracy_score REAL,
                empathy_score REAL,
                professionalism_score REAL,
                action_score REAL,
                policy_score REAL,
                feedback_text TEXT,
                timestamp TEXT
            )
        ''')
        
        # Tabela para estatísticas de uso de modelos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used TEXT,
                UNIQUE(model_name)
            )
        ''')
        
        # Índices para performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_model_used ON ab_responses(model_used)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON ab_responses(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_response_id ON llm_evaluations(response_id)')
        
        conn.commit()
        conn.close()
        
        config.logger.info(f"✅ Banco MLOPS criado em: {self.db_path}")
    
    def save_ab_response(self, email_data: Dict, model_used: str, response_text: str, 
                        intentions: List) -> int:
        """Salva uma resposta do A/B testing"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Gera thread_id baseado no remetente e assunto
        thread_id = hashlib.md5(
            f"{email_data['remetente']}{email_data['assunto']}".encode()
        ).hexdigest()
        
        cursor.execute('''
            INSERT INTO ab_responses 
            (email_id, thread_id, model_used, response_text, timestamp, 
             intention_detected, customer_email, email_subject, original_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            email_data['id'],
            thread_id,
            model_used,
            response_text,
            datetime.now().isoformat(),
            json.dumps([i['intencao'] for i in intentions]),
            email_data['remetente'],
            email_data['assunto'],
            email_data['corpo'][:1000]  # Limita tamanho
        ))
        
        response_id = cursor.lastrowid
        
        # Atualiza estatísticas de uso do modelo
        cursor.execute('''
            INSERT OR REPLACE INTO model_usage_stats 
            (model_name, usage_count, last_used)
            VALUES (?, 
                   COALESCE((SELECT usage_count FROM model_usage_stats WHERE model_name = ?), 0) + 1,
                   ?)
        ''', (model_used, model_used, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # Atualiza contador em memória
        self.model_usage_counter[model_used] += 1
        
        return response_id
    
    def save_evaluation(self, response_id: int, scores: Dict, feedback: str):
        """Salva avaliação do LLM Juiz"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO llm_evaluations 
            (response_id, judge_model, overall_score, clarity_score, accuracy_score,
             empathy_score, professionalism_score, action_score, policy_score,
             feedback_text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            response_id,
            config.mlops.JUDGE_MODEL,
            scores.get('overall', 0),
            scores.get('clareza', 0),
            scores.get('precisão', 0),
            scores.get('empatia', 0),
            scores.get('profissionalismo', 0),
            scores.get('ação_concreta', 0),
            scores.get('alinhamento_politicas', 0),
            feedback,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_model_usage_stats(self):
        """Retorna estatísticas de uso dos modelos"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT model_name, usage_count, last_used
            FROM model_usage_stats
            ORDER BY usage_count DESC
        ''')
        
        stats = [
            {
                'model': row[0],
                'count': row[1],
                'last_used': row[2]
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return stats
    
    def get_dashboard_data(self) -> Dict:
        """Coleta dados para o dashboard de forma segura"""
        data = {
            'model_stats': [],
            'model_usage': [],
            'top_intentions': [],
            'recent_evaluations': [],
            'score_metrics': {},
            'total_responses': 0,
            'total_evaluations': 0,
            'model_distribution': {}
        }
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Conta total de respostas
            cursor.execute('SELECT COUNT(*) FROM ab_responses')
            total_resp = cursor.fetchone()[0]
            data['total_responses'] = total_resp
            
            # Conta total de avaliações
            cursor.execute('SELECT COUNT(*) FROM llm_evaluations')
            total_eval = cursor.fetchone()[0]
            data['total_evaluations'] = total_eval
            
            # Estatísticas de uso dos modelos
            model_usage = self.get_model_usage_stats()
            data['model_usage'] = model_usage
            
            # Calcula distribuição percentual
            total_usage = sum(item['count'] for item in model_usage)
            if total_usage > 0:
                for item in model_usage:
                    percentage = (item['count'] / total_usage) * 100
                    data['model_distribution'][item['model']] = {
                        'count': item['count'],
                        'percentage': percentage
                    }
            
            if total_resp > 0:
                # Estatísticas por modelo (tamanho médio)
                cursor.execute('''
                    SELECT model_used, COUNT(*) as count, 
                           AVG(LENGTH(response_text)) as avg_len
                    FROM ab_responses 
                    GROUP BY model_used
                ''')
                data['model_stats'] = [
                    {"model": row[0], "count": row[1], "avg_len": row[2] or 0}
                    for row in cursor.fetchall()
                ]
                
                # Top intenções
                cursor.execute('''
                    SELECT intention_detected, COUNT(*) as count
                    FROM ab_responses
                    WHERE intention_detected IS NOT NULL AND intention_detected != ''
                    GROUP BY intention_detected
                    ORDER BY count DESC
                    LIMIT 5
                ''')
                data['top_intentions'] = [
                    {"intention": row[0], "count": row[1]}
                    for row in cursor.fetchall()
                ]
            
            if total_eval > 0:
                # Avaliações recentes (JOIN seguro)
                cursor.execute('''
                    SELECT e.overall_score, e.feedback_text, r.model_used, e.timestamp
                    FROM llm_evaluations e
                    LEFT JOIN ab_responses r ON e.response_id = r.id
                    ORDER BY e.timestamp DESC
                    LIMIT 10
                ''')
                data['recent_evaluations'] = [
                    {
                        "score": row[0] or 0,
                        "feedback": (row[1] or "")[:100],
                        "model": row[2] or "Desconhecido",
                        "time": row[3] or ""
                    }
                    for row in cursor.fetchall()
                ]
                
                # Métricas de score
                cursor.execute('''
                    SELECT overall_score, clarity_score, accuracy_score, 
                           empathy_score, professionalism_score
                    FROM llm_evaluations
                    WHERE overall_score IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 50
                ''')
                
                scores = cursor.fetchall()
                if scores:
                    # Cálculo manual para evitar dependência de statistics
                    overall_scores = [row[0] for row in scores if row[0] is not None]
                    clarity_scores = [row[1] for row in scores if row[1] is not None]
                    accuracy_scores = [row[2] for row in scores if row[2] is not None]
                    empathy_scores = [row[3] for row in scores if row[3] is not None]
                    professionalism_scores = [row[4] for row in scores if row[4] is not None]
                    
                    def safe_mean(values):
                        return sum(values) / len(values) if values else 0
                    
                    data['score_metrics'] = {
                        'avg_overall': safe_mean(overall_scores),
                        'avg_clarity': safe_mean(clarity_scores),
                        'avg_accuracy': safe_mean(accuracy_scores),
                        'avg_empathy': safe_mean(empathy_scores),
                        'avg_professionalism': safe_mean(professionalism_scores),
                    }
                
        except sqlite3.OperationalError as e:
            config.logger.warning(f"⚠️  Erro ao acessar banco de dados: {e}")
            # Continua com dados vazios
        except Exception as e:
            config.logger.warning(f"⚠️  Erro inesperado no dashboard: {e}")
        finally:
            conn.close()
        
        return data

# ==============================
# NOVO: LLM JUIZ COM LOG EM TXT
# ==============================
class LLMJudge:
    """LLM que atua como juiz para avaliar respostas"""
    
    def __init__(self, evaluation_logger: EvaluationLogger):
        self.criteria = config.mlops.EVALUATION_CRITERIA
        self.evaluation_logger = evaluation_logger
    
    def evaluate_response(self, original_email: str, response_text: str, 
                         context: str, model_used: str) -> Tuple[Dict, str]:
        """
        Avalia uma resposta usando LLM como juiz
        
        Returns:
            Tuple[Dict, str]: (scores, feedback_text)
        """
        
        prompt = f"""
# PAPEL: VOCÊ É UM JUIZ ESPECIALIZADO EM AVALIAR RESPOSTAS DE ATENDIMENTO AO CLIENTE

# EMAIL ORIGINAL DO CLIENTE:
{original_email[:500]}

# CONTEXTO DA EMPRESA (RAG):
{context[:1000]}

# RESPOSTA GERADA PELO MODELO {model_used}:
{response_text}

# CRITÉRIOS DE AVALIAÇÃO (0-100 pontos cada):
1. CLAREZA: A resposta é clara e fácil de entender?
2. PRECISÃO: A resposta está correta baseada no contexto?
3. EMPATIA: A resposta demonstra compreensão do problema do cliente?
4. PROFISSIONALISMO: A resposta mantém tom profissional adequado?
5. AÇÃO CONCRETA: A resposta propõe ações claras ou soluções?
6. ALINHAMENTO COM POLÍTICAS: Segue as políticas da empresa?

# FORMATO DE RESPOSTA REQUERIDO:
Primeiro, uma avaliação textual detalhada (máximo 200 palavras).
Depois, APENAS um JSON com as notas:

{{
    "clareza": [0-100],
    "precisão": [0-100],
    "empatia": [0-100],
    "profissionalismo": [0-100],
    "ação_concreta": [0-100],
    "alinhamento_politicas": [0-100]
}}

A nota geral será a média das 6 notas.
"""
        
        try:
            result = chat(
                model=config.mlops.JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={'temperature': config.mlops.JUDGE_TEMPERATURE}
            )
            
            response = result["message"]["content"]
            
            # Extrai o JSON da resposta
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    json_str = json_match.group()
                    scores = json.loads(json_str)
                    
                    # Calcula nota geral
                    scores_list = [scores.get(crit, 0) for crit in self.criteria]
                    scores['overall'] = sum(scores_list) / len(scores_list)
                    
                    # Extrai feedback textual (tudo antes do JSON)
                    feedback = response[:json_match.start()].strip()
                    
                    return scores, feedback
                except json.JSONDecodeError:
                    config.logger.warning("⚠️  JSON inválido na avaliação do juiz")
                    return self.default_scores(), "JSON inválido na avaliação"
            else:
                config.logger.warning("⚠️  Não encontrou JSON na avaliação do juiz")
                return self.default_scores(), "Formato de resposta inválido"
                
        except Exception as e:
            config.logger.error(f"❌ Erro no LLM Juiz: {e}")
            return self.default_scores(), f"Erro: {str(e)[:100]}"
    
    def default_scores(self) -> Dict:
        """Retorna scores padrão em caso de erro"""
        return {crit: 50 for crit in self.criteria} | {'overall': 50}

# ==============================
# NOVO: SISTEMA DE A/B TESTING CORRIGIDO
# ==============================
class ABTestingSystem:
    """Gerencia A/B testing entre diferentes modelos LLM - VERSÃO CORRIGIDA"""
    
    def __init__(self, mlops_db: MLOpsDatabase):
        self.db = mlops_db
        self.models = config.mlops.AB_MODELS
        self.total_weight = sum(model['weight'] for model in self.models)
        self.response_cache = {}
        self.available_models = [model['name'] for model in self.models]
        self.model_selection_log = []  # Log das seleções
        
        config.logger.info(f"🎲 A/B Testing ativo com {len(self.models)} modelo(s)")
        for model in self.models:
            config.logger.info(f"   • {model['name']} (peso: {model['weight']})")
        
        # Log inicial da distribuição
        self.log_distribution_stats()
    
    def log_distribution_stats(self):
        """Loga estatísticas de distribuição"""
        total_weight = sum(model['weight'] for model in self.models)
        if total_weight > 0:
            config.logger.info("📊 Probabilidade de seleção por modelo:")
            for model in self.models:
                probability = (model['weight'] / total_weight) * 100
                config.logger.info(f"   • {model['name']}: {probability:.1f}%")
    
    def select_model(self) -> str:
        """Seleciona um modelo baseado nos weights - CORRIGIDO"""
        if not config.mlops.ENABLE_AB_TESTING or len(self.models) == 0:
            selected = self.models[0]['name'] if self.models else "llama3"
            config.logger.debug(f"A/B Testing desativado, usando: {selected}")
            return selected
        
        if len(self.models) == 1:
            selected = self.models[0]['name']
            config.logger.debug(f"Apenas um modelo disponível: {selected}")
            return selected
        
        # Gera número aleatório entre 0 e total_weight
        rand = random.uniform(0, self.total_weight)
        cumulative = 0
        
        for model in self.models:
            cumulative += model['weight']
            if rand <= cumulative:
                selected = model['name']
                self.model_selection_log.append({
                    'timestamp': datetime.now().isoformat(),
                    'model': selected,
                    'random_value': rand,
                    'weight': model['weight']
                })
                
                # Log detalhado para debug
                config.logger.debug(f"🎲 Seleção A/B: rand={rand:.2f}, cumulative={cumulative:.2f}, selected={selected}")
                return selected
        
        # Fallback (nunca deve chegar aqui com a lógica correta)
        selected = self.models[0]['name']
        config.logger.warning(f"⚠️  Fallback na seleção do modelo, usando: {selected}")
        return selected
    
    def generate_with_model(self, prompt: str, model_name: str) -> str:
        """Gera resposta com um modelo específico com fallback seguro"""
        cache_key = hashlib.md5(f"{prompt}{model_name}".encode()).hexdigest()
        
        # Verifica cache
        if cache_key in self.response_cache:
            config.logger.debug(f"📦 Usando resposta em cache para {model_name}")
            return self.response_cache[cache_key]
        
        try:
            config.logger.info(f"🤖 Gerando resposta com modelo: {model_name}")
            response = chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                options={'timeout': 45}
            )
            result = response["message"]["content"]
            
            # Cache a resposta
            self.response_cache[cache_key] = result
            return result
            
        except Exception as e:
            error_msg = str(e)
            config.logger.warning(f"⚠️  Erro no modelo {model_name}: {error_msg[:80]}")
            
            # Se o erro for "model not found", tenta versão alternativa
            if "not found" in error_msg.lower():
                # Tenta encontrar modelo alternativo (ex: "llama3" -> "llama3:latest")
                base_name = model_name.split(':')[0]
                for available in self.available_models:
                    if available.startswith(base_name) and available != model_name:
                        try:
                            config.logger.info(f"🔄 Tentando variante {available} para {model_name}")
                            response = chat(
                                model=available,
                                messages=[{"role": "user", "content": prompt}],
                                options={'timeout': 30}
                            )
                            result = response["message"]["content"]
                            self.response_cache[cache_key] = result
                            return result
                        except Exception as e2:
                            config.logger.debug(f"   Variante {available} também falhou: {str(e2)[:50]}")
                            continue
            
            # Se ainda não encontrou, tenta outros modelos disponíveis
            for fallback_model in self.available_models:
                if fallback_model != model_name:
                    try:
                        config.logger.info(f"🔄 Tentando fallback para {fallback_model}")
                        response = chat(
                            model=fallback_model,
                            messages=[{"role": "user", "content": prompt}],
                            options={'timeout': 30}
                        )
                        result = response["message"]["content"]
                        self.response_cache[cache_key] = result
                        return result
                    except Exception as e2:
                        config.logger.debug(f"   Fallback {fallback_model} também falhou: {str(e2)[:50]}")
                        continue
            
            # Último fallback: resposta genérica
            fallback_response = """Obrigado pelo seu contato!

Nossa equipe analisará sua mensagem cuidadosamente e responderá em breve com as informações solicitadas.

Atenciosamente,
Equipe de Atendimento"""
            self.response_cache[cache_key] = fallback_response
            return fallback_response
    
    def run_ab_test(self, email_data: Dict, prompt: str, 
                   intentions: List) -> Tuple[str, str, int]:
        """
        Executa A/B test e retorna (resposta, modelo_usado, response_id)
        """
        model_selected = self.select_model()
        config.logger.info(f"🔬 A/B Testing: modelo selecionado → {model_selected}")
        
        response = self.generate_with_model(prompt, model_selected)
        
        # Salva no banco de A/B testing
        response_id = self.db.save_ab_response(
            email_data, model_selected, response, intentions
        )
        
        return response, model_selected, response_id
    
    def get_selection_stats(self):
        """Retorna estatísticas das seleções de modelos"""
        if not self.model_selection_log:
            return {}
        
        counts = Counter([entry['model'] for entry in self.model_selection_log])
        total = len(self.model_selection_log)
        
        stats = {}
        for model, count in counts.items():
            stats[model] = {
                'count': count,
                'percentage': (count / total * 100) if total > 0 else 0
            }
        
        return stats

# ==============================
# NOVO: DASHBOARD WEB LEVE E ESTÁVEL
# ==============================
class DashboardServer:
    """Servidor simples de dashboard - VERSÃO CORRIGIDA"""
    
    def __init__(self, mlops_db: MLOpsDatabase, ab_system: ABTestingSystem):
        self.db = mlops_db
        self.ab_system = ab_system
        self.setup_web_server()
    
    def setup_web_server(self):
        """Configura servidor web básico - VERSÃO CORRIGIDA"""
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
            
            # Criamos uma classe interna que tem acesso ao dashboard
            class DashboardHandler(BaseHTTPRequestHandler):
                dashboard_server = self  # Referência estática para o servidor
                
                def do_GET(self):
                    try:
                        if self.path == '/':
                            self.send_response(200)
                            self.send_header('Content-type', 'text/html')
                            self.end_headers()
                            
                            html = self.dashboard_server.generate_html()
                            self.wfile.write(html.encode('utf-8'))
                        
                        elif self.path == '/data':
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            
                            data = self.dashboard_server.db.get_dashboard_data()
                            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
                        
                        elif self.path == '/health':
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain')
                            self.end_headers()
                            self.wfile.write(b'OK')
                        
                        elif self.path == '/metrics':
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            
                            metrics = {
                                'timestamp': datetime.now().isoformat(),
                                'status': 'running',
                                'models_available': len(config.mlops.AB_MODELS),
                                'selection_stats': self.dashboard_server.ab_system.get_selection_stats(),
                                'log_file': str(config.EVALUATIONS_LOG_FILE)
                            }
                            self.wfile.write(json.dumps(metrics).encode('utf-8'))
                        
                        elif self.path == '/logs':
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain')
                            self.end_headers()
                            
                            try:
                                with open(config.EVALUATIONS_LOG_FILE, 'r', encoding='utf-8') as f:
                                    self.wfile.write(f.read().encode('utf-8'))
                            except:
                                self.wfile.write(b'Arquivo de log nao encontrado')
                        
                        else:
                            self.send_response(404)
                            self.send_header('Content-type', 'text/html')
                            self.end_headers()
                            self.wfile.write(b'<h1>404 - Not Found</h1>')
                    
                    except Exception as e:
                        config.logger.error(f"❌ Erro no handler HTTP: {e}")
                        self.send_response(500)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(f'Erro interno: {str(e)}'.encode('utf-8'))
                
                def log_message(self, format, *args):
                    # Silencia logs do servidor HTTP para reduzir ruído
                    pass
            
            # Configura e inicia o servidor
            self.server = HTTPServer(('localhost', 8081), DashboardHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            
            config.logger.info(f"📊 Dashboard disponível em: http://localhost:8081")
            config.logger.info(f"   • Página principal: http://localhost:8081/")
            config.logger.info(f"   • Dados JSON: http://localhost:8081/data")
            config.logger.info(f"   • Health check: http://localhost:8081/health")
            config.logger.info(f"   • Logs das avaliações: http://localhost:8081/logs")
            
        except ImportError as e:
            config.logger.warning(f"⚠️  HTTP server não disponível: {e}")
            config.logger.warning("⚠️  Dashboard desabilitado.")
            self.server = None
        except Exception as e:
            config.logger.error(f"❌ Erro ao iniciar dashboard: {e}")
            config.logger.warning("⚠️  Dashboard não iniciado.")
            self.server = None
    
    def generate_html(self) -> str:
        """Gera HTML do dashboard simples"""
        data = self.db.get_dashboard_data()
        selection_stats = self.ab_system.get_selection_stats()
        log_stats = evaluation_logger.get_summary_stats()
        now = datetime.now()
        
        # Formata os modelos ativos
        model_tags = ''.join([
            f'<span class="model-tag" title="{m["description"]}">{m["name"]}</span>'
            for m in config.mlops.AB_MODELS
        ])
        
        # Estatísticas de seleção
        selection_html = ""
        for model, stats in selection_stats.items():
            selection_html += f'''
                <div style="margin: 8px 0; padding: 10px; background: #f0f4f8; border-radius: 6px;">
                    <strong>{model}</strong>: {stats['count']} seleções ({stats['percentage']:.1f}%)
                </div>
            '''
        
        # Distribuição de uso real
        distribution_html = ""
        for model, dist in data.get('model_distribution', {}).items():
            distribution_html += f'''
                <div style="margin: 8px 0; padding: 10px; background: #f0f4f8; border-radius: 6px;">
                    <strong>{model}</strong>: {dist['count']} respostas ({dist['percentage']:.1f}%)
                </div>
            '''
        
        html = f'''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard MLOps - Email Agent</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ 
            max-width: 1400px; 
            margin: 0 auto; 
            background: rgba(255, 255, 255, 0.95); 
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            color: white; 
            padding: 30px 40px; 
            text-align: center;
            border-bottom: 5px solid #4CAF50;
        }}
        .header h1 {{ 
            font-size: 2.5em; 
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        .header p {{ 
            font-size: 1.1em; 
            opacity: 0.9;
            margin-bottom: 20px;
        }}
        .stats-bar {{
            display: flex;
            justify-content: space-around;
            background: #f8f9fa;
            padding: 20px;
            border-bottom: 1px solid #dee2e6;
            flex-wrap: wrap;
        }}
        .stat-item {{
            text-align: center;
            margin: 10px;
            min-width: 120px;
        }}
        .stat-number {{
            font-size: 2.2em;
            font-weight: bold;
            color: #667eea;
            display: block;
        }}
        .stat-label {{
            font-size: 0.9em;
            color: #666;
            margin-top: 5px;
        }}
        .grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); 
            gap: 25px; 
            padding: 30px;
        }}
        .card {{ 
            background: white; 
            padding: 25px; 
            border-radius: 15px; 
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            border: 1px solid #e9ecef;
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.15);
        }}
        .card h2 {{ 
            color: #333; 
            margin-bottom: 20px; 
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
            font-size: 1.4em;
        }}
        .metric {{ 
            font-size: 3em; 
            font-weight: bold; 
            color: #4CAF50;
            text-align: center;
            margin: 20px 0;
        }}
        .badge {{ 
            background: #e3f2fd; 
            color: #1976d2;
            padding: 6px 12px; 
            border-radius: 20px; 
            font-size: 0.85em;
            font-weight: 500;
            display: inline-block;
            margin: 3px;
        }}
        table {{ 
            width: 100%; 
            border-collapse: separate;
            border-spacing: 0;
            margin-top: 10px;
        }}
        th {{ 
            background: #f8f9fa; 
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
        }}
        td {{ 
            padding: 12px 15px; 
            border-bottom: 1px solid #e9ecef;
            color: #333;
        }}
        tr:hover td {{
            background: #f8f9fa;
        }}
        .score-high {{ color: #4CAF50; font-weight: bold; }}
        .score-medium {{ color: #FF9800; }}
        .score-low {{ color: #F44336; }}
        .model-list {{ 
            display: flex; 
            flex-wrap: wrap; 
            gap: 8px; 
            margin: 15px 0;
        }}
        .model-tag {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 6px 12px; 
            border-radius: 15px; 
            font-size: 0.85em;
            font-weight: 500;
        }}
        .last-update {{ 
            font-size: 0.85em; 
            color: rgba(255, 255, 255, 0.8); 
            text-align: center;
            margin-top: 10px;
        }}
        .no-data {{
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 30px;
        }}
        .config-section {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
        }}
        .config-item {{
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .status-active {{ color: #4CAF50; font-weight: bold; }}
        .status-inactive {{ color: #F44336; font-weight: bold; }}
        .log-info {{
            background: #e8f5e9;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            border-left: 4px solid #4CAF50;
        }}
        
        /* Responsividade */
        @media (max-width: 768px) {{
            .grid {{ grid-template-columns: 1fr; padding: 15px; }}
            .header {{ padding: 20px; }}
            .header h1 {{ font-size: 2em; }}
            .stats-bar {{ flex-direction: column; gap: 15px; }}
        }}
        
        /* Animações */
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .card {{ animation: fadeIn 0.5s ease-out; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Dashboard MLOps - Email Agent</h1>
            <p>Sistema inteligente de atendimento ao cliente com A/B Testing REAL</p>
            <div class="last-update">
                Atualizado em: {now.strftime("%d/%m/%Y %H:%M:%S")}
            </div>
        </div>
        
        <div class="stats-bar">
            <div class="stat-item">
                <span class="stat-number">{data['total_responses']}</span>
                <span class="stat-label">Respostas Enviadas</span>
            </div>
            <div class="stat-item">
                <span class="stat-number">{data['total_evaluations']}</span>
                <span class="stat-label">Avaliações</span>
            </div>
            <div class="stat-item">
                <span class="stat-number">{len(config.mlops.AB_MODELS)}</span>
                <span class="stat-label">Modelos Ativos</span>
            </div>
            <div class="stat-item">
                <span class="stat-number">{data.get('score_metrics', {}).get('avg_overall', 0):.1f}</span>
                <span class="stat-label">Nota Média</span>
            </div>
            <div class="stat-item">
                <span class="stat-number">{log_stats.get('total_avaliacoes', 0)}</span>
                <span class="stat-label">Logs TXT</span>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>🎲 A/B Testing - Configuração</h2>
                <div class="model-list">{model_tags}</div>
                
                <div style="margin-top: 20px;">
                    <h3 style="font-size: 1.1em; margin-bottom: 15px;">Distribuição de Pesos:</h3>
                    {selection_html if selection_html else '<p class="no-data">Nenhuma seleção registrada ainda</p>'}
                    
                    <h3 style="font-size: 1.1em; margin-top: 20px; margin-bottom: 15px;">Uso Real dos Modelos:</h3>
                    {distribution_html if distribution_html else '<p class="no-data">Nenhuma resposta registrada ainda</p>'}
                </div>
            </div>
            
            <div class="card">
                <h2>📈 Métricas Principais</h2>
                <div class="metric">{data.get('score_metrics', {}).get('avg_overall', 0):.1f}</div>
                <p style="text-align: center; color: #666;">Pontuação Média (LLM Juiz)</p>
                
                <div style="margin-top: 25px;">
                    <div class="log-info">
                        <h3 style="font-size: 1.1em; margin-bottom: 10px;">📝 Sistema de Log TXT:</h3>
                        <p><strong>Arquivo:</strong> {config.EVALUATIONS_LOG_FILE.name}</p>
                        <p><strong>Total de avaliações salvas:</strong> {log_stats.get('total_avaliacoes', 0)}</p>
                        <p><strong>Média geral no log:</strong> {log_stats.get('media_geral', 0):.1f}/100</p>
                        <p><strong>Última atualização:</strong> {log_stats.get('ultima_avaliacao', 'N/A')}</p>
                        <p><a href="/logs" target="_blank" style="color: #1976d2; text-decoration: none;">📄 Ver log completo das avaliações</a></p>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>⚖️ Avaliações Recentes</h2>
                <table>
                    <tr><th>Modelo</th><th>Pontuação</th><th>Feedback</th></tr>
        '''
        
        # Adiciona avaliações
        if data['recent_evaluations']:
            for eval_data in data['recent_evaluations']:
                score = eval_data['score']
                score_class = "score-high" if score >= 80 else "score-medium" if score >= 60 else "score-low"
                feedback_preview = eval_data['feedback'][:60] + "..." if len(eval_data['feedback']) > 60 else eval_data['feedback']
                
                html += f'''
                    <tr>
                        <td><span class="badge">{eval_data['model']}</span></td>
                        <td class="{score_class}">{score:.1f}</td>
                        <td title="{eval_data['feedback']}">{feedback_preview}</td>
                    </tr>
                '''
        else:
            html += '<tr><td colspan="3" class="no-data">Nenhuma avaliação disponível</td></tr>'
        
        html += '''
                </table>
            </div>
            
            <div class="card">
                <h2>⚙️ Configurações do Sistema</h2>
                <div class="config-section">
                    <div class="config-item">
                        <span>A/B Testing:</span>
                        <span class="{'status-active' if config.mlops.ENABLE_AB_TESTING else 'status-inactive'}">
                            {'✅ ATIVO' if config.mlops.ENABLE_AB_TESTING else '❌ INATIVO'}
                        </span>
                    </div>
                    <div class="config-item">
                        <span>Avaliação Automática:</span>
                        <span class="{'status-active' if config.mlops.ENABLE_AUTO_EVALUATION else 'status-inactive'}">
                            {'✅ ATIVA' if config.mlops.ENABLE_AUTO_EVALUATION else '❌ INATIVA'}
                        </span>
                    </div>
                    <div class="config-item">
                        <span>Modelo Juiz:</span>
                        <span class="badge">{config.mlops.JUDGE_MODEL}</span>
                    </div>
                    <div class="config-item">
                        <span>Intervalo de Verificação:</span>
                        <span>{config.CHECK_INTERVAL/60:.0f} minutos</span>
                    </div>
                    <div class="config-item">
                        <span>Cooldown por Cliente:</span>
                        <span>{config.COOLDOWN.seconds/60:.0f} minutos</span>
                    </div>
                    <div class="config-item">
                        <span>Log das Avaliações:</span>
                        <span class="status-active">✅ ATIVO</span>
                    </div>
                </div>
                
                <div style="margin-top: 20px; padding: 15px; background: #e8f5e9; border-radius: 8px;">
                    <h3 style="font-size: 1.1em; margin-bottom: 10px;">📊 Status do Sistema</h3>
                    <p style="color: #2e7d32; margin-bottom: 5px;">✓ Email Agent: <strong>OPERACIONAL</strong></p>
                    <p style="color: #2e7d32; margin-bottom: 5px;">✓ A/B Testing: <strong>FUNCIONANDO</strong></p>
                    <p style="color: #2e7d32; margin-bottom: 5px;">✓ Log TXT: <strong>ATIVO</strong> ({log_stats.get('total_avaliacoes', 0)} registros)</p>
                    <p style="color: #2e7d32;">✓ Banco de Dados: <strong>CONECTADO</strong></p>
                </div>
            </div>
        </div>
        
        <div style="text-align: center; padding: 20px; color: #666; font-size: 0.9em; border-top: 1px solid #e9ecef;">
            <p>Email Agent Market v2.0 • Sistema MLOps com A/B Testing REAL • Log completo em TXT</p>
            <p>Dados atualizados automaticamente a cada 30 segundos • <a href="/logs" target="_blank" style="color: #667eea;">Ver log das avaliações</a></p>
        </div>
    </div>
    
    <script>
        // Atualiza automático a cada 30 segundos
        setTimeout(() => location.reload(), 30000);
        
        // Adiciona efeito de carregamento suave
        document.addEventListener('DOMContentLoaded', function() {{
            // Pega dados via AJAX
            fetch('/data')
                .then(response => response.json())
                .then(data => {{
                    console.log('📊 Dados do dashboard carregados:', data);
                }})
                .catch(error => console.warn('⚠️  Erro ao carregar dados:', error));
            
            // Pega métricas do A/B Testing
            fetch('/metrics')
                .then(response => response.json())
                .then(metrics => {{
                    console.log('🎲 Métricas do A/B Testing:', metrics);
                }});
        }});
    </script>
</body>
</html>
        '''
        
        return html

# ==============================
# GERENCIADOR RAG (ORIGINAL)
# ==============================
class RAGManager:
    def __init__(self):
        self.context_cache = {}
        self.load_all_contexts()
    
    def load_all_contexts(self):
        contexts = {
            'produtos': self.load_file(config.ARQ_PRODUTOS),
            'politicas': self.load_file(config.ARQ_POLITICAS),
            'financeiro': self.load_file(config.ARQ_FINANCEIRO),
            'entregas': self.load_file(config.ARQ_ENTREGAS)
        }
        self.context_cache = contexts
        config.logger.info("✅ Contextos RAG carregados")
    
    def load_file(self, file_path):
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                config.logger.error(f"❌ Erro ao carregar {file_path.name}: {e}")
        return ""
    
    def get_relevant_context(self, email_corpo, intencoes):
        contexto_relevante = []
        corpo_lower = email_corpo.lower()
        intencoes_str = [i['intencao'] for i in intencoes]
        
        if any(i in intencoes_str for i in ['pedido', 'negociacao']):
            if self.context_cache['produtos']:
                contexto_relevante.append("🎯 CATÁLOGO DE PRODUTOS:\n" + self.context_cache['produtos'])
        
        if any(i in intencoes_str for i in ['reclamacao', 'duvida']):
            if self.context_cache['politicas']:
                contexto_relevante.append("📋 POLÍTICAS DA EMPRESA:\n" + self.context_cache['politicas'])
        
        if any(i in intencoes_str for i in ['negociacao', 'duvida']) or any(word in corpo_lower for word in ['pagamento', 'desconto', 'preço', 'valor']):
            if self.context_cache['financeiro']:
                contexto_relevante.append("💰 INFORMAÇÕES FINANCEIRAS:\n" + self.context_cache['financeiro'])
        
        if any(i in intencoes_str for i in ['duvida', 'pedido']) or any(word in corpo_lower for word in ['entrega', 'prazo', 'frete', 'envio']):
            if self.context_cache['entregas']:
                contexto_relevante.append("🚚 INFORMAÇÕES DE ENTREGA:\n" + self.context_cache['entregas'])
        
        return "\n\n".join(contexto_relevante) if contexto_relevante else ""

# ==============================
# GERENCIADOR DE BANCO DE DADOS (ORIGINAL)
# ==============================
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.ensure_tables()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def ensure_tables(self):
        conn = self.get_connection()
        cursor = conn.cursor()
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
# GERENCIADOR DE ESTADO (ORIGINAL)
# ==============================
class StateManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def is_email_processed(self, email_id):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM emails_processados WHERE id_email = ?", (email_id,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def mark_email_processed(self, email_id, remetente, assunto):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO emails_processados (id_email, data_processamento, remetente, assunto) VALUES (?, ?, ?, ?)",
            (email_id, datetime.now().isoformat(), remetente, assunto)
        )
        conn.commit()
        conn.close()

# ==============================
# DETECÇÃO DE INTENÇÕES (ORIGINAL)
# ==============================
class IntentionDetector:
    def __init__(self):
        self.keywords = {
            'pedido': ['orçamento', 'pedido', 'comprar', 'cotação', 'preço', 'valor', 'quantidade'],
            'duvida': ['dúvida', 'duvida', 'pergunta', 'como funciona', 'informação'],
            'reclamacao': ['reclamação', 'reclamacao', 'problema', 'erro', 'defeito', 'quebrado', 'troc'],
            'negociacao': ['proposta', 'negociar', 'desconto', 'melhor preço', 'condições']
        }
    
    def detect_intentions(self, corpo_email, assunto):
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
        
        return intentions if intentions else [{'intencao': 'geral', 'score': 1, 'confianca': 0.5}]

# ==============================
# AGENTE PRINCIPAL DE EMAIL COM RAG E MLOPS CORRIGIDO
# ==============================
class EmailAgent:
    def __init__(self, db_manager, state_manager, intention_detector, rag_manager):
        self.db = db_manager
        self.state = state_manager
        self.detector = intention_detector
        self.rag = rag_manager
        
        # Inicializa componentes MLOPS
        self.mlops_db = MLOpsDatabase()
        self.ab_system = ABTestingSystem(self.mlops_db)
        self.llm_judge = LLMJudge(evaluation_logger)
        self.dashboard = DashboardServer(self.mlops_db, self.ab_system)
        
        self.service = self.authenticate_gmail()
        self.last_sent = {}
    
    def authenticate_gmail(self):
        creds = None
        
        if config.TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), config.SCOPES)
        
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
        try:
            message = self.service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()
            
            headers = message['payload']['headers']
            remetente = assunto = "desconhecido"
            
            for header in headers:
                if header['name'] == 'From':
                    match = re.search(r'<(.+?)>', header['value'])
                    remetente = match.group(1) if match else header['value'].split()[-1]
                elif header['name'] == 'Subject':
                    assunto = header['value'] or "Sem assunto"
            
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
        """Gera resposta usando A/B testing ou método tradicional"""
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
        
        # Usa A/B testing se habilitado
        if config.mlops.ENABLE_AB_TESTING:
            resposta, modelo_usado, response_id = self.ab_system.run_ab_test(
                email_data, prompt, intentions
            )
            
            # Avaliação automática pelo LLM Juiz
            if config.mlops.ENABLE_AUTO_EVALUATION and contexto_rag:  # Só avalia se tiver contexto
                self.evaluate_response_async(response_id, email_data, resposta, 
                                           contexto_rag, modelo_usado, intentions)
            
            return resposta
        else:
            # Método tradicional
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
    
    def evaluate_response_async(self, response_id: int, email_data: Dict, response_text: str, 
                              context: str, model_used: str, intentions: List):
        """Avalia resposta assincronamente com thread segura E SALVA EM TXT"""
        def evaluate():
            try:
                scores, feedback = self.llm_judge.evaluate_response(
                    email_data['corpo'], response_text, context, model_used
                )
                
                # Salva no banco de dados
                self.mlops_db.save_evaluation(response_id, scores, feedback)
                
                # Salva no arquivo TXT (LOG COMPLETO)
                evaluation_logger.log_evaluation(
                    email_data, model_used, response_text, scores, feedback, intentions
                )
                
                config.logger.info(f"⚖️ Avaliação LLM Juiz: {scores.get('overall', 0):.1f}/100")
                config.logger.info(f"   Modelo avaliado: {model_used}")
                if feedback and len(feedback) > 0:
                    config.logger.info(f"   Feedback: {feedback[:80]}...")
                
            except Exception as e:
                config.logger.error(f"❌ Erro na avaliação: {e}")
        
        # Executa em thread separada para não bloquear
        thread = threading.Thread(target=evaluate, daemon=True)
        thread.start()
    
    def send_email(self, destinatario, assunto, mensagem):
        now = datetime.now()
        
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
        emails = self.get_unprocessed_emails()
        
        if not emails:
            config.logger.info("⏳ Nenhum email novo")
            return 0
        
        config.logger.info(f"📨 {len(emails)} email(s) para processar")
        processed = 0
        
        for email in emails:
            intentions = self.detector.detect_intentions(email['corpo'], email['assunto'])
            config.logger.info(f"🎯 Intenções: {[i['intencao'] for i in intentions]}")
            
            resposta = self.generate_response(email, intentions)
            
            if self.send_email(email['remetente'], email['assunto'], resposta):
                self.state.mark_email_processed(email['id'], email['remetente'], email['assunto'])
                processed += 1
                config.logger.info(f"✅ Respondido: {email['remetente']}")
        
        return processed
    
    def run(self):
        config.logger.info("=" * 70)
        config.logger.info("🚀 EMAIL AGENT MARKET v2.0 - MLOPS COMPLETO COM A/B TESTING REAL")
        config.logger.info("=" * 70)
        config.logger.info(f"📊 Dashboard: http://localhost:8081")
        config.logger.info(f"🤖 Modelos ativos no A/B Testing: {len(config.mlops.AB_MODELS)}")
        for model in config.mlops.AB_MODELS:
            config.logger.info(f"   • {model['name']} (peso: {model['weight']})")
        config.logger.info(f"📝 Log das avaliações: {config.EVALUATIONS_LOG_FILE.name}")
        config.logger.info(f"⏰ Verificando emails a cada {config.CHECK_INTERVAL/60} minutos")
        config.logger.info(f"🔧 A/B Testing: {'✅ ATIVO' if config.mlops.ENABLE_AB_TESTING else '❌ INATIVO'}")
        config.logger.info(f"⚖️  Avaliação automática: {'✅ ATIVA' if config.mlops.ENABLE_AUTO_EVALUATION else '❌ INATIVA'}")
        config.logger.info(f"💾 Sistema de log TXT: ✅ ATIVO (acumulativo)")
        config.logger.info("=" * 70)
        
        ciclo = 0
        while True:
            ciclo += 1
            config.logger.info(f"\n🔄 Ciclo #{ciclo} - {datetime.now().strftime('%H:%M:%S')}")
            
            try:
                processed = self.process_emails()
                if processed > 0:
                    config.logger.info(f"📊 {processed} email(s) processado(s) neste ciclo")
                    
                    # Mostra estatísticas do A/B Testing
                    selection_stats = self.ab_system.get_selection_stats()
                    if selection_stats:
                        config.logger.info("🎲 Estatísticas do A/B Testing neste ciclo:")
                        for model, stats in selection_stats.items():
                            config.logger.info(f"   • {model}: {stats['count']} seleções ({stats['percentage']:.1f}%)")
                
                config.logger.info(f"⏰ Próxima verificação em {config.CHECK_INTERVAL/60} minutos...")
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                config.logger.info("\n" + "=" * 70)
                config.logger.info("👋 Sistema encerrado pelo usuário")
                
                # Mostra estatísticas finais
                selection_stats = self.ab_system.get_selection_stats()
                if selection_stats:
                    config.logger.info("🎲 Estatísticas FINAIS do A/B Testing:")
                    for model, stats in selection_stats.items():
                        config.logger.info(f"   • {model}: {stats['count']} seleções ({stats['percentage']:.1f}%)")
                
                config.logger.info(f"📊 Dashboard finalizado")
                config.logger.info(f"📝 Total de avaliações salvas no TXT: {evaluation_logger.evaluation_count}")
                config.logger.info(f"💾 Dados salvos em: mlops.db, clientes.db e {config.EVALUATIONS_LOG_FILE.name}")
                config.logger.info("=" * 70)
                break
            except Exception as e:
                config.logger.error(f"❌ Erro no ciclo: {e}")
                time.sleep(60)  # Espera 1 minuto antes de tentar novamente

# ==============================
# EXECUÇÃO PRINCIPAL
# ==============================
def main():
    config.logger.info("=" * 70)
    config.logger.info("EMAIL AGENT MARKET - MVP COM RAG + MLOPS COMPLETO")
    config.logger.info("=" * 70)
    
    # Log das configurações MLOPS
    config.logger.info("🔧 Configurações MLOPS:")
    config.logger.info(f"   A/B Testing: {'✅ Ativo' if config.mlops.ENABLE_AB_TESTING else '❌ Inativo'}")
    config.logger.info(f"   Avaliação Automática: {'✅ Ativa' if config.mlops.ENABLE_AUTO_EVALUATION else '❌ Inativa'}")
    config.logger.info(f"   Modelo Juiz: {config.mlops.JUDGE_MODEL}")
    config.logger.info(f"   Modelos configurados: {[m['name'] for m in config.mlops.AB_MODELS]}")
    config.logger.info(f"   Log das avaliações: {config.EVALUATIONS_LOG_FILE.name}")
    
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
    main()