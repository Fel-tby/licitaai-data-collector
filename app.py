import argparse
import json
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any

import db
import pncp_crawler

# Modalidades padrão de maior volumetria no PNCP
MODALIDADES_PADRAO = [4, 6, 8, 9]


def calcular_fatias_temporais(dias_historico: int, tamanho_fatia_dias: int = 30) -> List[Tuple[str, str]]:
    """
    Calcula lotes de busca temporais retrospectivos contiguos e sem sobreposicao.
    Retorna uma lista de tuplas (data_inicial, data_final) no formato YYYYMMDD.
    """
    data_atual = datetime.now()
    data_inicial_limite = data_atual - timedelta(days=dias_historico)
    
    fatias = []
    corrente = data_inicial_limite
    
    while corrente < data_atual:
        proximo = min(corrente + timedelta(days=tamanho_fatia_dias), data_atual)
        fatias.append((corrente.strftime("%Y%m%d"), proximo.strftime("%Y%m%d")))
        corrente = proximo + timedelta(days=1)
        
    return fatias


async def executar_stage1_async(args, modalidades: List[int], uf_alvo: str) -> None:
    """
    Stage 1 Assincrono: Ingestao assincrona concorrente retrospectiva de 'editais' e 'itens' estimados
    com checkpoints de resiliencia no SQLite.
    """
    print("\n--- INICIANDO STAGE 1 ASSÍNCRONO CONCORRENTE: EDITAIS E ITENS ESTIMADOS ---")
    
    fatias = calcular_fatias_temporais(args.dias, args.fatia_tamanho)
    print(f"[ENGINE] Janela retrospectiva fatiada em {len(fatias)} lotes contiguos.")

    notices_saved = 0
    items_saved = 0
    lotes_pulados = 0

    async with pncp_crawler.AsyncPncpClient(mock=args.mock) as client:
        # Loop sequencial sobre as fatias para garantir resiliencia de checkpoint intacta
        for lote_idx, (data_ini, data_fim) in enumerate(fatias, start=1):
            print(f"\n>>> Lote {lote_idx}/{len(fatias)}: {data_ini} ate {data_fim}")
            print("-" * 60)
            
            for mod in modalidades:
                conn = db.get_connection()
                try:
                    if db.is_lote_concluido(conn, data_ini, data_fim, mod):
                        print(f"   -> Lote {data_ini}-{data_fim} | Modalidade {mod} ja CONCLUIDO. Pulando...")
                        lotes_pulados += 1
                        continue
                finally:
                    conn.close()

                print(f"   -> Varrendo modalidade {mod} assincronamente...")
                
                # 1. Coleta os editais de forma concorrente e sem limites de paginas artificiais
                editais = await pncp_crawler.fetch_published_notices_async(
                    client=client,
                    uf=uf_alvo,
                    data_inicial=data_ini,
                    data_final=data_fim,
                    modalidade_id=mod,
                    concurrency_paginas=args.concurrency_paginas,
                    max_pages=args.max_paginas # Se None, nao ha limite!
                )
                
                if not editais:
                    conn = db.get_connection()
                    try:
                        db.save_checkpoint(conn, data_ini, data_fim, mod)
                        conn.commit()
                    finally:
                        conn.close()
                    continue
                    
                print(f"      -> Encontrados {len(editais)} editais. Baixando itens estimados concorrentemente...")
                
                # 2. Coleta os itens estimados de todos os editais de forma concorrente
                itens = await pncp_crawler.fetch_items_for_notices_async(
                    client=client,
                    notices=editais,
                    concurrency_itens=args.concurrency_itens
                )
                
                # 3. Persistencia relacional agrupada dos editais e itens em transacao unica
                conn = db.get_connection()
                try:
                    for edital in editais:
                        db.save_edital(conn, edital)
                        notices_saved += 1
                        
                    for item in itens:
                        db.save_item(conn, item)
                        items_saved += 1
                        
                    conn.commit()
                    
                    # Salva checkpoint apos gravação no disco com sucesso
                    db.save_checkpoint(conn, data_ini, data_fim, mod)
                    conn.commit()
                    print(f"      [CONCLUIDO] Lote {data_ini}-{data_fim} | Mod {mod} persistido com sucesso.")
                    
                except Exception as e:
                    conn.rollback()
                    print(f"      [ERRO] Falha ao persistir lote no SQLite: {e}. Checkpoint nao gravado.")
                finally:
                    conn.close()

    print("\n" + "=" * 60)
    print("             STAGE 1 CONCLUIDO COM SUCESSO!             ")
    print("=" * 60)
    print(f"-> Lotes ignorados via checkpoint: {lotes_pulados}")
    print(f"-> Editais adicionados/atualizados: {notices_saved}")
    print(f"-> Itens estimados gravados:        {items_saved}")
    print("=" * 60)


