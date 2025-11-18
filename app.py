# app.py
# LegiTrack BR — Radar de Projetos de Lei (Câmara dos Deputados)
# Autores: Gustavo Jardim, Pedro Henrique Bastos e Sávio Verbicário

from typing import List
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from services.camara import (
    buscar_proposicoes, detalhes_proposicao, tramitacoes, autores_por_uri, CamaraAPIError
)
from utils.transforms import (
    df_proposicoes, extrair_autor_principal, dias_desde, parse_date
)

st.set_page_config(page_title="LegiTrack BR", page_icon="📜", layout="wide")
TIPOS_SUPORTADOS = ["PL", "PLP", "PEC", "PDC", "MPV"]

# ============== Sidebar (filtros) ==============
st.sidebar.header("🔎 Filtros de busca")
termo = st.sidebar.text_input("Palavra-chave (ementa)", placeholder="ex.: apostas, LGPD, anistia")

c1, c2 = st.sidebar.columns(2)
with c1:
    tipo = st.selectbox("Tipo", TIPOS_SUPORTADOS, index=0)
with c2:
    ano_val = st.number_input("Ano (opcional)", min_value=1990, max_value=2100, value=2025, step=1)
    usar_ano = st.checkbox("Filtrar por ano", value=True)

itens = st.sidebar.slider("Quantidade de resultados (da API)", min_value=10, max_value=200, value=50, step=10)
btn_buscar = st.sidebar.button("Buscar proposições", use_container_width=True)

# ============== Título ==============
st.title("📜 LegiTrack BR — Radar de Projetos de Lei")
st.caption("Busca e análise de proposições na Câmara dos Deputados (dados abertos).")

# ============== Busca & Tabela ==============
if btn_buscar:
    if not termo.strip():
        st.warning("Digite uma palavra-chave para buscar.")
        st.stop()

    try:
        with st.spinner("Consultando dados abertos da Câmara..."):
            # 1) Busca na API SOMENTE por tipo/ano (sem termo)
            dados = buscar_proposicoes(
                ano_val if usar_ano else None,
                tipo,
                itens
            )
            df_api = df_proposicoes(dados)
            total_api = len(df_api)

            if total_api == 0:
                st.info("Nenhuma proposição retornada pela API para esse tipo/ano.")
                st.stop()

            # 2) Filtro pelo termo na coluna 'ementa' (lado do Python)
            termo_busca = termo.strip()
            df_filtrado = df_api
            if termo_busca:
                df_filtrado = df_api[df_api["ementa"].str.contains(termo_busca, case=False, na=False)]

        # 3) Se o filtro por termo zerar, avisa e volta a usar o DF original
        if df_filtrado.empty:
            st.warning(
                f"Nenhum resultado com a palavra-chave “{termo_busca}” "
                f"nos {total_api} projetos carregados. Mostrando todos os resultados sem esse filtro."
            )
            df = df_api.copy()
        else:
            df = df_filtrado.copy()

        # Mostra um resumo no topo
        st.caption(
            f"Foram carregadas {total_api} proposições da API; "
            f"{len(df)} exibidas após aplicação dos filtros."
        )

        # Enriquecer com autor principal
        autores: List[str] = []
        partidos: List[str] = []
        ufs: List[str] = []
        tipos_autor: List[str] = []

        for _, row in df.iterrows():
            aut_payload = autores_por_uri(row.get("uriAutores", ""))
            a = extrair_autor_principal(aut_payload)
            autores.append(a["nome"])
            partidos.append(a["partido"])
            ufs.append(a["uf"])
            tipos_autor.append(a["tipoAutor"])

        df["autor"] = autores
        df["partido"] = partidos
        df["uf"] = ufs
        df["tipoAutor"] = tipos_autor
        df["dias_desde_status"] = df["data_status"].apply(dias_desde)

        st.subheader("Resultados")
        st.dataframe(
            df[[
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
            ]],
            use_container_width=True,
            hide_index=True,
        )

        # Downloads
        col1, col2 = st.columns(2)
        with col1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Baixar CSV", data=csv, file_name="legitrack_resultados.csv", mime="text/csv")
        with col2:
            raw_json = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button("⬇️ Baixar JSON (raw API)", data=raw_json, file_name="legitrack_raw.json", mime="application/json")

        # ============== Gráficos ==============
        st.subheader("Gráficos")
        g1, g2 = st.columns(2)

        # 1) Distribuição por situação
        with g1:
            sit = df["situacao"].fillna("Sem situação").value_counts().reset_index()
            sit.columns = ["situação", "quantidade"]
            fig1 = px.bar(sit, x="situação", y="quantidade", title="Distribuição por situação", text="quantidade")
            fig1.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)

        # 2) Autores por partido (Top 10)
        with g2:
            part = df["partido"].fillna("—").value_counts().head(10).reset_index()
            part.columns = ["partido", "quantidade"]
            fig2 = px.bar(part, x="partido", y="quantidade", title="Autores por partido (Top 10)", text="quantidade")
            fig2.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        # 3) Histograma de dias desde o último status
        st.markdown("### Tempo desde o último status (dias)")
        dias = df["dias_desde_status"].dropna()
        if not dias.empty:
            fig3 = px.histogram(dias, nbins=20, title="Histograma de dias desde o último status")
            fig3.update_layout(xaxis_title="dias", yaxis_title="proposições")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sem dados de data de status para gerar histograma.")

        # ============== Detalhe + Timeline ==============
        st.subheader("Detalhe e Linha do Tempo")
        escolha = st.selectbox("Selecione uma proposição para ver a timeline", options=df["rotulo"].tolist())
        row = df[df["rotulo"] == escolha].iloc[0]
        cA, cB = st.columns([2, 3])

        with cA:
            st.markdown(f"**{row['rotulo']}**  \n{row['ementa']}")
            st.markdown(f"**Autor:** {row['autor'] or '—'} ({row['partido'] or '—'}/{row['uf'] or '—'})")
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
                tdf["evento"] = tdf["descricaoSituacao"].fillna(tdf["despacho"]).fillna("(sem descrição)")
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
    st.info("Use os filtros na barra lateral e clique em **Buscar proposições** para começar.")

st.markdown("---")
st.markdown("**Participantes do grupo:** Gustavo Jardim • Pedro Henrique Bastos • Sávio Verbicário")

