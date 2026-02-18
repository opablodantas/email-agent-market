# 📧 Email Agent Market v2.0 - Sistema MLOps com A/B Testing para Atendimento Inteligente

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![MLOps](https://img.shields.io/badge/MLOps-A%2FB%20Testing-orange)
![RAG](https://img.shields.io/badge/RAG-Contextual-green)
![Gmail](https://img.shields.io/badge/API-Gmail-red)
![Ollama](https://img.shields.io/badge/Ollama-Multiple%20Models-yellow)

## 📖 Sobre o Projeto

### Para as pessoas menos técnicas 
Imagine um "atendente virtual inteligente" que **aprende e melhora com o tempo** - como um funcionário que fica mais experiente a cada dia! Ele lê e responde automaticamente os emails da sua empresa, 24/7, mas com um diferencial revolucionário: **ele testa diferentes formas de responder** para descobrir qual delas os clientes preferem, exatamente como fazemos com campanhas de marketing.

### Para profissionais técnicos 🛠️
Sistema completo de automação de emails com **arquitetura MLOps**, combinando:
- **RAG (Retrieval-Augmented Generation)** para respostas baseadas em conhecimento empresarial
- **A/B Testing em produção** entre múltiplos modelos LLM (Llama3, Mistral, Neural-Chat)
- **LLM-as-a-Judge** para avaliação automática da qualidade das respostas
- **Dashboard em tempo real** com métricas de performance
- **Log estruturado** para auditoria e análise histórica

## 🚀 Principais Inovações da v2.0

### 🎲 **A/B Testing em Produção**
- **Múltiplos Modelos**: Testa simultaneamente Llama3, Mistral, Neural-Chat e mais um modelo
- **Seleção Ponderada**: Distribuição baseada em pesos configuráveis
- **Métricas Comparativas**: Acompanhe qual modelo tem melhor performance
- **Sem Interrupção**: Experimentos rodam em produção sem afetar usuários

### ⚖️ **LLM Juiz Automático**
- **Avaliação Multi-Critério**: Clareza, precisão, empatia, profissionalismo
- **Feedback Estruturado**: Cada resposta recebe nota detalhada (0-100)
- **Log Completo em TXT**: Auditoria total de todas as avaliações
- **Thread Safety**: Avaliações assíncronas sem bloquear respostas

### 📊 **Dashboard MLOPS em Tempo Real**
```
📈 Acesse: http://localhost:8081
```
- Estatísticas de uso por modelo
- Distribuição real vs planejada do A/B Testing
- Últimas avaliações com notas e feedback
- Status completo do sistema
- Log das avaliações para download

### 💾 **Sistema de Persistência Robusto**
- **Banco SQLite**: Histórico completo de respostas e avaliações
- **Log TXT Acumulativo**: Todas as avaliações em arquivo legível
- **Cache Inteligente**: Evita reprocessamento de emails
- **Rate Limiting**: Controle de frequência por cliente

## 🎯 Objetivos do Projeto

| Benefício | Impacto na v2.0 |
|-----------|-----------------|
| 🔬 **Tomada de Decisão Baseada em Dados** | Métricas reais de performance dos LLMs |
| ⚡ **Resiliência** | Fallback automático entre modelos |
| 📊 **Visibilidade Total** | Dashboard completo com todas as métricas |
| 🎯 **Otimização de Custos** | Identifica modelos mais eficientes |

## 🤖 Modelos Suportados

### Modelos Pré-configurados
| Modelo | Descrição | Peso Padrão |
|--------|-----------|-------------|
| `llama3` | Llama 3 Padrão | 1.0 |
| `mistral` | Mistral 7B | 1.0 |
| `llama3.1:8b` | Llama 3.1 8B | 1.0 |
| `neural-chat` | Neural Chat 7B | 1.0 |

### Detecção Automática
- Verifica modelos instalados no Ollama
- Fallback inteligente para variantes (ex: `llama3:latest`)
- Log de disponibilidade na inicialização

## 📋 Requisitos

### Requisitos Mínimos
- **Python 3.8+**
- **Ollama** com modelos instalados
- **Conta Gmail** com API habilitada
- **4GB+ RAM** (recomendado 8GB para múltiplos modelos)

### Arquivos Necessários
```
credentials.json          # Credenciais Google API
produtos.txt             # Catálogo de produtos
politicas.txt            # Políticas da empresa
financeiro.txt           # Condições financeiras
entregas.txt            # Informações de entrega
```

## 🛠️ Instalação Rápida

### 1. Clone e Configure
```bash
git clone https://github.com/seu-usuario/email-agent-market.git
cd email-agent-market
pip install -r requirements.txt
```

### 2. Configure os Modelos Ollama
```bash
# Instale os modelos desejados
ollama pull llama3
ollama pull mistral
ollama pull neural-chat
```

### 3. Configure a Base de Conhecimento
Crie os arquivos de contexto conforme exemplos na documentação.

### 4. Execute o Sistema
```bash
python main.py
```

## 🎮 Como Usar

### Acessando o Dashboard
```
🌐 http://localhost:8081
```

### Configurando o A/B Testing
No arquivo `main.py`, ajuste:
```python
AB_MODELS = [
    {"name": "llama3", "description": "Llama 3", "weight": 2.0},  # Mais chance
    {"name": "mistral", "description": "Mistral", "weight": 1.0},
]
```

### Visualizando Avaliações
```
📝 Log completo: avaliacoes_llm_juiz.txt
📊 Dashboard: http://localhost:8081
📈 Dados JSON: http://localhost:8081/data
```

## 📁 Estrutura do Projeto

```
email-agent-market/
├── main.py                 # Sistema principal (v2.0)
├── mlops.db                # Banco MLOPS (A/B testing + avaliações)
├── clientes.db             # Banco de emails processados
├── avaliacoes_llm_juiz.txt # Log completo das avaliações
├── credentials.json        # Credenciais Google
├── token.json              # Token de autenticação
├── produtos.txt            # Base de conhecimento
├── politicas.txt           # Políticas da empresa
├── financeiro.txt          # Informações financeiras
├── entregas.txt            # Dados de entrega
└── README.md               # Documentação
```

## 🔬 Como Funciona o MLOPS

### Fluxo de Decisão
1. **Email Chega** → Detecção de intenções
2. **Seleção de Modelo** → A/B Testing baseado em pesos (mas no meu experimento, todos os modelos tem o mesmo peso)
3. **Geração com RAG** → Contexto + modelo selecionado
4. **Resposta e Registro** → Salva no banco e envia
5. **Avaliação Automática** → LLM Juiz avalia a resposta
6. **Dashboard Atualizado** → Métricas em tempo real

### Exemplo de Avaliação
```
AVALIAÇÃO #42 - 15/03/2024 14:30:22
📧 Cliente: cliente@email.com
🤖 Modelo: llama3
📊 Pontuações:
   • Clareza: 92/100
   • Precisão: 88/100
   • Empatia: 85/100
   • PONTUAÇÃO GERAL: 89.5/100
```

## 📊 Dashboard em Ação

### Cards Principais
- **Respostas Enviadas** - Total processado
- **Avaliações Realizadas** - Total de análises
- **Modelos Ativos** - Quantidade em teste
- **Nota Média** - Performance geral

### Gráficos e Tabelas
- Distribuição de uso por modelo
- Avaliações recentes com notas
- Estatísticas de seleção do A/B Testing
- Status completo do sistema

## 📄 Licença

MIT License - Use, modifique e distribua livremente.

## 👥 Autor

**Pablo Dantas** - [LinkedIn](https://www.linkedin.com/in/pablodantasevangelista/)

## 🙏 Agradecimentos

- Comunidade Ollama pelos modelos excepcionais
- Google pela API Gmail 
- Contribuidores que sugerirem melhorias

---

## 💡 Por que esse projeto eu considero empolgante?

Este projeto não é apenas um automatizador de emails - é um **laboratório de experimentação em produção** que pode ajudar a:

1. **Aprende Continuamente**: Cada resposta é uma oportunidade de aprendizado
2. **Toma Decisões Baseadas em Dados**: Não é "achismo", são métricas reais
3. **Escala com Inteligência**: Mais emails = mais dados = melhores decisões
4. **Garante Qualidade**: LLM Juiz mantém padrão consistente
5. **É Transparente**: Dashboard e logs mostram exatamente o que acontece

---
