# Guia Prático de Consultas SQL (SQLite)

Este documento contém uma coletânea de consultas SQL prontas e comentadas para análise do banco de dados de compras públicas (`data/licitacoes.db`). 

As consultas estão divididas em pacotes (bundles) temáticos para facilitar a exploração dos dados pela equipe durante o desenvolvimento e a preparação das apresentações do hackathon.

---

## Tabela de Conteúdos
1. [Conhecimento Geral do Banco (Estrutural)](#1-conhecimento-geral-do-banco-estrutural)
2. [Filtros de Localização e Busca Textual (Operacional)](#2-filtros-de-localizacao-e-busca-textual-operacional)
3. [Análises Estatísticas de Estimativas (Stage 1)](#3-analises-estatisticas-de-estimativas-stage-1)
4. [Análises Estatísticas de Vencedores e Resultados (Stage 2)](#4-analises-estatisticas-de-vencedores-e-resultados-stage-2)
5. [Cruzamento de Dados e Indicadores de Economia (Auditoria)](#5-cruzamento-de-dados-e-indicadores-de-economia-auditoria)

---

## 1. Conhecimento Geral do Banco (Estrutural)
Comandos para verificar o status atual da coleta, tamanho das tabelas e formatos dos dados.

### 1.1 Contagem de registros por tabela
Mapeia a quantidade total de dados salvos no banco.
```sql
SELECT 
  (SELECT COUNT(*) FROM editais) AS total_editais,
  (SELECT COUNT(*) FROM itens) AS total_itens,
  (SELECT COUNT(*) FROM resultados_itens) AS total_resultados;
```

### 1.2 Estrutura interna das tabelas (Schema)
Retorna as colunas e os tipos de dados configurados em cada tabela (recurso interno do SQLite).
```sql
-- Estrutura da tabela de editais
PRAGMA table_info(editais);

-- Estrutura da tabela de itens
PRAGMA table_info(itens);

-- Estrutura da tabela de resultados
PRAGMA table_info(resultados_itens);
```

### 1.3 Amostra rápida dos primeiros registros
Retorna as primeiras 5 linhas de cada tabela para conferência visual do formato dos payloads.
```sql
SELECT * FROM editais LIMIT 5;
```

---

## 2. Filtros de Localização e Busca Textual (Operacional)
Comandos focados na busca pontual de informações e filtragem de escopo por texto.

### 2.1 Filtrar compras por município ou estado
Substitua a sigla da UF ou o nome do município para consultar regiões específicas.
```sql
-- Filtrar por Estado (Paraíba)
SELECT numero_controle_pncp, municipio, objeto, valor_estimado 
FROM editais 
WHERE uf = 'PB';

-- Filtrar por Município (busca aproximada usando LIKE)
SELECT numero_controle_pncp, uf, municipio, objeto, valor_estimado 
FROM editais 
WHERE municipio LIKE '%João Pessoa%';
```

### 2.2 Busca por palavra-chave na descrição do objeto
Pesquisa editais que mencionam termos específicos no resumo do edital.
```sql
SELECT numero_controle_pncp, municipio, objeto, valor_estimado 
FROM editais 
WHERE objeto LIKE '%merenda%' 
   OR objeto LIKE '%alimentacao%';
```

### 2.3 Busca de itens específicos por especificação técnica
Pesquisa na tabela de itens por termos que definem o produto licitado.
```sql
SELECT numero_controle_pncp, numero_item, descricao, quantidade, valor_total 
FROM itens 
WHERE descricao LIKE '%computador%' 
   OR descricao LIKE '%notebook%';
```

### 2.4 Filtrar compras por situação cadastral
Filtra os editais por status atual da licitação no PNCP (ex: Publicada, Homologada, Suspensa).
```sql
SELECT numero_controle_pncp, municipio, objeto, situacao_compra_nome 
FROM editais 
WHERE situacao_compra_nome = 'Homologada';
```

---

## 3. Análises Estatísticas de Estimativas (Stage 1)
Estatísticas calculadas sobre os orçamentos estimados e o planejamento das prefeituras.

### 3.1 Maiores orçamentos estimados por município
Identifica os editais com maior previsão de gasto financeiro.
```sql
SELECT numero_controle_pncp, municipio, orgao_nome, valor_estimado 
FROM editais 
WHERE valor_estimado IS NOT NULL 
ORDER BY valor_estimado DESC 
LIMIT 10;
```

### 3.2 Total de gastos estimados agrupados por município
Calcula o total planejado de compras públicas somado por cidade no banco de dados.
```sql
SELECT 
  municipio, 
  uf,
  COUNT(*) AS total_editais,
  SUM(valor_estimado) AS soma_estimada,
  ROUND(AVG(valor_estimado), 2) AS media_estimada_por_edital
FROM editais 
GROUP BY municipio, uf 
ORDER BY soma_estimada DESC;
```

### 3.3 Concentração de compras por órgão público
Mostra quais entidades governamentais possuem o maior número de processos de compras.
```sql
SELECT 
  orgao_cnpj, 
  orgao_nome, 
  COUNT(*) AS quantidade_processos,
  SUM(valor_estimado) AS total_estimado
FROM editais 
GROUP BY orgao_cnpj 
ORDER BY quantidade_processos DESC 
LIMIT 10;
```

### 3.4 Estatísticas da modalidade de contratação
Identifica quais modalidades de licitação concentram o maior fluxo financeiro.
```sql
SELECT 
  modalidade_nome, 
  COUNT(*) AS quantidade,
  SUM(valor_estimado) AS total_estimado
FROM editais 
GROUP BY modalidade_nome 
ORDER BY total_estimado DESC;
```

---

## 4. Análises Estatísticas de Vencedores e Resultados (Stage 2)
Análises baseadas nas homologações e no perfil das empresas que venceram as licitações.

### 4.1 Concentração de mercado (Fornecedores que mais arrecadaram)
Lista os maiores vencedores financeiros das disputas no banco.
```sql
SELECT 
  fornecedor_nome, 
  fornecedor_cnpj, 
  COUNT(DISTINCT numero_controle_pncp) AS contratos_vencidos,
  SUM(valor_homologado_total) AS total_arrecadado
FROM resultados_itens 
WHERE situacao_resultado IN ('Homologado', 'Informado')
GROUP BY fornecedor_cnpj 
ORDER BY total_arrecadado DESC 
LIMIT 10;
```

### 4.2 Fornecedores com maior número de itens individuais vencidos
Indica empresas que ganham licitações recorrentemente em grande volume de itens físicos.
```sql
SELECT 
  fornecedor_nome, 
  COUNT(*) AS total_itens_vencidos 
FROM resultados_itens 
WHERE situacao_resultado IN ('Homologado', 'Informado') 
GROUP BY fornecedor_cnpj 
ORDER BY total_itens_vencidos DESC 
LIMIT 10;
```

### 4.3 Estatísticas de status dos resultados dos itens
Demonstra quantos itens foram homologados com sucesso versus quantos restaram desertos (sem interessados) ou fracassados.
```sql
SELECT 
  situacao_resultado, 
  COUNT(*) AS total_itens,
  ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM resultados_itens)), 2) AS percentual
FROM resultados_itens 
GROUP BY situacao_resultado 
ORDER BY total_itens DESC;
```

---

## 5. Cruzamento de Dados e Indicadores de Economia (Auditoria)
Consultas avançadas unindo as tabelas de itens estimados e resultados reais para gerar inteligência de mercado e insights de auditoria de compras.

### 5.1 Desconto médio obtido por município
Identifica quais municípios conseguiram as maiores margens médias de desconto nas compras homologadas.
```sql
SELECT 
  e.municipio, 
  e.uf,
  COUNT(r.numero_item) AS itens_analisados,
  ROUND(SUM(i.valor_total), 2) AS total_estimado_R$,
  ROUND(SUM(r.valor_homologado_total), 2) AS total_pago_R$,
  ROUND(SUM(i.valor_total) - SUM(r.valor_homologado_total), 2) AS economia_total_R$,
  ROUND(((SUM(i.valor_total) - SUM(r.valor_homologado_total)) / SUM(i.valor_total)) * 100, 2) AS percentual_economia_medio
FROM resultados_itens r
JOIN itens i ON r.numero_controle_pncp = i.numero_controle_pncp AND r.numero_item = i.numero_item
JOIN editais e ON r.numero_controle_pncp = e.numero_controle_pncp
WHERE r.situacao_resultado IN ('Homologado', 'Informado') 
  AND i.valor_total > 0
GROUP BY e.municipio, e.uf
HAVING economia_total_R$ > 0
ORDER BY percentual_economia_medio DESC;
```

### 5.2 Itens específicos com maior economia percentual
Mostra compras individuais onde a disputa gerou maior queda de preço relativo.
```sql
SELECT 
  e.municipio,
  i.descricao AS item_descricao,
  i.quantidade,
  i.valor_unitario AS preco_estimado,
  r.valor_homologado_unitario AS preco_contratado,
  ROUND(((i.valor_total - r.valor_homologado_total) / i.valor_total) * 100, 2) AS economia_percentual
FROM resultados_itens r
JOIN itens i ON r.numero_controle_pncp = i.numero_controle_pncp AND r.numero_item = i.numero_item
JOIN editais e ON r.numero_controle_pncp = e.numero_controle_pncp
WHERE r.situacao_resultado IN ('Homologado', 'Informado')
  AND i.valor_total > 0
ORDER BY economia_percentual DESC
LIMIT 15;
```

### 5.3 Auditoria de anomalias (Preço homologado superior ao estimado)
Consulta preventiva para auditar itens que foram homologados por valores superiores à estimativa oficial inicial do órgão comprador (possível sobrepreço ou distorção de cadastro).
```sql
SELECT 
  e.municipio,
  e.orgao_nome,
  i.descricao AS item_descricao,
  i.valor_total AS total_estimado,
  r.valor_homologado_total AS total_homologado,
  ROUND(r.valor_homologado_total - i.valor_total, 2) AS diferenca_excedente_R$
FROM resultados_itens r
JOIN itens i ON r.numero_controle_pncp = i.numero_controle_pncp AND r.numero_item = i.numero_item
JOIN editais e ON r.numero_controle_pncp = e.numero_controle_pncp
WHERE r.situacao_resultado IN ('Homologado', 'Informado')
  AND r.valor_homologado_total > i.valor_total
ORDER BY diferenca_excedente_R$ DESC;
```
