import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone

DB_PATH = Path("data/licitacoes.db")

def get_connection() -> sqlite3.Connection:
    """Retorna uma conexao ativa com o banco de dados SQLite otimizada para escrita pesada."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Aumenta timeout de conexao para 30s
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    # Otimizacoes para escrita e leitura concomitantes (WAL)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Cria as tabelas relacionais de editais, itens, resultados, checkpoints e status se nao existirem."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Tabela de Editais (Planejamento / Divulgacao da compra)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS editais (
            numero_controle_pncp TEXT PRIMARY KEY,
            uf TEXT NOT NULL,
            municipio TEXT,
            orgao_cnpj TEXT,
            orgao_nome TEXT,
            objeto TEXT,
            data_abertura TEXT,
            data_encerramento TEXT,
            valor_estimado REAL,
            modalidade_nome TEXT,
            situacao_compra_nome TEXT,
            modalidade_id INTEGER,
            tipo_contratacao TEXT,
            raw_json TEXT,
            collected_at TEXT
        );
    """)

    # 2. Tabela de Itens Estimados (Itens originalmente previstos no edital)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itens (
            numero_controle_pncp TEXT NOT NULL,
            numero_item INTEGER NOT NULL,
            lote INTEGER,
            descricao TEXT,
            quantidade REAL,
            valor_unitario REAL,
            valor_total REAL,
            unidade_medida TEXT,
            categoria TEXT,
            raw_json TEXT,
            collected_at TEXT,
            PRIMARY KEY (numero_controle_pncp, numero_item),
            FOREIGN KEY (numero_controle_pncp) REFERENCES editais (numero_controle_pncp) ON DELETE CASCADE
        );
    """)

    # 3. Tabela de Resultados de Itens (Vencedores, adjudicacoes e valores reais homologados)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resultados_itens (
            numero_controle_pncp TEXT NOT NULL,
            numero_item INTEGER NOT NULL,
            sequencial_resultado INTEGER NOT NULL,
            fornecedor_cnpj TEXT,
            fornecedor_nome TEXT,
            valor_homologado_unitario REAL,
            valor_homologado_total REAL,
            quantidade_homologada REAL,
            situacao_resultado TEXT,
            raw_json TEXT,
            collected_at TEXT,
            PRIMARY KEY (numero_controle_pncp, numero_item, sequencial_resultado),
            FOREIGN KEY (numero_controle_pncp, numero_item) REFERENCES itens (numero_controle_pncp, numero_item) ON DELETE CASCADE
        );
    """)

    # 4. Tabela de Checkpoints de Coleta (Resiliencia e retomada do Stage 1)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints_coleta (
            lote_inicio TEXT NOT NULL,
            lote_fim TEXT NOT NULL,
            modalidade_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            collected_at TEXT,
            PRIMARY KEY (lote_inicio, lote_fim, modalidade_id)
        );
    """)

    # 5. Tabela de Status de Homologação de Itens (Rastreamento do Stage 2)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resultados_status (
            numero_controle_pncp TEXT NOT NULL,
            numero_item INTEGER NOT NULL,
            status TEXT NOT NULL, -- 'SUCESSO', 'VAZIO', 'ERRO_TEMPORARIO'
            collected_at TEXT NOT NULL,
            PRIMARY KEY (numero_controle_pncp, numero_item),
            FOREIGN KEY (numero_controle_pncp, numero_item) REFERENCES itens (numero_controle_pncp, numero_item) ON DELETE CASCADE
        );
    """)

    # Criacao de indices estruturais para otimizar pesquisas e filtros do Stage 2
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_editais_uf_encerramento ON editais (uf, data_encerramento);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_editais_uf_modalidade ON editais (uf, modalidade_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_itens_pncp ON itens (numero_controle_pncp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_resultados_pncp_item ON resultados_itens (numero_controle_pncp, numero_item);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_resultados_status_uf ON resultados_status (status);")

    conn.commit()
    conn.close()
    print("[DB] Banco de dados relacional (3 tabelas + checkpoints + status) e indices inicializados.")

def save_edital(conn: sqlite3.Connection, edital: Dict[str, Any]) -> None:
    """Insere ou atualiza de forma nao-destrutiva um edital no banco de dados."""
    cursor = conn.cursor()
    raw_str = json.dumps(edital.get("raw", {}))
    
    cursor.execute("""
        INSERT INTO editais (
            numero_controle_pncp,
            uf,
            municipio,
            orgao_cnpj,
            orgao_nome,
            objeto,
            data_abertura,
            data_encerramento,
            valor_estimado,
            modalidade_nome,
            situacao_compra_nome,
            modalidade_id,
            tipo_contratacao,
            raw_json,
            collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(numero_controle_pncp) DO UPDATE SET
            uf = excluded.uf,
            municipio = excluded.municipio,
            orgao_cnpj = excluded.orgao_cnpj,
            orgao_nome = excluded.orgao_nome,
            objeto = excluded.objeto,
            data_abertura = excluded.data_abertura,
            data_encerramento = excluded.data_encerramento,
            valor_estimado = excluded.valor_estimado,
            modalidade_nome = excluded.modalidade_nome,
            situacao_compra_nome = excluded.situacao_compra_nome,
            modalidade_id = excluded.modalidade_id,
            tipo_contratacao = excluded.tipo_contratacao,
            raw_json = excluded.raw_json,
            collected_at = excluded.collected_at;
    """, (
        edital.get("numero_controle_pncp"),
        edital.get("uf"),
        edital.get("municipio"),
        edital.get("orgao_cnpj"),
        edital.get("orgao_nome"),
        edital.get("objeto"),
        edital.get("data_abertura"),
        edital.get("data_encerramento"),
        edital.get("valor_estimado"),
        edital.get("modalidade_nome"),
        edital.get("situacao_compra_nome"),
        edital.get("modalidade_id"),
        edital.get("tipo_contratacao"),
        raw_str,
        edital.get("collected_at")
    ))

def save_item(conn: sqlite3.Connection, item: Dict[str, Any]) -> None:
    """Insere ou atualiza de forma nao-destrutiva um item estimado no banco de dados."""
    cursor = conn.cursor()
    raw_str = json.dumps(item.get("raw", {}))
    
    cursor.execute("""
        INSERT INTO itens (
            numero_controle_pncp,
            numero_item,
            lote,
            descricao,
            quantidade,
            valor_unitario,
            valor_total,
            unidade_medida,
            categoria,
            raw_json,
            collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(numero_controle_pncp, numero_item) DO UPDATE SET
            lote = excluded.lote,
            descricao = excluded.descricao,
            quantidade = excluded.quantidade,
            valor_unitario = excluded.valor_unitario,
            valor_total = excluded.valor_total,
            unidade_medida = excluded.unidade_medida,
            categoria = excluded.categoria,
            raw_json = excluded.raw_json,
            collected_at = excluded.collected_at;
    """, (
        item.get("numero_controle_pncp"),
        item.get("numero_item"),
        item.get("lote"),
        item.get("descricao"),
        item.get("quantidade"),
        item.get("valor_unitario"),
        item.get("valor_total"),
        item.get("unidade_medida"),
        item.get("categoria"),
        raw_str,
        item.get("collected_at")
    ))

def save_resultado_item(conn: sqlite3.Connection, res: Dict[str, Any]) -> None:
    """Insere ou atualiza de forma nao-destrutiva um resultado de homologacao de item no banco de dados."""
    cursor = conn.cursor()
    raw_str = json.dumps(res.get("raw", {}))
    
    cursor.execute("""
        INSERT INTO resultados_itens (
            numero_controle_pncp,
            numero_item,
            sequencial_resultado,
            fornecedor_cnpj,
            fornecedor_nome,
            valor_homologado_unitario,
            valor_homologado_total,
            quantidade_homologada,
            situacao_resultado,
            raw_json,
            collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(numero_controle_pncp, numero_item, sequencial_resultado) DO UPDATE SET
            fornecedor_cnpj = excluded.fornecedor_cnpj,
            fornecedor_nome = excluded.fornecedor_nome,
            valor_homologado_unitario = excluded.valor_homologado_unitario,
            valor_homologado_total = excluded.valor_homologado_total,
            quantidade_homologada = excluded.quantidade_homologada,
            situacao_resultado = excluded.situacao_resultado,
            raw_json = excluded.raw_json,
            collected_at = excluded.collected_at;
    """, (
        res.get("numero_controle_pncp"),
        res.get("numero_item"),
        res.get("sequencial_resultado"),
        res.get("fornecedor_cnpj"),
        res.get("fornecedor_nome"),
        res.get("valor_homologado_unitario"),
        res.get("valor_homologado_total"),
        res.get("quantidade_homologada"),
        res.get("situacao_resultado"),
        raw_str,
        res.get("collected_at")
    ))

def save_resultado_status(conn: sqlite3.Connection, control_number: str, num_item: int, status: str) -> None:
    """Salva ou atualiza o status de consulta de homologacao do item no Stage 2."""
    cursor = conn.cursor()
    collected_at = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO resultados_status (
            numero_controle_pncp,
            numero_item,
            status,
            collected_at
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(numero_controle_pncp, numero_item) DO UPDATE SET
            status = excluded.status,
            collected_at = excluded.collected_at;
    """, (control_number, num_item, status, collected_at))

def save_checkpoint(conn: sqlite3.Connection, lote_inicio: str, lote_fim: str, modalidade_id: int) -> None:
    """Registra um lote e modalidade como concluidos com sucesso na base de checkpoints."""
    cursor = conn.cursor()
    collected_at = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT OR REPLACE INTO checkpoints_coleta (
            lote_inicio,
            lote_fim,
            modalidade_id,
            status,
            collected_at
        ) VALUES (?, ?, ?, ?, ?);
    """, (lote_inicio, lote_fim, modalidade_id, "CONCLUIDO", collected_at))

def is_lote_concluido(conn: sqlite3.Connection, lote_inicio: str, lote_fim: str, modalidade_id: int) -> bool:
    """Retorna True se o lote e modalidade informados ja constam como concluidos na base de checkpoints."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM checkpoints_coleta 
        WHERE lote_inicio = ? AND lote_fim = ? AND modalidade_id = ? AND status = 'CONCLUIDO';
    """, (lote_inicio, lote_fim, modalidade_id))
    return cursor.fetchone()[0] > 0

def get_itens_pendentes_homologacao(conn: sqlite3.Connection, uf: str) -> List[Dict[str, Any]]:
    """
    Retorna todos os itens do banco de dados pertencentes a uma determinada UF que pertencem a editais
    ja encerrados e que ainda nao foram consultados com sucesso ou vazios no Stage 2.
    """
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    sql = """
        SELECT i.numero_controle_pncp, i.numero_item, e.uf, e.orgao_cnpj, e.objeto, e.raw_json AS edital_raw_json
        FROM itens i
        JOIN editais e ON i.numero_controle_pncp = e.numero_controle_pncp
        LEFT JOIN resultados_status s ON i.numero_controle_pncp = s.numero_controle_pncp AND i.numero_item = s.numero_item
        WHERE e.uf = ?
          AND e.situacao_compra_nome NOT IN ('Anulada', 'Revogada', 'Suspensa')
          AND (s.status IS NULL OR s.status = 'ERRO_TEMPORARIO')
          AND e.data_encerramento < ?;
    """
    cursor.execute(sql, (uf.strip().upper(), now_str))
    return [dict(row) for row in cursor.fetchall()]

def get_stats(conn: sqlite3.Connection) -> Dict[str, int]:
    """Retorna estatisticas consolidadas das tabelas relacionais, checkpoints e status."""
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM editais;")
    total_editais = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM itens;")
    total_itens = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM resultados_itens;")
    total_resultados = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM checkpoints_coleta;")
    total_checkpoints = cursor.fetchone()[0]
    
    try:
        cursor.execute("SELECT COUNT(*) FROM resultados_status;")
        total_status = cursor.fetchone()[0]
    except Exception:
        total_status = 0
    
    return {
        "total_editais": total_editais,
        "total_itens": total_itens,
        "total_resultados": total_resultados,
        "total_checkpoints": total_checkpoints,
        "total_status": total_status
    }
