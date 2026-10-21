from pathlib import Path
import sys

import pandas as pd


CARPETA_DATOS = Path(__file__).resolve().parent / "datos"

COLUMNAS_OBLIGATORIAS = [
    "id_transaccion",
    "id_cliente",
    "fecha_hora",
    "monto",
    "canal",
]

CANALES_PERMITIDOS = ["app", "web", "cajero", "agente"]

MINIMO_HISTORIAL = 20


def cargar_y_validar_csv(ruta):
    # Primero leemos los campos como texto.
    # Luego convertimos montos y fechas de forma controlada.
    tabla = pd.read_csv(
        ruta,
        dtype="string",
        encoding="utf-8-sig",
    )

    faltantes = [
        columna
        for columna in COLUMNAS_OBLIGATORIAS
        if columna not in tabla.columns
    ]

    if faltantes:
        raise ValueError(
            f"{ruta.name}: faltan columnas: {', '.join(faltantes)}"
        )

    if tabla.empty:
        raise ValueError(f"{ruta.name}: no contiene operaciones.")

    # Quitamos espacios al inicio y al final de cada campo.
    for columna in COLUMNAS_OBLIGATORIAS:
        tabla[columna] = tabla[columna].str.strip()

        vacios = (
            tabla[columna].isna()
            | tabla[columna].eq("").fillna(False)
        )

        if vacios.any():
            raise ValueError(
                f"{ruta.name}: hay {int(vacios.sum())} valores "
                f"vacios en '{columna}'."
            )

    duplicados = tabla["id_transaccion"].duplicated(keep=False)

    if duplicados.any():
        raise ValueError(
            f"{ruta.name}: hay {int(duplicados.sum())} filas "
            "con identificadores de transaccion repetidos."
        )

    tabla["fecha_hora"] = pd.to_datetime(
        tabla["fecha_hora"],
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )

    fechas_invalidas = tabla["fecha_hora"].isna()

    if fechas_invalidas.any():
        raise ValueError(
            f"{ruta.name}: hay {int(fechas_invalidas.sum())} "
            "fechas invalidas."
        )

    tabla["monto"] = pd.to_numeric(
        tabla["monto"],
        errors="coerce",
    )

    montos_invalidos = (
        tabla["monto"].isna()
        | tabla["monto"].le(0).fillna(False)
        | tabla["monto"].isin([float("inf"), float("-inf")])
    )

    if montos_invalidos.any():
        raise ValueError(
            f"{ruta.name}: hay {int(montos_invalidos.sum())} "
            "montos invalidos. Deben ser numeros positivos y finitos."
        )

    canales_invalidos = ~tabla["canal"].isin(CANALES_PERMITIDOS)

    if canales_invalidos.any():
        raise ValueError(
            f"{ruta.name}: hay {int(canales_invalidos.sum())} "
            "operaciones con canales no permitidos."
        )

    # Las etiquetas son opcionales y solo se usarán para evaluar.
    if "es_anomalia" in tabla.columns:
        etiquetas = pd.to_numeric(
            tabla["es_anomalia"],
            errors="coerce",
        )

        if not etiquetas.isin([0, 1]).all():
            raise ValueError(
                f"{ruta.name}: 'es_anomalia' solo admite 0 o 1."
            )

        tabla["es_anomalia"] = etiquetas.astype(int)

    return tabla.sort_values(
        ["fecha_hora", "id_transaccion"]
    ).reset_index(drop=True)


def validar_separacion(historial, operaciones):
    # Para este proyecto usamos un historial fijo,
    # completamente anterior al lote que analizamos.
    if historial["fecha_hora"].max() >= operaciones["fecha_hora"].min():
        raise ValueError(
            "El historial debe ser completamente anterior "
            "a las operaciones que se analizaran."
        )

    ids_compartidos = historial["id_transaccion"].isin(
        operaciones["id_transaccion"]
    )

    if ids_compartidos.any():
        raise ValueError(
            "Hay transacciones que aparecen tanto en el historial "
            "como en el lote que se analizara."
        )


def calcular_perfiles(historial):
    perfiles = historial.groupby(
        "id_cliente",
        as_index=False,
    ).agg(
        cantidad_historica=("monto", "size"),
        mediana_monto=("monto", "median"),
    )

    perfiles["historial_suficiente"] = (
        perfiles["cantidad_historica"] >= MINIMO_HISTORIAL
    )

    return perfiles


def main():
    historial = cargar_y_validar_csv(
        CARPETA_DATOS / "historial.csv"
    )

    desarrollo = cargar_y_validar_csv(
        CARPETA_DATOS / "desarrollo.csv"
    )

    validar_separacion(historial, desarrollo)

    perfiles = calcular_perfiles(historial)

    clientes_sin_historial = desarrollo.loc[
        ~desarrollo["id_cliente"].isin(perfiles["id_cliente"]),
        "id_cliente",
    ].unique()

    print("Validacion terminada correctamente.")
    print(f"Operaciones historicas: {len(historial)}")
    print(f"Operaciones de desarrollo: {len(desarrollo)}")
    print(f"Clientes con historial: {len(perfiles)}")
    print(f"Clientes sin historial: {len(clientes_sin_historial)}")

    print("\nPerfiles calculados exclusivamente con el historial:")

    # Redondeamos solo para mostrar el resultado.
    print(
        perfiles.round({"mediana_monto": 2}).to_string(index=False)
    )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        OSError,
        UnicodeError,
        pd.errors.ParserError,
    ) as error:
        print(f"\nERROR: {error}")
        sys.exit(1)