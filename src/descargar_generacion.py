"""Descarga la generación real de SiMEM (dataset 055A4D) mes a mes,
la reduce a generación mensual por planta (GWh) y guarda un CSV por mes.

Uso, desde la raíz del repo y con el .venv activo:
    caffeinate -i python src/descargar_generacion.py
"""
import time
from pathlib import Path

import pandas as pd
from pydataxm.pydatasimem import ReadSIMEM

DATASET_ID = "055A4D"
PRIMER_MES = "2013-01"
ULTIMO_MES = "2026-10"  # último mes completo disponible
CARPETA_SALIDA = Path(__file__).resolve().parents[1] / "data" / "raw" / "generacion_mensual"
REINTENTOS = 3

# Orden de las versiones de liquidación, de preliminar a más definitiva
ORDEN_VERSION = {
    "TX1": 1, "TX2": 2, "TXR": 3, "TXF": 4,
    "TX3": 5, "TX4": 6, "TX5": 7, "TX6": 8, "TX7": 9, "TX8": 10,
}


def procesar_mes(inicio: str, fin: str) -> pd.DataFrame:
    """Devuelve la generación mensual por planta (GWh) entre inicio y fin."""
    df = ReadSIMEM(DATASET_ID, inicio, fin).main()

    # Si aparece una versión desconocida, parar: no sabemos dónde ordenarla
    df["orden_version"] = df["Version"].map(ORDEN_VERSION)
    desconocidas = set(df.loc[df["orden_version"].isna(), "Version"])
    if desconocidas:
        raise ValueError(f"Versiones desconocidas: {desconocidas}")

    # Versión más definitiva por planta-hora
    df = (
        df.sort_values("orden_version")
          .drop_duplicates(subset=["CodigoPlanta", "FechaHora"], keep="last")
    )

    # Agregar a mensual por planta y pasar a GWh
    df["mes"] = pd.to_datetime(df["FechaHora"]).dt.to_period("M").astype(str)
    mensual = df.groupby(["CodigoPlanta", "mes"])["Valor"].sum().reset_index()
    mensual["GWh"] = mensual["Valor"] / 1e6
    return mensual.drop(columns="Valor")


def main() -> None:
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    meses = pd.period_range(PRIMER_MES, ULTIMO_MES, freq="M")

    for periodo in meses:
        archivo = CARPETA_SALIDA / f"{periodo}.csv"
        if archivo.exists():
            print(f"{periodo}: ya existe, se salta")
            continue

        inicio = periodo.start_time.strftime("%Y-%m-%d")
        fin = periodo.end_time.strftime("%Y-%m-%d")

        for intento in range(1, REINTENTOS + 1):
            try:
                mensual = procesar_mes(inicio, fin)
                mensual.to_csv(archivo, index=False)
                print(f"OK {periodo}: {len(mensual)} plantas, {mensual['GWh'].sum():,.0f} GWh")
                break
            except ValueError as e:  # problema de datos: reintentar no sirve
                print(f"ERROR {periodo}: {e}")
                break
            except Exception as e:  # problema de red: esperar y reintentar
                print(f"{periodo}: fallo en intento {intento} ({e})")
                time.sleep(30 * intento)
        else:
            print(f"FALLÓ {periodo} tras {REINTENTOS} intentos")


if __name__ == "__main__":
    main()