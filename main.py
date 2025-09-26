import os
import time
import sqlite3
import base64
import re
import json
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
            status TEXT DEFAULT 'pendente',
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
            corrigido BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (id_pedido) REFERENCES pedidos (id),
            FOREIGN KEY (id_produto) REFERENCES produtos (id)
        )
    ''')

    # tabela logs_envio
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs_envio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER,
            email TEXT NOT NULL,
            mensagem_enviada TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            tipo_agente TEXT NOT NULL,
            FOREIGN KEY (id_cliente) REFERENCES clientes (id)
        )
    ''')

    # tabela correcoes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS correcoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pedido INTEGER,
            id_produto INTEGER,
            quantidade_original INTEGER,
            quantidade_corrigida INTEGER,
            data_correcao TEXT NOT NULL,
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
        print("📁 Arquivo produtos.txt não encontrado.")
        return

    with open(ARQ_PRODUTOS, "r", encoding="utf-8") as f:
        linhas = f.readlines()

    produtos_novos = 0
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
                produtos_novos += 1
        except Exception as e:
            print(f"⚠️ Erro ao processar linha '{linha}': {e}")

    if produtos_novos == 0:
        print("✅ Nenhum produto novo para adicionar.")
    else:
        print(f"📊 Total de produtos novos adicionados: {produtos_novos}")

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