def executar_stage2_serial(args) -> None:
    """
    Stage 2 (Sequencial/Serial): Fallback de seguranca. Executa de forma síncrona
    e unitaria o enriquecimento de homologacoes no SQLite.
    """
    print(f"\n--- INICIANDO STAGE 2 (MODO SERIAL DE SEGURANCA - UF: {args.uf}) ---")
    
    conn = db.get_connection()
    try:
        itens_pendentes = db.get_itens_pendentes_homologacao(conn, args.uf)
    finally:
        conn.close()

    if not itens_pendentes:
        print("[STAGE 2] Nao existem itens pendentes de homologacao no banco relacional.")
        return

    total_itens = len(itens_pendentes)
    print(f"[STAGE 2] Encontrados {total_itens} itens pendentes de dados de homologacao.")
    print("Iniciando consulta síncrona sequencial (Serial)...")

    results_saved = 0
    results_empty = 0

    with pncp_crawler.PncpClient(mock=args.mock) as client:
        for idx, item_pendente in enumerate(itens_pendentes, start=1):
            control_number = item_pendente["numero_controle_pncp"]
            num_item = item_pendente["numero_item"]
            
            raw_edital_json = {}
            if item_pendente.get("edital_raw_json"):
                try:
                    raw_edital_json = json.loads(item_pendente["edital_raw_json"])
                except Exception:
                    pass
            
            edital_pai = {
                "numero_controle_pncp": control_number,
                "orgao_cnpj": item_pendente["orgao_cnpj"],
                "raw": raw_edital_json
            }
            
            try:
                resultados = pncp_crawler.fetch_resultados_for_item(
                    client=client,
                    notice=edital_pai,
                    numero_item=num_item
                )
                status = "SUCESSO" if resultados else "VAZIO"
            except Exception as e:
                status = "ERRO_TEMPORARIO"
                resultados = []
                print(f"   [ERRO] Falha ao processar item: {e}")
            
            conn = db.get_connection()
            try:
                if status == "SUCESSO":
                    for res in resultados:
                        db.save_resultado_item(conn, res)
                        results_saved += 1
                elif status == "VAZIO":
                    results_empty += 1
                
                db.save_resultado_status(conn, control_number, num_item, status)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"   [ERRO] Falha ao persistir resultado do item: {e}")
            finally:
                conn.close()
                
            if idx % args.progress_step == 0 or idx == len(itens_pendentes):
                print(f"[STAGE 2] {idx}/{len(itens_pendentes)} itens processados | salvos: {results_saved} | vazios: {results_empty}")


