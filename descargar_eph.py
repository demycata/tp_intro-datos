"""Descarga y consolida las bases individuales de la EPH (INDEC), 2016-2026.

Recorre cada año y trimestre, lee en memoria la base individual de cada ZIP,
conserva los aglomerados de interés y exporta todo a un único archivo .parquet.

Uso:
    pip install requests pandas pyarrow
    python descargar_eph.py
"""

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph"
ANIO_INICIO = 2016
ANIO_FIN = 2026

# Códigos según el diseño de registro de la EPH (EPH_registro_2T2026.pdf).
# Gran Rosario es el 4: el código 39 no existe en el diseño ni en los datos.
AGLOMERADOS = {
    4: "Gran Rosario",
    29: "Gran Tucumán - Tafí Viejo",
}

ARCHIVO_SALIDA = (
    Path(__file__).resolve().parent
    / "eph_individual_rosario_tucuman_2016_2026.parquet"
)

# Columnas que deben quedar como texto. Los códigos de ocupación y actividad no
# son cantidades, y convertirlos a número les borraría los ceros a la izquierda.
COLUMNAS_TEXTO = {
    "CODUSU", "MAS_500", "CH05", "CH15_COD", "CH16_COD",
    "PP04B_COD", "PP04D_COD", "PP09A_ESP", "PP09C_ESP",
    "PP11B_COD", "PP11D_COD",
}

ORDINALES = {1: "1er", 2: "2do", 3: "3er", 4: "4to"}
TIMEOUT_SEGUNDOS = (15, 120)  # (conexión, lectura)


class TrimestreNoDisponible(Exception):
    """El INDEC no publica un ZIP para ese trimestre."""


def crear_sesion():
    """Crea una sesión que reintenta ante cortes y errores temporales del servidor."""
    reintentos = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    sesion = requests.Session()
    sesion.headers["User-Agent"] = "Mozilla/5.0"
    sesion.mount("https://", HTTPAdapter(max_retries=reintentos))
    return sesion


def urls_candidatas(anio, trimestre):
    """Devuelve las URL posibles: el INDEC cambió el nombre del ZIP con los años."""
    ordinal = ORDINALES[trimestre]
    variantes = (f"{trimestre}_Trim", f"{ordinal}_Trim", f"{ordinal}Trim")
    return [f"{BASE_URL}/EPH_usu_{v}_{anio}_txt.zip" for v in variantes]


def descargar_zip(sesion, anio, trimestre):
    """Descarga el ZIP del trimestre y devuelve su contenido en bytes."""
    for url in urls_candidatas(anio, trimestre):
        respuesta = sesion.get(url, timeout=TIMEOUT_SEGUNDOS)
        if respuesta.status_code == 404:
            continue
        respuesta.raise_for_status()
        # Si el archivo no existe, el INDEC suele responder 200 con una página
        # HTML en lugar de un 404, así que el código HTTP no alcanza.
        if zipfile.is_zipfile(io.BytesIO(respuesta.content)):
            return respuesta.content
    raise TrimestreNoDisponible("no hay un ZIP publicado (HTTP 404 o página de error)")


def leer_base_individual(contenido_zip):
    """Devuelve la base individual del ZIP como DataFrame, con todo en texto.

    El archivo se identifica por su encabezado y no por su nombre, porque el
    nombre varía (por ejemplo, 2020 T4 se llama "EPH_usu_personas_4to...").
    """
    with zipfile.ZipFile(io.BytesIO(contenido_zip)) as archivo_zip:
        for nombre in archivo_zip.namelist():
            es_tabla = nombre.lower().endswith((".txt", ".csv"))
            if not es_tabla or "__macosx" in nombre.lower():
                continue
            crudo = archivo_zip.read(nombre)
            encabezado = crudo.split(b"\n", 1)[0].upper()
            if b"COMPONENTE" in encabezado and b"CH04" in encabezado:
                break
        else:
            raise ValueError("el ZIP no contiene la base individual")

    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")

    separador = ";" if encabezado.count(b";") > encabezado.count(b",") else ","
    df = pd.read_csv(io.StringIO(texto), sep=separador, dtype=str, low_memory=False)

    df.columns = df.columns.str.strip().str.upper()
    # 2021 T3 trae un separador sobrante que genera una columna vacía.
    return df.loc[:, ~df.columns.str.startswith("UNNAMED")]


