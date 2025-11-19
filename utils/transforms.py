# utils/transforms.py
#
# Funções utilitárias para transformar os dados de proposições da Câmara
# em DataFrames prontos para análise no app Streamlit.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import pandas as pd
from dateutil import parser as dateparser


def parse_date(value: Any) -> Optional[pd.Timestamp]:
    """
    Converte strings de data/hora da API em Timestamp do pandas.
    Retorna None se não conseguir converter.
    """
    if value in (None, "", pd.NaT):
        return None
    try:
        dt = dateparser.parse(str(value))
        return pd.to_datetime(dt)
    except Exception:
        return None


def dias_desde(dt: Any) -> Optional[int]:
    """
    Calcula quantos dias se passaram desde dt até hoje.
    dt pode ser date, datetime ou Timestamp.
    """
    if dt in (None, "", pd.NaT):
        return None
    if isinstance(dt, pd.Timestamp):
        d = dt.date()
    elif isinstance(dt, datetime):
        d = dt.date()
    elif isinstance(dt, date):
        d = dt
    else:
        # tenta converter
        parsed = parse_date(dt)
        if parsed is None:
            return None
        d = parsed.date()

    hoje = date.today()
    return (hoje - d).days


def _safe_get(d: Dict[str, Any], *keys, default=None) -> Any:
    """
    Busca encadeada em d[key1][key2]... com fallback para default se algo falhar.
    """
    cur: Any = d
    try:
        for k in keys:
            if cur is None:
                return default
            cur = cur.get(k)
        return cur if cur is not None else default
    except Exception:
        return default


def df_proposicoes(registros: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Recebe uma lista de dicionários de proposições (vinda do arquivo anual
    OU da API) e retorna um DataFrame padronizado com as colunas que o app usa.

    Campos principais:
      - id, siglaTipo, numero, ano
      - ementa
      - situacao, tramitacao_atual, data_status
      - uri, link (para a página oficial da proposição)
      - uriAutores (se disponível)
    """
    linhas: List[Dict[str, Any]] = []

    for p in registros:
        # ids básicos
        id_prop = p.get("id") or p.get("idProposicao")
        sigla_tipo = p.get("siglaTipo") or p.get("sigla_tipo")
        numero = p.get("numero") or p.get("numProposicao") or p.get("num")
        ano = p.get("ano") or p.get("anoProposicao")

        ementa = p.get("ementa") or ""
        ementa_det = p.get("ementaDetalhada") or p.get("ementa_detalhada") or ""
        uri = p.get("uri") or p.get("uriProposicao")

        # Status pode vir como "statusProposicao", "status_proposicao", etc.
        status = (
            p.get("statusProposicao")
            or p.get("status_proposicao")
            or p.get("ultimoStatus")
            or {}
        )

        situacao = (
            _safe_get(status, "descricaoSituacao")
            or _safe_get(status, "situacao")
            or _safe_get(status, "descricaoTramitacao")
        )
        tramitacao_atual = (
            _safe_get(status, "descricaoTramitacao")
            or _safe_get(status, "apreciacao")
        )
        data_status_raw = (
            _safe_get(status, "dataHora")
            or _safe_get(status, "data")
            or _safe_get(status, "dataUltimoDespacho")
        )

        data_status = parse_date(data_status_raw)

        # Alguns arquivos trazem uriAutores, outros não.
        uri_autores = p.get("uriAutores") or p.get("uri_autores")

        # Monta link "bonito" para a ficha de tramitação, se tivermos o id.
        if id_prop:
            link = f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={id_prop}"
        else:
            # fallback: usa a própria URI, se existir
            link = uri or ""

        rotulo = None
        if sigla_tipo and numero and ano:
            rotulo = f"{sigla_tipo} {numero}/{ano}"

        linhas.append(
            {
                "id": int(id_prop) if id_prop is not None else None,
                "siglaTipo": sigla_tipo,
                "numero": numero,
                "ano": ano,
                "rotulo": rotulo,
                "ementa": ementa or ementa_det,
                "situacao": situacao,
                "tramitacao_atual": tramitacao_atual,
                "data_status": data_status,
                "uri": uri,
                "uriAutores": uri_autores,
                "link": link,
            }
        )

    if not linhas:
        return pd.DataFrame(
            columns=[
                "id",
                "siglaTipo",
                "numero",
                "ano",
                "rotulo",
                "ementa",
                "situacao",
                "tramitacao_atual",
                "data_status",
                "uri",
                "uriAutores",
                "link",
            ]
        )

    df = pd.DataFrame(linhas)

    # Garante tipos básicos
    if "data_status" in df.columns:
        df["data_status"] = df["data_status"].apply(
            lambda x: x if isinstance(x, pd.Timestamp) else parse_date(x)
        )

    return df


def extrair_autor_principal(autores_payload: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """
    Recebe a lista de autores vinda de /proposicoes/{id}/autores e devolve
    um dict padronizado com:
      - nome
      - partido
      - uf
      - tipoAutor

    OBS: a API da Câmara nem sempre usa os mesmos nomes de campo,
    então aqui a gente tenta várias possibilidades para cada coisa.
    """
    if not autores_payload:
        return {"nome": None, "partido": None, "uf": None, "tipoAutor": None}

    # Prioriza autores do tipo "Deputado(a)"
    deputado = None
    for a in autores_payload:
        tipo = (a.get("tipo") or "").lower()
        if "deputado" in tipo:
            deputado = a
            break

    autor = deputado or autores_payload[0]

    # Nome (pode vir como "nome" ou "nomeAutor")
    nome = (
        autor.get("nome")
        or autor.get("nomeAutor")
        or autor.get("nomeAutorPrimeiroSignatario")
    )

    # Partido (várias possibilidades de chave)
    partido = (
        autor.get("siglaPartido")
        or autor.get("siglaPartidoAutor")
        or autor.get("sigla_partido")
        or autor.get("partido")
    )

    # UF (a API usa muito "siglaUf", mas vamos cobrir outras variações)
    uf = (
        autor.get("siglaUf")
        or autor.get("siglaUF")
        or autor.get("uf")
        or autor.get("ufAutor")
        or autor.get("siglaUfAutor")
    )

    tipo_autor = autor.get("tipo")

    return {
        "nome": nome,
        "partido": partido,
        "uf": uf,
        "tipoAutor": tipo_autor,
    }
