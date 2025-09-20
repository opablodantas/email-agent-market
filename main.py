import os
import time
import sqlite3
import base64
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

from ollama import chat  # ✅ integração com Ollama

# ==============================
# CONFIGURAÇÕES
# ==============================
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "credentials.json"
DB_CLIENTES = "clientes.db"
ARQ_PRODUTOS = "produtos.txt"

COOLDOWN = timedelta(minutes=10)
ultimos_emails = {}

# ==============================
# BANCO DE DADOS
# ==============================
def inicializar_banco():
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()

    # tabela clientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            nome TEXT
        )
    ''')

    # tabela produtos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY,
            descricao TEXT NOT NULL,
            preco_un REAL NOT NULL
        )
    ''')

    # tabela pedidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER,
            data TEXT NOT NULL,
            FOREIGN KEY (id_cliente) REFERENCES clientes (id)
        )
    ''')

    # tabela pedidos_produtos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pedido INTEGER,
            id_produto INTEGER,
            quantidade INTEGER,
            FOREIGN KEY (id_pedido) REFERENCES pedidos (id),
            FOREIGN KEY (id_produto) REFERENCES produtos (id)
        )
    ''')

    conn.commit()
    conn.close()

# ==============================
# PRODUTOS TXT -> DB
# ==============================
def atualizar_produtos():
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()

    if not os.path.exists(ARQ_PRODUTOS):
        return

    with open(ARQ_PRODUTOS, "r", encoding="utf-8") as f:
        linhas = f.readlines()

    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("produto_id") or not linha:
            continue
        try:
            parts = [p.strip().rstrip("),") for p in linha.split(",")]
            if len(parts) < 3:
                continue
            produto_id, descricao, preco = int(parts[0]), parts[1], float(parts[2])
            cursor.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO produtos (id, descricao, preco_un) VALUES (?, ?, ?)",
                    (produto_id, descricao, preco)
                )
                print(f"🆕 Produto adicionado: ID {produto_id} | {descricao} | R${preco:.2f}")
        except Exception as e:
            print(f"⚠️ Erro ao processar linha '{linha}': {e}")

    conn.commit()
    conn.close()

# ==============================
# FUNÇÕES DE CLIENTE E LOG
# ==============================
def cliente_existe(email):
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM clientes WHERE email = ?", (email,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None

def cadastrar_cliente(email, nome=None):
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO clientes (email, nome) VALUES (?, ?)", (email, nome))
    conn.commit()
    conn.close()

