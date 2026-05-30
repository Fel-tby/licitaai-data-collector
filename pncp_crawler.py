import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

URL_EDITAIS_PUBLICACAO = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
URL_ITENS_BASE = "https://pncp.gov.br/api/pncp/v1/orgaos"


class PncpClient:
    """
    Cliente HTTP síncrono resiliente para a API Publica do PNCP.
    Gerencia automaticamente rate limits, instabilidades do servidor e timeouts.
    Possui suporte completo a simulacao offline (Mock) para desenvolvimento local.
    """

    def __init__(self, mock: bool = False, timeout: float = 30.0, max_retries: int = 3) -> None:
        self.mock = mock
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.Client(headers=HEADERS, timeout=timeout)

    def close(self) -> None:
        """Fecha a conexao HTTP."""
        self.client.close()

    def __enter__(self) -> "PncpClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Executa chamada GET a API publica de forma síncrona com politicas de retry e backoff."""
        if self.mock:
            return self._get_mock_data(url, params)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.get(url, params=params)
                
                if response.status_code == 204:
                    return {"data": [], "totalRegistros": 0, "totalPaginas": 0}

                if response.status_code == 404:
                    return None

                if response.status_code == 429:
                    wait_time = attempt * 8
                    print(f"[CRAWLER] Rate limit (429). Aguardando {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                if response.status_code in (500, 502, 503, 504):
                    wait_time = attempt * 5
                    print(f"[CRAWLER] Instabilidade no servidor PNCP ({response.status_code}). Aguardando {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                
                if not response.text.strip():
                    return None

                return response.json()

            except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                wait_time = attempt * 3
                print(f"[CRAWLER] Falha de rede ou resposta invalida ({type(exc).__name__}). Tentativa {attempt}/{self.max_retries}. Aguardando {wait_time}s...")
                time.sleep(wait_time)

        print(f"[CRAWLER] ERRO: Nao foi possivel acessar a URL {url} de forma síncrona apos {self.max_retries} tentativas.")
        if last_error:
            print(f"[CRAWLER] Detalhes da falha: {last_error}")
        return None

    def _get_mock_data(self, url: str, params: Optional[Dict[str, Any]]) -> Any:
        """Gera massa de dados simulada síncrona para desenvolvimento offline."""
        return _mock_data_selector(url, params)


class AsyncPncpClient:
    """
    Cliente HTTP assincrono resiliente para a API Publica do PNCP.
    Gerencia rate limits e erros de rede de forma assincrona e nao-bloqueante.
    Possui suporte completo a simulacao offline (Mock) assincrona.
    """

    def __init__(self, mock: bool = False, timeout: float = 30.0, max_retries: int = 3) -> None:
        self.mock = mock
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(headers=HEADERS, timeout=timeout)

    async def close(self) -> None:
        """Fecha a conexao HTTP de forma assincrona."""
        await self.client.aclose()

    async def __aenter__(self) -> "AsyncPncpClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def fetch_json_async(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Executa chamada GET a API publica de forma assincrona com retry e backoff nao-bloqueantes."""
        if self.mock:
            # Simula atraso minimo de I/O assincrono de rede para realismo
            await asyncio.sleep(0.01)
            return _mock_data_selector(url, params)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.get(url, params=params)
                
                if response.status_code == 204:
                    return {"data": [], "totalRegistros": 0, "totalPaginas": 0}

                if response.status_code == 404:
                    return None

                if response.status_code == 429:
                    wait_time = attempt * 8
                    print(f"[ASYNC CRAWLER] Rate limit (429) detectado. Aguardando {wait_time}s assincronamente...")
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code in (500, 502, 503, 504):
                    wait_time = attempt * 5
                    print(f"[ASYNC CRAWLER] Instabilidade no PNCP ({response.status_code}). Aguardando {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                
                if not response.text.strip():
                    return None

                return response.json()

            except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                wait_time = attempt * 3
                print(f"[ASYNC CRAWLER] Falha de rede ou resposta invalida ({type(exc).__name__}). Tentativa {attempt}/{self.max_retries}. Aguardando {wait_time}s...")
                await asyncio.sleep(wait_time)

        print(f"[ASYNC CRAWLER] ERRO: Nao foi possivel acessar a URL {url} de forma assincrona apos {self.max_retries} tentativas.")
        if last_error:
            print(f"[ASYNC CRAWLER] Detalhes da falha: {last_error}")
        return None


def _mock_data_selector(url: str, params: Optional[Dict[str, Any]]) -> Any:
    """Seletor centralizado de dados mockados realistas para ambos os clientes síncrono e assíncrono."""
    uf = params.get("uf", "PB") if params else "PB"
    mod_id = params.get("codigoModalidadeContratacao", 6) if params else 6
    
    # Mock de Editais Publicados (/publicacao)
    if "consulta/v1/contratacoes/publicacao" in url:
        return {
            "totalRegistros": 2,
            "totalPaginas": 1,
            "data": [
                {
                    "numeroControlePNCP": "15023998000126-1-000001/2026",
                    "anoCompra": 2026,
                    "sequencialCompra": 1,
                    "numeroCompra": "00001/2026",
                    "processo": "001/2026",
                    "objetoCompra": f"AQUISICAO DE GENEROS ALIMENTICIOS PARA MERENDA ESCOLAR DO ESTADO ({uf})",
                    "orgaoEntidade": {
                        "cnpj": "15023998000126",
                        "razaoSocial": "SECRETARIA ESTADUAL DE EDUCACAO"
                    },
                    "unidadeOrgao": {
                        "codigoUnidade": "100",
                        "nomeUnidade": "DIRETORIA DE COMPRAS MUNICIPAIS",
                        "municipioNome": "JOAO PESSOA",
                        "ufSigla": uf
                    },
                    "modalidadeId": mod_id,
                    "modalidadeNome": "Pregao Eletronico" if mod_id == 6 else "Concorrencia Eletronica",
                    "situacaoCompraNome": "Homologada",
                    "valorTotalEstimado": 120000.0,
                    "dataPublicacaoPncp": "2026-05-10T10:00:00Z",
                    "dataAberturaProposta": "2026-05-15T09:00:00Z",
                    "dataEncerramentoProposta": "2026-05-20T18:00:00Z",
                },
                {
                    "numeroControlePNCP": "98765432100099-1-000045/2026",
                    "anoCompra": 2026,
                    "sequencialCompra": 45,
                    "numeroCompra": "00045/2026",
                    "processo": "2026/045",
                    "objetoCompra": f"AQUISICAO DE LICENCAS DE PLATAFORMA DE GESTAO DE DADOS E INFRAESTRUTURA ({uf})",
                    "orgaoEntidade": {
                        "cnpj": "98765432100099",
                        "razaoSocial": "COMPANHIA DE PROCESSAMENTO DE DADOS"
                    },
                    "unidadeOrgao": {
                        "codigoUnidade": "200",
                        "nomeUnidade": "DEPARTAMENTO DE TECNOLOGIA DA INFORMACAO",
                        "municipioNome": "CAMPINA GRANDE",
                        "ufSigla": uf
                    },
                    "modalidadeId": mod_id,
                    "modalidadeNome": "Pregao Eletronico" if mod_id == 6 else "Concorrencia Eletronica",
                    "situacaoCompraNome": "Publicada",
                    "valorTotalEstimado": 95000.0,
                    "dataPublicacaoPncp": "2026-05-26T08:00:00Z",
                    "dataAberturaProposta": "2026-06-25T09:00:00Z",
                    "dataEncerramentoProposta": "2026-07-15T17:00:00Z",
                }
            ]
        }

    # Mock de Itens Estimados (/itens)
    if "itens" in url and not url.endswith("resultados"):
        if "15023998000126/compras/2026/1/itens" in url:
            return [
                {
                    "numeroItem": 1,
                    "descricao": "ARROZ INTEGRAL TIPO 1 - PACOTE DE 1KG",
                    "loteNumero": 1,
                    "quantidade": 8000.0,
                    "valorUnitarioEstimado": 7.50,
                    "valorTotal": 60000.0,
                    "unidadeMedida": "KG",
                    "itemCategoriaNome": "Alimentos",
                },
                {
                    "numeroItem": 2,
                    "descricao": "FEIJAO MACASSAR TIPO 1 - PACOTE DE 1KG",
                    "loteNumero": 1,
                    "quantidade": 6000.0,
                    "valorUnitarioEstimado": 10.00,
                    "valorTotal": 60000.0,
                    "unidadeMedida": "KG",
                    "itemCategoriaNome": "Alimentos",
                }
            ]
        elif "98765432100099/compras/2026/45/itens" in url:
            return [
                {
                    "numeroItem": 1,
                    "descricao": "SERVICO DE ASSINATURA ANUAL DE BANCO DE DADOS EM NUVEM",
                    "loteNumero": 1,
                    "quantidade": 1.0,
                    "valorUnitarioEstimado": 95000.0,
                    "valorTotal": 95000.0,
                    "unidadeMedida": "UNIDADE",
                    "itemCategoriaNome": "Tecnologia",
                }
            ]
        return []

    # Mock de Resultados de Homologacao (/resultados)
    if url.endswith("resultados"):
        if "15023998000126/compras/2026/1/itens/1/resultados" in url:
            return [
                {
                    "sequencialResultado": 1,
                    "niFornecedor": "12345678000199",
                    "nomeRazaoSocialFornecedor": "DISTRIBUIDORA ALIMENTAR S.A.",
                    "valorUnitarioHomologado": 6.80,
                    "valorTotalHomologado": 54400.0,
                    "quantidadeHomologada": 8000.0,
                    "situacaoCompraItemResultadoNome": "Homologado",
                }
            ]
        elif "15023998000126/compras/2026/1/itens/2/resultados" in url:
            return [
                {
                    "sequencialResultado": 1,
                    "niFornecedor": "98765432000188",
                    "nomeRazaoSocialFornecedor": "CEREAIS VALE DO SOL LTDA",
                    "valorUnitarioHomologado": 9.20,
                    "valorTotalHomologado": 55200.0,
                    "quantidadeHomologada": 6000.0,
                    "situacaoCompraItemResultadoNome": "Homologado",
                }
            ]
        return []

    return None


def normalize_notice(row: Dict[str, Any], uf: str) -> Dict[str, Any]:
    """Normaliza o payload de edital obtido do endpoint /publicacao."""
    orgao = row.get("orgaoEntidade") or {}
    unidade = row.get("unidadeOrgao") or {}
    
    return {
        "numero_controle_pncp": row.get("numeroControlePNCP"),
        "uf": uf.upper(),
        "municipio": unidade.get("municipioNome"),
        "orgao_cnpj": orgao.get("cnpj"),
        "orgao_nome": orgao.get("razaoSocial"),
        "objeto": row.get("objetoCompra"),
        "data_abertura": row.get("dataAberturaProposta"),
        "data_encerramento": row.get("dataEncerramentoProposta"),
        "valor_estimado": row.get("valorTotalEstimado"),
        "modalidade_nome": row.get("modalidadeNome"),
        "situacao_compra_nome": row.get("situacaoCompraNome"),
        "modalidade_id": row.get("modalidadeId"),
        "tipo_contratacao": row.get("tipoContratacao"),
        "raw": row,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_item(item: Dict[str, Any], control_number: str) -> Dict[str, Any]:
    """Normaliza os dados estimados de planejamento originais do item de edital."""
    return {
        "numero_controle_pncp": control_number,
        "numero_item": item.get("numeroItem"),
        "lote": item.get("loteNumero"),
        "descricao": item.get("descricao"),
        "quantidade": item.get("quantidade"),
        "valor_unitario": item.get("valorUnitarioEstimado"),
        "valor_total": item.get("valorTotal"),
        "unidade_medida": item.get("unidadeMedida"),
        "categoria": item.get("itemCategoriaNome"),
        "raw": item,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_resultado(res: Dict[str, Any], control_number: str, num_item: int) -> Dict[str, Any]:
    """Normaliza de forma defensiva o resultado da homologacao do item."""
    return {
        "numero_controle_pncp": control_number,
        "numero_item": num_item,
        "sequencial_resultado": res.get("sequencialResultado", 1),
        "fornecedor_cnpj": res.get("niFornecedor"),
        "fornecedor_nome": res.get("nomeRazaoSocialFornecedor"),
        "valor_homologado_unitario": res.get("valorUnitarioHomologado"),
        "valor_homologado_total": res.get("valorTotalHomologado"),
        "quantidade_homologada": res.get("quantidadeHomologada"),
        "situacao_resultado": res.get("situacaoCompraItemResultadoNome"),
        "raw": res,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_published_notices(
    client: PncpClient,
    uf: str,
    data_inicial: str,
    data_final: str,
    modalidade_id: int,
    max_pages: int = 1000,
    page_size: int = 50,
) -> List[Dict[str, Any]]:
    """Busca editais historicos publicados no PNCP por UF, Modalidade e Datas (YYYYMMDD)."""
    uf = uf.strip().upper()
    all_notices: List[Dict[str, Any]] = []
    
    for pagina in range(1, max_pages + 1):
        params = {
            "uf": uf,
            "dataInicial": data_inicial,
            "dataFinal": data_final,
            "codigoModalidadeContratacao": modalidade_id,
            "pagina": pagina,
            "tamanhoPagina": page_size,
        }
        
        payload = client.fetch_json(URL_EDITAIS_PUBLICACAO, params=params)
        
        if not payload or not isinstance(payload, dict):
            break
            
        data = payload.get("data") or []
        if not data:
            break
            
        for item in data:
            normalized = normalize_notice(item, uf)
            all_notices.append(normalized)
            
        total_paginas = payload.get("totalPaginas") or 1
        if pagina >= total_paginas:
            break
            
    return all_notices


def fetch_items_for_notice(
    client: PncpClient,
    notice: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Busca a listagem de itens estimados de um edital de forma síncrona."""
    control_number = notice.get("numero_controle_pncp")
    raw_notice = notice.get("raw") or {}
    
    cnpj_raw = raw_notice.get("orgaoEntidade", {}).get("cnpj") or notice.get("orgao_cnpj") or ""
    cnpj = "".join(ch for ch in str(cnpj_raw) if ch.isdigit())
    ano = raw_notice.get("anoCompra") or notice.get("raw", {}).get("anoCompra")
    sequencial = raw_notice.get("sequencialCompra") or notice.get("raw", {}).get("sequencialCompra")
    
    if not cnpj or not ano or not sequencial or not control_number:
        return []
        
    items_url = f"{URL_ITENS_BASE}/{cnpj}/compras/{int(ano)}/{int(sequencial)}/itens"
    
    pagina = 1
    page_size = 500
    all_items: List[Dict[str, Any]] = []
    
    while True:
        params = {"pagina": pagina, "tamanhoPagina": page_size}
        payload = client.fetch_json(items_url, params=params)
        
        if not payload or not isinstance(payload, list):
            break
            
        for it in payload:
            normalized = normalize_item(it, control_number)
            all_items.append(normalized)
            
        if len(payload) < page_size:
            break
        pagina += 1
        
    return all_items


def fetch_resultados_for_item(
    client: PncpClient,
    notice: Dict[str, Any],
    numero_item: int,
) -> List[Dict[str, Any]]:
    """Busca os resultados de homologacao (adjudicacoes) de um determinado item de forma síncrona."""
    control_number = notice.get("numero_controle_pncp")
    raw_notice = notice.get("raw") or {}
    
    cnpj_raw = raw_notice.get("orgaoEntidade", {}).get("cnpj") or notice.get("orgao_cnpj") or ""
    cnpj = "".join(ch for ch in str(cnpj_raw) if ch.isdigit())
    ano = raw_notice.get("anoCompra") or notice.get("raw", {}).get("anoCompra")
    sequencial = raw_notice.get("sequencialCompra") or notice.get("raw", {}).get("sequencialCompra")
    
    if not cnpj or not ano or not sequencial or not control_number:
        return []
        
    result_url = f"{URL_ITENS_BASE}/{cnpj}/compras/{int(ano)}/{int(sequencial)}/itens/{numero_item}/resultados"
    
    res_payload = client.fetch_json(result_url)
    
    if not res_payload or not isinstance(res_payload, list):
        return []
        
    all_results: List[Dict[str, Any]] = []
    for res in res_payload:
        normalized = normalize_resultado(res, control_number, numero_item)
        all_results.append(normalized)
        
    return all_results


async def fetch_resultados_for_item_async(
    client: AsyncPncpClient,
    notice: Dict[str, Any],
    numero_item: int,
) -> List[Dict[str, Any]]:
    """Busca e normaliza de forma defensiva e nao-bloqueante os resultados de homologacao do item (Async)."""
    control_number = notice.get("numero_controle_pncp")
    raw_notice = notice.get("raw") or {}
    
    cnpj_raw = raw_notice.get("orgaoEntidade", {}).get("cnpj") or notice.get("orgao_cnpj") or ""
    cnpj = "".join(ch for ch in str(cnpj_raw) if ch.isdigit())
    ano = raw_notice.get("anoCompra") or notice.get("raw", {}).get("anoCompra")
    sequencial = raw_notice.get("sequencialCompra") or notice.get("raw", {}).get("sequencialCompra")
    
    if not cnpj or not ano or not sequencial or not control_number:
        return []
        
    result_url = f"{URL_ITENS_BASE}/{cnpj}/compras/{int(ano)}/{int(sequencial)}/itens/{numero_item}/resultados"
    
    res_payload = await client.fetch_json_async(result_url)
    
    if not res_payload or not isinstance(res_payload, list):
        return []
        
    all_results: List[Dict[str, Any]] = []
    for res in res_payload:
        normalized = normalize_resultado(res, control_number, numero_item)
        all_results.append(normalized)
        
    return all_results


async def fetch_published_notices_async(
    client: AsyncPncpClient,
    uf: str,
    data_inicial: str,
    data_final: str,
    modalidade_id: int,
    concurrency_paginas: int = 5,
    max_pages: Optional[int] = None,
    page_size: int = 50,
) -> List[Dict[str, Any]]:
    """Busca editais historicos publicados no PNCP de forma assincrona e concorrente."""
    uf = uf.strip().upper()
    all_notices: List[Dict[str, Any]] = []
    
    # 1. Faz a requisicao da pagina 1 para descobrir o total real de paginas
    params = {
        "uf": uf,
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "codigoModalidadeContratacao": modalidade_id,
        "pagina": 1,
        "tamanhoPagina": page_size,
    }
    
    payload = await client.fetch_json_async(URL_EDITAIS_PUBLICACAO, params=params)
    if not payload or not isinstance(payload, dict):
        return []
        
    data = payload.get("data") or []
    for item in data:
        all_notices.append(normalize_notice(item, uf))
        
    total_paginas = payload.get("totalPaginas") or 1
    if max_pages is not None:
        total_paginas = min(total_paginas, max_pages)
        
    if total_paginas <= 1:
        return all_notices

    # 2. Gera e executa as tarefas para as paginas restantes concorrentemente com semaforo
    semaphore = asyncio.Semaphore(concurrency_paginas)
    
    async def fetch_page(page: int) -> List[Dict[str, Any]]:
        async with semaphore:
            page_params = params.copy()
            page_params["pagina"] = page
            p_payload = await client.fetch_json_async(URL_EDITAIS_PUBLICACAO, params=page_params)
            if p_payload and isinstance(p_payload, dict):
                p_data = p_payload.get("data") or []
                return [normalize_notice(item, uf) for item in p_data]
            return []

    # Cria tarefas para as paginas de 2 ate total_paginas
    tasks = [fetch_page(p) for p in range(2, total_paginas + 1)]
    results = await asyncio.gather(*tasks)
    
    for r in results:
        all_notices.extend(r)
        
    return all_notices


async def fetch_items_for_notice_async(
    client: AsyncPncpClient,
    notice: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Busca a listagem de itens estimados de um edital de forma assincrona."""
    control_number = notice.get("numero_controle_pncp")
    raw_notice = notice.get("raw") or {}
    
    cnpj_raw = raw_notice.get("orgaoEntidade", {}).get("cnpj") or notice.get("orgao_cnpj") or ""
    cnpj = "".join(ch for ch in str(cnpj_raw) if ch.isdigit())
    ano = raw_notice.get("anoCompra") or notice.get("raw", {}).get("anoCompra")
    sequencial = raw_notice.get("sequencialCompra") or notice.get("raw", {}).get("sequencialCompra")
    
    if not cnpj or not ano or not sequencial or not control_number:
        return []
        
    items_url = f"{URL_ITENS_BASE}/{cnpj}/compras/{int(ano)}/{int(sequencial)}/itens"
    
    params = {"pagina": 1, "tamanhoPagina": 500}
    payload = await client.fetch_json_async(items_url, params=params)
    
    if not payload or not isinstance(payload, list):
        return []
        
    all_items: List[Dict[str, Any]] = []
    for it in payload:
        all_items.append(normalize_item(it, control_number))
        
    if len(payload) < 500:
        return all_items
        
    pagina = 2
    while True:
        params["pagina"] = pagina
        p_payload = await client.fetch_json_async(items_url, params=params)
        if not p_payload or not isinstance(p_payload, list):
            break
        for it in p_payload:
            all_items.append(normalize_item(it, control_number))
        if len(p_payload) < 500:
            break
        pagina += 1
        
    return all_items


async def fetch_items_for_notices_async(
    client: AsyncPncpClient,
    notices: List[Dict[str, Any]],
    concurrency_itens: int = 20,
) -> List[Dict[str, Any]]:
    """Busca itens estimados de uma lista de editais concorrentemente com semaforo."""
    semaphore = asyncio.Semaphore(concurrency_itens)
    all_items: List[Dict[str, Any]] = []
    
    async def fetch_item(notice: Dict[str, Any]) -> List[Dict[str, Any]]:
        async with semaphore:
            try:
                return await fetch_items_for_notice_async(client, notice)
            except Exception as exc:
                print(f"[CRAWLER] Erro ao buscar itens do edital {notice.get('numero_controle_pncp')}: {exc}")
                return []
                
    tasks = [fetch_item(n) for n in notices]
    results = await asyncio.gather(*tasks)
    
    for r in results:
        all_items.extend(r)
        
    return all_items