def registrar_log(email, mensagem, tipo_agente):
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM clientes WHERE email = ?", (email,))
    cliente = cursor.fetchone()
    id_cliente = cliente[0] if cliente else None

    cursor.execute(
        "INSERT INTO logs_envio (id_cliente, email, mensagem_enviada, timestamp, tipo_agente) VALUES (?, ?, ?, ?, ?)",
        (id_cliente, email, mensagem, datetime.now().isoformat(), tipo_agente)
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
# AGENTE ORQUESTRADOR
# ==============================
def classificar_intencao_email(corpo_email, assunto):
    """Classifica a intenção do email para direcionar ao agente correto"""
    
    corpo_lower = corpo_email.lower()
    assunto_lower = assunto.lower()
    
    # Palavras-chave para cada tipo de intenção
    palavras_pedido = ['orçamento', 'pedido', 'solicitar', 'comprar', 'cotação', 'preço', 'valor']
    palavras_duvida = ['dúvida', 'duvida', 'pergunta', 'como funciona', 'prazo', 'entrega', 'pagamento', 'troca']
    palavras_reclamacao = ['reclamação', 'reclamacao', 'problema', 'erro', 'faltando', 'quebrado', 'defeito', 'devolução']
    palavras_negociacao = ['proposta', 'oferta', 'negociar', 'desconto', 'melhor preço', 'contraproposta']
    
    # Verificar intenções por ordem de prioridade
    if any(palavra in corpo_lower or palavra in assunto_lower for palavra in palavras_reclamacao):
        return "reclamacao"
    elif any(palavra in corpo_lower or palavra in assunto_lower for palavra in palavras_negociacao):
        return "negociacao"
    elif any(palavra in corpo_lower or palavra in assunto_lower for palavra in palavras_duvida):
        return "duvida"
    elif any(palavra in corpo_lower or palavra in assunto_lower for palavra in palavras_pedido):
        return "pedido"
    else:
        # Usar Ollama para classificação mais precisa
        return classificar_intencao_ollama(corpo_email, assunto)

def classificar_intencao_ollama(corpo_email, assunto):
    """Usa Ollama para classificação mais precisa da intenção"""
    
    prompt = f"""
Classifique a intenção deste email em uma das categorias: pedido, duvida, reclamacao, negociacao.

Assunto: {assunto}
Corpo: {corpo_email[:500]}

Responda APENAS com uma das palavras: pedido, duvida, reclamacao, negociacao
"""
    
    try:
        resposta = chat(
            model="llama3",
            messages=[
                {"role": "system", "content": "Você é um classificador de intenções de emails."},
                {"role": "user", "content": prompt}
            ]
        )
        intencao = resposta["message"]["content"].strip().lower()
        return intencao
    except:
        return "pedido"  # Fallback

# ==============================
# AGENTE NEGOCIADOR
# ==============================
def calcular_orcamento(produtos_pedido):
    """Calcula o orçamento completo com descontos e condições"""
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    
    orcamento = {
        'itens': [],
        'subtotal': 0,
        'descontos': [],
        'total_unidades': 0,
        'total_final': 0,
        'condicoes_pagamento': []
    }
    
    # Calcular subtotal e totais
    for produto in produtos_pedido:
        cursor.execute("SELECT descricao, preco_un FROM produtos WHERE id = ?", (produto['id'],))
        resultado = cursor.fetchone()
        
        if resultado:
            descricao, preco_un = resultado
            subtotal_item = preco_un * produto['quantidade']
            
            orcamento['itens'].append({
                'id': produto['id'],
                'descricao': descricao,
                'quantidade': produto['quantidade'],
                'preco_un': preco_un,
                'subtotal': subtotal_item
            })
            
            orcamento['subtotal'] += subtotal_item
            orcamento['total_unidades'] += produto['quantidade']
    
    orcamento['total_final'] = orcamento['subtotal']
    
    # Aplicar condições de desconto
    # 1. Desconto por quantidade (acima de 500 unidades)
    if orcamento['total_unidades'] > 500:
        desconto = orcamento['subtotal'] * 0.10
        orcamento['total_final'] -= desconto
        orcamento['descontos'].append({
            'tipo': 'Quantidade (10%)',
            'valor': desconto
        })
    
    # 2. Frete grátis (acima de 1000 unidades) - considerado como desconto simbólico
    if orcamento['total_unidades'] > 1000:
        orcamento['descontos'].append({
            'tipo': 'Frete Grátis',
            'valor': 'GRÁTIS'
        })
    
    # 3. Condições de pagamento
    orcamento['condicoes_pagamento'].append("À vista: 5% de desconto")
    orcamento['condicoes_pagamento'].append("Parcelamento em até 3x sem juros")
    
    conn.close()
    return orcamento

def gerar_resposta_negociador(orcamento, cliente_novo=True, contra_proposta=False):
    """Gera a resposta do agente negociador com orçamento detalhado"""
    
    if contra_proposta:
        return """
Obrigado pela sua contraproposta!

Analisando sua solicitação, identificamos que ela foge das nossas condições padrão de negociação. 

Para garantir que possamos atendê-lo da melhor forma possível, vou transferir seu atendimento para nosso negociador humano especializado.

Em até 24 horas úteis, um de nossos representantes entrará em contato para discutir as melhores condições possíveis para seu pedido.

Agradecemos sua compreensão e estamos à disposição para qualquer esclarecimento adicional.

Atenciosamente,
Equipe de Vendas - Fábrica de Utensílios Domésticos
"""
    
    # Montar o texto do orçamento
    texto_orcamento = f"""
📋 **ORÇAMENTO DETALHADO**

"""
    
    # Itens do pedido
    for item in orcamento['itens']:
        texto_orcamento += f"• {item['descricao']}: {item['quantidade']} und × R${item['preco_un']:.2f} = R${item['subtotal']:.2f}\n"
    
    texto_orcamento += f"\n📊 **RESUMO DO PEDIDO**\n"
    texto_orcamento += f"Subtotal: R${orcamento['subtotal']:.2f}\n"
    texto_orcamento += f"Total de unidades: {orcamento['total_unidades']}\n"
    
    # Descontos aplicados
    if orcamento['descontos']:
        texto_orcamento += f"\n🎁 **DESCONTOS APLICADOS**\n"
        for desconto in orcamento['descontos']:
            if desconto['tipo'] == 'Frete Grátis':
                texto_orcamento += f"• {desconto['tipo']}: {desconto['valor']}\n"
            else:
                texto_orcamento += f"• {desconto['tipo']}: R${desconto['valor']:.2f}\n"
    
    texto_orcamento += f"💰 **TOTAL FINAL: R${orcamento['total_final']:.2f}**\n"
    
    # Condições de pagamento
    texto_orcamento += f"\n💳 **CONDIÇÕES DE PAGAMENTO**\n"
    for condicao in orcamento['condicoes_pagamento']:
        texto_orcamento += f"• {condicao}\n"
    
    # Avisos sobre descontos adicionais
    texto_orcamento += f"\n💡 **OBSERVAÇÕES**\n"
    if orcamento['total_unidades'] <= 500:
        texto_orcamento += f"• Faltam {501 - orcamento['total_unidades']} unidades para ganhar 10% de desconto!\n"
    if orcamento['total_unidades'] <= 1000:
        texto_orcamento += f"• Faltam {1001 - orcamento['total_unidades']} unidades para frete grátis!\n"
    
    # Mensagem personalizada
    if cliente_novo:
        saudacao = "Agradecemos seu interesse em nossos produtos!"
    else:
        saudacao = "É um prazer atendê-lo novamente!"
    
    mensagem_final = f"""
{saudacao}

{texto_orcamento}

**💬 Possui alguma contraproposta?**
Caso deseje negociar condições diferentes, responda este email com sua proposta. Para propostas complexas, nosso negociador humano entrará em contato.

Estamos à disposição para quaisquer esclarecimentos adicionais.

Atenciosamente,
Equipe de Vendas - Fábrica de Utensílios Domésticos
"""
    
    return mensagem_final

# ==============================
# AGENTE DE DÚVIDAS
# ==============================
def gerar_resposta_duvidas(corpo_email, cliente_novo=True):
    """Agente especializado em tirar dúvidas"""
    
    prompt = f"""
Você é um atendente especializado em tirar dúvidas de uma fábrica de utensílios domésticos.

Dúvida do cliente:
---
{corpo_email}
---

Informações importantes para suas respostas:
- Prazo de entrega: 5-10 dias úteis para grandes centros, 10-15 dias para interior
- Condições de pagamento: À vista com 5% desconto ou parcelado em até 3x sem juros
- Trocas: 30 dias para trocas de produtos com defeito
- Fretes: Grátis para compras acima de 1000 unidades
- Contato humano: sac@fabricautensilios.com.br

Responda de forma clara, objetiva e educada, usando as informações acima quando relevantes.
"""
    
    try:
        resposta = chat(
            model="llama3",
            messages=[
                {"role": "system", "content": "Você é um atendente educado e informativo que responde dúvidas de clientes."},
                {"role": "user", "content": prompt}
            ]
        )
        return resposta["message"]["content"]
    except Exception as e:
        return f"""
Obrigado pelo seu contato!

Em relação à sua dúvida, aqui estão algumas informações gerais:

📦 **Prazos de Entrega:** 5-10 dias úteis para grandes centros, 10-15 dias para interior
💳 **Pagamento:** À vista com 5% desconto ou parcelado em até 3x sem juros
🔄 **Trocas:** 30 dias para produtos com defeito
🚚 **Frete:** Grátis para compras acima de 1000 unidades

Para informações mais específicas sobre sua dúvida, entre em contato com nosso atendimento humano: sac@fabricautensilios.com.br

Atenciosamente,
Equipe de Atendimento
"""

# ==============================
# AGENTE DE RECLAMAÇÕES
# ==============================
def gerar_resposta_reclamacao(corpo_email):
    """Agente especializado em tratar reclamações"""
    
    prompt = f"""
Você é um atendente especializado em tratar reclamações de uma fábrica de utensílios domésticos.

Reclamação do cliente:
---
{corpo_email}
---

Sua função é:
1. Pedir desculpas pelo ocorrido
2. Solicitar informações específicas (número do pedido, produtos com problema)
3. Informar que o caso será encaminhado para nossa equipe especializada
4. Dar um prazo para retorno (24-48 horas)

Seja empático, profissional e ofereça uma solução adequada.
"""
    
    try:
        resposta = chat(
            model="llama3",
            messages=[
                {"role": "system", "content": "Você é um atendente empático que trata reclamações de clientes."},
                {"role": "user", "content": prompt}
            ]
        )
        return resposta["message"]["content"]
    except Exception as e:
        return """
Lamentamos muito pelo ocorrido!

Para podermos resolver sua situação da melhor forma possível, precisamos de algumas informações:

📋 **Número do pedido:**
🛍️ **Produtos com problema:**
📝 **Descrição detalhada do problema:**

Nossa equipe especializada entrará em contato em até 24 horas úteis para resolver sua situação.

Agradecemos sua paciência e compreensão.

Atenciosamente,
Equipe de Atendimento ao Cliente
"""

# ==============================
# DETECÇÃO DE CONTRAPROPOSTA
# ==============================
def detectar_contra_proposta(corpo_email):
    """Detecta se o cliente está fazendo uma contraproposta"""
    
    palavras_chave = [
        'proposta', 'oferta', 'negociar', 'desconto', 'melhor preço', 
        'contraproposta', 'abaixo', 'menor', 'reduzir', 'flexibilizar',
        'condições melhores', 'outra proposta'
    ]
    
    corpo_lower = corpo_email.lower()
    
    # Verifica palavras-chave
    if any(palavra in corpo_lower for palavra in palavras_chave):
        return True
    
    # Verifica números que podem indicar proposta (valores, quantidades)
    numeros = re.findall(r'\b\d+\b', corpo_email)
    if len(numeros) > 2:  # Se tem vários números, pode ser proposta
        return True
    
    return False

# ==============================
# INTERFACE PARA CORREÇÕES
# ==============================
def exibir_interface_correcoes():
    """Interface simples para correção de pedidos"""
    print("\n" + "="*50)
    print("🔧 INTERFACE DE CORREÇÃO DE PEDIDOS")
    print("="*50)
    
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    
    # Buscar pedidos pendentes de correção
    cursor.execute('''
        SELECT p.id, c.email, p.data, COUNT(pp.id) as total_itens
        FROM pedidos p
        JOIN clientes c ON p.id_cliente = c.id
        JOIN pedidos_produtos pp ON p.id = pp.id_pedido
        WHERE pp.corrigido = FALSE
        GROUP BY p.id
        ORDER BY p.data DESC
    ''')
    
    pedidos = cursor.fetchall()
    
    if not pedidos:
        print("✅ Nenhum pedido pendente de correção.")
        return
    
    print("\n📋 Pedidos pendentes de correção:")
    for i, (pedido_id, email, data, total_itens) in enumerate(pedidos, 1):
        print(f"{i}. Pedido #{pedido_id} - {email} - {data} - {total_itens} itens")
    
    try:
        opcao = int(input("\nSelecione o pedido para correção (0 para voltar): "))
        if opcao == 0:
            return
        
        pedido_selecionado = pedidos[opcao-1][0]
        corrigir_pedido(pedido_selecionado, conn, cursor)
        
    except (ValueError, IndexError):
        print("❌ Opção inválida.")
    
    conn.close()

def corrigir_pedido(pedido_id, conn, cursor):
    """Corrige um pedido específico"""
    
    print(f"\n📝 Corrigindo Pedido #{pedido_id}")
    print("-" * 30)
    
    # Buscar itens do pedido
    cursor.execute('''
        SELECT pp.id, pr.descricao, pp.quantidade, pr.preco_un
        FROM pedidos_produtos pp
        JOIN produtos pr ON pp.id_produto = pr.id
        WHERE pp.id_pedido = ? AND pp.corrigido = FALSE
    ''', (pedido_id,))
    
    itens = cursor.fetchall()
    
    for item_id, descricao, quantidade, preco in itens:
        print(f"\n🛍️ Produto: {descricao}")
        print(f"📦 Quantidade atual: {quantidade}")
        print(f"💰 Preço unitário: R${preco:.2f}")
        
        try:
            nova_quantidade = int(input("Nova quantidade (0 para remover, Enter para manter): ") or quantidade)
            
            if nova_quantidade == 0:
                cursor.execute("DELETE FROM pedidos_produtos WHERE id = ?", (item_id,))
                print("❌ Produto removido do pedido.")
            else:
                cursor.execute("UPDATE pedidos_produtos SET quantidade = ?, corrigido = TRUE WHERE id = ?", 
                             (nova_quantidade, item_id))
                
                # Registrar correção
                cursor.execute('''
                    INSERT INTO correcoes (id_pedido, id_produto, quantidade_original, quantidade_corrigida, data_correcao)
                    VALUES (?, ?, ?, ?, ?)
                ''', (pedido_id, item_id, quantidade, nova_quantidade, datetime.now().isoformat()))
                
                print(f"✅ Quantidade corrigida para {nova_quantidade}")
                
        except ValueError:
            print("❌ Valor inválido. Mantendo quantidade original.")
    
    conn.commit()
    print(f"\n✅ Pedido #{pedido_id} corrigido com sucesso!")

# ==============================
# FUNÇÃO PARA ENVIO DE ERRATA
# ==============================
def enviar_email_correcao(service, pedido_id, destinatario):
    """Envia email de correção após ajuste humano"""
    
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    
    # Buscar dados do pedido corrigido
    cursor.execute('''
        SELECT pr.descricao, pp.quantidade, pr.preco_un, c.quantidade_original
        FROM pedidos_produtos pp
        JOIN produtos pr ON pp.id_produto = pr.id
        LEFT JOIN correcoes c ON pp.id_pedido = c.id_pedido AND pp.id_produto = c.id_produto
        WHERE pp.id_pedido = ?
    ''', (pedido_id,))
    
    itens = cursor.fetchall()
    
    mensagem = f"""
Prezado cliente,

Identificamos a necessidade de corrigir seu pedido #{pedido_id} conforme ajustado com nosso atendente.

📋 **PEDIDO CORRIGIDO:**

"""
    
    for descricao, quantidade, preco, original in itens:
        if original and original != quantidade:
            mensagem += f"• {descricao}: {original} → {quantidade} unidades\n"
        else:
            mensagem += f"• {descricao}: {quantidade} unidades\n"
    
    mensagem += f"""
    
Agradecemos pela compreensão e estamos à disposição para quaisquer esclarecimentos.

Atenciosamente,
Equipe de Vendas - Fábrica de Utensílios Domésticos
"""
    
    enviar_email(service, destinatario, f"[ERRATA] Correção do Pedido #{pedido_id}", mensagem)
    conn.close()

# ==============================
# RECONHECIMENTO DE PRODUTOS (MELHORADO PARA PLURAIS)
# ==============================
def normalizar_palavra(palavra):
    """Remove plural e transforma para minúsculo"""
    palavra = palavra.lower().strip()
    
    # Lista de sufixos plurais comuns em português
    sufixos_plurais = ['s', 'es', 'ões', 'ães', 'ais', 'eis', 'óis', 'uis']
    
    # Palavras irregulares (singular -> plural)
    irregulares = {
        'males': 'mal', 'cômodos': 'cômodo', 'cômodas': 'cômoda',
        'país': 'país', 'lápis': 'lápis'  # palavras que não mudam no plural
    }
    
    if palavra in irregulares:
        return irregulares[palavra]
    
    # Remove sufixos plurais
    for sufixo in sufixos_plurais:
        if palavra.endswith(sufixo) and len(palavra) > len(sufixo):
            palavra_singular = palavra[:-len(sufixo)]
            # Verifica se a palavra singular faz sentido
            if len(palavra_singular) >= 2:  # Evita palavras muito curtas
                return palavra_singular
    
    return palavra

def produtos_reconhecidos(texto):
    conn = sqlite3.connect(DB_CLIENTES)
    cursor = conn.cursor()
    cursor.execute("SELECT id, descricao FROM produtos")
    produtos = cursor.fetchall()
    conn.close()

    texto_lower = texto.lower()
    resultado = []

    for pid, desc in produtos:
        desc_lower = desc.lower()
        
        # Divide a descrição em palavras
        palavras_desc = desc_lower.split()
        palavras_texto = texto_lower.split()
        
        # Normaliza todas as palavras (remove plurais)
        palavras_desc_normalizadas = [normalizar_palavra(p) for p in palavras_desc]
        palavras_texto_normalizadas = [normalizar_palavra(p) for p in palavras_texto]
        
        # Verifica se todas as palavras da descrição estão no texto (considerando plurais)
        match = all(
            any(palavra_desc == palavra_texto 
                for palavra_texto in palavras_texto_normalizadas)
            for palavra_desc in palavras_desc_normalizadas
        )
        
        if match:
            # Tenta extrair quantidade usando regex mais flexível
            # Procura por padrões como "2 panelas", "3 unidades de panela", etc.
            padroes_quantidade = [
                r"(\d+)\s+" + re.escape(palavras_desc[0]),
                r"(\d+)\s+unidades?\s+(?:de\s+)?" + re.escape(desc_lower),
                r"quantidade[:\s]*(\d+).*?" + re.escape(desc_lower),
                r"pedir\s+(\d+).*?" + re.escape(desc_lower)
            ]
            
            quantidade = 1
            for padrao in padroes_quantidade:
                quantidade_match = re.search(padrao, texto_lower, re.IGNORECASE)
                if quantidade_match:
                    try:
                        quantidade = int(quantidade_match.group(1))
                        break
                    except ValueError:
                        continue
            
            resultado.append({
                "id": pid, 
                "descricao": desc, 
                "quantidade": quantidade,
                "match_exato": desc_lower in texto_lower
            })
    
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
        # Registrar log com tipo de agente detectado pelo assunto
        tipo_agente = "negociador" if "orçamento" in assunto.lower() else "duvidas" if "dúvida" in assunto.lower() else "reclamacao" if "reclamação" in assunto.lower() else "geral"
        registrar_log(destinatario, mensagem, tipo_agente)
        print(f"📤 Email enviado para {destinatario}")
    except HttpError as error:
        print(f"⚠️ Erro ao enviar email: {error}")

# ==============================
# LER NOVO EMAIL
# ==============================
def obter_ultimo_email(service):
    try:
        resultados = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        mensagens = resultados.get('messages', [])
        if not mensagens:
            return None
        mensagem_id = mensagens[0]['id']
        mensagem = service.users().messages().get(userId='me', id=mensagem_id, format='full').execute()
        headers = mensagem['payload']['headers']

        remetente = assunto = "(desconhecido)"
        corpo = ""
        
        # Extrair email do remetente
        for header in headers:
            if header['name'] == 'From':
                remetente = header['value']
                # Extrair apenas o email se vier no formato "Nome <email@dominio.com>"
                match = re.search(r'<(.+?)>', remetente)
                if match:
                    remetente = match.group(1)
                else:
                    remetente = remetente.split()[-1] if ' ' in remetente else remetente
            elif header['name'] == 'Subject':
                assunto = header['value']

        # Extrair corpo do email
        if "parts" in mensagem["payload"]:
            for part in mensagem["payload"]["parts"]:
                if part["mimeType"] == "text/plain" and "data" in part["body"]:
                    corpo = base64.urlsafe_b64decode(part["body"]["data"]).decode('utf-8')
                    break
        else:
            if "data" in mensagem["payload"]["body"]:
                corpo = base64.urlsafe_b64decode(mensagem["payload"]["body"]["data"]).decode('utf-8')

        return mensagem_id, remetente, assunto, corpo
    except Exception as e:
        print(f"⚠️ Erro ao obter email: {e}")
        return None

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
# MONITORAMENTO PRINCIPAL
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
                    print(f"Corpo: {corpo[:200]}...")

                    # Classificar intenção do email
                    intencao = classificar_intencao_email(corpo, assunto)
                    print(f"🎯 Intenção detectada: {intencao}")

                    # Verificar se é resposta com contraproposta
                    contra_proposta = detectar_contra_proposta(corpo)
                    if contra_proposta:
                        print("💼 Contraproposta detectada!")

                    produtos_pedido = produtos_reconhecidos(corpo)
                    
                    if produtos_pedido:
                        print("🛒 Produtos reconhecidos no pedido:")
                        for p in produtos_pedido:
                            status_match = "✅" if p["match_exato"] else "🔍"
                            print(f" {status_match} ID {p['id']}: {p['descricao']} x{p['quantidade']}")

                    # Direcionar para o agente correto
                    if intencao == "pedido" and produtos_pedido and not contra_proposta:
                        print("\n💰 Agente Negociador ativado...")
                        orcamento = calcular_orcamento(produtos_pedido)
                        
                        print(f"📊 RESUMO DO ORÇAMENTO:")
                        print(f"   Total de unidades: {orcamento['total_unidades']}")
                        print(f"   Subtotal: R${orcamento['subtotal']:.2f}")
                        print(f"   Total final: R${orcamento['total_final']:.2f}")
                        
                        if not cliente_existe(remetente):
                            cadastrar_cliente(remetente)
                            cliente_novo = True
                        else:
                            cliente_novo = False
                        
                        resposta = gerar_resposta_negociador(orcamento, cliente_novo, False)
                        assunto_email = f"Orçamento - Pedido {mensagem_id[:8]}"
                        
                    elif intencao == "duvida":
                        print("\n❓ Agente de Dúvidas ativado...")
                        resposta = gerar_resposta_duvidas(corpo, not cliente_existe(remetente))
                        assunto_email = "Resposta à sua dúvida"
                        
                    elif intencao == "reclamacao":
                        print("\n🚨 Agente de Reclamações ativado...")
                        resposta = gerar_resposta_reclamacao(corpo)
                        assunto_email = "Registro da sua reclamação"
                        
                    elif contra_proposta:
                        print("\n💼 Encaminhando para negociador humano...")
                        resposta = gerar_resposta_negociador(None, True, True)
                        assunto_email = "Sua contraproposta - Encaminhamento"
                        
                    else:
                        print("\n🤖 Agente Geral ativado...")
                        resposta = gerar_resposta_ollama(corpo, not cliente_existe(remetente))
                        assunto_email = "Agradecimento pelo contato"

                    enviar_email(service, remetente, assunto_email, resposta)

                    if produtos_pedido and intencao == "pedido" and not contra_proposta:
                        registrar_pedido(remetente, produtos_pedido)
                        print("📦 Pedido registrado no banco de dados.")

                    ultimo_id = mensagem_id
                    
            # Verificar se usuário quer acessar interface de correções
            time.sleep(2)  # Pequena pausa para não sobrecarregar
            if False:  # Modificar para True quando quiser testar a interface
                exibir_interface_correcoes()
                
            time.sleep(8)  # Intervalo total de 10 segundos
                
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