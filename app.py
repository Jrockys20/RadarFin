"""Interfaz de RadarFin. Las reglas y la evaluación se delegan al motor existente."""
import hashlib
import logging
import sqlite3

import pandas as pd
import streamlit as st

from revisiones import ESTADOS_REVISION, inicializar_bd, leer_revisiones, guardar_revision
from validar_datos import CARPETA_DATOS, COLUMNAS_OBLIGATORIAS, cargar_y_validar_csv
from motor_alertas import analizar_operaciones
from evaluar_motor import evaluar_resultados
from interfaz import (
    PRIORIDADES, aplicar_estilos, etiqueta_prioridad, mostrar_resumen,
    mostrar_evaluacion, columnas_operaciones, colorear_prioridad,
)

from diseno import ROOT, PAGINAS, SIMBOLOS, encabezado, contexto

LOGGER = logging.getLogger(__name__)


def cargar_datos():
    st.sidebar.markdown("### Datos de entrada")
    origen = st.sidebar.radio("Origen de los datos", ["Ejemplo incluido", "Cargar CSV"], key="origen_datos")
    if origen == "Ejemplo incluido":
        conjunto = st.sidebar.selectbox("Lote de ejemplo", ["desarrollo", "prueba"])
        historial = cargar_y_validar_csv(CARPETA_DATOS / "historial.csv")
        operaciones = cargar_y_validar_csv(CARPETA_DATOS / f"{conjunto}.csv")
        return historial, operaciones, f"Ejemplo incluido · {conjunto}"
    st.sidebar.caption("Carga ambos CSV. El historial debe ser anterior al lote; utiliza datos ficticios.")
    archivo_historial = st.sidebar.file_uploader("Historial de operaciones", type=["csv"], key="archivo_historial")
    archivo_operaciones = st.sidebar.file_uploader("Operaciones para analizar", type=["csv"], key="archivo_operaciones")
    if archivo_historial is None or archivo_operaciones is None:
        st.info("Carga el historial y el lote desde la barra lateral para comenzar. "
                "Columnas: " + ", ".join(COLUMNAS_OBLIGATORIAS) + ".")
        st.stop()
    archivo_historial.seek(0)
    archivo_operaciones.seek(0)
    return (cargar_y_validar_csv(archivo_historial),
            cargar_y_validar_csv(archivo_operaciones), f"CSV · {archivo_operaciones.name}")


def limpiar_filtros():
    for clave, valor in [("prioridades", PRIORIDADES[:3]), ("clientes", []),
                         ("canales", []), ("estados", [])]:
        st.session_state[f"filtro_{clave}"] = valor

    st.session_state["buscar_operacion"] = ""
    st.session_state["orden_bandeja"] = "Mayor puntuaci?n"
    st.session_state["filtros_guardados"] = {}


def registrar_seleccion(clave_tabla, ids, id_lote):
    # Streamlit devuelve índices del dataframe original aun tras ordenar en el navegador.
    evento = st.session_state.get(clave_tabla, {})
    filas = evento.get("selection", {}).get("rows", [])
    seleccion = ids[filas[0]] if filas and 0 <= filas[0] < len(ids) else None
    st.session_state["operacion_seleccionada"] = (id_lote, seleccion)


def resolver_seleccion(id_lote, visibles):
    lote, identificador = st.session_state.get("operacion_seleccionada", (None, None))
    if lote != id_lote or identificador not in set(visibles["id_transaccion"]):
        st.session_state["operacion_seleccionada"] = (id_lote, None)
        return None
    return identificador


