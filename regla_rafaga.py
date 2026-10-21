from collections import deque

import pandas as pd


VENTANA_MINUTOS = 10
MINIMO_OPERACIONES = 5
PUNTOS_RAFAGA = 35


def aplicar_regla_rafaga(operaciones):
    # Conservamos las columnas existentes, incluidas las de monto.
    resultado = operaciones.copy()

    resultado = resultado.sort_values(
        ["id_cliente", "fecha_hora", "id_transaccion"]
    ).reset_index(drop=True)

    resultado["cantidad_en_ventana"] = 0

    ventana = pd.Timedelta(minutes=VENTANA_MINUTOS)

    # Cada cliente tiene su propia ventana.
    for _, grupo in resultado.groupby("id_cliente", sort=False):
        fechas_recientes = deque()

        for indice, fila in grupo.iterrows():
            fecha_actual = fila["fecha_hora"]
            limite_inferior = fecha_actual - ventana

            # Retiramos las operaciones que ya quedaron fuera.
            while (
                fechas_recientes
                and fechas_recientes[0] < limite_inferior
            ):
                fechas_recientes.popleft()

            # Incorporamos la operación actual.
            fechas_recientes.append(fecha_actual)

            resultado.at[indice, "cantidad_en_ventana"] = len(
                fechas_recientes
            )

    resultado["alerta_rafaga"] = (
        resultado["cantidad_en_ventana"] >= MINIMO_OPERACIONES
    )

    resultado["puntos_rafaga"] = (
        resultado["alerta_rafaga"].astype(int) * PUNTOS_RAFAGA
    )

    explicaciones = []

    for fila in resultado.itertuples(index=False):
        detalle = (
            f"{fila.cantidad_en_ventana} operaciones del cliente "
            f"en los ultimos {VENTANA_MINUTOS} minutos, "
            "incluyendo la actual."
        )

        if fila.alerta_rafaga:
            explicacion = (
                f"{detalle} Alcanza el minimo de "
                f"{MINIMO_OPERACIONES} operaciones. "
                f"Aporta {PUNTOS_RAFAGA} puntos."
            )
        else:
            explicacion = (
                f"{detalle} No alcanza el minimo de "
                f"{MINIMO_OPERACIONES} operaciones."
            )

        explicaciones.append(explicacion)

    resultado["explicacion_rafaga"] = explicaciones

    return resultado.sort_values(
        ["fecha_hora", "id_transaccion"]
    ).reset_index(drop=True)