async def executar_stage2_async(args) -> None:
    """
    Stage 2 (Assincrono Concorrente Otimizado): Carrega itens da UF alvo em lotes (batches),
    executa chamadas concorrentes com semaforo e persiste status de sucesso, vazio ou erro temporario.
    """
    print(f"\n--- INICIANDO STAGE 2 ASSÍNCRONO CONCORRENTE: RESULTADOS (UF: {args.uf}) ---")
    
    conn = db.get_connection()
    try:
        itens_pendentes = db.get_itens_pendentes_homologacao(conn, args.uf)
    finally:
        conn.close()

    if not itens_pendentes:
        print("[STAGE 2] Nao existem itens pendentes de homologacao para a UF indicada.")
        return

    total_itens = len(itens_pendentes)
    print(f"[STAGE 2] Encontrados {total_itens} itens pendentes de dados de homologacao.")
    
    batch_size = args.batch_size
    print(f"[ENGINE] Processamento em lotes de {batch_size} itens com concorrencia limite de {args.concurrency}.")

    contadores = {
        "processados": 0,
        "salvos": 0,
        "vazios": 0,
        "erros": 0
    }

    semaphore = asyncio.Semaphore(args.concurrency)
    db_lock = asyncio.Lock()

    async def processar_item_async(item_pendente: Dict[str, Any], client: pncp_crawler.AsyncPncpClient):
        control_number = item_pendente["numero_controle_pncp"]
        num_item = item_pendente["numero_item"]
        
        raw_edital_json = {}
        if item_pendente.get("edital_raw_json"):
            try:
                raw_edital_json = json.loads(item_pendente["edital_raw_json"])
            except Exception:
                pass
        
        edital_pai = {
            "numero_controle_pncp": control_number,
            "orgao_cnpj": item_pendente["orgao_cnpj"],
            "raw": raw_edital_json
        }
        
        async with semaphore:
            try:
                resultados = await pncp_crawler.fetch_resultados_for_item_async(
                    client=client,
                    notice=edital_pai,
                    numero_item=num_item
                )
                status = "SUCESSO" if resultados else "VAZIO"
            except Exception as exc:
                status = "ERRO_TEMPORARIO"
                resultados = []
                print(f"[STAGE 2] [Falha] Item {num_item} do edital {control_number}: {exc}")

        # Grava os resultados e atualiza a tabela de status sob lock
        async with db_lock:
            conn = db.get_connection()
            try:
                if status == "SUCESSO":
                    for res in resultados:
                        db.save_resultado_item(conn, res)
                    contadores["salvos"] += len(resultados)
                elif status == "VAZIO":
                    contadores["vazios"] += 1
                else:
                    contadores["erros"] += 1
                
                db.save_resultado_status(conn, control_number, num_item, status)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"[STAGE 2] [Falha SQLite] Item {num_item} do edital {control_number}: {e}")
            finally:
                conn.close()
                
        contadores["processados"] += 1

    # Loop assincrono rodando lote por lote
    async with pncp_crawler.AsyncPncpClient(mock=args.mock) as client:
        for i in range(0, total_itens, batch_size):
            batch = itens_pendentes[i : i + batch_size]
            print(f"\n[STAGE 2] Iniciando Lote {i // batch_size + 1} ({len(batch)} itens)...")
            
            tasks = [processar_item_async(item, client) for item in batch]
            await asyncio.gather(*tasks)
            
            proc = contadores["processados"]
            print(f"[STAGE 2] Progresso: {proc}/{total_itens} processados | homologados: {contadores['salvos']} | vazios: {contadores['vazios']} | erros: {contadores['erros']}")

    print("\n" + "=" * 60)
    print("             STAGE 2 CONCLUIDO COM SUCESSO!             ")
    print("=" * 60)
    print(f"-> Total de Itens processados:         {contadores['processados']}")
    print(f"-> Resultados/Homologacoes salvas:     {contadores['salvos']}")
    print(f"-> Itens sem homologacao (vazios):     {contadores['vazios']}")
    print(f"-> Falhas temporarias registradas:      {contadores['erros']}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline de Engenharia de Ingestão Histórica do PNCP - Otimizado e Paralelo",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--stage", 
        type=int, 
        choices=[1, 2], 
        default=1, 
        help="Estagio de execucao: 1 (Editais & Itens Estimados) ou 2 (Resultados de Homologacao)"
    )
    parser.add_argument(
        "--uf", 
        type=str, 
        default="PB", 
        help="Estado (UF) alvo da ingestao"
    )
    parser.add_argument(
        "--dias", 
        type=int, 
        default=360, 
        help="Quantidade de dias de retrospectiva historica (Stage 1)"
    )
    parser.add_argument(
        "--fatia-tamanho", 
        type=int, 
        default=30, 
        help="Tamanho de cada lote de busca temporal em dias (Stage 1)"
    )
    parser.add_argument(
        "--max-paginas", 
        type=int, 
        default=None, # None = Sem limites artificiais de paginas (Full)
        help="Limite artificial de paginas de editais por fatia (deixe como None para coleta completa)"
    )
    parser.add_argument(
        "--todas-modalidades", 
        action="store_true", 
        default=False, 
        help="Se ativado, varre as modalidades de 1 a 14. Se desativado, varre as 4 principais"
    )
    parser.add_argument(
        "--concurrency", 
        type=int, 
        default=20, 
        help="Concorrencia de chamadas de resultados no Stage 2"
    )
    parser.add_argument(
        "--concurrency-paginas", 
        type=int, 
        default=5, 
        help="Concorrencia de download de paginas de editais no Stage 1"
    )
    parser.add_argument(
        "--concurrency-itens", 
        type=int, 
        default=20, 
        help="Concorrencia de download de itens estimados por edital no Stage 1"
    )
    parser.add_argument(
        "--batch-size", 
        type=int, 
        default=500, 
        help="Tamanho do lote de processamento de itens pendentes no Stage 2"
    )
    parser.add_argument(
        "--progress-step", 
        type=int, 
        default=100, 
        help="Intervalo de itens para progresso no modo serial"
    )
    parser.add_argument(
        "--serial", 
        action="store_true", 
        default=False, 
        help="Se ativado, forca a execucao síncrona sequencial tradicional de seguranca no Stage 2"
    )
    parser.add_argument(
        "--mock", 
        action="store_true", 
        default=False, 
        help="Habilita o modo de simulacao offline (Mock) para desenvolvimento local"
    )

    args = parser.parse_args()

    modalidades = list(range(1, 15)) if args.todas_modalidades else MODALIDADES_PADRAO
    uf_alvo = args.uf.strip().upper()

    print("=" * 60)
    print("      PIPELINE DE ENGENHARIA DE INGESTÃO HISTÓRICA DO PNCP     ")
    print("=" * 60)
    print(f"-> Estagio de Execucao: Stage {args.stage}")
    print(f"-> Estado Filtrado:     {uf_alvo}")
    print(f"-> Modo Simulacao:      {'ATIVADO (OFFLINE)' if args.mock else 'DESATIVADO (ONLINE)'}")
    print("=" * 60)

    db.init_db()

    if args.stage == 1:
        asyncio.run(executar_stage1_async(args, modalidades, uf_alvo))
    else:
        if args.serial:
            executar_stage2_serial(args)
        else:
            asyncio.run(executar_stage2_async(args))

    stats_conn = db.get_connection()
    stats = db.get_stats(stats_conn)
    stats_conn.close()
    
    print("\n" + "=" * 60)
    print("             TOTAL CONSOLIDADO NA BASE SQLite             ")
    print("=" * 60)
    print(f"   -> Total de Editais gravados:       {stats['total_editais']}")
    print(f"   -> Total de Itens estimados:        {stats['total_itens']}")
    print(f"   -> Total de Homologacoes salvas:    {stats['total_resultados']}")
    print(f"   -> Total de Itens com status:       {stats.get('total_status', 0)}")
    print(f"   -> Total de Checkpoints salvos:     {stats['total_checkpoints']}")
    print("=" * 60)
    print("O banco de dados relacional 'data/licitacoes.db' esta atualizado!")
    print("=" * 60)

if __name__ == "__main__":
    main()
