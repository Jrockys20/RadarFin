import pandas as pd
import plotly.express as px
import streamlit as st
import hashlib
import sqlite3

from validar_datos import COLUMNAS_OBLIGATORIAS

from revisiones import (
    ESTADOS_REVISION,
    inicializar_bd,
    leer_revisiones,
    guardar_revision,
)
from validar_datos import CARPETA_DATOS, cargar_y_validar_csv
from motor_alertas import analizar_operaciones
from evaluar_motor import evaluar_resultados


PRIORIDADES = ["Alta", "Media", "Baja", "Sin alerta"]

COLORES = {
    "Alta": "#D64550",
    "Media": "#E89B25",
    "Baja": "#3978BA",
}


def formatear_porcentaje(valor):
    if valor is None:
        return "No definida"

    return f"{valor:.2%}"


def cargar_datos():
    st.sidebar.header("Datos de entrada")

    origen = st.sidebar.radio(
        "Selecciona el origen",
        ["Ejemplo incluido", "Cargar CSV"],
    )

    if origen == "Ejemplo incluido":
        historial = cargar_y_validar_csv(
            CARPETA_DATOS / "historial.csv"
        )

        operaciones = cargar_y_validar_csv(
            CARPETA_DATOS / "desarrollo.csv"
        )

        st.sidebar.caption(
            "Ejemplo: historial y conjunto de desarrollo."
        )

        return historial, operaciones

    st.sidebar.caption(
        "Carga un historial anterior al lote que deseas analizar. "
        "Utiliza datos ficticios y montos en soles."
    )

    archivo_historial = st.sidebar.file_uploader(
        "Historial de operaciones",
        type=["csv"],
        key="archivo_historial",
    )

    archivo_operaciones = st.sidebar.file_uploader(
        "Operaciones para analizar",
        type=["csv"],
        key="archivo_operaciones",
    )

    if archivo_historial is None or archivo_operaciones is None:
        st.info(
            "Carga ambos archivos desde la barra lateral "
            "para comenzar el análisis."
        )
        st.stop()

    # Cada lectura empieza al principio del archivo.
    archivo_historial.seek(0)
    archivo_operaciones.seek(0)

    historial = cargar_y_validar_csv(archivo_historial)
    operaciones = cargar_y_validar_csv(archivo_operaciones)

    return historial, operaciones


def mostrar_resumen(resultado):
    total = len(resultado)
    cantidad_alertas = int(resultado["tiene_alerta"].sum())
    altas = int(resultado["prioridad"].eq("Alta").sum())

    columnas = st.columns(4)

    columnas[0].metric("Operaciones", total)
    columnas[1].metric("Con alerta", cantidad_alertas)
    columnas[2].metric("Prioridad alta", altas)
    columnas[3].metric(
        "Enviadas a revisión",
        f"{cantidad_alertas / total:.2%}",
    )

    st.caption(
        "Los indicadores y el gráfico corresponden al lote completo."
    )

    incompletas = int((
        ~resultado["monto_evaluable"]
        | ~resultado["horario_evaluable"]
    ).sum())

    if incompletas:
        st.warning(
            f"{incompletas} operaciones tienen historial insuficiente "
            "para evaluar monto u horario. "
            "La regla de ráfaga sí puede evaluarlas."
        )

    alertas = resultado.loc[resultado["tiene_alerta"]]

    distribucion = (
        alertas["prioridad"]
        .value_counts()
        .reindex(PRIORIDADES[:3], fill_value=0)
        .rename_axis("Prioridad")
        .reset_index(name="Alertas")
    )

    grafico = px.bar(
        distribucion,
        x="Prioridad",
        y="Alertas",
        color="Prioridad",
        text="Alertas",
        color_discrete_map=COLORES,
        category_orders={"Prioridad": PRIORIDADES[:3]},
        title="Alertas por prioridad",
    )

    grafico.update_layout(
        showlegend=False,
        yaxis={"dtick": 1},
    )

    st.plotly_chart(grafico, width="stretch")