def registrar_log(email, mensagem):
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM clientes WHERE email = ?", (email,))
    cliente = cursor.fetchone()
    id_cliente = cliente[0] if cliente else None

    cursor.execute(
        "INSERT INTO logs_envio (id_cliente, email, mensagem_enviada, timestamp) VALUES (?, ?, ?, ?)",
        (id_cliente, email, mensagem, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

# ==============================
# AUTENTICAÇÃO GMAIL
# ==============================
def autenticar_gmail():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

# ==============================
# INTEGRAÇÃO COM OLLAMA
# ==============================
def gerar_resposta_ollama(email_texto, cliente_novo=True):
    prompt = f"""
Você é um assistente de uma fábrica de utensílios domésticos.
O cliente enviou o seguinte email:

---
{email_texto}
---

Regras:
- Se for um cliente novo, agradeça o interesse e diga que logo enviaremos o orçamento.
- Se for um cliente recorrente, agradeça o retorno e diga que logo enviaremos o orçamento.
- Sempre responda de forma educada e profissional.
    """
    resposta = chat(
        model="llama3",
        messages=[
            {"role": "system", "content": "Você é um assistente educado que responde emails de clientes."},
            {"role": "user", "content": prompt}
        ]
    )
    return resposta["message"]["content"]

# ==============================
# RECONHECIMENTO DE PRODUTOS
# ==============================
def produtos_reconhecidos(texto):
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    cursor.execute("SELECT id, descricao FROM produtos")
    produtos = cursor.fetchall()
    conn.close()

    texto_lower = texto.lower()
    resultado = []

    for pid, desc in produtos:
        # Simplificação: ignora plural simples 's'
        desc_tokens = desc.lower().split()
        texto_tokens = texto_lower.split()
        match = all(
            token.rstrip("s") in [t.rstrip("s") for t in texto_tokens]
            for token in desc_tokens
        )
        if match:
            # tenta extrair quantidade usando regex
            pattern = r"(\d+)\s+" + re.escape(desc_tokens[0])
            quantidade_match = re.search(pattern, texto_lower)
            quantidade = int(quantidade_match.group(1)) if quantidade_match else 1
            resultado.append({"id": pid, "descricao": desc, "quantidade": quantidade})
    return resultado

# ==============================
# ENVIAR EMAIL
# ==============================
def enviar_email(service, destinatario, assunto, mensagem):
    global ultimos_emails
    agora = datetime.now()
    if destinatario in ultimos_emails and agora - ultimos_emails[destinatario] < COOLDOWN:
        print(f"⏳ Email não enviado para {destinatario}, ainda no cooldown.")
        return

    mime_message = MIMEText(mensagem)
    mime_message['to'] = destinatario
    mime_message['subject'] = assunto
    raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

    try:
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        ultimos_emails[destinatario] = agora
        registrar_log(destinatario, mensagem)
        print(f"📤 Email enviado para {destinatario}")
    except HttpError as error:
        print(f"⚠️ Erro ao enviar email: {error}")

# ==============================
# LER NOVO EMAIL
# ==============================
def obter_ultimo_email(service):
    resultados = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
    mensagens = resultados.get('messages', [])
    if not mensagens:
        return None
    mensagem_id = mensagens[0]['id']
    mensagem = service.users().messages().get(userId='me', id=mensagem_id, format='full').execute()
    headers = mensagem['payload']['headers']

    remetente = assunto = "(desconhecido)"
    corpo = ""
    for header in headers:
        if header['name'] == 'From':
            remetente = header['value']
        elif header['name'] == 'Subject':
            assunto = header['value']

    if "parts" in mensagem["payload"]:
        for part in mensagem["payload"]["parts"]:
            if part["mimeType"] == "text/plain":
                corpo = base64.urlsafe_b64decode(part["body"]["data"]).decode()

    return mensagem_id, remetente, assunto, corpo

# ==============================
# PROCESSAR PEDIDO
# ==============================
def registrar_pedido(email, produtos_pedido):
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM clientes WHERE email = ?", (email,))
    cliente = cursor.fetchone()
    id_cliente = cliente[0] if cliente else None

    data_atual = datetime.now().isoformat()
    cursor.execute("INSERT INTO pedidos (id_cliente, data) VALUES (?, ?)", (id_cliente, data_atual))
    id_pedido = cursor.lastrowid

    for p in produtos_pedido:
        cursor.execute(
            "INSERT INTO pedidos_produtos (id_pedido, id_produto, quantidade) VALUES (?, ?, ?)",
            (id_pedido, p["id"], p["quantidade"])
        )
    conn.commit()
    conn.close()

# ==============================
# MONITORAMENTO
# ==============================
def monitorar_emails():
    print("🔄 Monitorando novos e-mails...\n")
    service = autenticar_gmail()
    ultimo_id = None
    inicializar_banco()
    atualizar_produtos()

    while True:
        try:
            resultado = obter_ultimo_email(service)
            if resultado:
                mensagem_id, remetente, assunto, corpo = resultado
                if mensagem_id != ultimo_id:
                    print(f"\n📬 Novo e-mail recebido!")
                    print(f"De: {remetente}")
                    print(f"Assunto: {assunto}")
                    print(f"Corpo: {corpo}")

                    produtos_pedido = produtos_reconhecidos(corpo)
                    if produtos_pedido:
                        print("🛒 Produtos reconhecidos no pedido:")
                        for p in produtos_pedido:
                            print(f" - ID {p['id']}: {p['descricao']} x{p['quantidade']}")

                    if not cliente_existe(remetente):
                        cadastrar_cliente(remetente)
                        resposta = gerar_resposta_ollama(corpo, cliente_novo=True)
                    else:
                        resposta = gerar_resposta_ollama(corpo, cliente_novo=False)

                    enviar_email(service, remetente, "Orçamento solicitado", resposta)

                    if produtos_pedido:
                        registrar_pedido(remetente, produtos_pedido)

                    ultimo_id = mensagem_id
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Monitoramento encerrado pelo usuário.")
            break
        except Exception as e:
            print(f"⚠️ Erro: {e}")
            time.sleep(10)

# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    monitorar_emails()
