# Datos del grupo: EPH Gran Rosario y Gran Tucumán, 2016-2026

Base común para el TP de Introducción al análisis de datos. **Trabajemos todos con estos archivos y estas definiciones**, así las tasas y los ingresos cierran entre sí en el informe.

## Qué hay en esta carpeta

| Archivo | Para qué sirve |
|---|---|
| `eph_rosario_tucuman_completa.parquet` | Base principal: 164.614 personas, las columnas originales del INDEC y las variables nuevas. **Usen esta si pueden.** |
| `eph_rosario_tucuman_reducida.csv` | Las 50 columnas más útiles, para quien no pueda abrir parquet. |
| `tablas_de_control.xlsx` | Resultados ya calculados, para comprobar que sus números den igual. |
| `codigo/` | Scripts para regenerar todo desde el INDEC. No hace falta correrlos. |

Cubre 41 trimestres, de 2016-T2 a 2026-T2. El INDEC no publicó 2016-T1, y 2026-T3 y T4 todavía no estaban disponibles.

## Cómo abrir los datos

**Python** (`pip install pandas pyarrow`)

```python
import pandas as pd
df = pd.read_parquet("eph_rosario_tucuman_completa.parquet")
```

**R**

```r
df <- arrow::read_parquet("eph_rosario_tucuman_completa.parquet")
```

**Si usan el CSV**, indiquen que los códigos son texto, porque si no se pierden los ceros iniciales:

```python
df = pd.read_csv("eph_rosario_tucuman_reducida.csv", low_memory=False,
                 dtype={"PP04B_COD": str, "PP04D_COD": str})
```

## Prueba rápida antes de arrancar

Calculen la tasa de desocupación de Gran Rosario en 2026-T2. Tiene que dar **11,49 %**:

```python
s = df[(df["periodo"] == "2026-T2") & (df["AGLOMERADO"] == 4)]
desocupados = s.loc[s["ESTADO"] == 2, "PONDERA"].sum()
activos = s.loc[s["ESTADO"].isin([1, 2]), "PONDERA"].sum()
print(100 * desocupados / activos)
```

## Definiciones por tema

| Tema | Fórmula o variable | Filtro | Ponderador | Hoja de control |
|---|---|---|---|---|
| Tasa de actividad | (ocupados + desocupados) / población total | Toda la población | `PONDERA` | `tasas_trimestrales` |
| Tasa de empleo | ocupados / población total | Toda la población | `PONDERA` | `tasas_trimestrales` |
| Tasa de desocupación | desocupados / (ocupados + desocupados) | Población activa | `PONDERA` | `tasas_trimestrales` |
| Ingreso de la ocupación principal | `p21_real` | `ESTADO == 1` y `p21_nominal > 0` | `PONDIIO` | `ingresos_trimestrales` |
| Ingreso total individual | `p47t_real` | `p47t_nominal > 0` | `PONDII` | `ingresos_trimestrales` |
| Ingreso per cápita familiar | `ipcf_real` | `ipcf_nominal` no vacío | `PONDIH` | `ingresos_trimestrales` |

`ESTADO`: 1 ocupado, 2 desocupado, 3 inactivo, 4 menor de 10 años, 0 entrevista individual no realizada. Los cinco cuentan en la población total.

Las hojas `tasas_anuales` y `tasas_por_grupo` tienen las tasas por año y por sexo, edad y nivel educativo. La hoja `diccionario` explica cada variable nueva. Para las variables originales, ver el [diseño de registro del INDEC](https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_registro_2T2026.pdf).

## Reglas que hay que respetar

1. **Siempre ponderar.** Sin ponderadores los resultados no representan a la población.
2. **Cada ingreso va con su ponderador**, el de la tabla. No usar `PONDERA` para ingresos.
3. **No usar `P21`, `P47T`, `ITF` ni `IPCF` directamente para calcular.** Usar las columnas `_nominal` o `_real`, que ya sacan la no respuesta. Las originales quedan para analizarla.
4. **Ojo con `IPCF` e `ITF`:** la no respuesta figura como 0, no como -9. Afecta al 22,6 % de las personas, y solo se detecta con `PONDIH == 0`. Si se promedia sin sacarla, en el total nacional de 2026-T1 da $441.256 en lugar de los $728.008 oficiales.
5. **Para ver la evolución real, usar las columnas `_real`.** Están en pesos de 2026-T2.

## Cómo se ajustó por inflación

