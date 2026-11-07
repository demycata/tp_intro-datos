# Trabajo final: EPH Gran Rosario y Gran Tucumán, 2016-2026

Registro de los procedimientos que se hicieron para empezar el trabajo: de dónde salieron los datos, qué se les hizo y cómo se comprobaron. Está reconstruido a partir de la conversación con Claude Code del 5/11/2026, y los archivos se volvieron a verificar el 6/11/2026.

**Estado:** los datos están listos y empaquetados en `datos_grupo.zip`. Falta el análisis y el informe, y quedan [dos cosas por resolver](#pendientes).

Este README cuenta cómo se prepararon los datos. Para usarlos (fórmulas, filtros, ponderadores y reglas) la referencia es [`datos_grupo/LEEME.md`](datos_grupo/LEEME.md).

## La consigna

`TP final.pdf`: Introducción al análisis de datos, UTN Avellaneda, segundo parcial, 27/11/2026.

- **Entrega:** informe de 6 a 10 páginas, en grupos de 3 o 4 personas, comparando dos aglomerados.
- **Contenido:** evolución de las tasas de desocupación, empleo y actividad, y de los ingresos teniendo en cuenta la inflación, con microdatos de la EPH 2016-2026.
- **Objetivos 1 a 3 (nota 4 a 5):** análisis univariado, análisis multivariado y gráficos.
- **Objetivo 4 (nota 6 a 10):** modelo de regresión para imputar la no respuesta de ingresos, con R² mayor a 0,3 sin transformar la variable original.

## Procedimiento

### 1. Explorar la fuente

Antes de escribir código se revisó cómo publica el INDEC los datos:

1. Se probaron las URL de los ZIP de cada trimestre. El servidor responde `200` con una página HTML cuando el archivo no existe, así que el código HTTP no alcanza para saber si un trimestre está publicado.
2. Se buscaron las variantes del nombre de los ZIP. Hay tres: `2doTrim`, `1er_Trim` y `2_Trim`.
3. Se abrieron todos los ZIP disponibles para comparar archivos, separadores y columnas.
4. Se consultó el diseño de registro (`EPH_registro_2T2026.pdf`) para confirmar los códigos de aglomerado y las variables.

Hay 41 trimestres disponibles, de 2016-T2 a 2026-T2. El 2016-T1 no está publicado, y 2026-T3 y T4 no estaban disponibles al 5/11/2026.

### 2. Descargar y consolidar (`descargar_eph.py`)

El script recorre cada año y trimestre, lee el ZIP en memoria, conserva los dos aglomerados, agrega `anio` y `trimestre`, y exporta un parquet. Si un trimestre falla, lo avisa por consola y sigue con el próximo.

Resuelve estas particularidades de los archivos:

| Problema en los datos | Solución |
|---|---|
| Un archivo inexistente responde `200` con HTML | Se comprueba que lo descargado sea un ZIP válido |
| El nombre del ZIP cambia según el año | Se prueban las tres variantes |
| El archivo interno cambia de nombre (en 2020-T4 es `EPH_usu_personas...`) | La base individual se reconoce por su encabezado |
| `MAS_500` aparece como S/N y como SI/NO | Se unifica a una letra |
| Columnas numéricas con formatos distintos (`CH14` como `04` y `4`) | Se convierten a número |
| 2021-T3 trae una columna vacía de más | Se elimina |
| `PP04D_COD` y `PP11D_COD` pierden el cero inicial desde 2020 (`05002` pasa a `5002`) | Se restaura, para que cada ocupación tenga un solo código en toda la serie |

**Resultado:** `eph_individual_rosario_tucuman_2016_2026.parquet`, con 164.614 registros y 241 columnas, sin duplicados. Son 74.940 de Gran Rosario y 89.674 de Gran Tucumán.

**Pruebas de errores:** con un servidor local se simularon 404, página HTML con `200`, ZIP corrupto, ZIP sin base individual, trimestre equivocado, 403, 503 y falta de conexión. En todos los casos el script avisó y siguió. El 503 se reintentó antes de darse por fallido, y sin ningún trimestre válido no generó el archivo.

### 3. Fijar definiciones comunes

Para que los cuatro temas cierren entre sí, se fijaron las definiciones a partir del diseño de registro:

- **Tasas:** se calculan con `ESTADO` y `PONDERA`. La población total incluye todos los valores de `ESTADO`.
- **Ponderadores de ingresos:** `PONDIIO` para `P21`, `PONDII` para `P47T` y `PONDIH` para `ITF` e `IPCF`.
- **No respuesta de ingresos:** en `P21` y `P47T` figura como `-9`. En `ITF` e `IPCF` figura como `0`, y solo se detecta con `PONDIH == 0`. Afecta al 22,6 % de las personas de la base.

### 4. Ajustar por inflación

- **Índice:** IPC Pampeana para Rosario e IPC Noroeste para Tucumán, de la serie regional del INDEC, con base diciembre 2016 = 100.
- **Año 2016:** la serie regional empieza en diciembre de 2016. Para los meses anteriores se usó el IPC-GBA, que tiene la misma base, en los dos aglomerados.
- **Meses:** la EPH capta lo cobrado el mes anterior a la entrevista, así que T1 usa diciembre a febrero, T2 marzo a mayo, T3 junio a agosto y T4 septiembre a noviembre. El 2016-T2 queda calculado solo con abril y mayo.
- **Resultado:** los ingresos reales están en pesos de 2026-T2.

### 5. Etiquetar la rama y la ocupación

- **Clasificadores:** se tomaron las tablas del paquete [`eph` de rOpenSci](https://docs.ropensci.org/eph/), que no es un producto oficial del INDEC, y se guardaron en `clasificadores/`.
- **`PP04B_COD`:** se agrupó en 14 ramas con CAES 1.0. Los códigos de 1 y 3 dígitos se completan con un cero solo para calcular `rama_eph`, y la columna original queda como la publica el INDEC.
- **`PP04D_COD`:** se separó con CNO 2001 en carácter, jerarquía, tecnología y calificación.

### 6. Armar la base del grupo (`preparar_datos_grupo.py`)

El script toma el parquet del paso 2 y agrega 27 columnas, con lo que la base queda en 268:

- **Etiquetas:** `sexo`, `grupo_edad`, `nivel_educativo`, `condicion_actividad`, `rama_eph` y otras.
- **Ingresos sin no respuesta:** columnas `_nominal`.
- **Ingresos ajustados:** columnas `_real` y `factor_deflactor`.
- **Marcas de no respuesta:** `nr_p21`, `nr_p47t` y `nr_ipcf`.

También genera `tablas_de_control.xlsx`, con los resultados ya calculados para que cada integrante compare sus números. Sus hojas son `tasas_trimestrales`, `tasas_anuales`, `tasas_por_grupo`, `ingresos_trimestrales`, `no_respuesta`, `ipc` y `diccionario`.

### 7. Validar

| Comprobación | Base | Publicado | Fuente |
|---|---|---|---|
| Total nacional 2026-T2: actividad, empleo, desocupación | 48,9 / 45,0 / 7,9 | 48,9 / 45 / 7,9 | Prensa que cita al INDEC |
| Desocupación Gran Rosario 2026-T2 | 11,49 | 11,5 | Prensa que cita al INDEC |
| Desocupación Gran Rosario 2026-T1 | 8,23 | 8,2 | Prensa que cita al INDEC |
| `IPCF` medio nacional 2026-T1 | $728.008 | $728.008 | Informe del INDEC |

Sin sacar los falsos ceros, ese mismo `IPCF` da $441.256.

**Lo que no se validó:** las tasas por aglomerado no se contrastaron con el cuadro oficial, y para Tucumán no se comparó ningún dato publicado. Se calcularon con el mismo procedimiento.

### 8. Empaquetar y probar

1. Se escribió `datos_grupo/LEEME.md` para el grupo, con instrucciones, definiciones, reglas y advertencias.
2. Se copiaron los scripts y clasificadores a `datos_grupo/codigo/`.
3. Se generó `datos_grupo.zip` (16,5 MB).
4. Se descomprimió en otra carpeta y se corrió la prueba rápida del LEEME, que dio 11,49 %.
5. Se regeneró todo desde cero y el CSV salió idéntico.

**Verificación del 6/11/2026:** los 8 archivos del ZIP son idénticos a los de `datos_grupo/`, las dimensiones de las bases coinciden y la prueba rápida sigue dando 11,49 %.

## Cambios respecto del pedido original

- **Gran Rosario es `AGLOMERADO == 4`, no 39.** El código 39 no existe en el diseño de registro ni en ninguno de los 41 trimestres. Con 39 la base habría quedado solo con Tucumán, sin ningún error visible.
- **El filtro por aglomerado se aplica en cada trimestre, no al final.** El resultado es el mismo y evita cargar más de 2 millones de filas en memoria.

## Archivos

```text
trabajo final/
├── README.md                     este archivo
├── TP final.pdf                  consigna
├── descargar_eph.py              paso 2: descarga y consolida
├── preparar_datos_grupo.py       paso 6: arma la base del grupo
├── clasificadores/               tablas de rama y ocupación
├── eph_individual_rosario_tucuman_2016_2026.parquet    base sin variables nuevas
├── datos_grupo/                  paquete común
│   ├── LEEME.md
│   ├── eph_rosario_tucuman_completa.parquet            164.614 x 268
│   ├── eph_rosario_tucuman_reducida.csv                50 columnas
│   ├── tablas_de_control.xlsx
│   └── codigo/                   copia de los scripts y clasificadores
└── datos_grupo.zip               lo que se comparte con el grupo
```

## Cómo regenerar los datos

```bash
pip install requests pandas pyarrow openpyxl
python descargar_eph.py
python preparar_datos_grupo.py
```

La descarga tarda alrededor de un minuto y medio.

**No conviene regenerar mientras el grupo está trabajando.** Si el INDEC publicó trimestres nuevos, la base cambia y deja de coincidir con la de los demás y con los números del LEEME.

Los scripts actualizan `datos_grupo/`, pero no `datos_grupo/codigo/` ni el ZIP. Si se regenera o se cambia un script, hay que actualizar esos dos a mano.

## Reparto del trabajo

El grupo son 4 personas y se divide por tema. Los cruces son una sugerencia para que no se repitan:

| Tema | Cruces sugeridos | Tener en cuenta |
|---|---|---|
| Tasa de actividad | Sexo y edad | Comparar por año con la hoja `tasas_por_grupo` |
| Tasa de empleo | Rama y calificación | Usar `rama_eph` y `calificacion_ocupacional` |
| Tasa de desocupación | Edad y nivel educativo | Tiene pocos casos: hacer los cruces por año y marcar 2020 en Tucumán |
| Ingresos | Sexo, educación y categoría ocupacional | Usar columnas `_real` con su ponderador, y mirar medianas además de promedios |

Las otras advertencias para el análisis (no respuesta desigual, salto de ingresos en Tucumán, muestra en pandemia y cambio de cuestionario en 2023-T4) están en el [LEEME](datos_grupo/LEEME.md#advertencias-para-el-análisis).

## Pendientes

1. **Confirmar con el docente el ajuste por inflación.** Se usaron los meses de ingreso (T1 = diciembre a febrero) y no el trimestre calendario. Conviene resolverlo antes de que arranque la persona de ingresos, porque cambia todos los valores reales. Para pasar al trimestre calendario hay que editar `meses` en `ipc_trimestral` (`preparar_datos_grupo.py:157`), regenerar, actualizar el LEEME y volver a armar el ZIP.
2. **Asignar el modelo de imputación (objetivo 4).** Es lo que habilita la nota de 6 a 10 y no tiene responsable. Le corresponde a ingresos, pero esa persona ya tiene la parte más pesada, así que se sugirió que ayude quien tenga la tasa de actividad o quien termine primero.
