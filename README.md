# ⚓ NavegAI v3.2

> **Laboratório de Inteligência Artificial para Gestão Pública**
> 
> SEPAF — Secretaria de Planejamento e Gestão Pública  
> Prefeitura de Navegantes, Santa Catarina, Brasil

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32%2B-FF4B4B)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Em%20Produ%C3%A7%C3%A3o-success)](https://projetosia.streamlit.app)

---

## 🎯 Uso da IA para Chat com Dados da Plataforma Congres

NavegAI transforma perguntas em linguagem natural em análises executivas com gráficos interativos em tempo real. Um gestor público pode perguntar *"Quais os 5 projetos mais caros em andamento?"* e receber uma resposta completa — com ranking, gráfico de barras e narrativa executiva — em menos de 3 segundos.

### O que era antes:
- ❌ Consultas manuais a múltiplos sistemas
- ❌ Respostas demoradas para tomada de decisão
- ❌ Dados fragmentados em silos

### O que é agora:
- ✅ Chat inteligente com linguagem natural
- ✅ Resposta em 3 segundos
- ✅ 12 views integradas da plataforma Congres
- ✅ Baixa alucinação SQL (arquitetura determinística)

---

## 🏗️ Arquitetura

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  Streamlit App  │  ←──→   │  Agente SQL      │  ←──→   │  Cloud SQL      │
│  (Interface)    │  HTTPS  │  (Python Puro)   │  TCP    │  (congres_db)   │
└─────────────────┘         └──────────────────┘         └─────────────────┘
        ↑                           ↑
   Usuário faz pergunta      LLM extrai intenção
   em linguagem natural      (JSON estruturado)
```

### Pipeline de Processamento

1. **🧠 Extrator de Intenção (LLM)** — Analisa a pergunta e extrai parâmetros em JSON
2. **🔒 Construtor SQL (Python Puro)** — Monta a query SQL de forma 100% determinística
3. **⚡ Agente SQL** — Executa a query no Cloud SQL e retorna DataFrame
4. **📊 Motor de Visualização** — Gera gráficos interativos com Apache ECharts
5. **🎤 Narrador Executivo** — Gera narrativa profissional em português

---

## 📊 Views Inteligentes (12)

| View | Descrição |
|------|-----------|
| `vw_ia_engajamento_acesso_completo` | Acesso completo com secretaria |
| `vw_ia_engajamento_acesso` | Acesso básico de usuários |
| `vw_ia_engajamento_faixas` | Faixas temporais de inatividade |
| `vw_projetos_inteligencia` | Projetos e investimentos |
| `vw_projetos_executivo` | Visão executiva consolidada |
| `vw_ia_tarefas_operacional` | Tarefas e prazos |
| `vw_ia_tarefas_completa` | Tarefas com responsáveis |
| `vw_ia_usuarios_secretaria` | Total de usuários por secretaria |
| `vw_ia_indicadores_pem` | Indicadores PEM com metas |
| `vw_ia_rotinas_usuarios` | Rotinas com usuários vinculados |
| `vw_ia_tags_classificacao` | Tags e classificações |
| `vw_ia_usuarios_perfil` | Perfil completo dos usuários |
| `vw_ia_projetos_pm_completa` | Projetos PM com itens |

---

## 🚀 Deploy no Streamlit Cloud

### Secrets Necessários

Configure em **Settings > Secrets**:

```toml
GOOGLE_API_KEY = "sua_chave_api_gemini"
DB_HOST = "34.39.146.2"
DB_PORT = "3306"
DB_USER = "root"
DB_PASSWORD = "sua_senha"
DB_NAME = "congres_db"
```

### Deploy Automático

O deploy é automático a cada push na branch `main`.

---

## 🛡️ Segurança

- ✅ **Zero SQL Injection** — LLM nunca gera SQL livre
- ✅ **Validação de Views** — Apenas views do catálogo são aceitas
- ✅ **Operadores Fechados** — `=`, `!=`, `<`, `>`, `<=`, `>=`, `LIKE`
- ✅ **Sanitização** — Inputs escapados antes da query
- ✅ **Pool de Conexões** — SQLAlchemy QueuePool com timeout

---

## 📁 Estrutura do Projeto

```
projetosia/
├── navegai_v33.py          # Aplicação principal
├── requirements.txt        # Dependências
├── .streamlit/
│   └── config.toml         # Configurações do tema
├── README.md               # Este arquivo
└── docs/
    └── index.html          # Storytelling do projeto
```

---

## 📜 Licença

Distribuído sob a licença MIT.

---

<div align="center">

**⚓ NavegAI v3.2**  
*Cloud SQL | Arquitetura Determinística | Baixa Alucinação | 2026*

Prefeitura de Navegantes — Santa Catarina — Brasil

</div>
