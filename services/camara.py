# services/camara.py
# Camada de acesso à API de Dados Abertos da Câmara dos Deputados
# Docs: https://dadosabertos.camara.leg.br/swagger/api.html

from typing import Optional, List, Dict, Any
import requests

BASE = "https://dadosabertos.camara.leg.br/api/v2"

class CamaraAPIError(RuntimeError):
    pass

def _get(url: str, params: Optional[dict] = None, timeout: int = 25) -> dict:
    """
    Função interna para chamar a API da Câmara com tratamento básico de erro.
    """
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        # Aqui a gente lança um erro mais amigável pro app pegar e exibir
        raise CamaraAPIError(f"Erro ao consultar a API da Câmara ({url}): {e}") from e

def buscar_proposicoes(
    termo: str,
    ano: Optional[int] = None,
    tipo: str = "PL",
    itens: int = 100,
    ordenar_por: str = "id",   # 👈 AQUI: agora ordena por 'id', que é aceito pela API
    ordem: str = "DESC",
) -> List[Dict[str, Any]]:
    """
    Busca proposições pela ementa (palavra-chave), filtrando por tipo e ano.

    Parâmetros enviados para a API:
      - siglaTipo: PL, PLP, PEC, etc.
      - ano: ano da proposição (opcional)
      - ementa: termo de busca no texto da ementa
      - ordem: ASC/DESC
      - ordenarPor: id  (campo seguro suportado pela API)
      - itens: quantidade de resultados
    """
    params: Dict[str, Any] = {
        "siglaTipo": tipo,
        "itens": itens,
        "ordem": ordem,
        "ordenarPor": ordenar_por,
    }

    # só manda se tiver termo
    if termo:
        params["ementa"] = termo

    # só manda se tiver ano
    if ano:
        params["ano"] = ano

    data = _get(f"{BASE}/proposicoes", params=params)
    return data.get("dados", [])

def detalhes_proposicao(id_prop: int) -> Dict[str, Any]:
    data = _get(f"{BASE}/proposicoes/{id_prop}")
    return data.get("dados", {})

def tramitacoes(id_prop: int) -> List[Dict[str, Any]]:
    data = _get(f"{BASE}/proposicoes/{id_prop}/tramitacoes")
    return data.get("dados", [])

def autores_por_uri(uri_autores: str) -> List[Dict[str, Any]]:
    if not uri_autores:
        return []
    data = _get(uri_autores)
    return data.get("dados", [])
