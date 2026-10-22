"""Regresiones del flujo del analista, sin modificar reglas ni datos de ejemplo."""
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app
import revisiones
from motor_alertas import analizar_operaciones
from validar_datos import CARPETA_DATOS, cargar_y_validar_csv

RUTA_APP = Path(__file__).with_name("app.py")


@pytest.fixture
def tablas():
    historial = cargar_y_validar_csv(CARPETA_DATOS / "historial.csv")
    operaciones = cargar_y_validar_csv(CARPETA_DATOS / "desarrollo.csv")
    return historial, operaciones, analizar_operaciones(historial, operaciones)


@pytest.fixture
def interfaz():
    at = AppTest.from_file(str(RUTA_APP), default_timeout=30)
    at.secrets["modo_demo_publica"] = True
    at.run(timeout=30)
    assert not at.exception
    assert not at.error
    return at


def test_resumen_filtros_y_limpieza(interfaz):
    at = interfaz
    assert [m.value for m in at.metric[:4]] == ["424", "12", "0", "2.83%"]
    at.radio(key="pagina").set_value("Bandeja de revisión").run()
    assert len(at.dataframe[0].value) == 12
    at.multiselect(key="filtro_prioridades").set_value(["Alta"]).run()
    assert any("No hay operaciones con estos filtros" in i.value for i in at.info)
    next(b for b in at.button if b.label == "Limpiar filtros").click().run()
    assert len(at.dataframe[0].value) == 12
    assert at.multiselect(key="filtro_prioridades").value == ["Alta", "Media", "Baja"]


@pytest.mark.parametrize("demo", [True, False])
def test_guardado_seleccion_y_aislamiento_por_lote(tablas, tmp_path, monkeypatch, demo):
    monkeypatch.setattr(revisiones, "RUTA_BD", tmp_path / "prueba.db")
    historial, operaciones, resultado = tablas
    lote = app.calcular_id_lote(historial, operaciones)
    identificador = resultado.iloc[0]["id_transaccion"]
    at = AppTest.from_file(str(RUTA_APP), default_timeout=30)
    at.secrets["modo_demo_publica"] = demo
    at.run(timeout=30)
    at.radio(key="pagina").set_value("Bandeja de revisión").run()
    at.session_state["operacion_seleccionada"] = (lote, identificador)
    at.run()
    tabla_id = at.dataframe[0].proto.id
    assert any(identificador in titulo.value for titulo in at.subheader)
    at.selectbox(key=f"estado_{lote}_{identificador}").set_value("Revisada")
    at.text_area[0].set_value("  Comprobación del analista  ")
    next(b for b in at.button if b.label == "Guardar revisión").click().run()
    assert not at.exception
    assert any("guardada correctamente" in s.value for s in at.success)
    assert at.session_state["operacion_seleccionada"] == (lote, identificador)
    assert at.dataframe[0].proto.id == tabla_id
    fila = at.dataframe[0].value.query("id_transaccion == @identificador").iloc[0]
    assert fila["estado_revision"] == "Revisada"
    if demo:
        assert not revisiones.RUTA_BD.exists()
        registro = at.session_state["revisiones_demo"][lote][identificador]
        assert registro["comentario_revision"] == "Comprobación del analista"
        otra = AppTest.from_file(str(RUTA_APP), default_timeout=30)
        otra.secrets["modo_demo_publica"] = True
        otra.run()
        otra.radio(key="pagina").set_value("Bandeja de revisión").run()
        assert otra.dataframe[0].value["estado_revision"].eq("Pendiente").all()
    else:
        assert revisiones.leer_revisiones(lote).iloc[0]["comentario_revision"] == "Comprobación del analista"
        otra = AppTest.from_file(str(RUTA_APP), default_timeout=30)
        otra.secrets["modo_demo_publica"] = False
        otra.run()
        otra.radio(key="pagina").set_value("Bandeja de revisión").run()
        assert "Revisada" in otra.dataframe[0].value["estado_revision"].tolist()
    at.multiselect(key="filtro_estados").set_value(["Pendiente"]).run()
    assert at.session_state["operacion_seleccionada"] == (lote, None)
    next(w for w in at.selectbox if w.label == "Lote de ejemplo").set_value("prueba").run()
    assert at.session_state["lote_activo"] != lote
    assert at.session_state["operacion_seleccionada"][1] is None
    assert at.multiselect(key="filtro_estados").value == []


def test_seleccion_usa_posicion_original_y_lote(monkeypatch):
    estado = {"tabla": {"selection": {"rows": [1]}}}
    monkeypatch.setattr(app.st, "session_state", estado)
    app.registrar_seleccion("tabla", ("TX_Z", "TX_A"), "lote_A")
    assert estado["operacion_seleccionada"] == ("lote_A", "TX_A")
    visibles = pd.DataFrame({"id_transaccion": ["TX_A"]})
    assert app.resolver_seleccion("lote_A", visibles) == "TX_A"
    assert app.resolver_seleccion("lote_B", visibles) is None
    estado["tabla"]["selection"]["rows"] = []
    app.registrar_seleccion("tabla", ("TX_Z", "TX_A"), "lote_A")
    assert estado["operacion_seleccionada"] == ("lote_A", None)


