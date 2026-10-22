"""Componentes de presentación de RadarFin; no modifica el motor de detección."""
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from diseno import PRIORIDADES, COLORES, TOKENS, aplicar_estilos, etiqueta_prioridad


def configurar_grafico(figura, titulo, altura=290):
    figura.update_layout(
        template="plotly_dark", title=dict(text=titulo, font=dict(size=15, color=TOKENS["text"])),
        height=altura, margin=dict(l=12, r=16, t=48, b=16),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", color=TOKENS["muted"], size=12),
        legend_title_text="", legend=dict(orientation="h", y=1.15),
    )
    figura.update_xaxes(showgrid=False, zeroline=False)
    figura.update_yaxes(gridcolor=TOKENS["border"], zeroline=False, rangemode="tozero")
    return figura


def mostrar_resumen(resultado):
    st.caption("Lote completo · Los filtros de la bandeja no modifican este análisis.")
    total = len(resultado)
    alertas = int(resultado["tiene_alerta"].sum())
    columnas = st.columns(4)
    for indice, (col, titulo, valor) in enumerate(zip(
        columnas,
        ["Operaciones analizadas", "Operaciones con alerta", "Prioridad alta", "Enviadas a revisión"],
        [f"{total:,}", f"{alertas:,}", str(int(resultado["prioridad"].eq("Alta").sum())),
         f"{alertas / total:.2%}" if total else "No definida"],
    )):
        with col.container(key=f"kpi-{indice}"):
            st.metric(titulo, valor)

    incompletas = int((~resultado["monto_evaluable"] | ~resultado["horario_evaluable"]).sum())
    if incompletas:
        st.warning(f"{incompletas} operaciones sin historial suficiente para monto u horario. "
                   "La regla de ráfaga sigue disponible; carga más historial para completar la evaluación.")

    izquierda, derecha = st.columns(2)
    with izquierda, st.container(border=True, key="chart-priority"):
        if not alertas:
            st.info("Este lote no presenta alertas. Puedes consultar todas las operaciones en la bandeja.")
        distribucion = (resultado.loc[resultado["tiene_alerta"], "prioridad"].value_counts()
                        .reindex(PRIORIDADES[:3], fill_value=0).rename_axis("Prioridad")
                        .reset_index(name="Operaciones"))
        fig = px.bar(distribucion, x="Prioridad", y="Operaciones", color="Prioridad",
                     text="Operaciones", color_discrete_map=COLORES)
        fig.update_layout(showlegend=False)
        fig.update_traces(hovertemplate="%{x}<br>%{y} operaciones<extra></extra>", cliponaxis=False)
        st.plotly_chart(configurar_grafico(fig, "Alertas por prioridad"), width="stretch",
                        theme=None, config={"displayModeBar": False})
    with derecha, st.container(border=True, key="chart-rules"):
        reglas = pd.DataFrame({
            "Regla": ["Monto", "Ráfaga", "Horario"],
            "Operaciones": [int(resultado[f"alerta_{r}"].sum()) for r in ["monto", "rafaga", "horario"]],
        })
        fig = px.bar(reglas, x="Regla", y="Operaciones", text="Operaciones",
                     color_discrete_sequence=[TOKENS["cyan"]])
        fig.update_traces(hovertemplate="%{x}<br>%{y} operaciones<extra></extra>", cliponaxis=False)
        st.plotly_chart(configurar_grafico(fig, "Reglas activadas"), width="stretch",
                        theme=None, config={"displayModeBar": False})
        st.caption("Una operación puede activar varias reglas; estos conteos no se suman como alertas únicas.")

    with st.container(border=True, key="chart-timeline"):
        temporal = (resultado.set_index("fecha_hora")
                    .resample("D").agg(Operaciones=("id_transaccion", "size"), Alertas=("tiene_alerta", "sum"))
                    .rename_axis("Fecha").reset_index())
        if len(temporal) > 1:
            fig = px.line(temporal, x="Fecha", y=["Operaciones", "Alertas"], markers=True,
                          color_discrete_map={"Operaciones": TOKENS["cyan"], "Alertas": TOKENS["brand"]},
                          labels={"value": "Operaciones", "variable": "Serie"})
            fig.update_xaxes(tickformat="%d/%m")
            fig.update_traces(hovertemplate="%{x|%d/%m/%Y}<br>%{y} operaciones<extra>%{fullData.name}</extra>")
            st.plotly_chart(configurar_grafico(fig, "Actividad diaria · operaciones y alertas", 270),
                            width="stretch", theme=None, config={"displayModeBar": False})
        else:
            st.caption("El lote cubre un solo día. La evolución diaria estará disponible con un periodo mayor.")

    st.markdown("#### Últimas señales")
    recientes = resultado.loc[resultado["tiene_alerta"]].sort_values("fecha_hora", ascending=False).head(5)
    if not recientes.empty:
        st.caption("Las cinco alertas más recientes del lote · Consulta sus motivos en la bandeja.")
        st.dataframe(recientes[["id_transaccion", "fecha_hora", "prioridad", "puntaje_total", "monto"]],
                     hide_index=True, width="stretch", column_config=columnas_operaciones())


