# app.py
# LegiTrack BR — Radar Temático de Projetos de Lei
# Autores: Gustavo Jardim, Pedro Henrique Bastos e Sávio Verbicário

from typing import List
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from services.camara import (
    buscar_proposicoes_por_tema,
    tramitacoes,
    autores_por_proposicao,
    CamaraAPIError,
)

from utils.transforms import (
    df_proposicoes,
    dias_desde,
    parse_date,
    extrair_autor_principal,
)

st.set_page_config(page_title="LegiTrack BR", page_icon="📜", layout="wide")

TIPOS_SUPORTADOS = ["PL", "PLP", "PEC", "MPV", "PDC"]

# ---------------------------------------------------------
# Sidebar de filtros
# ---------------------------------------------------------
st.sidebar.header("🔎 Filtros de busca")

termo = st.sidebar.text_input(
    "Palavra-chave (ementa/keywords)",
    placeholder="ex.: apostas, anistia, LGPD, violência doméstica",
)

ano_val = st.sidebar.number_input(
    "Ano da apresentação",
    min_value=1990,
    max_value=2100,
    value=2024,
    step=1,
)

tipos_sel = st.sidebar.multiselect(
    "Tipos de proposição",
    options=TIPOS_SUPORTADOS,
    default=["PL", "PEC", "PLP"],
)

itens_max = st.sidebar.slider(
    "Máximo de resultados exibidos",
    min_value=10,
    max_value=300,
    value=80,
    step=10,
)

btn_buscar = st.sidebar.button("Buscar proposições", use_container_width=True)

# ---------------------------------------------------------
# Título
# ---------------------------------------------------------
st.title("📜 LegiTrack BR — Radar Temático de Projetos de Lei")
st.caption(
    "Busca proposições (PL, PEC, PLP, MPV, PDC) por tema usando ementa e keywords "
    "com base nos dados abertos da Câmara dos Deputados."
)

