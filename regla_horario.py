from validar_datos import MINIMO_HISTORIAL


UMBRAL_PORCENTAJE_HORARIO = 5
PUNTOS_HORARIO = 25


def aplicar_regla_horario(operaciones, historial):
    referencia = historial[
        ["id_cliente", "fecha_hora"]
    ].copy()

    # La división entera convierte cada hora en una franja.
    referencia["franja_horaria"] = (
        referencia["fecha_hora"].dt.hour // 6
    )

    totales = referencia.groupby("id_cliente").size()

    conteos = (
        referencia.groupby(
            ["id_cliente", "franja_horaria"]
        )
        .size()
        .rename("cantidad_hist_franja")
        .reset_index()
    )

    resultado = operaciones.copy()

    resultado["franja_horaria"] = (
        resultado["fecha_hora"].dt.hour // 6
    )

    resultado = resultado.merge(
        conteos,
        on=["id_cliente", "franja_horaria"],
        how="left",
        validate="many_to_one",
    )

    # Una franja sin operaciones históricas tiene conteo cero.
    resultado["cantidad_hist_franja"] = (
        resultado["cantidad_hist_franja"]
        .fillna(0)
        .astype(int)
    )

    resultado["cantidad_hist_horario"] = (
        resultado["id_cliente"]
        .map(totales)
        .fillna(0)
        .astype(int)
    )

    resultado["horario_evaluable"] = (
        resultado["cantidad_hist_horario"] >= MINIMO_HISTORIAL
    )

    # Dejamos el porcentaje ausente si falta historial suficiente.
    denominador = resultado["cantidad_hist_horario"].where(
        resultado["horario_evaluable"]
    )

    resultado["porcentaje_hist_franja"] = (
        resultado["cantidad_hist_franja"] / denominador * 100
    )

    resultado["alerta_horario"] = (
        resultado["horario_evaluable"]
        & resultado["porcentaje_hist_franja"]
        .lt(UMBRAL_PORCENTAJE_HORARIO)
        .fillna(False)
    )

    resultado["puntos_horario"] = (
        resultado["alerta_horario"].astype(int) * PUNTOS_HORARIO
    )

    explicaciones = []

    for fila in resultado.itertuples(index=False):
        if not fila.horario_evaluable:
            explicacion = (
                "Regla de horario no evaluada: "
                "historial insuficiente."
            )
        else:
            hora_inicio = fila.franja_horaria * 6
            hora_fin = hora_inicio + 6

            detalle = (
                f"Franja de {hora_inicio:02d}:00 "
                f"a antes de {hora_fin:02d}:00: "
                f"{fila.cantidad_hist_franja} de "
                f"{fila.cantidad_hist_horario} operaciones "
                f"historicas ({fila.porcentaje_hist_franja:.2f}%)."
            )

            if fila.alerta_horario:
                explicacion = (
                    f"{detalle} Es inferior al umbral de "
                    f"{UMBRAL_PORCENTAJE_HORARIO}%. "
                    f"Aporta {PUNTOS_HORARIO} puntos."
                )
            else:
                explicacion = (
                    f"{detalle} No activa la regla de horario."
                )

        explicaciones.append(explicacion)

    resultado["explicacion_horario"] = explicaciones

    return resultado