def mostrar_bandeja(resultado, id_lote):
    st.subheader("Bandeja de revisión")

    filtro1, filtro2, filtro3 = st.columns(3)

    with filtro1:
        prioridades = st.multiselect(
            "Prioridad",
            options=PRIORIDADES,
            default=PRIORIDADES[:3],
        )

    with filtro2:
        clientes = st.multiselect(
            "Clientes",
            options=sorted(resultado["id_cliente"].unique().tolist()),
            help="Déjalo vacío para incluir a todos los clientes.",
        )

    with filtro3:
        canales = st.multiselect(
            "Canales",
            options=sorted(resultado["canal"].unique().tolist()),
            help="Déjalo vacío para incluir todos los canales.",
        )

    mascara = resultado["prioridad"].isin(prioridades)

    if clientes:
        mascara = mascara & resultado["id_cliente"].isin(clientes)

    if canales:
        mascara = mascara & resultado["canal"].isin(canales)

    visibles = resultado.loc[mascara].copy()

    st.caption(
        f"{len(visibles)} operaciones visibles de {len(resultado)}. "
        "Orden inicial: mayor puntuación y, en caso de empate, "
        "operación más reciente."
    )

    if visibles.empty:
        st.info("No hay operaciones que coincidan con estos filtros.")
        return

    columnas_tabla = [
        "id_transaccion",
        "id_cliente",
        "fecha_hora",
        "monto",
        "canal",
        "puntaje_total",
        "prioridad",
    ]

        # Si cambian las filas visibles, reiniciamos la selección.
    contenido_tabla = visibles[columnas_tabla].to_csv(
        index=False
    ).encode("utf-8")

    identificador_tabla = hashlib.sha256(
        contenido_tabla
    ).hexdigest()

    st.caption(
        "Marca la casilla a la izquierda de una fila "
        "para consultar su detalle."
    )

    evento = st.dataframe(
        visibles[columnas_tabla],
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=f"tabla_operaciones_{identificador_tabla}",
        column_config={
            "id_transaccion": "Operación",
            "id_cliente": "Cliente",
            "fecha_hora": st.column_config.DatetimeColumn(
                "Fecha y hora",
                format="DD/MM/YYYY HH:mm",
            ),
            "monto": st.column_config.NumberColumn(
                "Monto (S/)",
                format="S/ %.2f",
            ),
            "canal": "Canal",
            "puntaje_total": st.column_config.NumberColumn(
                "Puntuación",
                format="%d",
            ),
            "prioridad": "Prioridad",
        },
    )

    st.download_button(
        "Descargar operaciones filtradas",
        data=visibles.to_csv(
            index=False,
            date_format="%Y-%m-%d %H:%M:%S",
        ).encode("utf-8-sig"),
        file_name="radarfin_operaciones_filtradas.csv",
        mime="text/csv",
    )

    st.subheader("Detalle de la operación")

    filas_seleccionadas = evento.selection.rows

    if not filas_seleccionadas:
        st.info(
            "Selecciona una fila de la tabla para ver su detalle."
        )
        return

    posicion = filas_seleccionadas[0]

    detalle = visibles.iloc[posicion]

    st.write(f"**Operación seleccionada:** {detalle['id_transaccion']}")

    dato1, dato2, dato3 = st.columns(3)

    dato1.metric("Cliente", detalle["id_cliente"])
    dato2.metric("Puntuación", int(detalle["puntaje_total"]))
    dato3.metric("Prioridad", detalle["prioridad"])

    st.info(detalle["explicacion"])

    if not detalle["monto_evaluable"]:
        st.warning(
            "Monto no evaluado: falta historial suficiente."
        )

    if not detalle["horario_evaluable"]:
        st.warning(
            "Horario no evaluado: falta historial suficiente."
        )

    st.caption(
        "La puntuación expresa prioridad de revisión. "
        "No representa una probabilidad de fraude."
    )

    st.subheader("Seguimiento de la revisión")

    clave_revision = (
        f"{id_lote}_{detalle['id_transaccion']}"
    )

    with st.form(key=f"formulario_{clave_revision}"):
        estado = st.selectbox(
            "Estado de revisión",
            options=ESTADOS_REVISION,
            index=ESTADOS_REVISION.index(
                detalle["estado_revision"]
            ),
            key=f"estado_{clave_revision}",
        )

        comentario = st.text_area(
            "Comentario del analista",
            value=detalle["comentario_revision"],
            max_chars=2000,
            placeholder=(
                "Describe lo observado y las verificaciones realizadas."
            ),
            key=f"comentario_{clave_revision}",
        )

        guardar = st.form_submit_button("Guardar revisión")

    if guardar:
        guardar_revision(
            id_lote=id_lote,
            id_transaccion=detalle["id_transaccion"],
            estado=estado,
            comentario=comentario,
        )

        st.session_state["revision_guardada"] = True
        st.rerun()

    if pd.notna(detalle["actualizado_utc"]):
        st.caption(
            "Última actualización (UTC): "
            f"{detalle['actualizado_utc']}"
        )


