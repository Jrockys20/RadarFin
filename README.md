# RadarFin

Aplicación web para priorizar la revisión de transacciones financieras
ficticias mediante reglas explicables.

Una operación inusual no implica fraude. RadarFin apoya la revisión
humana y no bloquea operaciones automáticamente.

## Funcionalidades

- Carga y validación de transacciones en CSV.
- Detección de montos inusuales, operaciones en ráfaga y horarios
  poco habituales.
- Puntuación y clasificación por prioridad.
- Bandeja con filtros y selección de operaciones.
- Explicación de las reglas activadas.
- Registro local de estados y comentarios mediante SQLite.
- Descarga de resultados filtrados.
- Evaluación frente a anomalías etiquetadas.

## Tecnologías

Python, pandas, Streamlit, Plotly, SQLite, pytest y Git.

Esta versión utiliza reglas explicables; no incorpora un modelo
de aprendizaje automático.

## Ejecución local en Windows

Desde la carpeta del proyecto:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

El navegador mostrará la dirección indicada por Streamlit,
habitualmente http://localhost:8501.

Para detener la aplicación, presionar Ctrl + C en la terminal.

## Datos de ejemplo

Todos los clientes y operaciones son ficticios.

- `datos/historial.csv`: 1,200 operaciones históricas de veinte clientes.
- `datos/desarrollo.csv`: 424 operaciones, con 24 anomalías etiquetadas.
- `datos/prueba.csv`: 424 operaciones adicionales, con 24 anomalías
  etiquetadas.

Los conjuntos de desarrollo y prueba proceden del mismo generador,
con semillas diferentes.

Para regenerar los archivos:

```bat
python generar_datos.py
```

Este comando reemplaza los tres CSV con datos reproducibles.

## Formato de entrada

Columnas obligatorias:

| Columna | Contenido |
|---|---|
| id_transaccion | Identificador único de la operación |
| id_cliente | Identificador del cliente ficticio |
| fecha_hora | Fecha en formato YYYY-MM-DD HH:MM:SS |
| monto | Número positivo y finito, expresado en soles |
| canal | app, web, cajero o agente |

Todas las fechas se interpretan en una misma zona horaria.

El historial debe ser completamente anterior al lote analizado.
Los identificadores de transacción no deben repetirse entre ambos.

La columna opcional `es_anomalia`, con valores 0 o 1, permite calcular
métricas. `tipo_anomalia` permite describir el escenario simulado.
Estas etiquetas no intervienen en las predicciones.

## Reglas de detección

| Regla | Condición | Puntos |
|---|---|---:|
| Monto | Superior a cinco veces la mediana histórica del cliente | 40 |
| Ráfaga | Quinta operación o posterior del cliente en diez minutos | 35 |
| Horario | Franja de seis horas que concentra menos del 5 % de su historial | 25 |

Las reglas de monto y horario requieren al menos veinte operaciones
históricas por cliente.

La regla de ráfaga incluye la operación actual y las anteriores del
lote dentro de la ventana. Una operación exactamente diez minutos
anterior todavía cuenta. Los empates temporales se ordenan por
identificador.

## Prioridades

| Puntuación | Prioridad |
|---|---|
| 0–24 | Sin alerta |
| 25–39 | Baja |
| 40–69 | Media |
| 70–100 | Alta |

La puntuación indica prioridad de revisión, no probabilidad de fraude.

## Resultados de evaluación

Resultados por transacción de la versión inicial:

| Indicador | Desarrollo | Prueba |
|---|---:|---:|
| Operaciones | 424 | 424 |
| Anomalías etiquetadas | 24 | 24 |
| Verdaderos positivos | 12 | 12 |
| Falsos positivos | 0 | 0 |
| Falsos negativos | 12 | 12 |
| Verdaderos negativos | 400 | 400 |
| Precisión | 100 % | 100 % |
| Exhaustividad | 50 % | 50 % |
| F1 | 66.67 % | 66.67 % |
| Operaciones enviadas a revisión | 2.83 % | 2.83 % |

Las doce anomalías omitidas corresponden a las primeras cuatro
operaciones de cada uno de los tres episodios de ráfaga.
La regla comienza a alertar desde la quinta operación.

Para evaluar:

```bat
python evaluar_motor.py --conjunto desarrollo
python evaluar_motor.py --conjunto prueba
```

## Pruebas automáticas

```bat
python -m pytest -q
```

Las pruebas incluyen límites de detección, separación de clientes,
historial insuficiente, combinaciones de reglas, independencia de
las etiquetas, validación de entradas y persistencia de revisiones.

## Revisiones del analista

SQLite conserva el estado, el comentario y la última actualización
de cada revisión en `datos/radarfin.db`.

Estados disponibles: Pendiente, En revisión y Revisada.

Las revisiones se asocian a una versión del historial y del lote.
Actualizar una revisión reemplaza sus valores anteriores.

La base se crea automáticamente y no se incluye en Git.
La persistencia comprobada corresponde a la ejecución local.

## Limitaciones

- La evaluación utiliza escenarios sintéticos relativamente sencillos.
- No demuestra desempeño sobre operaciones bancarias reales.
- La ventana de ráfaga no conserva contexto de lotes anteriores.
- Las primeras operaciones de una ráfaga no se alertan retrospectivamente.
- Las franjas horarias de seis horas son una aproximación.
- Los clientes sin suficiente historial no pueden evaluarse por monto
  ni horario.
- No incluye autenticación, roles ni historial de cambios de revisiones.

## Modos de ejecución

La ejecución local utiliza SQLite para conservar las revisiones.

La demo pública utiliza almacenamiento temporal por sesión:
cada visitante tiene sus propios estados y comentarios.
Estos pueden perderse al recargar la página o finalizar la sesión.
La descarga de resultados permite conservar una copia.

El modo se configura mediante `modo_demo_publica` en la
configuración de Streamlit: `false` para SQLite local y
`true` para la demo temporal.