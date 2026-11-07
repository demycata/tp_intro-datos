"""Arma el paquete de datos común del grupo a partir de la base de la EPH.

Toma el parquet generado por descargar_eph.py, agrega variables derivadas
(etiquetas, ingresos sin códigos de no respuesta, ingresos reales) y calcula
las tablas de control para que todo el grupo parta de las mismas definiciones.

Uso:
    pip install requests pandas pyarrow openpyxl
    python descargar_eph.py
    python preparar_datos_grupo.py
"""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

CARPETA = Path(__file__).resolve().parent
ENTRADA = CARPETA / "eph_individual_rosario_tucuman_2016_2026.parquet"
CLASIFICADORES = CARPETA / "clasificadores"
SALIDA = CARPETA / "datos_grupo"

URL_IPC_REGIONAL = "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv"
URL_IPC_GBA = (
    "https://apis.datos.gob.ar/series/api/series/"
    "?ids=101.1_I2NG_2016_M_22&start_date=2016-03-01&end_date=2016-12-01&format=csv"
)

# Los ingresos reales quedan expresados en pesos de este trimestre.
PERIODO_BASE = (2026, 2)

AGLOMERADOS = {4: "Gran Rosario", 29: "Gran Tucumán"}
REGION_IPC = {4: "Pampeana", 29: "Noroeste"}

SEXO = {1: "Varón", 2: "Mujer"}
CONDICION = {
    0: "Entrevista individual no realizada",
    1: "Ocupado",
    2: "Desocupado",
    3: "Inactivo",
    4: "Menor de 10 años",
}
NIVEL_EDUCATIVO = {
    1: "Primario incompleto",
    2: "Primario completo",
    3: "Secundario incompleto",
    4: "Secundario completo",
    5: "Superior incompleto",
    6: "Superior completo",
    7: "Sin instrucción",
    9: "Ns/Nr",
}
NIVEL_EDUCATIVO_GRUPO = {
    7: "1. Hasta primario incompleto",
    1: "1. Hasta primario incompleto",
    2: "2. Primario completo a secundario incompleto",
    3: "2. Primario completo a secundario incompleto",
    4: "3. Secundario completo a superior incompleto",
    5: "3. Secundario completo a superior incompleto",
    6: "4. Superior completo",
}
CATEGORIA_OCUPACIONAL = {
    1: "Patrón",
    2: "Cuenta propia",
    3: "Obrero o empleado",
    4: "Trabajador familiar sin remuneración",
    9: "Ns/Nr",
}

COLUMNAS_REDUCIDA = [
    "anio", "trimestre", "periodo", "AGLOMERADO", "aglomerado_nombre",
    "CODUSU", "NRO_HOGAR", "COMPONENTE",
    "PONDERA", "PONDIIO", "PONDII", "PONDIH",
    "ESTADO", "condicion_actividad", "CH04", "sexo", "edad", "grupo_edad",
    "NIVEL_ED", "nivel_educativo", "nivel_ed_grupo",
    "CAT_OCUP", "categoria_ocupacional", "INTENSI", "PP04A", "PP07H", "PP3E_TOT",
    "PP04B_COD", "rama_eph", "PP04D_COD", "caracter_ocupacional",
    "jerarquia_ocupacional", "tecnologia_ocupacional", "calificacion_ocupacional",
    "P21", "P47T", "ITF", "IPCF",
    "p21_nominal", "p47t_nominal", "itf_nominal", "ipcf_nominal",
    "p21_real", "p47t_real", "itf_real", "ipcf_real",
    "nr_p21", "nr_p47t", "nr_ipcf", "factor_deflactor",
]