def procesar_trimestre(sesion, anio, trimestre):
    """Descarga un trimestre y devuelve sus registros de los aglomerados elegidos."""
    df = leer_base_individual(descargar_zip(sesion, anio, trimestre))

    origen_ok = (
        pd.to_numeric(df["ANO4"]).eq(anio).all()
        and pd.to_numeric(df["TRIMESTRE"]).eq(trimestre).all()
    )
    if not origen_ok:
        raise ValueError("ANO4/TRIMESTRE del archivo no coinciden con el pedido")

    # Filtrar acá da el mismo resultado que hacerlo al final y evita tener en
    # memoria más de 2 millones de filas de todo el país.
    aglomerado = pd.to_numeric(df["AGLOMERADO"])
    df = df[aglomerado.isin(AGLOMERADOS)].copy()
    df["anio"] = anio
    df["trimestre"] = trimestre
    return df


def tipar_columnas(df):
    """Unifica los códigos entre trimestres y convierte a número las demás columnas."""
    df = df.copy()
    # Según el trimestre aparece como S/N o como SI/NO.
    df["MAS_500"] = df["MAS_500"].str.strip().str[0].str.upper()

    # Hasta 2019 estos códigos tienen 5 dígitos; después se pierde el cero inicial.
    for columna in ("PP04D_COD", "PP11D_COD"):
        codigo = df[columna].str.strip()
        df[columna] = codigo.mask(codigo.str.len().eq(4), "0" + codigo)

    for columna in df.columns.difference([*COLUMNAS_TEXTO, "anio", "trimestre"]):
        valores = df[columna].str.strip().str.replace(",", ".", regex=False)
        valores = valores.mask(valores.eq(""))
        numeros = pd.to_numeric(valores, errors="coerce")
        if numeros.notna().sum() != valores.notna().sum():
            print(f"  [AVISO] {columna} tiene valores no numéricos: queda como texto")
            continue
        enteros = numeros.dropna().mod(1).eq(0).all()
        df[columna] = numeros.astype("Int64") if enteros else numeros
    return df


def main():
    sesion = crear_sesion()
    tablas = []
    omitidos = []

    for anio in range(ANIO_INICIO, ANIO_FIN + 1):
        for trimestre in range(1, 5):
            etiqueta = f"{anio} T{trimestre}"
            try:
                tabla = procesar_trimestre(sesion, anio, trimestre)
            except TrimestreNoDisponible as error:
                print(f"[NO DISPONIBLE] {etiqueta}: {error}")
                omitidos.append(etiqueta)
            except Exception as error:
                # Un trimestre con problemas no debe frenar a los demás.
                print(f"[ERROR] {etiqueta}: {type(error).__name__}: {error}")
                omitidos.append(etiqueta)
            else:
                print(f"[OK] {etiqueta}: {len(tabla):,} registros")
                tablas.append(tabla)

    if not tablas:
        sys.exit("No se pudo procesar ningún trimestre: no se generó el archivo.")

    consolidado = tipar_columnas(pd.concat(tablas, ignore_index=True))
    consolidado.to_parquet(ARCHIVO_SALIDA, index=False, compression="zstd")

    print(f"\nTrimestres procesados: {len(tablas)}")
    print(f"Trimestres omitidos: {', '.join(omitidos) if omitidos else 'ninguno'}")
    print("Registros por aglomerado:")
    for codigo, cantidad in consolidado["AGLOMERADO"].value_counts().sort_index().items():
        print(f"  {codigo} - {AGLOMERADOS[codigo]}: {cantidad:,}")
    print(f"Archivo generado: {ARCHIVO_SALIDA}")


if __name__ == "__main__":
    main()
