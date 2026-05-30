# Interface de Inteligência Artificial para Consulta de Compras Públicas

Este projeto tem como objetivo facilitar o acesso aos dados de compras públicas municipais. 

A proposta final é permitir que qualquer cidadão ou gestor interaja com os dados de licitações municipais por meio de uma interface de chatbot com Inteligência Artificial, traduzindo perguntas em linguagem natural (como "Quanto o município gastou com merenda escolar?") em consultas diretas ao banco de dados local.

Este repositório contém a base inicial do projeto: o módulo de coleta de dados (crawler) assíncrono de alta performance e o banco de dados relacional.

---

## Funcionamento básico

Para estruturar as informações que alimentam a interface de perguntas, o sistema executa duas etapas básicas de forma altamente concorrente:

1.  **Etapa 1 (Coleta de Editais e Itens - Stage 1):** O sistema conecta-se ao portal público do governo (PNCP), coleta as licitações ativas da região e a lista de itens com seus respectivos valores estimados. As chamadas de páginas e detalhamentos de itens ocorrem em paralelo.
2.  **Etapa 2 (Identificação dos Vencedores - Stage 2):** O sistema busca os resultados homologados e adjudicados para identificar quais fornecedores venceram cada disputa e os valores finais contratados. Ele opera de forma incremental, registrando status por item para evitar reconsultas redundantes.

Todas as informações coletadas são armazenadas localmente no arquivo de banco de dados SQLite otimizado (modo WAL) em `data/licitacoes.db`.

---

## Instalação e Preparação do Ambiente

Recomenda-se a utilização de um ambiente virtual (venv) para isolar as dependências do projeto e evitar conflitos. Siga os passos no terminal dentro da pasta do projeto:

### 1. Criar o Ambiente Virtual:
```bash
python -m venv .venv
```

### 2. Ativar o Ambiente Virtual:
*   **No Windows (PowerShell):**
    ```powershell
    .venv\Scripts\Activate.ps1
    ```
*   **No Windows (Prompt de Comando/CMD):**
    ```cmd
    .venv\Scripts\activate.bat
    ```
*   **No macOS ou Linux:**
    ```bash
    source .venv/bin/activate
    ```

### 3. Instalar as Dependências:
Com o ambiente ativado, instale as bibliotecas necessárias:
```bash
pip install -r requirements.txt
```

---

## Execução e Testes do Coletor

O coletor pode ser executado em modo de simulação (offline) ou com dados reais (online).

### Opção A: Simulação Offline (Mock)
Útil para testar o comportamento do código rapidamente e sem dependência de conexão de rede:
```bash
# Simula a coleta de editais e itens
python app.py --mock --stage 1

# Simula a coleta de resultados de vencedores
python app.py --mock --stage 2
```

### Opção B: Coleta Real Completa (Produção)
Para buscar todos os dados reais diretamente do portal do governo do estado da Paraíba (PB):

```bash
# Etapa 1: Coleta real completa de editais e itens estimados (Todas as 14 modalidades)
python app.py --todas-modalidades --stage 1

# Etapa 2: Coleta real e incremental de resultados de homologação/vencedores (Em lotes concorrentes)
python app.py --stage 2
```

#### Parâmetros Úteis de Customização:
*   `--max-paginas <N>`: Limita a quantidade máxima de páginas coletadas por mês por modalidade (útil para testes rápidos, ex: `--max-paginas 5`). Se omitido, a coleta é ilimitada (full).
*   `--dias <N>`: Define a janela retrospectiva em dias (padrão: 360 dias).
*   `--concurrency <N>`: Ajusta o limite de requisições de rede paralelas concorrentes no Stage 2 (padrão: 20).

---

## Visualização dos Dados via Interface Web

Para visualizar e filtrar os dados do banco de forma rápida sem escrever código SQL:

1. Garanta que o ambiente virtual está ativo (`.venv`).
2. Execute o servidor local do Datasette apontando para o banco do projeto:
   ```bash
   datasette data/licitacoes.db
   ```
3. Acesse o endereço retornado no terminal (por padrão, `http://127.0.0.1:8001`) no seu navegador.

A interface permite navegar pelas tabelas, aplicar filtros simples por coluna e executar consultas personalizadas.

---

## Planejamento do Desenvolvimento

O trabalho a ser desenvolvido consiste em três pilares principais:

*   **1. Taxonomia e Categorização:** Implementação de script para classificar os itens licitados em categorias de interesse (como Saúde, Educação, Tecnologia e Alimentação).
*   **2. Cérebro da IA (Text-to-SQL):** Integração com API de modelo de linguagem (LLM) para traduzir perguntas em linguagem natural para queries SQL estruturadas.
*   **3. Interface de Chatbot e Dashboard:** Criação de uma interface web simples e interativa para interação com o usuário final.