DICCIONARIO = [
    ("anio, trimestre", "Año y trimestre de la base de origen."),
    ("periodo", "Año y trimestre en texto, por ejemplo 2016-T2."),
    ("aglomerado_nombre", "Gran Rosario (AGLOMERADO 4) o Gran Tucumán (AGLOMERADO 29)."),
    ("condicion_actividad", "Etiqueta de ESTADO."),
    ("sexo", "Etiqueta de CH04."),
    ("edad", "CH06, con -1 (menores de un año) recodificado a 0."),
    ("grupo_edad", "0-13, 14-29, 30-64 y 65 y más."),
    ("nivel_educativo", "Etiqueta de NIVEL_ED."),
    ("nivel_ed_grupo", "NIVEL_ED en 4 grupos, para cruces con pocos casos."),
    ("categoria_ocupacional", "Etiqueta de CAT_OCUP."),
    ("rama_eph", "Rama de actividad en 14 grupos, a partir de PP04B_COD."),
    ("caracter_ocupacional", "Dígitos 1 y 2 de PP04D_COD (CNO 2001)."),
    ("jerarquia_ocupacional", "Dígito 3 de PP04D_COD (CNO 2001)."),
    ("tecnologia_ocupacional", "Dígito 4 de PP04D_COD (CNO 2001)."),
    ("calificacion_ocupacional", "Dígito 5 de PP04D_COD (CNO 2001)."),
    ("p21_nominal", "P21 con la no respuesta (-9) en vacío. Ponderador: PONDIIO."),
    ("p47t_nominal", "P47T con la no respuesta (-9) en vacío. Ponderador: PONDII."),
    ("itf_nominal", "ITF con la no respuesta (PONDIH = 0) en vacío. Ponderador: PONDIH."),
    ("ipcf_nominal", "IPCF con la no respuesta (PONDIH = 0) en vacío. Ponderador: PONDIH."),
    ("p21_real, p47t_real, itf_real, ipcf_real", "Ingreso nominal por factor_deflactor."),
    ("factor_deflactor", "IPC regional del período base dividido el IPC del trimestre."),
    ("nr_p21", "Ocupado que no informó P21 (P21 = -9)."),
    ("nr_p47t", "Persona que no informó P47T (P47T = -9)."),
    ("nr_ipcf", "Persona en un hogar sin ingreso familiar informado (PONDIH = 0)."),
]


def descargar_ipc():
    """Devuelve el IPC mensual de cada región, con base diciembre 2016 = 100.

    El IPC regional empieza en diciembre de 2016. Para abril-noviembre de 2016
    se usa el IPC-GBA, único oficial del período y con la misma base.
    """
    cabeceras = {"User-Agent": "Mozilla/5.0"}
    respuesta = requests.get(URL_IPC_REGIONAL, headers=cabeceras, timeout=120)
    respuesta.raise_for_status()
    ipc = pd.read_csv(io.StringIO(respuesta.content.decode("latin-1")), sep=";", dtype=str)
    ipc = ipc[ipc["Codigo"].eq("0") & ipc["Region"].isin(REGION_IPC.values())]
    ipc = pd.DataFrame({
        "mes": pd.PeriodIndex(ipc["Periodo"].str[:4] + "-" + ipc["Periodo"].str[4:], freq="M"),
        "region": ipc["Region"].to_numpy(),
        "ipc": ipc["Indice_IPC"].str.replace(",", ".").astype(float).to_numpy(),
        "fuente": "IPC regional",
    })

    respuesta = requests.get(URL_IPC_GBA, headers=cabeceras, timeout=120)
    respuesta.raise_for_status()
    gba = pd.read_csv(io.StringIO(respuesta.text))
    gba.columns = ["mes", "ipc"]
    gba["mes"] = pd.PeriodIndex(gba["mes"].str[:7], freq="M")
    if gba.loc[gba["mes"].eq(pd.Period("2016-12")), "ipc"].iloc[0] != 100:
        raise ValueError("El IPC-GBA no tiene base diciembre 2016 = 100")
    gba = gba[gba["mes"] < pd.Period("2016-12")].assign(fuente="IPC-GBA")

    empalmes = [gba.assign(region=region) for region in REGION_IPC.values()]
    return pd.concat([ipc, *empalmes], ignore_index=True)


