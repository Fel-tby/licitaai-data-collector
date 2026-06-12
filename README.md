# licitaai-data-collector

Crawler assincrono para coleta de dados de licitacoes publicas via API do PNCP (Portal Nacional de Contratacoes Publicas).

Este repositorio foi construido como parte da solucao **LicitaAI**, segundo lugar do hackaton SACC 2026, cuja tematica era inteligencia artificial aplicada a transparencia e analise de dados publicos.

O crawler foi a camada de coleta: busca, pagina e persiste os dados brutos do PNCP em um banco SQLite local para que a interface de consulta em linguagem natural possa operar sobre eles.

---

## O que o crawler faz

O codigo opera em dois estagios sequenciais. No primeiro, conecta-se a API publica do PNCP e coleta os editais publicados dentro de uma janela de tempo configuravel, disparando chamadas paralelas para extrair os itens licitados e os respectivos valores estimados de cada contratacao. No segundo, busca de forma incremental os resultados homologados, identificando os fornecedores vencedores e os valores finais adjudicados por item.

Toda a persistencia e feita em SQLite com modo WAL, em `data/licitacoes.db`. O progresso e salvo em checkpoints por lote temporal e modalidade, o que permite retomar execucoes interrompidas sem repetir consultas ja concluidas.

---

## Estrutura do repositorio

```text
app.py              # CLI principal: orquestra os dois estagios de coleta
pncp_crawler.py     # Clientes HTTP sincrono e assincrono para a API do PNCP
db.py               # Persistencia e leitura do SQLite
requirements.txt    # Dependencias
docs/               # Documentacao complementar
```

---

## Instalacao

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Execucao

Teste sem conexao de rede, usando dados simulados:

```bash
python app.py --mock --stage 1
python app.py --mock --stage 2
```

Coleta real contra a API do PNCP para o estado da Paraiba:

```bash
python app.py --todas-modalidades --stage 1
python app.py --stage 2
```

Parametros uteis:

- `--dias <N>`: janela retroativa de busca em dias (padrao: 360).
- `--max-paginas <N>`: limita paginas por modalidade por mes, util em testes rapidos.
- `--concurrency <N>`: numero de requisicoes simultaneas no Stage 2 (padrao: 20).

---

## Visualizacao dos dados

```bash
datasette data/licitacoes.db
```

Abre uma interface web local em `http://127.0.0.1:8001` para navegar pelas tabelas, filtrar registros e executar queries customizadas.
