import pytest

import revisiones


@pytest.fixture
def base_temporal(tmp_path, monkeypatch):
    # Cada prueba utiliza una base independiente.
    monkeypatch.setattr(
        revisiones,
        "RUTA_BD",
        tmp_path / "revisiones_prueba.db",
    )

    revisiones.inicializar_bd()


def test_base_inicia_sin_revisiones(base_temporal):
    resultado = revisiones.leer_revisiones("lote_A")

    assert resultado.empty


def test_guardar_y_actualizar_sin_duplicar(base_temporal):
    revisiones.guardar_revision(
        "lote_A",
        "TX001",
        "En revisión",
        "Primera observación",
    )

    primera_lectura = revisiones.leer_revisiones("lote_A")

    assert len(primera_lectura) == 1
    assert primera_lectura.iloc[0]["estado_revision"] == "En revisión"

    revisiones.guardar_revision(
        "lote_A",
        "TX001",
        "Revisada",
        "Verificación terminada",
    )

    segunda_lectura = revisiones.leer_revisiones("lote_A")

    assert len(segunda_lectura) == 1
    assert segunda_lectura.iloc[0]["estado_revision"] == "Revisada"
    assert (
        segunda_lectura.iloc[0]["comentario_revision"]
        == "Verificación terminada"
    )


def test_mismo_identificador_en_lotes_diferentes(base_temporal):
    revisiones.guardar_revision(
        "lote_A", "TX001", "Revisada", "Comentario del lote A"
    )

    revisiones.guardar_revision(
        "lote_B", "TX001", "En revisión", "Comentario del lote B"
    )

    lote_a = revisiones.leer_revisiones("lote_A")
    lote_b = revisiones.leer_revisiones("lote_B")

    assert lote_a.iloc[0]["estado_revision"] == "Revisada"
    assert lote_b.iloc[0]["estado_revision"] == "En revisión"
    assert (
        lote_b.iloc[0]["comentario_revision"]
        == "Comentario del lote B"
    )


@pytest.mark.parametrize(
    "estado,comentario,mensaje",
    [
        ("Aprobada", "", "no permitido"),
        ("Pendiente", "x" * 2001, "2000"),
    ],
)
def test_revision_invalida_se_rechaza(
    base_temporal, estado, comentario, mensaje
):
    with pytest.raises(ValueError, match=mensaje):
        revisiones.guardar_revision(
            "lote_A", "TX001", estado, comentario
        )

    assert revisiones.leer_revisiones("lote_A").empty