- **Fórmula:** `ingreso real = ingreso nominal × factor_deflactor`. El factor es el IPC de 2026-T2 dividido el IPC del trimestre.
- **Índice regional:** Gran Rosario usa el IPC Pampeana y Gran Tucumán el IPC Noroeste.
- **Meses usados:** la EPH capta lo cobrado el mes anterior a la entrevista. Por eso T1 usa diciembre a febrero, T2 marzo a mayo, T3 junio a agosto y T4 septiembre a noviembre.
- **Año 2016:** el IPC regional empieza en diciembre de 2016. Antes se usa el IPC-GBA, para ambos aglomerados, con la misma base. Como arranca en abril, **2016-T2 se calcula solo con abril y mayo**.
- **Límite:** el IPC mide cómo cambian los precios, no cuánto cuesta vivir en cada lugar. Las evoluciones se pueden comparar, pero los niveles entre Rosario y Tucumán no reflejan diferencias de costo de vida.

## Advertencias para el análisis

- **Pocos casos de desocupados:** la mediana es de unos 78 por trimestre y aglomerado, con un mínimo de 33. Las variaciones trimestrales de la desocupación tienen mucho ruido, y los cruces por sexo, edad o educación conviene hacerlos por año.
- **Pandemia:** en Tucumán la muestra cayó a 904 casos en 2020-T2 y 757 en 2020-T3, contra unos 2.500 habituales.
- **No respuesta de ingresos muy desigual:** de los ocupados no informó `P21` el 44,9 % en Rosario en 2016 (13,2 % en 2026), contra 8,2 % en Tucumán (11,3 % en 2026). El INDEC la compensa con los ponderadores, pero conviene explicarlo en el informe y tenerlo en cuenta para el modelo de imputación. Ver hoja `no_respuesta`.
- **Salto de ingresos en Tucumán:** la mediana nominal de `P21` pasa de $360.000 en 2024-T4 a $500.000 en 2025-T1. Viene de los datos, no del deflactor, y no tenemos identificada la causa. Hay que revisarlo antes de interpretarlo.
- **Medianas en números redondos:** la gente declara montos como $500.000, así que las medianas se mueven de a escalones.
- **Cambio de cuestionario en 2023-T4:** se agregan unas 60 columnas y `V2_M`, `V5_M`, `V11_M` y `V21_M` se dividen en subcomponentes. Por eso muchas columnas están vacías en parte del período. Ver si este cambio afecta la comparación de ingresos antes y después.
- **Años incompletos:** 2016 tiene 3 trimestres y 2026 tiene 2. Tenerlo en cuenta en los promedios anuales.

## Variables de empleo

- **`PP04D_COD`:** se usó el CNO 2001, que el diseño de registro indica para todo el período. Ya tiene restaurado el cero inicial perdido desde 2020.
- **`PP04B_COD`:** queda como lo publica el INDEC. Los códigos cortos se completan solo al calcular `rama_eph`.
- **Etiquetas:** `rama_eph` y las columnas `*_ocupacional` usan las tablas del paquete [`eph` de rOpenSci](https://docs.ropensci.org/eph/), que no es un producto oficial del INDEC. Están en `codigo/clasificadores/`.

## Qué se validó

| Comprobación | Base del grupo | Publicado |
|---|---|---|
| Total nacional 2026-T2: actividad, empleo, desocupación | 48,9 / 45,0 / 7,9 | 48,9 / 45 / 7,9 (prensa) |
| Desocupación Gran Rosario 2026-T2 | 11,49 | 11,5 (prensa) |
| Desocupación Gran Rosario 2026-T1 | 8,23 | 8,2 (prensa) |
| `IPCF` medio nacional 2026-T1 | $728.008 | $728.008 ([INDEC](https://www.indec.gob.ar/uploads/informesdeprensa/ingresos1trim26536C8EDD3E.pdf)) |

Las cifras de prensa citan al INDEC, pero no se contrastaron con el cuadro oficial por aglomerado. Tucumán se calculó con el mismo procedimiento, sin un dato publicado propio para comparar.

## Fuentes

- Microdatos y diseño de registro: [INDEC, bases de la EPH](https://www.indec.gob.ar/indec/web/Institucional-Indec-BasesDeDatos).
- IPC regional: [INDEC, serie_ipc_divisiones.csv](https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv).
- IPC-GBA de 2016: [API de Series de Tiempo de datos.gob.ar](https://apis.datos.gob.ar/series/api/series/?ids=101.1_I2NG_2016_M_22&format=csv).
