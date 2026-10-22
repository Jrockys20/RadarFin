"""Tokens de RadarFin: tema, marca y superficies compartidas."""
from pathlib import Path
from html import escape
import streamlit as st

ROOT = Path(__file__).resolve().parent
TOKENS = {
    "background": "#080B12", "secondary": "#0D1220", "surface": "#111827",
    "elevated": "#192235", "border": "#283348", "text": "#F4F7FB",
    "muted": "#9BA8BA", "brand": "#F72585", "cyan": "#40D9E6",
    "action": "#C01864", "positive": "#36D6A0", "medium": "#F5B942", "high": "#FF5C75",
}
PRIORIDADES = ["Alta", "Media", "Baja", "Sin alerta"]
COLORES = dict(zip(PRIORIDADES, [TOKENS["high"], TOKENS["medium"], TOKENS["cyan"], TOKENS["muted"]]))
SIMBOLOS = {"Alta": "▲", "Media": "◆", "Baja": "●", "Sin alerta": "—"}
PAGINAS = ["Resumen", "Bandeja de revisión", "Evaluación", "Datos y configuración"]


def aplicar_estilos():
    st.html((ROOT / "assets" / "radarfin.css").read_text(encoding="utf-8").replace(
        "/* TOKENS */", ":root{" + ";".join(f"--rf-{k}:{v}" for k,v in TOKENS.items()) + "}"
    ))


def encabezado(pagina):
    textos = {
        "Resumen": ("Centro de análisis", "Señales claras. Decisiones con contexto."),
        "Bandeja de revisión": ("Investiga cada señal", "Prioriza alertas y documenta tu criterio."),
        "Evaluación": ("Rendimiento del detector", "Resultados explicables frente a etiquetas sintéticas."),
        "Datos y configuración": ("El contexto empieza en los datos", "Gestiona el historial y el lote que deseas analizar."),
    }
    titulo, descripcion = textos[pagina]
    st.html(f'<header class="rf-header"><p class="rf-eyebrow">RADARFIN / {escape(pagina.upper())}</p>'
            f'<h1>{titulo}</h1><p>{descripcion}</p></header>')


def contexto(origen, operaciones):
    tipo = "DATOS DE EJEMPLO" if origen.startswith("Ejemplo") else "CSV DEL USUARIO"
    st.html(f'<div class="rf-context"><span class="rf-source">{tipo}</span>'
            f'<span>{escape(origen)}</span><span>{operaciones["fecha_hora"].min():%d/%m/%Y} — '
            f'{operaciones["fecha_hora"].max():%d/%m/%Y}</span>'
            '<span>PEN · S/</span><span class="rf-ready">✓ Análisis completado</span></div>')


def etiqueta_prioridad(prioridad):
    color = COLORES.get(prioridad, TOKENS["muted"])
    st.html(f'<span class="rf-priority" style="color:{color}">'
            f'{SIMBOLOS.get(prioridad, "")} Prioridad {escape(prioridad)}</span>')