def mostrar_evaluacion(operaciones, resultado):
    st.subheader("Evaluación del lote completo")

    st.caption(
        "Estas métricas no cambian con los filtros de la bandeja."
    )

    if "es_anomalia" not in operaciones.columns:
        st.info(
            "Este lote no incluye etiquetas de anomalías. "
            "Puedes revisar las alertas, pero no calcular "
            "precisión, exhaustividad ni F1."
        )
        return

    metricas, comparacion = evaluar_resultados(
        operaciones,
        resultado,
    )

    columna1, columna2, columna3 = st.columns(3)

    columna1.metric(
        "Precisión",
        formatear_porcentaje(metricas["precision"]),
    )

    columna2.metric(
        "Exhaustividad",
        formatear_porcentaje(metricas["exhaustividad"]),
    )

    columna3.metric(
        "F1",
        formatear_porcentaje(metricas["f1"]),
    )

    st.subheader("Comparación con las etiquetas")

    matriz = pd.DataFrame(
        [
            [
                metricas["verdaderos_positivos"],
                metricas["falsos_negativos"],
            ],
            [
                metricas["falsos_positivos"],
                metricas["verdaderos_negativos"],
            ],
        ],
        index=["Anómala según etiqueta", "Normal según etiqueta"],
        columns=["Con alerta", "Sin alerta"],
    )

    st.dataframe(matriz, width="stretch")

    st.caption(
        "Los resultados describen este conjunto sintético. "
        "No demuestran desempeño sobre operaciones bancarias reales."
    )

    omitidas = comparacion.loc[
        comparacion["es_falso_negativo"]
    ]

    with st.expander("Ver anomalías no detectadas"):
        if omitidas.empty:
            st.write("No hay anomalías etiquetadas sin detectar.")
        else:
            columnas = ["id_transaccion"]

            for columna in ["id_cliente", "tipo_anomalia"]:
                if columna in omitidas.columns:
                    columnas.append(columna)

            st.dataframe(
                omitidas[columnas],
                hide_index=True,
                width="stretch",
            )


def calcular_id_lote(historial, operaciones):
    huella = hashlib.sha256()

    for tabla in [historial, operaciones]:
        contenido = (
            tabla[COLUMNAS_OBLIGATORIAS]
            .sort_values("id_transaccion")
            .to_csv(
                index=False,
                date_format="%Y-%m-%d %H:%M:%S",
            )
        )

        huella.update(contenido.encode("utf-8"))
        huella.update(b"\0")

    return huella.hexdigest()


def main():
    st.set_page_config(
        page_title="RadarFin",
        page_icon="📡",
        layout="wide",
    )

    st.title("RadarFin")
    st.caption("Priorización explicable de alertas financieras")

    st.info(
        "Demo con transacciones ficticias. "
        "Una operación inusual requiere revisión humana: "
        "no implica fraude ni produce bloqueos automáticos."
    )

    historial, operaciones = cargar_datos()

    with st.spinner("Analizando operaciones..."):
        resultado = analizar_operaciones(historial, operaciones)

    id_lote = calcular_id_lote(historial, operaciones)

    inicializar_bd()

    revisiones = leer_revisiones(id_lote)

    resultado = resultado.merge(
        revisiones,
        on="id_transaccion",
        how="left",
        validate="one_to_one",
    )

    resultado["estado_revision"] = (
        resultado["estado_revision"].fillna("Pendiente")
    )

    resultado["comentario_revision"] = (
        resultado["comentario_revision"].fillna("")
    )

    if st.session_state.pop("revision_guardada", False):
        st.success("Revisión guardada correctamente.")

    resumen, bandeja, evaluacion = st.tabs([
        "Resumen",
        "Bandeja de revisión",
        "Evaluación",
    ])

    with resumen:
        mostrar_resumen(resultado)

    with bandeja:
        mostrar_bandeja(resultado, id_lote)

    with evaluacion:
        mostrar_evaluacion(operaciones, resultado)


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        OSError,
        UnicodeError,
        sqlite3.Error,
        pd.errors.ParserError,
        pd.errors.MergeError,
    ) as error:
        st.error(f"No se pudo completar el análisis: {error}")