# ---------------------------------------------------------
# Lógica de busca
# ---------------------------------------------------------
if btn_buscar:
    if not termo.strip():
        st.warning("Digite uma palavra-chave para buscar.")
        st.stop()

    try:
        with st.spinner("Carregando proposições e filtrando por tema..."):
            dados_filtrados = buscar_proposicoes_por_tema(
                termo=termo.strip(),
                ano=int(ano_val),
                tipos=tipos_sel,
            )

            total_filtradas = len(dados_filtrados)

            if total_filtradas == 0:
                st.error(
                    f"Nenhuma proposição de tipo {', '.join(tipos_sel)} "
                    f"em {ano_val} encontrada com o termo “{termo.strip()}”."
                )
                st.stop()

            dados_filtrados = dados_filtrados[:itens_max]

            df_api = df_proposicoes(dados_filtrados)

        if df_api.empty:
            st.info("Não há dados suficientes para exibir resultados.")
            st.stop()

        # Recuperar autores (somente NOME)
        autores_lista = []
        for _, row_api in df_api.iterrows():
            try:
                aut_payload = autores_por_proposicao(int(row_api["id"]))
                autor_nome = extrair_autor_principal(aut_payload)
            except Exception:
                autor_nome = None
            autores_lista.append(autor_nome)

        df = df_api.copy()
        df["autor"] = autores_lista
        df["dias_desde_status"] = df["data_status"].apply(dias_desde)

        # Resumo
        st.caption(
            f"Foram encontradas {total_filtradas} proposições que mencionam “{termo.strip()}” "
            f"em {ano_val}. Exibindo as {len(df)} primeiras."
        )

        # ---------------------------------------------------------
        # Tabela principal
        # ---------------------------------------------------------
        st.subheader("Resultados")

        st.dataframe(
            df[
                [
                    "rotulo",
                    "autor",
                    "ementa",
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

        # ---------------------------------------------------------
        # Downloads
        # ---------------------------------------------------------
        col1, col2 = st.columns(2)
        with col1:
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Baixar CSV",
                data=csv_bytes,
                file_name="legitrack_resultados.csv",
                mime="text/csv",
            )
        with col2:
            raw_json = json.dumps(dados_filtrados, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button(
                "⬇️ Baixar JSON original",
                data=raw_json,
                file_name="legitrack_raw.json",
                mime="application/json",
            )

        # ---------------------------------------------------------
        # Gráficos
        # ---------------------------------------------------------
        st.subheader("Gráficos")

        g1, g2 = st.columns(2)

        # 1) Situação
        with g1:
            sit = df["situacao"].fillna("—").value_counts().reset_index()
            sit.columns = ["situacao", "quantidade"]

            fig1 = px.bar(
                sit,
                x="situacao",
                y="quantidade",
                text="quantidade",
                title="Distribuição por situação",
            )
            fig1.update_layout(showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)

        # 2) Tipo
        with g2:
            tipos = df["siglaTipo"].value_counts().reset_index()
            tipos.columns = ["tipo", "quantidade"]

            fig2 = px.bar(
                tipos,
                x="tipo",
                y="quantidade",
                text="quantidade",
                title="Tipos encontrados",
            )
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        # 3) Histograma
        st.markdown("### Tempo desde o último status")
        dias = df["dias_desde_status"].dropna()
        if not dias.empty:
            fig3 = px.histogram(
                dias, nbins=20, title="Histograma de dias desde o último status"
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sem informações de data para gerar histograma.")

        # ---------------------------------------------------------
        # Detalhes + Timeline
        # ---------------------------------------------------------
        st.subheader("Detalhe + Linha do Tempo")

        escolha = st.selectbox(
            "Selecione uma proposição",
            df["rotulo"].tolist(),
        )
        row = df[df["rotulo"] == escolha].iloc[0]

        cA, cB = st.columns([2, 3])

        with cA:
            st.markdown(f"### {row['rotulo']}")
            st.markdown(f"**Autor:** {row['autor'] or '—'}")
            st.markdown(f"**Ementa:** {row['ementa']}")
            st.markdown(f"**Situação:** {row['situacao'] or '—'}")
            st.markdown(f"**Tramitação atual:** {row['tramitacao_atual'] or '—'}")
            if row["data_status"]:
                st.markdown(
                    f"**Data do status:** {row['data_status'].date()} "
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
                tdf["data"] = tdf["dataHora"].dt.date

                # Evento (descrição)
                desc = tdf.get("descricaoSituacao")
                desp = tdf.get("despacho")
                if desc is not None:
                    tdf["evento"] = desc.fillna(desp).fillna("(sem descrição)")
                else:
                    tdf["evento"] = desp.fillna("(sem descrição)") if desp is not None else "(sem descrição)"

                fig_t = px.scatter(
                    tdf,
                    x="dataHora",
                    y=["evento"],
                    title="Linha do tempo",
                    hover_data={"evento": True, "dataHora": "|%Y-%m-%d %H:%M"},
                )
                fig_t.update_layout(showlegend=False)
                st.plotly_chart(fig_t, use_container_width=True)

                with st.expander("Ver tabela de eventos"):
                    colunas_base = ["data", "evento"]
                    coluna_orgao = None

                    for cand in ["orgaoDestino.sigla", "siglaOrgao", "siglaOrgaoDestino"]:
                        if cand in tdf.columns:
                            coluna_orgao = cand
                            break

                    if coluna_orgao:
                        tabela = tdf[colunas_base + [coluna_orgao]].rename(
                            columns={coluna_orgao: "órgão"}
                        )
                    else:
                        tabela = tdf[colunas_base]

                    st.dataframe(
                        tabela,
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.info("Sem dados de tramitação.")

    except CamaraAPIError as e:
        st.error(str(e))

    except Exception as e:
        st.error(f"Erro inesperado: {e}")

else:
    st.info(
        "Use os filtros na barra lateral e clique em **Buscar proposições** para começar."
    )

st.markdown("---")
st.markdown("**Participantes do grupo:** Gustavo Jardim • Pedro Henrique Bastos • Sávio Verbicário")
