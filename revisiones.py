import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pandas as pd

from validar_datos import CARPETA_DATOS


RUTA_BD = CARPETA_DATOS / "radarfin.db"

ESTADOS_REVISION = ["Pendiente", "En revisión", "Revisada"]


def inicializar_bd():
    RUTA_BD.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(RUTA_BD)) as conexion:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS revisiones (
                id_lote TEXT NOT NULL,
                id_transaccion TEXT NOT NULL,
                estado_revision TEXT NOT NULL
                    CHECK (
                        estado_revision IN (
                            'Pendiente', 'En revisión', 'Revisada'
                        )
                    ),
                comentario_revision TEXT NOT NULL,
                actualizado_utc TEXT NOT NULL,
                PRIMARY KEY (id_lote, id_transaccion)
            )
        """)

        conexion.commit()


def leer_revisiones(id_lote):
    with closing(sqlite3.connect(RUTA_BD)) as conexion:
        return pd.read_sql_query(
            """
            SELECT
                id_transaccion,
                estado_revision,
                comentario_revision,
                actualizado_utc
            FROM revisiones
            WHERE id_lote = ?
            """,
            conexion,
            params=(id_lote,),
        )


def guardar_revision(
    id_lote,
    id_transaccion,
    estado,
    comentario,
):
    if estado not in ESTADOS_REVISION:
        raise ValueError("Estado de revisión no permitido.")

    comentario = comentario.strip()

    if len(comentario) > 2000:
        raise ValueError(
            "El comentario no puede superar los 2000 caracteres."
        )

    actualizado = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )

    with closing(sqlite3.connect(RUTA_BD)) as conexion:
        conexion.execute(
            """
            INSERT INTO revisiones (
                id_lote,
                id_transaccion,
                estado_revision,
                comentario_revision,
                actualizado_utc
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (id_lote, id_transaccion)
            DO UPDATE SET
                estado_revision = excluded.estado_revision,
                comentario_revision = excluded.comentario_revision,
                actualizado_utc = excluded.actualizado_utc
            """,
            (
                id_lote,
                id_transaccion,
                estado,
                comentario,
                actualizado,
            ),
        )

        conexion.commit()