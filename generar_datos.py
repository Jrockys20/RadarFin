from pathlib import Path
from datetime import datetime, timedelta
import random

import pandas as pd


# Permite obtener los mismos datos al ejecutar nuevamente el programa.
SEMILLA = 20

# Los CSV se guardarán en una carpeta junto a este archivo.
CARPETA_DATOS = Path(__file__).resolve().parent / "datos"

CANALES = ["app", "web", "cajero", "agente"]


def crear_clientes():
    clientes = []

    for numero in range(1, 21):
        cliente = {
            "id_cliente": f"C{numero:03d}",
            "monto_habitual": [50, 150, 450][(numero - 1) % 3],
            "es_nocturno": numero >= 17,
        }

        clientes.append(cliente)

    return clientes


def elegir_fecha(inicio, cantidad_dias, cliente, generador):
    dia = generador.randrange(cantidad_dias)

    if cliente["es_nocturno"]:
        horas_habituales = [0, 1, 2, 3, 4, 22, 23]
    else:
        horas_habituales = list(range(8, 21))

    return inicio + timedelta(
        days=dia,
        hours=generador.choice(horas_habituales),
        minutes=generador.randrange(60),
        seconds=generador.randrange(60),
    )


def elegir_monto(cliente, generador):
    # Introduce variación alrededor del monto habitual.
    factor = generador.lognormvariate(0, 0.35)
    monto = cliente["monto_habitual"] * factor

    return round(max(monto, 1.00), 2)


def generar_conjunto(
    clientes,
    inicio,
    cantidad_dias,
    operaciones_por_cliente,
    prefijo,
    semilla,
    incluir_anomalias,
):
    generador = random.Random(semilla)
    operaciones = []

    def agregar(cliente, fecha, monto, etiqueta=0, tipo="normal"):
        operaciones.append({
            "id_transaccion": f"{prefijo}{len(operaciones) + 1:06d}",
            "id_cliente": cliente["id_cliente"],
            "fecha_hora": fecha,
            "monto": monto,
            "canal": generador.choice(CANALES),
            "es_anomalia": etiqueta,
            "tipo_anomalia": tipo,
        })

    # Primero generamos operaciones habituales.
    for cliente in clientes:
        for _ in range(operaciones_por_cliente):
            agregar(
                cliente,
                elegir_fecha(
                    inicio, cantidad_dias, cliente, generador
                ),
                elegir_monto(cliente, generador),
            )

    if incluir_anomalias:
        # Tres clientes realizan una operación de monto elevado.
        for cliente in clientes[0:3]:
            fecha = elegir_fecha(
                inicio, cantidad_dias, cliente, generador
            )

            monto = round(
                cliente["monto_habitual"]
                * generador.uniform(7, 12),
                2,
            )

            agregar(cliente, fecha, monto, 1, "monto_inusual")

        # Tres clientes realizan seis operaciones en pocos minutos.
        for cliente in clientes[3:6]:
            inicio_rafaga = inicio + timedelta(
                days=generador.randrange(cantidad_dias),
                hours=14,
            )

            for posicion in range(6):
                fecha = inicio_rafaga + timedelta(
                    seconds=posicion * 45
                )

                agregar(
                    cliente,
                    fecha,
                    elegir_monto(cliente, generador),
                    1,
                    "rafaga",
                )

        # Tres clientes diurnos realizan una operación de madrugada.
        for cliente in clientes[6:9]:
            fecha = inicio + timedelta(
                days=generador.randrange(cantidad_dias),
                hours=3,
                minutes=generador.randrange(60),
            )

            agregar(
                cliente,
                fecha,
                elegir_monto(cliente, generador),
                1,
                "horario_inusual",
            )

    tabla = pd.DataFrame(operaciones)

    # Dejamos las operaciones ordenadas cronológicamente.
    tabla = tabla.sort_values(
        ["fecha_hora", "id_transaccion"]
    ).reset_index(drop=True)

    return tabla


def guardar_csv(tabla, nombre_archivo):
    ruta = CARPETA_DATOS / nombre_archivo

    tabla.to_csv(
        ruta,
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%d %H:%M:%S",
    )

    print(f"\nArchivo: {nombre_archivo}")
    print(f"Operaciones: {len(tabla)}")

    if "es_anomalia" in tabla.columns:
        print(f"Anomalias simuladas: {int(tabla['es_anomalia'].sum())}")

    print(f"Guardado en: {ruta}")


def main():
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

    clientes = crear_clientes()

    historial = generar_conjunto(
        clientes=clientes,
        inicio=datetime(2026, 9, 1),
        cantidad_dias=30,
        operaciones_por_cliente=60,
        prefijo="H",
        semilla=SEMILLA,
        incluir_anomalias=False,
    )

    # El historial es una referencia, sin etiquetas de evaluación.
    historial = historial.drop(
        columns=["es_anomalia", "tipo_anomalia"]
    )

    desarrollo = generar_conjunto(
        clientes=clientes,
        inicio=datetime(2026, 10, 1),
        cantidad_dias=7,
        operaciones_por_cliente=20,
        prefijo="D",
        semilla=SEMILLA + 1,
        incluir_anomalias=True,
    )

    prueba = generar_conjunto(
        clientes=clientes,
        inicio=datetime(2026, 10, 8),
        cantidad_dias=7,
        operaciones_por_cliente=20,
        prefijo="P",
        semilla=SEMILLA + 2,
        incluir_anomalias=True,
    )

    guardar_csv(historial, "historial.csv")
    guardar_csv(desarrollo, "desarrollo.csv")
    guardar_csv(prueba, "prueba.csv")

    print("\nResumen del conjunto de desarrollo:")
    print(desarrollo["tipo_anomalia"].value_counts().to_string())

    print("\nGeneracion terminada correctamente.")


if __name__ == "__main__":
    main()