def mostrar_detalle(detalle, id_lote):
    with st.container(border=True, key="detalle-operacion"):
        st.subheader(f"Operación {detalle['id_transaccion']}")
        etiqueta_prioridad(detalle["prioridad"])
        st.caption(f"Cliente {detalle['id_cliente']} · {detalle['fecha_hora']:%d/%m/%Y %H:%M} · Canal {detalle['canal']}")
        st.html(f'<div class="rf-facts"><div><span>Monto</span><strong>S/ {detalle["monto"]:,.2f}</strong></div>'
                f'<div><span>Puntuación</span><strong>{int(detalle["puntaje_total"])} / 100</strong></div></div>')
        st.caption("La puntuación expresa prioridad de revisión; no es una probabilidad de fraude.")
        st.markdown("**Aportes de las reglas**")
        for clave, titulo in [("monto", "Monto inusual"), ("rafaga", "Operaciones en ráfaga"),
                              ("horario", "Horario poco habitual")]:
            evaluable = bool(detalle.get(f"{clave}_evaluable", True))
            estado = "No evaluada" if not evaluable else ("Activada" if detalle[f"alerta_{clave}"] else "Sin activación")
            with st.expander(f"{titulo} · {estado} · +{int(detalle[f'puntos_{clave}'])} puntos",
                             expanded=bool(detalle[f"alerta_{clave}"]) or not evaluable):
                st.write(detalle[f"explicacion_{clave}"])
                if not evaluable:
                    st.caption("Carga más historial del cliente para evaluar esta regla.")

        st.markdown("**Seguimiento del analista**")
        clave_revision = f"{id_lote}_{detalle['id_transaccion']}"
        with st.form(key=f"formulario_{clave_revision}"):
            estado = st.selectbox("Estado de revisión", ESTADOS_REVISION,
                                  index=ESTADOS_REVISION.index(detalle["estado_revision"]),
                                  key=f"estado_{clave_revision}")
            comentario = st.text_area("Comentario del analista", value=detalle["comentario_revision"],
                                      max_chars=2000, key=f"comentario_{clave_revision}",
                                      placeholder="Observaciones y verificaciones realizadas.")
            guardar = st.form_submit_button("Guardar revisión", type="primary")
        if guardar:
            try:
                guardar_revision_desde_app(id_lote, detalle["id_transaccion"], estado, comentario)
            except (ValueError, OSError, sqlite3.Error):
                LOGGER.exception("No se pudo guardar la revisión")
                st.error("No se pudo guardar la revisión. Conserva tu comentario e inténtalo de nuevo.")
            else:
                st.session_state["revision_guardada"] = True
                st.rerun()
        if pd.notna(detalle["actualizado_utc"]):
            st.caption(f"Última actualización (UTC): {detalle['actualizado_utc']}")
        st.caption("El estado y el comentario no cambian las etiquetas ni las métricas del detector.")


def mostrar_bandeja(resultado, id_lote):
    for clave, valor in st.session_state.get("filtros_guardados", {}).items():
        st.session_state.setdefault(clave, valor)
    st.session_state.setdefault("filtro_prioridades", PRIORIDADES[:3])
    st.caption("Prioriza, selecciona una operación y registra lo observado.")
    with st.container(border=True, key="filtros-bandeja"):
        columnas = st.columns(4)
        prioridades = columnas[0].multiselect("Prioridad", PRIORIDADES, key="filtro_prioridades", placeholder="Selecciona prioridades")
        clientes = columnas[1].multiselect("Cliente", sorted(resultado["id_cliente"].unique()),
                                          key="filtro_clientes", placeholder="Todos los clientes", help="Vacío incluye todos los clientes.")
        canales = columnas[2].multiselect("Canal", sorted(resultado["canal"].unique()),
                                         key="filtro_canales", placeholder="Todos los canales", help="Vacío incluye todos los canales.")
        estados = columnas[3].multiselect("Estado de revisión", ESTADOS_REVISION, key="filtro_estados",
                                         placeholder="Todos los estados", help="Vacío incluye todos los estados.")
        st.button("Limpiar filtros", on_click=limpiar_filtros, help="Restablece la bandeja a todas las alertas.")
    busqueda_col, orden_col = st.columns([2, 1])
    busqueda = busqueda_col.text_input("Buscar operación o cliente", key="buscar_operacion",
                                     placeholder="Identificador de operación o cliente")
    orden = orden_col.selectbox("Ordenar por", ["Mayor puntuación", "Más recientes", "Mayor monto"], key="orden_bandeja")
    st.session_state["filtros_guardados"] = {
        k: st.session_state[k] for k in ["filtro_prioridades", "filtro_clientes", "filtro_canales",
                                         "filtro_estados", "buscar_operacion", "orden_bandeja"]
    }
    mascara = resultado["prioridad"].isin(prioridades)
    if busqueda.strip():
        texto = busqueda.strip()
        mascara &= (resultado["id_transaccion"].str.contains(texto, case=False, regex=False)
                    | resultado["id_cliente"].str.contains(texto, case=False, regex=False))
    for campo, valores in [("id_cliente", clientes), ("canal", canales), ("estado_revision", estados)]:
        if valores:
            mascara &= resultado[campo].isin(valores)
    campo_orden = {"Mayor puntuación": "puntaje_total", "Más recientes": "fecha_hora", "Mayor monto": "monto"}[orden]
    campos_orden = [campo_orden, "fecha_hora", "id_transaccion"] if orden == "Mayor puntuación" else [campo_orden, "id_transaccion"]
    sentidos = [False, False, True] if orden == "Mayor puntuación" else [False, True]
    visibles = resultado.loc[mascara].sort_values(
        campos_orden, ascending=sentidos, kind="stable").reset_index(drop=True)
    seleccion_previa = st.session_state.get("operacion_seleccionada", (None, None))[1]
    identificador = resolver_seleccion(id_lote, visibles)
    st.caption(f"{len(visibles)} de {len(resultado)} operaciones · {orden}.")
    if seleccion_previa is not None and identificador is None:
        st.caption("Se limpió la selección porque la operación dejó de estar visible o cambió el lote.")
    # Incluye el lote y los IDs en orden; guardar un comentario no reinicia la tabla.
    ids = tuple(visibles["id_transaccion"])
    huella = hashlib.sha256(repr((id_lote, ids)).encode("utf-8")).hexdigest()
    clave_tabla = f"tabla_operaciones_{huella}"
    st.session_state[clave_tabla] = {"selection": {"rows": [ids.index(identificador)] if identificador in ids else []}}
    campos = ["id_transaccion", "prioridad", "puntaje_total", "id_cliente", "fecha_hora",
              "monto", "canal", "estado_revision"]
    tabla_col, detalle_col = st.columns([1.65, 1], gap="large")
    with tabla_col:
        if visibles.empty:
            st.info("No hay operaciones con estos filtros. Usa «Limpiar filtros» para volver a todas las alertas.")
        else:
            st.caption("Selecciona una fila para abrir su detalle. Puedes ordenar por cualquier columna.")
            presentacion = visibles[campos].copy()
            presentacion["prioridad"] = presentacion["prioridad"].map(lambda p: f"{SIMBOLOS[p]} {p}")
            tabla = presentacion.style.map(colorear_prioridad, subset=["prioridad"])
            st.dataframe(tabla, hide_index=True, width="stretch", height=460,
                         selection_mode="single-row", key=clave_tabla,
                         on_select=lambda: registrar_seleccion(clave_tabla, ids, id_lote),
                         column_config=columnas_operaciones())
        st.download_button("Descargar operaciones filtradas",
                           data=visibles.to_csv(index=False, date_format="%Y-%m-%d %H:%M:%S").encode("utf-8-sig"),
                           file_name="radarfin_operaciones_filtradas.csv", mime="text/csv",
                           disabled=visibles.empty)
    with detalle_col:
        if identificador is None:
            if not visibles.empty:
                with st.container(border=True):
                    st.markdown("**Detalle de la operación**")
                    st.caption("Selecciona una operación de la tabla para consultar sus reglas y registrar una revisión.")
        else:
            mostrar_detalle(visibles.loc[visibles["id_transaccion"].eq(identificador)].iloc[0], id_lote)


