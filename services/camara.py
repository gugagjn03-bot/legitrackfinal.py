# services/camara.py
# Camada de acesso à API de Dados Abertos da Câmara dos Deputados
# Aqui NÃO usamos mais 'ementa' nem termo na URL.

from typing import Optional, List, Dict, Any
import requests

BASE = "https://dadosabertos.camara.leg.br/api/v2"

class CamaraAPIError(RuntimeError):
    pass

def _get(path: str, params: Optional[dict] = None, timeout: int = 25) -> dict:
    """
    Função interna para chamar a API da Câmara com tratamento básico de erro.
    """
    url = f"{BASE}{path}"
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise CamaraAPIError(f"Erro ao consultar a API da Câmara ({url}): {e}") from e


def buscar_proposicoes(
    ano: Optional[int] = None,
    tipo: str = "PL",
    itens: int = 100,
    ordenar_por: str = "id",
    ordem: str = "DESC",
) -> List[Dict[str, Any]]:
    """
    Busca proposições filtrando por tipo e, opcionalmente, ano.

    IMPORTANTE:
    - NÃO usa 'ementa' nem qualquer termo de busca na URL.
    - O filtro por palavra-chave será feito depois, no Python (app.py).
    """
    params: Dict[str, Any] = {
        "siglaTipo": tipo,
        "itens": itens,
        "ordem": ordem,
        "ordenarPor": ordenar_por,
    }

    if ano:
        params["ano"] = ano

    data = _get("/proposicoes", params=params)
    return data.get("dados", [])


def detalhes_proposicao(id_prop: int) -> Dict[str, Any]:
    data = _get(f"/proposicoes/{id_prop}")
    return data.get("dados", {})


def tramitacoes(id_prop: int) -> List[Dict[str, Any]]:
    data = _get(f"/proposicoes/{id_prop}/tramitacoes")
    return data.get("dados", [])


def autores_por_uri(uri_autores: str) -> List[Dict[str, Any]]:
    if not uri_autores:
        return []
    # uri_autores já vem com URL completa da API (incluindo https://...)
    try:
        r = requests.get(uri_autores, timeout=25)
        r.raise_for_status()
        data = r.json()
        return data.get("dados", [])
    except requests.RequestException:
        return []

