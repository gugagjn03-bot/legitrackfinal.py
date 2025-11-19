# app.py
# LegiTrack BR — Radar de Projetos de Lei (Câmara dos Deputados)
# Autores: Gustavo Jardim, Pedro Henrique Bastos e Sávio Verbicário

from typing import List
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from services.camara import (
    buscar_proposicoes_por_tema,
    detalhes_proposicao,
    tramitacoes,
    autores_por_uri,
    CamaraAPIError,
)
from utils.transforms import (
    df_proposicoes,
    extrair_autor_principal,
    dias_desde,
    parse_date,
)

st.set_page_config(page_title="LegiTrack BR", page_icon="📜", layout="wide")
TIPOS_SUPORTADOS = ["PL", "PLP", "PEC", "MPV", "PDC"]

# ============== Sidebar (filtros) ==============
st.sidebar.header("🔎 Filtros de busca")
termo = st.sidebar.text_input(
    "Palavra-chave (ementa/keywords)",
    placeholder="ex.: apostas, anistia, LGPD, violência doméstica",
)

ano_val = st.sidebar.number_input(
    "Ano da apresentação (obrigatório)",
    min_value=1990,
    max_value=2100,
    value=2024,
    step=1,
)

tipos_sel = st.sidebar.multiselect(
    "Tipos de proposição",
    options=TIPOS_SUPORTADOS,
    default=["PL", "PEC", "PLP"],
    help="Selecione quais tipos de proposição serão considerados na busca.",
)

itens_max = st.sidebar.slider(
    "Máximo de resultados exibidos",
    min_value=10,
    max_value=300,
    value=80,
    step=10,
)

btn_buscar = st.sidebar.button("Buscar proposições", use_container_width=True)

# ============== Título ==============
st.title("📜 LegiTrack BR — Radar Temático de Projetos de Lei")
st.caption(
    "Busca proposições (PL, PEC, PLP, MPV, PDC) por tema usando ementa e keywords "
    "com base nos dados abertos da Câmara dos Deputados."
)