def mostrar_datos(historial, operaciones):
    st.write("Selecciona un ejemplo o carga tus archivos desde la barra lateral. Los cambios actualizan todo el análisis.")
    uno, dos = st.columns(2)
    with uno.container(key="datos-historial"):
        st.caption("01 / HISTORIAL DE REFERENCIA")
        st.metric("Operaciones históricas", f"{len(historial):,}", border=True)
    with dos.container(key="datos-lote"):
        st.caption("02 / LOTE ACTIVO")
        st.metric("Operaciones del lote", f"{len(operaciones):,}", border=True)
    st.caption(f"Historial: {historial['fecha_hora'].min():%d/%m/%Y} — {historial['fecha_hora'].max():%d/%m/%Y}")
    with st.expander("Formato de los CSV", expanded=True):
        st.write("Columnas obligatorias: " + ", ".join(COLUMNAS_OBLIGATORIAS) + ".")
        st.write("Fechas: YYYY-MM-DD HH:MM:SS · Montos positivos en soles · Canales: app, web, cajero o agente.")
        st.write("El historial debe ser anterior al lote y sus identificadores no deben repetirse.")
        st.caption("Opcionales: es_anomalia (0 o 1) y tipo_anomalia. Solo se utilizan para evaluación.")
    with st.expander("Reglas y prioridades"):
        st.table(pd.DataFrame([
            ["Monto", "Más de 5 veces la mediana histórica", 40],
            ["Ráfaga", "Quinta operación o posterior en 10 minutos", 35],
            ["Horario", "Franja de 6 horas con menos del 5 % del historial", 25],
        ], columns=["Regla", "Condición", "Puntos"]))
        st.caption("Monto y horario requieren al menos 20 operaciones históricas por cliente.")
        st.write("Alta: 70–100 · Media: 40–69 · Baja: 25–39 · Sin alerta: 0–24.")
    with st.expander("Vista previa del lote"):
        st.dataframe(operaciones.head(50), hide_index=True, width="stretch", column_config=columnas_operaciones())


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


def es_demo_publica():
    try:
        return bool(
            st.secrets.get("modo_demo_publica", True)
        )
    except FileNotFoundError:
        # Sin configuración, usamos la demo por sesión.
        return True


def cargar_revisiones_desde_app(id_lote):
    if not es_demo_publica():
        inicializar_bd()
        return leer_revisiones(id_lote)

    lotes = st.session_state.get("revisiones_demo", {})
    registros = lotes.get(id_lote, {})

    return pd.DataFrame(
        list(registros.values()),
        columns=[
            "id_transaccion",
            "estado_revision",
            "comentario_revision",
            "actualizado_utc",
        ],
    )