def ipc_trimestral(ipc_mensual, periodos):
    """Calcula el IPC de cada trimestre según los meses a los que refieren los ingresos.

    La EPH capta lo percibido el mes anterior a la entrevista: las entrevistas
    de T1 (enero a marzo) relevan ingresos de diciembre a febrero, y así.
    """
    filas = []
    for anio, trimestre in periodos:
        primer_mes = pd.Period(f"{anio}-{3 * trimestre - 2:02d}", freq="M")
        meses = [primer_mes - 1, primer_mes, primer_mes + 1]
        for region in REGION_IPC.values():
            datos = ipc_mensual[ipc_mensual["region"].eq(region) & ipc_mensual["mes"].isin(meses)]
            filas.append({
                "anio": anio,
                "trimestre": trimestre,
                "region": region,
                "meses_de_ingreso": f"{meses[0]} a {meses[-1]}",
                "meses_con_dato": len(datos),
                "fuente": " + ".join(sorted(datos["fuente"].unique())),
                "ipc": datos["ipc"].mean(),
            })
    tabla = pd.DataFrame(filas)
    base = tabla[tabla["anio"].eq(PERIODO_BASE[0]) & tabla["trimestre"].eq(PERIODO_BASE[1])]
    tabla["factor_deflactor"] = tabla["region"].map(base.set_index("region")["ipc"]) / tabla["ipc"]
    return tabla


def agregar_clasificadores(df):
    """Agrega rama de actividad y las dimensiones del código de ocupación."""
    caes = pd.read_csv(CLASIFICADORES / "caes_rama_eph.csv", dtype=str)
    cno = pd.read_csv(CLASIFICADORES / "cno_2001.csv", dtype=str)

    rama = df["PP04B_COD"].str.strip()
    # Los códigos de 1 y 3 dígitos perdieron el cero inicial; los de 2 son divisiones.
    rama = rama.mask(rama.str.len().isin([1, 3]), "0" + rama)
    df["rama_eph"] = rama.map(caes.set_index("codigo")["rama_eph"])

    ocupacion = df["PP04D_COD"].str.strip()
    ocupacion = ocupacion.where(ocupacion.str.len().eq(5))
    posiciones = {
        "caracter_ocupacional": ("caracter", slice(0, 2)),
        "jerarquia_ocupacional": ("jerarquia", slice(2, 3)),
        "tecnologia_ocupacional": ("tecnologia", slice(3, 4)),
        "calificacion_ocupacional": ("calificacion", slice(4, 5)),
    }
    for columna, (dimension, posicion) in posiciones.items():
        etiquetas = cno[cno["dimension"].eq(dimension)].set_index("valor")["etiqueta"]
        df[columna] = ocupacion.str[posicion].map(etiquetas)
    return df


def agregar_variables(df, ipc):
    """Agrega al DataFrame todas las variables derivadas de uso común."""
    df = df.copy()
    df["periodo"] = df["anio"].astype(str) + "-T" + df["trimestre"].astype(str)
    df["aglomerado_nombre"] = df["AGLOMERADO"].map(AGLOMERADOS)
    df["condicion_actividad"] = df["ESTADO"].map(CONDICION)
    df["sexo"] = df["CH04"].map(SEXO)
    df["edad"] = df["CH06"].clip(lower=0)
    df["grupo_edad"] = pd.cut(
        df["edad"].astype("float64"),
        bins=[-1, 13, 29, 64, 200],
        labels=["0-13", "14-29", "30-64", "65 y más"],
    ).astype(str)
    df["nivel_educativo"] = df["NIVEL_ED"].map(NIVEL_EDUCATIVO)
    df["nivel_ed_grupo"] = df["NIVEL_ED"].map(NIVEL_EDUCATIVO_GRUPO)
    df["categoria_ocupacional"] = df["CAT_OCUP"].map(CATEGORIA_OCUPACIONAL)
    df = agregar_clasificadores(df)

    # P21 y P47T marcan la no respuesta con -9. ITF e IPCF la marcan con un 0 que
    # no es un ingreso real: lo que la identifica es el ponderador PONDIH en 0.
    df["nr_p21"] = df["ESTADO"].eq(1) & df["P21"].eq(-9)
    df["nr_p47t"] = df["P47T"].eq(-9).fillna(False)
    df["nr_ipcf"] = df["PONDIH"].eq(0)
    df["p21_nominal"] = df["P21"].astype("float64").mask(df["P21"].eq(-9))
    df["p47t_nominal"] = df["P47T"].astype("float64").mask(df["nr_p47t"])
    df["itf_nominal"] = df["ITF"].astype("float64").mask(df["nr_ipcf"])
    df["ipcf_nominal"] = df["IPCF"].astype("float64").mask(df["nr_ipcf"])

    deflactor = ipc[["anio", "trimestre", "region", "factor_deflactor"]]
    df["region_ipc"] = df["AGLOMERADO"].map(REGION_IPC)
    df = df.merge(
        deflactor,
        left_on=["anio", "trimestre", "region_ipc"],
        right_on=["anio", "trimestre", "region"],
        how="left",
        validate="many_to_one",
    ).drop(columns="region")
    for ingreso in ("p21", "p47t", "itf", "ipcf"):
        df[f"{ingreso}_real"] = (df[f"{ingreso}_nominal"] * df["factor_deflactor"]).round(2)
    return df