# ============== Busca & Tabela ==============
if btn_buscar:
    if not termo.strip():
        st.warning("Digite uma palavra-chave para buscar.")
        st.stop()

    try:
        with st.spinner("Carregando proposições do ano e filtrando por tema..."):
            # 1) Busca temática em cima do arquivo anual
            dados_filtrados = buscar_proposicoes_por_tema(
                termo=termo.strip(),
                ano=int(ano_val),
                tipos=tipos_sel,
            )

            total_filtradas = len(dados_filtrados)

            if total_filtradas == 0:
                st.error(
                    f"Nenhuma proposição de tipo {', '.join(tipos_sel) or 'qualquer'} "
                    f"em {int(ano_val)} encontrada com o termo “{termo.strip()}”."
                )
                st.stop()

            # Limita a quantidade para não ficar pesado
            dados_filtrados = dados_filtrados[:itens_max]

            df_api = df_proposicoes(dados_filtrados)
            total_api = len(df_api)

        if df_api.empty:
            st.info("Não há dados suficientes para exibir resultados.")
            st.stop()

        # Mensagem de resumo
        st.caption(
            f"Foram encontradas {total_filtradas} proposições que mencionam “{termo.strip()}” "
            f"em {int(ano_val)} (tipos: {', '.join(tipos_sel)}). "
            f"Exibindo as {total_api} primeiras."
        )

        # Enriquecer com autor principal
        autores: List[str] = []
        partidos: List[str] = []
        ufs: List[str] = []
        tipos_autor: List[str] = []

        for _, row in df_api.iterrows():
            aut_payload = autores_por_uri(row.get("uriAutores", ""))
            a = extrair_autor_principal(aut_payload)
            autores.append(a["nome"])
            partidos.append(a["partido"])
            ufs.append(a["uf"])
            tipos_autor.append(a["tipoAutor"])

        df = df_api.copy()
        df["autor"] = autores
        df["partido"] = partidos
        df["uf"] = ufs
        df["tipoAutor"] = tipos_autor
        df["dias_desde_status"] = df["data_status"].apply(dias_desde)

        st.subheader("Resultados")
        st.dataframe(
            df[
                [
                    "rotulo",
                    "ementa",
                    "autor",
                    "partido",
                    "uf",
                    "situacao",
                    "tramitacao_atual",
                    "data_status",
                    "dias_desde_status",
                    "link",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        # Downloads
        col1, col2 = st.columns(2)
        with col1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Baixar CSV", data=csv, file_name="legitrack_resultados.csv", mime="text/csv"
            )
        with col2:
            raw_json = json.dumps(dados_filtrados, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button(
                "⬇️ Baixar JSON (raw proposicoes-ano)", data=raw_json, file_name="legitrack_raw.json", mime="application/json"
            )

        # ============== Gráficos ==============
        st.subheader("Gráficos")
        g1, g2 = st.columns(2)

        # 1) Distribuição por situação
        with g1:
            sit = df["situacao"].fillna("Sem situação").value_counts().reset_index()
            sit.columns = ["situação", "quantidade"]
            fig1 = px.bar(
                sit,
                x="situação",
                y="quantidade",
                title="Distribuição por situação",
                text="quantidade",
            )
            fig1.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)

        # 2) Distribuição por tipo de proposição
        with g2:
            tipos = df["siglaTipo"].fillna("—").value_counts().reset_index()
            tipos.columns = ["tipo", "quantidade"]
            fig2 = px.bar(
                tipos,
                x="tipo",
                y="quantidade",
                title="Tipos de proposição encontrados",
                text="quantidade",
            )
            fig2.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        # 3) Histograma de dias desde o último status
        st.markdown("### Tempo desde o último status (dias)")
        dias = df["dias_desde_status"].dropna()
        if not dias.empty:
            fig3 = px.histogram(
                dias, nbins=20, title="Histograma de dias desde o último status"
            )
            fig3.update_layout(xaxis_title="dias", yaxis_title="proposições")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sem dados de data de status para gerar histograma.")

        # ============== Detalhe + Timeline ==============
        st.subheader("Detalhe e Linha do Tempo")
        escolha = st.selectbox(
            "Selecione uma proposição para ver a timeline", options=df["rotulo"].tolist()
        )
        row = df[df["rotulo"] == escolha].iloc[0]
        cA, cB = st.columns([2, 3])

        with cA:
            st.markdown(f"**{row['rotulo']}**  \n{row['ementa']}")
            st.markdown(
                f"**Autor:** {row['autor'] or '—'} ({row['partido'] or '—'}/{row['uf'] or '—'})"
            )
            st.markdown(f"**Situação:** {row['situacao'] or '—'}")
            st.markdown(f"**Tramitação atual:** {row['tramitacao_atual'] or '—'}")
            if row["data_status"]:
                st.markdown(
                    f"**Data do status:** {row['data_status'].date().isoformat()} "
                    f"({row['dias_desde_status']} dia(s) atrás)"
                )
            st.markdown(f"[🔗 Página oficial]({row['link']})")

        with cB:
            with st.spinner("Carregando tramitações..."):
                tram = tramitacoes(int(row["id"]))
            if tram:
                tdf = pd.DataFrame(tram)
                tdf["dataHora"] = tdf["dataHora"].apply(parse_date)
                tdf = tdf.dropna(subset=["dataHora"]).sort_values("dataHora")
                tdf["evento"] = (
                    tdf["descricaoSituacao"]
                    .fillna(tdf["despacho"])
                    .fillna("(sem descrição)")
                )
                tdf["data"] = tdf["dataHora"].dt.date

                fig_t = px.scatter(
                    tdf,
                    x="dataHora",
                    y=["evento"],
                    title="Linha do tempo da tramitação",
                    hover_data={"evento": True, "dataHora": "|%Y-%m-%d %H:%M"},
                )
                fig_t.update_layout(showlegend=False, yaxis_title=None, xaxis_title=None)
                st.plotly_chart(fig_t, use_container_width=True)

                with st.expander("Ver eventos (tabela)"):
                    st.dataframe(
                        tdf[["data", "evento", "orgaoDestino.sigla"]].rename(
                            columns={"orgaoDestino.sigla": "órgão destino"}
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.info("Sem dados de tramitação disponíveis para esta proposição.")

    except CamaraAPIError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")

else:
    st.info(
        "Use os filtros na barra lateral, escolha um ano, selecione tipos de proposição "
        "e clique em **Buscar proposições** para começar."
    )

st.markdown("---")
st.markdown("**Participantes do grupo:** Gustavo Jardim • Pedro Henrique Bastos • Sávio Verbicário")
