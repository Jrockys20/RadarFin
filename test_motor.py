import pandas as pd
import pytest

from motor_alertas import analizar_operaciones
from regla_rafaga import aplicar_regla_rafaga
from validar_datos import cargar_y_validar_csv


# Estas funciones crean datos pequeños para las pruebas.
# No leen ni modifican los CSV del proyecto.

def crear_historial(cantidad=60, hora=14):
    filas = []

    for indice in range(cantidad):
        fecha = pd.Timestamp("2026-09-01") + pd.Timedelta(
            days=indice % 30,
            hours=hora,
            minutes=indice // 30,
        )

        filas.append({
            "id_transaccion": f"H{indice:03d}",
            "id_cliente": "C001",
            "fecha_hora": fecha,
            "monto": 100.00,
            "canal": "app",
        })

    return pd.DataFrame(filas)


def crear_operaciones(fechas, montos=None, clientes=None):
    filas = []

    for indice, fecha in enumerate(fechas):
        monto = 100.00 if montos is None else montos[indice]
        cliente = "C001" if clientes is None else clientes[indice]

        filas.append({
            "id_transaccion": f"T{indice:03d}",
            "id_cliente": cliente,
            "fecha_hora": pd.Timestamp(fecha),
            "monto": monto,
            "canal": "app",
        })

    return pd.DataFrame(filas)


@pytest.mark.parametrize(
    "monto,esperado",
    [
        (499.99, False),
        (500.00, False),
        (500.01, True),
    ],
)
def test_limite_monto(monto, esperado):
    historial = crear_historial()

    operaciones = crear_operaciones(
        ["2026-10-01 14:00:00"],
        montos=[monto],
    )

    resultado = analizar_operaciones(historial, operaciones)
    fila = resultado.iloc[0]

    assert bool(fila["alerta_monto"]) == esperado
    assert fila["puntos_monto"] == (40 if esperado else 0)


@pytest.mark.parametrize(
    "cantidad,evaluable",
    [
        (19, False),
        (20, True),
    ],
)
def test_minimo_historial(cantidad, evaluable):
    historial = crear_historial(cantidad=cantidad)

    operaciones = crear_operaciones(
        ["2026-10-01 14:00:00"],
        montos=[1000.00],
    )

    resultado = analizar_operaciones(historial, operaciones)
    fila = resultado.iloc[0]

    assert bool(fila["monto_evaluable"]) == evaluable
    assert bool(fila["horario_evaluable"]) == evaluable
    assert fila["puntos_monto"] == (40 if evaluable else 0)


def test_cliente_nuevo_puede_activar_rafaga():
    historial = crear_historial()

    operaciones = crear_operaciones(
        [
            f"2026-10-01 14:0{minuto}:00"
            for minuto in range(5)
        ],
        clientes=["C999"] * 5,
    )

    resultado = analizar_operaciones(historial, operaciones)

    assert not resultado["monto_evaluable"].any()
    assert not resultado["horario_evaluable"].any()
    assert resultado["veces_mediana"].isna().all()

    quinta = resultado.set_index("id_transaccion").loc["T004"]

    assert quinta["puntos_monto"] == 0
    assert quinta["puntos_horario"] == 0
    assert quinta["puntos_rafaga"] == 35
    assert quinta["prioridad"] == "Baja"


def test_ventana_rafaga_y_orden_cronologico():
    inicio = pd.Timestamp("2026-10-01 14:00:00")

    segundos = [0, 60, 120, 180, 600, 601, 1202]

    operaciones = crear_operaciones([
        inicio + pd.Timedelta(seconds=valor)
        for valor in segundos
    ])

    # Entregamos las operaciones al revés para comprobar
    # que la regla las ordena antes de procesarlas.
    operaciones = operaciones.iloc[::-1]

    resultado = aplicar_regla_rafaga(operaciones)

    assert resultado["cantidad_en_ventana"].tolist() == [
        1, 2, 3, 4, 5, 5, 1
    ]

    assert resultado["alerta_rafaga"].tolist() == [
        False, False, False, False, True, True, False
    ]