def columnas_operaciones():
    return {
        "id_transaccion": st.column_config.TextColumn("Operación", pinned=True),
        "id_cliente": "Cliente",
        "fecha_hora": st.column_config.DatetimeColumn("Fecha y hora", format="DD/MM/YYYY HH:mm"),
        "monto": st.column_config.NumberColumn("Monto (S/)", format="S/ %.2f"),
        "canal": "Canal",
        "puntaje_total": st.column_config.ProgressColumn("Puntuación / 100", min_value=0, max_value=100, format="%d"),
        "prioridad": "Prioridad",
        "estado_revision": "Revisión",
        "comentario_revision": "Comentario del analista",
        "tipo_anomalia": "Escenario etiquetado",
    }


def colorear_prioridad(valor):
    valor = valor if valor in COLORES else valor.split(" ", 1)[-1]
    color = COLORES.get(valor, TOKENS["muted"])
    return f"color: {color}; font-weight: 600"


def mostrar_evaluacion(operaciones, resultado, evaluar_resultados):
    st.subheader("¿Qué detectó RadarFin?")
    st.caption("Evaluación del lote completo contra etiquetas sintéticas. Los estados del analista no intervienen.")
    if "es_anomalia" not in operaciones.columns:
        st.info("Este lote no incluye etiquetas. Puedes revisar alertas; para evaluar el detector, "
                "carga un CSV con la columna es_anomalia (0 o 1).")
        return
    metricas, comparacion = evaluar_resultados(operaciones, resultado)
    for col, clave, titulo, ayuda in zip(
        st.columns(3), ["precision", "exhaustividad", "f1"],
        ["Precisión", "Exhaustividad", "F1"],
        ["De las alertas, cuántas corresponden a anomalías etiquetadas.",
         "De las anomalías etiquetadas, cuántas generaron una alerta.",
         "Equilibrio entre precisión y exhaustividad."],
    ):
        valor = metricas[clave]
        col.metric(titulo, "No definida" if valor is None else f"{valor:.2%}", help=ayuda, border=True)
        col.caption(ayuda)
    if any(metricas[k] is None for k in ["precision", "exhaustividad", "f1"]):
        st.info("Una métrica sin denominador válido aparece como «No definida». "
                "Revisa si el lote contiene alertas y anomalías etiquetadas.")

    izquierda, derecha = st.columns(2)
    with izquierda, st.container(border=True, key="eval-matriz"):
        matriz = [
            [metricas["verdaderos_positivos"], metricas["falsos_negativos"]],
            [metricas["falsos_positivos"], metricas["verdaderos_negativos"]],
        ]
        fig = px.imshow(matriz, x=["Con alerta", "Sin alerta"],
                        y=["Anómala", "Normal"], text_auto=True,
                        color_continuous_scale=[TOKENS["elevated"], TOKENS["brand"]],
                        labels={"x": "Predicción del detector", "y": "Etiqueta real", "color": "Operaciones"},
                        aspect="auto")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(configurar_grafico(fig, "Matriz de confusión", 310),
                        width="stretch", theme=None, config={"displayModeBar": False})
    with derecha, st.container(border=True, key="eval-lectura"):
        st.markdown("**Cómo leer la comparación**")
        for nombre, clave in [
            ("Anomalías detectadas · verdaderos positivos", "verdaderos_positivos"),
            ("Alertas sobre normales · falsos positivos", "falsos_positivos"),
            ("Anomalías omitidas · falsos negativos", "falsos_negativos"),
            ("Normales sin alerta · verdaderos negativos", "verdaderos_negativos"),
        ]:
            st.write(f"{nombre}: **{metricas[clave]}**")
        st.caption("Estos resultados describen datos ficticios; no demuestran desempeño en operaciones bancarias reales.")
    omitidas = comparacion.loc[comparacion["es_falso_negativo"], ["id_transaccion"]]
    st.markdown(f"**Anomalías no detectadas · {len(omitidas)} operaciones**")
    if omitidas.empty:
        st.info("No hay anomalías etiquetadas sin detectar en este lote.")
    else:
        detalle = omitidas.merge(operaciones, on="id_transaccion", validate="one_to_one")
        columnas = ["id_transaccion", "id_cliente", "fecha_hora", "monto", "canal"]
        if "tipo_anomalia" in detalle:
            columnas.append("tipo_anomalia")
        st.dataframe(detalle[columnas], hide_index=True, width="stretch",
                     column_config=columnas_operaciones())
        st.download_button("Descargar anomalías no detectadas",
                           detalle.to_csv(index=False).encode("utf-8-sig"),
                           "radarfin_anomalias_no_detectadas.csv", "text/csv")