def calcular_tasas(df, claves):
    """Calcula las tres tasas del mercado laboral, ponderadas con PONDERA."""
    datos = df.assign(
        poblacion=df["PONDERA"],
        ocupados=df["PONDERA"].where(df["ESTADO"].eq(1), 0),
        desocupados=df["PONDERA"].where(df["ESTADO"].eq(2), 0),
        n_ocupados=df["ESTADO"].eq(1),
        n_desocupados=df["ESTADO"].eq(2),
    )
    tabla = datos.groupby(claves, as_index=False).agg(
        n_muestra=("PONDERA", "size"),
        n_ocupados=("n_ocupados", "sum"),
        n_desocupados=("n_desocupados", "sum"),
        poblacion=("poblacion", "sum"),
        ocupados=("ocupados", "sum"),
        desocupados=("desocupados", "sum"),
    )
    activos = tabla["ocupados"] + tabla["desocupados"]
    tabla["tasa_actividad"] = (100 * activos / tabla["poblacion"]).astype("float64").round(2)
    tabla["tasa_empleo"] = (100 * tabla["ocupados"] / tabla["poblacion"]).astype("float64").round(2)
    tabla["tasa_desocupacion"] = (100 * tabla["desocupados"] / activos).astype("float64").round(2)
    return tabla.drop(columns=["poblacion", "ocupados", "desocupados"])


def cuantil_ponderado(valores, pesos, cuantil):
    """Devuelve el primer valor cuyo peso acumulado alcanza el cuantil pedido."""
    orden = np.argsort(valores)
    acumulado = np.cumsum(pesos[orden])
    return valores[orden][np.searchsorted(acumulado, cuantil * acumulado[-1])]


def calcular_ingresos(df):
    """Resume cada ingreso por aglomerado y trimestre, con su ponderador."""
    definiciones = [
        ("P21: ocupación principal", "p21", "PONDIIO", df["ESTADO"].eq(1) & df["p21_nominal"].gt(0)),
        ("P47T: ingreso total individual", "p47t", "PONDII", df["p47t_nominal"].gt(0)),
        ("IPCF: per cápita familiar", "ipcf", "PONDIH", df["ipcf_nominal"].notna()),
    ]
    filas = []
    for nombre, ingreso, ponderador, filtro in definiciones:
        for (anio, trimestre, aglomerado), grupo in df[filtro].groupby(
            ["anio", "trimestre", "aglomerado_nombre"]
        ):
            real = grupo[f"{ingreso}_real"].to_numpy(dtype="float64")
            nominal = grupo[f"{ingreso}_nominal"].to_numpy(dtype="float64")
            pesos = grupo[ponderador].to_numpy(dtype="float64")
            filas.append({
                "anio": anio,
                "trimestre": trimestre,
                "aglomerado_nombre": aglomerado,
                "ingreso": nombre,
                "ponderador": ponderador,
                "n_casos": len(grupo),
                "media_real": round(np.average(real, weights=pesos)),
                "p25_real": round(cuantil_ponderado(real, pesos, 0.25)),
                "mediana_real": round(cuantil_ponderado(real, pesos, 0.50)),
                "p75_real": round(cuantil_ponderado(real, pesos, 0.75)),
                "mediana_nominal": round(cuantil_ponderado(nominal, pesos, 0.50)),
            })
    return pd.DataFrame(filas)


