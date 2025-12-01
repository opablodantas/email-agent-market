# 📧 Email Agent Market - Sistema Automatizado de Resposta a Emails

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![IA](https://img.shields.io/badge/IA-RAG--Ollama-green)
![Gmail](https://img.shields.io/badge/API-Gmail-red)
![Status](https://img.shields.io/badge/Status-Production%20Ready-success)

## 📖 Sobre o Projeto

### Para as pessoas menos técnicas 🤔
Imagine um "atendente virtual inteligente" que lê e responde automaticamente os emails da sua empresa, 24 horas por dia, 7 dias por semana. Ele conhece todos os seus produtos, políticas e procedimentos e responde cada cliente de forma personalizada e precisa, como se fosse um funcionário humano altamente treinado além da sua alta disponibilidade.

### Detalhes Técnicos 🛠️
Sistema de automação de emails baseado em **RAG (Retrieval-Augmented Generation)** que combina:
- **API do Gmail** para monitoramento em tempo real
- **Ollama com Llama3**, o LLM para geração de respostas inteligentes
- **Base de conhecimento empresarial** para respostas precisas
- **Detecção multi-intenção** para classificação automática
- **Rate limiting inteligente** para evitar spam

## 🎯 Objetivo do Projeto

Transformar a produtividade da sua equipe através da automação inteligente de comunicação por email:

| Benefício | Impacto |
|-----------|---------|
| ⏱️ **Economia de Tempo** | Redução de pelo menos 50% no tempo gasto com emails rotineiros |
| 📈 **Aumento de Eficiência** | Respostas instantâneas 24/7 sem intervenção humana |
| ✨ **Melhoria na Qualidade** | Respostas consistentes e com poucos erros de digitação |
| 🔄 **Redução de Erros** | Eliminação de inconsistências na comunicação |
| 🎯 **Foco em Prioridades** | Equipe livre para demandas estratégicas |
| 😊 **Satisfação Dupla** | Clientes e colaboradores mais felizes |

**Resultado Final:** Equipes mais produtivas, menos estressadas e clientes mais satisfeitos com atendimento rápido e preciso.

## 🚀 Funcionalidades Principais

### 🤖 Agentes Especializados
- **Agente de Pedidos**: Orçamentos automáticos baseados no catálogo
- **Agente de Dúvidas**: Respostas precisas sobre prazos, produtos, políticas
- **Agente de Reclamações**: Processo automatizado para trocas e garantias
- **Agente Financeiro**: Condições de pagamento e descontos
- **Agente de Entregas**: Informações de prazos e fretes

### 🧠 Inteligência Artificial
- **Detecção Multi-Intenção**: Identifica automaticamente o que o cliente precisa
- **RAG Contextual**: Respostas baseadas EXCLUSIVAMENTE nos dados da empresa
- **Rate Limiting Inteligente**: Evita spam para o mesmo cliente
- **Controle de Estado**: Nunca responde o mesmo email duas vezes

### 📊 Monitoramento
- Verificação automática a cada **5 minutos**
- Logs detalhados em tempo real
- Histórico completo de interações
- Estatísticas de performance

## 📋 Requisitos

### Requisitos Mínimos
- **Python 3.8** ou superior
- **Conta Gmail** com acesso à API
- **Ollama** instalado com modelo **Llama3**
- **4GB RAM** mínima
- **Conexão internet** estável

### Arquivos de Configuração
- `credentials.json` (Google API)
- `produtos.txt` (Catálogo de produtos)
- `politicas.txt` (Políticas da empresa)
- `financeiro.txt` (Condições financeiras)
- `entregas.txt` (Prazos e fretes)

## 🛠️ Instalação

### 1. Clone o Repositório
```bash
git clone https://github.com/seu-usuario/email-agent-market.git
cd email-agent-market
```

### 2. Instale as Dependências
```bash
pip install requirements.txt
```

### 3. Configure as Credenciais do Google
1. Acesse [Google Cloud Console](https://console.cloud.google.com)
2. Crie um projeto e ative a Gmail API
3. Baixe o arquivo `credentials.json` para a pasta do projeto

### 4. Configure a Base de Conhecimento
Crie os arquivos com as informações da sua empresa:

**produtos.txt**
```
CATÁLOGO DE PRODUTOS:

PANELAS:
- Panela Antiaderente 24cm: R$ 89,90 | Código: PAN24
- Panela Antiaderente 28cm: R$ 119,90 | Código: PAN28

TALHERES:
- Talheres Inox 24 peças: R$ 129,90 | Código: TAL24

DESCONTOS:
- Acima de R$ 500: 5% desconto
- Acima de R$ 1000: 10% desconto
```

**politicas.txt**
```
POLÍTICAS DA EMPRESA:

TROCAS E DEVOLUÇÕES:
- Prazo para trocas: 30 dias
- Produtos com defeito: 90 dias de garantia
- Necessário nota fiscal
```

### 5. Execute o Sistema
```bash
python email_agent.py
```

## 📁 Estrutura do Projeto

```
email-agent-market/
├── email_agent.py          # Arquivo principal
├── credentials.json        # Credenciais Google API
├── token.json             # Token de autenticação (gerado automaticamente)
├── clientes.db           # Banco de dados SQLite
├── produtos.txt          # Catálogo de produtos
├── politicas.txt         # Políticas da empresa
├── financeiro.txt        # Condições financeiras
├── entregas.txt          # Informações de entrega
└── README.md            # Este arquivo
```

## 🔧 Como Funciona

### Fluxo do Sistema
1. **Monitoramento**: Verifica novos emails a cada 5 minutos
2. **Classificação**: Detecta automaticamente as intenções do cliente
3. **Contextualização**: Busca informações relevantes nos arquivos RAG
4. **Geração**: Cria resposta personalizada usando Ollama + contexto
5. **Envio**: Responde o email automaticamente
6. **Registro**: Marca como processado para evitar duplicatas

### Exemplo de Funcionamento
**Email Recebido:**
```
Assunto: Problema com panela
Corpo: Comprei uma panela e veio com defeito. Como faço a troca?
```

**Resposta Automática:**
```
Prezado cliente,

Conforme nossas políticas, o prazo para trocas é de 30 dias...
Para iniciar o processo, envie fotos para sac@empresa.com.br...
```

## 🎯 Casos de Uso

### Varejo (Projeto Original)
- Lojas de utensílios domésticos
- Comércio eletrônico
- Distribuidoras
- Atacado

### Adaptação para Outros Ramos
- **Serviços**: Consultorias, agências
- **Saúde**: Clínicas, laboratórios, hospitais
- **Educação**: Escolas, cursos, universidades
- **Imobiliária**: Corretores, incorporadoras

**Como adaptar:** Basta substituir os arquivos RAG pelo conhecimento específico do seu ramo!


## 📄 Licença

Distribuído sob licença MIT. Veja `LICENSE` para mais informações.

## 👥 Autor

- **Pablo Dantas** - *Desenvolvimento Inicial* - [Pablo Dantas](https://www.linkedin.com/in/pablodantasevangelista/)

## 🙏 Agradecimentos

- Equipe do Ollama pelos modelos de IA
- Google pela API Gmail
- Comunidade Python pelas bibliotecas incríveis

---

## 💡 Conclusão

Este projeto representa a **evolução da produtividade empresarial** através da inteligência artificial. Mais do que um simples automatizador de emails, é um **assistente inteligente** que:

- 🧠 **Aprende** com a base de conhecimento da empresa
- ⚡ **Responde** com velocidade e precisão  
- 🔄 **Escala** para atender milhares de clientes
- 💰 **Economiza** recursos valiosos e tempo
- 😊 **Satisfaz** tanto clientes quanto colaboradores



---

<div align="center">

**⭐ Se este projeto te ajudou, deixe uma estrela no repositório!**

</div>