def test_rafaga_no_mezcla_clientes():
    operaciones = crear_operaciones(
        [
            f"2026-10-01 14:0{minuto}:00"
            for minuto in range(5)
        ],
        clientes=["C001", "C002", "C001", "C002", "C001"],
    )

    resultado = aplicar_regla_rafaga(operaciones)

    assert resultado["cantidad_en_ventana"].tolist() == [
        1, 1, 2, 2, 3
    ]

    assert not resultado["alerta_rafaga"].any()


@pytest.mark.parametrize(
    "hora_historica,esperado",
    [
        (3, False),
        (14, True),
    ],
)
def test_horario_depende_del_cliente(hora_historica, esperado):
    historial = crear_historial(hora=hora_historica)

    operaciones = crear_operaciones(
        ["2026-10-01 03:00:00"]
    )

    resultado = analizar_operaciones(historial, operaciones)
    fila = resultado.iloc[0]

    assert bool(fila["alerta_horario"]) == esperado
    assert fila["puntos_horario"] == (25 if esperado else 0)


@pytest.mark.parametrize(
    "cantidad_madrugada,esperado",
    [
        (2, True),
        (3, False),
    ],
)
def test_limite_porcentaje_horario(cantidad_madrugada, esperado):
    historial = crear_historial()

    # Dos de sesenta equivalen a 3.33%.
    # Tres de sesenta equivalen exactamente a 5%.
    historial.loc[
        historial.index[:cantidad_madrugada],
        "fecha_hora",
    ] = pd.Timestamp("2026-09-01 03:00:00")

    operaciones = crear_operaciones(
        ["2026-10-01 03:00:00"]
    )

    resultado = analizar_operaciones(historial, operaciones)

    assert bool(resultado.iloc[0]["alerta_horario"]) == esperado


@pytest.mark.parametrize(
    "hora,puntaje_esperado",
    [
        (14, 75),
        (3, 100),
    ],
)
def test_combinacion_de_reglas_prioridad_alta(hora, puntaje_esperado):
    historial = crear_historial(hora=14)

    operaciones = crear_operaciones(
        [
            f"2026-10-01 {hora:02d}:0{minuto}:00"
            for minuto in range(5)
        ],
        montos=[100, 100, 100, 100, 1000],
    )

    resultado = analizar_operaciones(historial, operaciones)

    quinta = resultado.set_index("id_transaccion").loc["T004"]

    assert quinta["puntos_monto"] == 40
    assert quinta["puntos_rafaga"] == 35
    assert quinta["puntos_horario"] == (25 if hora == 3 else 0)
    assert quinta["puntaje_total"] == puntaje_esperado
    assert quinta["prioridad"] == "Alta"


def test_etiquetas_no_cambian_predicciones():
    historial = crear_historial()

    operaciones = crear_operaciones(
        ["2026-10-01 14:00:00"],
        montos=[1000],
    )

    operaciones["es_anomalia"] = 0
    operaciones["tipo_anomalia"] = "normal"

    resultado_original = analizar_operaciones(
        historial, operaciones
    )

    operaciones["es_anomalia"] = 1
    operaciones["tipo_anomalia"] = "monto_inusual"

    resultado_modificado = analizar_operaciones(
        historial, operaciones
    )

    pd.testing.assert_frame_equal(
        resultado_original,
        resultado_modificado,
    )


@pytest.mark.parametrize(
    "columna,valor,mensaje",
    [
        ("monto", "0", "montos invalidos"),
        ("fecha_hora", "fecha_invalida", "fechas invalidas"),
        ("canal", "desconocido", "canales no permitidos"),
    ],
)
def test_csv_incorrecto_se_rechaza(
    tmp_path, columna, valor, mensaje
):
    operaciones = crear_operaciones(
        ["2026-10-01 14:00:00"]
    ).astype("string")

    operaciones.loc[0, columna] = valor

    ruta = tmp_path / "entrada_incorrecta.csv"

    operaciones.to_csv(
        ruta,
        index=False,
        encoding="utf-8-sig",
    )

    with pytest.raises(ValueError, match=mensaje):
        cargar_y_validar_csv(ruta)