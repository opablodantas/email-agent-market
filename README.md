# Email Agent Market - Parte 1

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Google Gmail API](https://img.shields.io/badge/Gmail%20API-Integrated-red)
![Ollama](https://img.shields.io/badge/Ollama-LLM%20Integration-orange)
![SQLite](https://img.shields.io/badge/Database-SQLite-green)

## 📋 Sobre o Projeto

O **Email Agent Market** é um sistema inteligente de automação comercial que monitora caixas de email, classifica intenções de clientes e responde automaticamente usando agentes especializados em IA. Esta é a **Parte 1** do projeto, focada no processamento automático de emails.

### 🎯 Funcionalidades Principais

- **📧 Monitoramento Automático** de caixa de entrada do Gmail
- **🤖 Classificação Inteligente** de intenções usando Ollama
- **🛒 Reconhecimento Automático** de produtos e quantidades
- **💰 Agente Negociador** que calcula orçamentos com descontos
- **❓ Agente de Dúvidas** para atendimento ao cliente
- **🚨 Agente de Reclamações** para suporte técnico
- **🔧 Sistema de Correções** manual com envio de errata
- **💾 Controle Persistente** de emails processados

## 🏗️ Arquitetura do Sistema

### Agentes Especializados

| Agente | Função | Tecnologia |
|--------|--------|------------|
| **Orquestrador** | Classifica intenções dos emails | Ollama LLM |
| **Negociador** | Calcula orçamentos e descontos | Lógica de Negócio |
| **Suporte** | Responde dúvidas dos clientes | Ollama LLM |
| **Reclamações** | Gerencia problemas e issues | Ollama LLM |

### Condições de Negociação

- **Compra acima de 500 unidades**: 10% de desconto
- **Compra acima de 1000 unidades**: Frete grátis
- **Pagamento à vista**: 5% de desconto adicional
- **Parcelamento**: Até 3x sem juros

## 🚀 Instalação e Configuração

### Pré-requisitos

- Python 3.8+
- Conta Gmail com API habilitada
- Ollama instalado e configurado
- Modelo Llama3 rodando no Ollama

### 1. Clone o Repositório

```bash
git clone https://github.com/seu-usuario/email-agent-market.git
cd email-agent-market
```

### 2. Instale as Dependências

```bash
pip install -r requirements.txt
```

### 3. Configure as Credenciais do Gmail

1. Acesse [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um projeto e habilite a Gmail API
3. Crie credenciais OAuth 2.0
4. Baixe o arquivo `credentials.json` e coloque na pasta do projeto

### 4. Configure o Arquivo de Produtos

Crie o arquivo `produtos.txt` com o formato:

```
1, Panela antiaderente, 15.00
2, Frigideira grande, 20.00
3, Jogo de facas, 5.00

Obs: o arquivo não deve conter cabeçaho
```

### 5. Execute o Sistema

```bash
python main.py
```

## 📁 Estrutura do Projeto

```
email-agent-market/
├── main.py                 # Arquivo principal
├── requirements.txt        # Dependências do projeto
├── clientes.db             # Banco de dados SQLite
├── produtos.txt            # Catálogo de produtos
├── credentials.json        # Credenciais Gmail API
├── token.json              # Token de autenticação (gerado automaticamente)
└── README.md               # Este arquivo
```

## 🎮 Como Usar

### Execução Básica

```bash
python main.py
```

### Exemplo de Saída no Terminal

```
🔄 Monitorando novos e-mails...

✅ Banco de dados inicializado
✅ Nenhum produto novo para adicionar.
✅ Autenticação Gmail verificada com sucesso!
📧 Último email processado: 189f3a7c8a1b2c3d4e5f...

📨 Encontrados 2 email(s) não processado(s)

📬 Processando email: 189f3a7c8a1b2c3d4e5f...
De: cliente@empresa.com
Assunto: Solicitação de orçamento
Corpo: Olá, gostaria de solicitar orçamento para 200 panelas antiaderentes...
🎯 Intenção detectada: pedido

🛒 Produtos reconhecidos no pedido:
 ✅ ID 1: Panela antiaderente x200

💰 Agente Negociador ativado...
📊 RESUMO DO ORÇAMENTO:
   Total de unidades: 200
   Subtotal: R$3000.00
   Total final: R$3000.00

👤 Novo cliente cadastrado: cliente@empresa.com
📤 Email enviado para cliente@empresa.com
📦 Pedido registrado no banco de dados.
✅ Email registrado como processado.
```

### Interface de Correções

Pressione `Ctrl+C` durante a execução para acessar o menu de correções:

```
🛑 Monitoramento interrompido pelo usuário.
💡 Acessando menu de correções...

🔧 INTERFACE DE CORREÇÃO DE PEDIDOS - EDIÇÃO COMPLETA
==========================================================

📋 Todos os pedidos:
1. Pedido #15 - cliente@empresa.com - 2024-01-15 - 1 itens

Selecione o pedido para correção (0 para voltar): 1

📝 Corrigindo Pedido #15
----------------------------------------
🛍️ Itens atuais do pedido:
1. ID 1: Panela antiaderente - 200 und × R$15.00

📋 Opções de correção:
1. ✏️ Editar quantidade de um produto
2. ➕ Adicionar novo produto
3. ❌ Remover produto
4. ✅ Finalizar correção e enviar errata
5. 🚪 Sair sem salvar

Selecione uma opção: 1
Selecione o número do item para editar: 1
📦 Editando: Panela antiaderente
Quantidade atual: 200
Nova quantidade: 250
✅ Quantidade alterada de 200 para 250

📧 Preparando para enviar email de correção para cliente@empresa.com...
✅ Email de errata enviado com sucesso!
```

## 🗃️ Banco de Dados

### Tabelas Principais

- **clientes**: Cadastro de clientes
- **produtos**: Catálogo de produtos
- **pedidos**: Registro de pedidos
- **pedidos_produtos**: Itens de cada pedido
- **emails_processados**: Controle de emails já lidos
- **correcoes**: Histórico de correções manuais
- **logs_envio**: Log de emails enviados

### Arquivo produtos.txt

Este arquivo é a base para o banco de dados de produtos. Formato:

```
produto_id, descricao, preco
1, Panela antiaderente, 15.00
2, Frigideira grande, 20.00
3, Jogo de facas, 5.00
4, Conjunto de potes, 45.90
```

## ⚙️ Configurações

### Variáveis de Configuração no Código

```python
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "credentials.json"
DB_CLIENTES = "clientes.db"
ARQ_PRODUTOS = "produtos.txt"
COOLDOWN = timedelta(minutes=10)  # Intervalo entre emails
```

### Condições de Negócio

As condições estão no agente negociador:
- 10% desconto para +500 unidades
- Frete grátis para +1000 unidades
- 5% desconto para pagamento à vista
- Parcelamento em 3x sem juros

## 🔧 Funcionalidades Técnicas

### Reconhecimento de Produtos

- **Plurais inteligentes**: Reconhece "panelas" → "panela"
- **Extração de quantidades**: Detecta "2 panelas", "3 unidades de panela"
- **Match flexível**: Encontra produtos mesmo com descrição parcial

### Controle de Emails Processados

- **Persistência**: Sistema lembra onde parou entre execuções
- **Evita duplicação**: Não processa emails já lidos
- **Processamento ordenado**: Do mais antigo para o mais recente

### Sistema de Correções

- **Edição completa**: Quantidades, adição e remoção de produtos
- **Email automático**: Envio de errata com correções
- **Recálculo automático**: Novo orçamento após correções

## 🐛 Solução de Problemas

### Erro de Autenticação Gmail

```
❌ Token inválido: Token has been expired or revoked.
🗑️ Token inválido removido.
🔐 Iniciando processo de autenticação...
```

**Solução**: O sistema detecta automaticamente e solicita nova autenticação.

### Email Não Reconhecido

**Causa**: Descrição do produto não corresponde ao catálogo
**Solução**: Verificar o arquivo `produtos.txt` e adicionar sinônimos

### Ollama Não Responde

**Solução**: Verificar se o Ollama está rodando:
```bash
ollama serve
```

## 🚧 Próximas Atualizações - Parte 2

### Roadmap Futuro

- **🤖 Assistente Virtual Web**: FAQ interativo no site
- **🌐 Interface Web**: Dashboard administrativo
- **📊 Analytics**: Gráficos e relatórios em tempo real
- **🐳 Containerização**: Docker para deploy fácil
- **⚙️ Configurações JSON**: Arquivos de configuração por agente
- **🧠 Machine Learning**: Previsões de vendas e comportamento
- **📨 Filtro Automático**: Ignorar emails "noreply" automaticamente
- **🧩 Modularização do Código**: Dividir o código para futuras atualizações ou manutenção
  
### Assistente Virtual (Parte 2)

O próximo estágio incluirá um assistente web que:
- Atenderá clientes via chat no site
- Fará orçamentos automaticamente
- Cadastrará pedidos no mesmo banco de dados
- Integrará com os mesmos agentes especializados
- Oferecerá suporte 24/7 para dúvidas frequentes

## 📊 Exemplos de Uso

### Caso 1: Novo Cliente com Pedido

```
📬 Email Recebido: "Preciso de orçamento para 600 panelas"
🎯 Intenção: pedido
🛒 Produto: Panela antiaderente ×600
💰 Orçamento: R$9000.00 → R$8100.00 (10% desconto)
📤 Resposta: Email com orçamento detalhado
```

### Caso 2: Cliente com Dúvida

```
📬 Email Recebido: "Qual o prazo de entrega?"
🎯 Intenção: duvida
🤖 Agente: Suporte
📤 Resposta: Informações sobre prazos e condições
```

### Caso 3: Reclamação

```
📬 Email Recebido: "Produto veio quebrado"
🎯 Intenção: reclamacao
🚨 Agente: Reclamações
📤 Resposta: Protocolo de atendimento e solução
```

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para detalhes.

## 👥 Autores

- **Pablo Dantas** - *Desenvolvimento Inicial* - [Link do meu Assistente](https://interactive-resume-pablo.streamlit.app/)

## 🙏 Agradecimentos

- Equipe Ollama pelo modelo Llama3
- Google pelas APIs do Gmail
- Comunidade Python pelas bibliotecas incríveis
- Sem essas tecnologias, esse projeto não poderia ser desenvolvido

---

**⭐ Se este projeto foi útil, deixe uma estrela no repositório!**

---

# requirements.txt

```txt
google-auth-oauthlib==0.4.6
google-auth-httplib2==0.1.0
google-api-python-client==2.80.0
ollama==0.1.7
sqlite3
datetime
email
base64
re
os
time
json
```

*Nota: sqlite3, datetime, email, base64, re, os, time e json são bibliotecas padrão do Python*