def calcular_no_respuesta(df):
    """Mide la no respuesta de ingresos, en porcentaje de casos sin ponderar."""
    ocupados = df[df["ESTADO"].eq(1)]
    claves = ["anio", "trimestre", "aglomerado_nombre"]
    tabla = ocupados.groupby(claves, as_index=False).agg(
        ocupados=("nr_p21", "size"),
        pct_nr_p21_ocupados=("nr_p21", "mean"),
    )
    personas = df.groupby(claves, as_index=False).agg(
        personas=("nr_ipcf", "size"),
        pct_nr_p47t_personas=("nr_p47t", "mean"),
        pct_nr_ipcf_personas=("nr_ipcf", "mean"),
    )
    tabla = tabla.merge(personas, on=claves)
    porcentajes = [c for c in tabla.columns if c.startswith("pct_")]
    tabla[porcentajes] = (tabla[porcentajes] * 100).round(1)
    return tabla


def tasas_por_grupo(df):
    """Calcula las tasas anuales por sexo, edad y nivel educativo."""
    tablas = []
    for dimension in ("sexo", "grupo_edad", "nivel_ed_grupo"):
        tabla = calcular_tasas(df, ["aglomerado_nombre", "anio", dimension])
        tablas.append(tabla.rename(columns={dimension: "categoria"}).assign(dimension=dimension))
    columnas = ["aglomerado_nombre", "anio", "dimension", "categoria"]
    tabla = pd.concat(tablas, ignore_index=True)
    return tabla[columnas + [c for c in tabla.columns if c not in columnas]]


def escribir_excel(hojas, ruta):
    """Escribe las tablas de control, con encabezado fijo y filtros en cada hoja."""
    with pd.ExcelWriter(ruta, engine="openpyxl") as libro:
        for nombre, tabla in hojas.items():
            tabla.to_excel(libro, sheet_name=nombre, index=False)
            hoja = libro.sheets[nombre]
            hoja.freeze_panes = "A2"
            hoja.auto_filter.ref = hoja.dimensions
            for indice, columna in enumerate(tabla.columns, start=1):
                hoja.cell(row=1, column=indice).font = Font(bold=True)
                ancho = max(len(str(columna)), tabla[columna].astype(str).str.len().max())
                hoja.column_dimensions[get_column_letter(indice)].width = min(ancho + 2, 70)


def main():
    SALIDA.mkdir(exist_ok=True)
    base = pd.read_parquet(ENTRADA)

    periodos = sorted(set(zip(base["anio"], base["trimestre"])))
    ipc = ipc_trimestral(descargar_ipc(), periodos)
    df = agregar_variables(base, ipc)
    if df["factor_deflactor"].isna().any():
        raise ValueError("Hay trimestres sin deflactor")

    tasas_trim = calcular_tasas(df, ["aglomerado_nombre", "anio", "trimestre", "periodo"])
    tasas_anio = calcular_tasas(df, ["aglomerado_nombre", "anio"])
    tasas_anio["trimestres"] = tasas_anio["anio"].map(df.groupby("anio")["trimestre"].nunique())

    df.to_parquet(SALIDA / "eph_rosario_tucuman_completa.parquet", index=False, compression="zstd")
    df[COLUMNAS_REDUCIDA].to_csv(
        SALIDA / "eph_rosario_tucuman_reducida.csv", index=False, encoding="utf-8-sig"
    )
    escribir_excel(
        {
            "tasas_trimestrales": tasas_trim,
            "tasas_anuales": tasas_anio,
            "tasas_por_grupo": tasas_por_grupo(df),
            "ingresos_trimestrales": calcular_ingresos(df),
            "no_respuesta": calcular_no_respuesta(df),
            "ipc": ipc,
            "diccionario": pd.DataFrame(DICCIONARIO, columns=["variable", "descripcion"]),
        },
        SALIDA / "tablas_de_control.xlsx",
    )
    print(f"Registros: {len(df):,} | Columnas: {df.shape[1]} | Carpeta: {SALIDA}")


if __name__ == "__main__":
    main()
