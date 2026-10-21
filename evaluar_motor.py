import sys
import argparse
import pandas as pd

from validar_datos import CARPETA_DATOS, cargar_y_validar_csv
from motor_alertas import analizar_operaciones


def dividir_si_es_posible(numerador, denominador):
    if denominador == 0:
        return None

    return numerador / denominador


def evaluar_resultados(operaciones, resultados):
    if "es_anomalia" not in operaciones.columns:
        raise ValueError(
            "No se pueden calcular estas metricas sin "
            "la columna 'es_anomalia'."
        )

    if operaciones.empty:
        raise ValueError("No hay operaciones para evaluar.")

    if not operaciones["es_anomalia"].isin([0, 1]).all():
        raise ValueError("Las etiquetas deben ser 0 o 1.")

    if not resultados["tiene_alerta"].isin([True, False]).all():
        raise ValueError(
            "Los resultados deben indicar True o False "
            "en 'tiene_alerta'."
        )

    columnas_etiquetas = ["id_transaccion", "es_anomalia"]

    for columna in ["id_cliente", "tipo_anomalia"]:
        if columna in operaciones.columns:
            columnas_etiquetas.append(columna)

    # Relacionamos etiquetas y predicciones por identificador.
    # No suponemos que ambas tablas tengan el mismo orden.
    comparacion = operaciones[columnas_etiquetas].merge(
        resultados[["id_transaccion", "tiene_alerta"]],
        on="id_transaccion",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    if not comparacion["_merge"].eq("both").all():
        raise ValueError(
            "Las operaciones y los resultados no contienen "
            "exactamente los mismos identificadores."
        )

    comparacion = comparacion.drop(columns="_merge")

    es_anomala = comparacion["es_anomalia"].eq(1)
    genera_alerta = comparacion["tiene_alerta"].eq(True)

    vp = int((es_anomala & genera_alerta).sum())
    fp = int((~es_anomala & genera_alerta).sum())
    fn = int((es_anomala & ~genera_alerta).sum())
    vn = int((~es_anomala & ~genera_alerta).sum())

    metricas = {
        "verdaderos_positivos": vp,
        "falsos_positivos": fp,
        "falsos_negativos": fn,
        "verdaderos_negativos": vn,
        "precision": dividir_si_es_posible(vp, vp + fp),
        "exhaustividad": dividir_si_es_posible(vp, vp + fn),
        "f1": dividir_si_es_posible(
            2 * vp,
            2 * vp + fp + fn,
        ),
        "proporcion_alertada": dividir_si_es_posible(
            vp + fp,
            len(comparacion),
        ),
    }

    comparacion["es_falso_negativo"] = (
        es_anomala & ~genera_alerta
    )

    return metricas, comparacion


def mostrar_porcentaje(nombre, valor):
    if valor is None:
        print(f"{nombre}: no definida")
    else:
        print(f"{nombre}: {valor:.2%}")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluar las reglas de RadarFin."
    )

    parser.add_argument(
        "--conjunto",
        choices=["desarrollo", "prueba"],
        default="desarrollo",
        help="Conjunto de datos que se evaluará.",
    )

    argumentos = parser.parse_args()

    historial = cargar_y_validar_csv(
        CARPETA_DATOS / "historial.csv"
    )

    operaciones = cargar_y_validar_csv(
        CARPETA_DATOS / f"{argumentos.conjunto}.csv"
    )

    resultados = analizar_operaciones(historial, operaciones)

    metricas, comparacion = evaluar_resultados(
        operaciones,
        resultados,
    )

    print(
        f"Evaluacion del conjunto de {argumentos.conjunto}"
    )
    print(f"Operaciones evaluadas: {len(comparacion)}")
    print(
        "Anomalias etiquetadas: "
        f"{int(comparacion['es_anomalia'].sum())}"
    )

    print("\nConteos:")

    for nombre, clave in [
        ("Verdaderos positivos", "verdaderos_positivos"),
        ("Falsos positivos", "falsos_positivos"),
        ("Falsos negativos", "falsos_negativos"),
        ("Verdaderos negativos", "verdaderos_negativos"),
    ]:
        print(f"{nombre}: {metricas[clave]}")

    print("\nMetricas:")

    mostrar_porcentaje("Precision", metricas["precision"])
    mostrar_porcentaje(
        "Exhaustividad",
        metricas["exhaustividad"],
    )
    mostrar_porcentaje("F1", metricas["f1"])
    mostrar_porcentaje(
        "Operaciones enviadas a revision",
        metricas["proporcion_alertada"],
    )

    no_detectadas = comparacion.loc[
        comparacion["es_falso_negativo"]
    ].copy()

    if not no_detectadas.empty:
        print("\nAnomalias no detectadas:")

        columnas = ["id_transaccion"]

        for columna in ["id_cliente", "tipo_anomalia"]:
            if columna in no_detectadas.columns:
                columnas.append(columna)

        print(
            no_detectadas[columnas]
            .sort_values("id_transaccion")
            .to_string(index=False)
        )


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