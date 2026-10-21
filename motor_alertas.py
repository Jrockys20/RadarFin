import sys

import pandas as pd

from validar_datos import (
    CARPETA_DATOS,
    COLUMNAS_OBLIGATORIAS,
    cargar_y_validar_csv,
    validar_separacion,
    calcular_perfiles,
)
from regla_rafaga import aplicar_regla_rafaga
from regla_horario import aplicar_regla_horario

UMBRAL_MONTO = 5
PUNTOS_MONTO = 40


def aplicar_regla_monto(operaciones, perfiles):
    # Seleccionamos solo los datos de las operaciones.
    # Las etiquetas no intervienen en la detección.
    resultado = operaciones[COLUMNAS_OBLIGATORIAS].copy()

    # Asociamos cada operación con el perfil de su cliente.
    resultado = resultado.merge(
        perfiles,
        on="id_cliente",
        how="left",
        validate="many_to_one",
    )

    # Un cliente nuevo no tendrá perfil.
    # También exigimos una mediana positiva y suficiente historial.
    resultado["monto_evaluable"] = (
        resultado["historial_suficiente"].fillna(False)
        & resultado["mediana_monto"].gt(0).fillna(False)
    )

    # Si no es evaluable, dejamos la referencia como valor ausente.
    referencia = resultado["mediana_monto"].where(
        resultado["monto_evaluable"]
    )

    resultado["veces_mediana"] = resultado["monto"] / referencia

    resultado["alerta_monto"] = (
        resultado["monto_evaluable"]
        & resultado["veces_mediana"].gt(UMBRAL_MONTO).fillna(False)
    )

    resultado["puntos_monto"] = (
        resultado["alerta_monto"].astype(int) * PUNTOS_MONTO
    )

    explicaciones = []

    for fila in resultado.itertuples(index=False):
        if not fila.monto_evaluable:
            explicacion = (
                "Regla de monto no evaluada: "
                "historial insuficiente o referencia no disponible."
            )

        elif fila.alerta_monto:
            explicacion = (
                f"Monto de S/ {fila.monto:.2f} frente a una mediana "
                f"historica de S/ {fila.mediana_monto:.2f}: "
                f"{fila.veces_mediana:.2f} veces la mediana. "
                f"Supera el umbral de {UMBRAL_MONTO} veces. "
                f"Aporta {PUNTOS_MONTO} puntos."
            )

        else:
            explicacion = (
                f"El monto equivale a {fila.veces_mediana:.2f} "
                f"veces la mediana historica. "
                f"No supera el umbral de {UMBRAL_MONTO} veces."
            )

        explicaciones.append(explicacion)

    resultado["explicacion_monto"] = explicaciones

    return resultado

def asignar_prioridad(puntaje):
    if puntaje >= 70:
        return "Alta"

    if puntaje >= 40:
        return "Media"

    if puntaje >= 25:
        return "Baja"

    return "Sin alerta"


def analizar_operaciones(historial, operaciones):
    validar_separacion(historial, operaciones)

    perfiles = calcular_perfiles(historial)

    resultado = aplicar_regla_monto(operaciones, perfiles)
    resultado = aplicar_regla_rafaga(resultado)
    resultado = aplicar_regla_horario(resultado, historial)

    resultado["puntaje_total"] = (
        resultado["puntos_monto"]
        + resultado["puntos_rafaga"]
        + resultado["puntos_horario"]
    )

    resultado["prioridad"] = resultado["puntaje_total"].map(
        asignar_prioridad
    )

    resultado["tiene_alerta"] = resultado["puntaje_total"] >= 25

    explicaciones = []

    for fila in resultado.itertuples(index=False):
        motivos = []

        if fila.alerta_monto:
            motivos.append(fila.explicacion_monto)

        if fila.alerta_rafaga:
            motivos.append(fila.explicacion_rafaga)

        if fila.alerta_horario:
            motivos.append(fila.explicacion_horario)

        if motivos:
            explicaciones.append(" | ".join(motivos))
        else:
            explicaciones.append(
                "Ninguna de las reglas evaluadas activo una alerta."
            )

    resultado["explicacion"] = explicaciones

    return resultado.sort_values(
        ["puntaje_total", "fecha_hora", "id_transaccion"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def main():
    historial = cargar_y_validar_csv(
        CARPETA_DATOS / "historial.csv"
    )

    desarrollo = cargar_y_validar_csv(
        CARPETA_DATOS / "desarrollo.csv"
    )

    resultado = analizar_operaciones(historial, desarrollo)

    alertas = resultado.loc[
        resultado["tiene_alerta"]
    ].copy()

    print("Motor de tres reglas ejecutado correctamente.")
    print(f"Operaciones analizadas: {len(resultado)}")
    print(f"Alertas por monto: {int(resultado['alerta_monto'].sum())}")
    print(f"Alertas por rafaga: {int(resultado['alerta_rafaga'].sum())}")
    print(f"Alertas por horario: {int(resultado['alerta_horario'].sum())}")
    print(f"Operaciones con alguna alerta: {len(alertas)}")

    print("\nDistribucion por prioridad:")

    for prioridad in ["Alta", "Media", "Baja", "Sin alerta"]:
        cantidad = int(
            resultado["prioridad"].eq(prioridad).sum()
        )
        print(f"{prioridad}: {cantidad}")

    if not alertas.empty:
        columnas_resumen = [
            "id_transaccion",
            "id_cliente",
            "monto",
            "puntos_monto",
            "puntos_rafaga",
            "puntos_horario",
            "puntaje_total",
            "prioridad",
        ]

        print("\nOperaciones con alertas:")

        print(
            alertas[columnas_resumen]
            .round({"monto": 2})
            .to_string(index=False)
        )

        print("\nExplicaciones:")

        for fila in alertas.itertuples(index=False):
            print(
                f"\n{fila.id_transaccion} | {fila.id_cliente} "
                f"| {fila.prioridad} | {fila.puntaje_total} puntos"
            )
            print(fila.explicacion)

    ruta_salida = CARPETA_DATOS / "resultados_desarrollo.csv"

    resultado.to_csv(
        ruta_salida,
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%d %H:%M:%S",
    )

    print(f"\nResultados guardados en: {ruta_salida}")


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        OSError,
        UnicodeError,
        pd.errors.ParserError,
        pd.errors.MergeError,
    ) as error:
        print(f"\nERROR: {error}")
        sys.exit(1)