def guardar_revision_desde_app(
    id_lote,
    id_transaccion,
    estado,
    comentario,
):
    comentario = comentario.strip()

    if estado not in ESTADOS_REVISION:
        raise ValueError("Estado de revisión no permitido.")

    if len(comentario) > 2000:
        raise ValueError(
            "El comentario no puede superar los 2000 caracteres."
        )

    if not es_demo_publica():
        guardar_revision(
            id_lote,
            id_transaccion,
            estado,
            comentario,
        )
        return

    lotes = st.session_state.get("revisiones_demo", {})

    if id_lote not in lotes:
        lotes[id_lote] = {}

    lotes[id_lote][id_transaccion] = {
        "id_transaccion": id_transaccion,
        "estado_revision": estado,
        "comentario_revision": comentario,
        "actualizado_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }

    st.session_state["revisiones_demo"] = lotes





def ir_a_carga():
    st.session_state["pagina"] = "Datos y configuración"
    st.session_state["origen_datos"] = "Cargar CSV"


def main():
    st.set_page_config(page_title="RadarFin · Análisis financiero",
                       page_icon=str(ROOT / "assets/radarfin-icon.svg"), layout="wide")
    aplicar_estilos()
    # Mantener el estado de filtros aunque sus widgets no est?n en la p?gina activa.
    for clave in ["filtro_prioridades", "filtro_clientes", "filtro_canales", "filtro_estados", "buscar_operacion", "orden_bandeja"]:
        if clave in st.session_state:
            st.session_state[clave] = st.session_state[clave]
    st.logo(str(ROOT / "assets/radarfin-logo.svg"), size="large",
            icon_image=str(ROOT / "assets/radarfin-icon.svg"))
    with st.sidebar.container(key="navegacion"):
        pagina = st.radio("Espacio de análisis", PAGINAS, key="pagina", label_visibility="collapsed")
    st.sidebar.divider()
    encabezado(pagina)
    if pagina == "Resumen":
        st.button("Cargar un lote", type="primary", icon=":material/upload_file:", on_click=ir_a_carga)
    historial, operaciones, origen = cargar_datos()
    demo = es_demo_publica()
    st.sidebar.divider()
    st.sidebar.markdown("**Revisión temporal**" if demo else "**Persistencia local · SQLite**")
    st.sidebar.caption(
        "Los comentarios pertenecen a esta sesión. Descarga los resultados para conservarlos."
        if demo else "Estados y comentarios guardados en esta computadora."
    )
    with st.spinner("Analizando operaciones…"):
        resultado = analizar_operaciones(historial, operaciones)
    id_lote = calcular_id_lote(historial, operaciones)
    if st.session_state.get("lote_activo") != id_lote:
        limpiar_filtros()
        st.session_state["operacion_seleccionada"] = (id_lote, None)
        st.session_state["lote_activo"] = id_lote
    revisiones = cargar_revisiones_desde_app(id_lote)
    resultado = resultado.merge(revisiones, on="id_transaccion", how="left", validate="one_to_one")
    resultado["estado_revision"] = resultado["estado_revision"].fillna("Pendiente")
    resultado["comentario_revision"] = resultado["comentario_revision"].fillna("")
    contexto(origen, operaciones)
    if st.session_state.pop("revision_guardada", False):
        st.success("Revisión guardada correctamente.")
    if pagina == "Resumen":
        mostrar_resumen(resultado)
    elif pagina == "Bandeja de revisión":
        mostrar_bandeja(resultado, id_lote)
    elif pagina == "Evaluación":
        mostrar_evaluacion(operaciones, resultado, evaluar_resultados)
    else:
        mostrar_datos(historial, operaciones)
    st.html('<p class="rf-note">Entorno con datos ficticios · Una anomalía requiere revisión humana. '
            'No confirma fraude ni bloquea operaciones. La puntuación indica prioridad, no probabilidad de fraude.</p>')


def ejecutar():
    try:
        main()
    except (OSError, UnicodeError, sqlite3.Error, pd.errors.ParserError, pd.errors.EmptyDataError, pd.errors.MergeError):
        LOGGER.exception("No se pudo completar el análisis")
        st.error("No se pudo leer el archivo o el almacenamiento de revisiones. "
                 "Comprueba que el CSV esté en UTF-8, tenga encabezados y que el almacenamiento esté disponible.")
    except ValueError as error:
        LOGGER.exception("Datos no válidos")
        st.error(f"Revisa los archivos de entrada: {error}")
        st.caption("Corrige los campos indicados y vuelve a cargar ambos CSV desde la barra lateral.")


if __name__ == "__main__":
    ejecutar()