def test_lote_sin_etiquetas_y_metricas_no_definidas():
    def vista_sin_etiquetas():
        import pandas as pd
        from interfaz import mostrar_evaluacion
        from evaluar_motor import evaluar_resultados
        mostrar_evaluacion(pd.DataFrame(), pd.DataFrame(), evaluar_resultados)
    at = AppTest.from_function(vista_sin_etiquetas, default_timeout=30).run()
    assert not at.exception
    assert any("no incluye etiquetas" in i.value for i in at.info)
    def vista_sin_positivos():
        import pandas as pd
        from interfaz import mostrar_evaluacion
        from evaluar_motor import evaluar_resultados
        operaciones = pd.DataFrame({"id_transaccion": ["TX1"], "es_anomalia": [0]})
        resultado = pd.DataFrame({"id_transaccion": ["TX1"], "tiene_alerta": [False]})
        mostrar_evaluacion(operaciones, resultado, evaluar_resultados)
    at = AppTest.from_function(vista_sin_positivos, default_timeout=30).run()
    assert not at.exception
    assert [m.value for m in at.metric] == ["No definida"] * 3


def test_carga_csv_en_memoria_y_error():
    archivo = BytesIO(b"id_transaccion,id_cliente,fecha_hora,monto,canal\nTX1,C1,2026-01-01 12:00:00,12.50,web\n")
    archivo.name = "lote.csv"
    tabla = cargar_y_validar_csv(archivo)
    assert tabla.iloc[0]["monto"] == 12.5
    archivo = BytesIO(b"id_transaccion,monto\nTX1,12\n")
    archivo.name = "invalido.csv"
    with pytest.raises(ValueError, match="faltan columnas"):
        cargar_y_validar_csv(archivo)

def test_sin_alertas_e_historial_insuficiente():
    def vista():
        from interfaz import mostrar_resumen
        from motor_alertas import analizar_operaciones
        from validar_datos import CARPETA_DATOS, cargar_y_validar_csv
        historial = cargar_y_validar_csv(CARPETA_DATOS / "historial.csv").head(1)
        operaciones = cargar_y_validar_csv(CARPETA_DATOS / "desarrollo.csv").head(1)
        mostrar_resumen(analizar_operaciones(historial, operaciones))
    at = AppTest.from_function(vista, default_timeout=30).run()
    assert not at.exception
    assert [m.value for m in at.metric] == ["1", "0", "0", "0.00%"]
    assert any("sin historial suficiente" in w.value for w in at.warning)
    assert any("no presenta alertas" in i.value for i in at.info)

def test_busqueda_orden_y_navegacion(interfaz):
    at = interfaz
    at.radio(key="pagina").set_value("Bandeja de revisión").run()
    at.text_input(key="buscar_operacion").set_value("D000402").run()
    assert at.dataframe[0].value["id_transaccion"].tolist() == ["D000402"]
    at.radio(key="pagina").set_value("Evaluación").run()
    assert [m.value for m in at.metric] == ["100.00%", "50.00%", "66.67%"]
    at.radio(key="pagina").set_value("Bandeja de revisión").run()
    assert at.text_input(key="buscar_operacion").value == "D000402"
    next(b for b in at.button if b.label == "Limpiar filtros").click().run()
    at.selectbox(key="orden_bandeja").set_value("Mayor monto").run()
    assert at.dataframe[0].value["monto"].is_monotonic_decreasing
    at.text_input(key="buscar_operacion").set_value("[.*").run()
    assert any("No hay operaciones con estos filtros" in i.value for i in at.info)
    at.radio(key="pagina").set_value("Resumen").run()
    assert [m.value for m in at.metric] == ["424", "12", "0", "2.83%"]


def test_accion_cargar_lote(interfaz):
    at = interfaz
    next(b for b in at.button if b.label == "Cargar un lote").click().run()
    assert at.radio(key="pagina").value == "Datos y configuración"
    assert at.radio(key="origen_datos").value == "Cargar CSV"
    assert any("Carga el historial" in i.value for i in at.info)


def test_tokens_tema_y_logo():
    import tomllib
    from xml.etree import ElementTree
    from diseno import ROOT, TOKENS
    tema = tomllib.loads((ROOT / ".streamlit/config.toml").read_text(encoding="utf-8"))["theme"]
    assert tema["base"] == "dark"
    assert tema["primaryColor"] == TOKENS["action"]
    assert tema["backgroundColor"] == TOKENS["background"]
    for nombre in ["radarfin-icon.svg", "radarfin-logo.svg"]:
        assert ElementTree.parse(ROOT / "assets" / nombre).getroot().tag.endswith("svg")
