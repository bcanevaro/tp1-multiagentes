"""Datos del PDF sintético "Anuario Estadístico 2023 — Provincia de San Aurelio" (ficticia).

Es la única fuente de verdad de los números: el generador del PDF, el archivo
`tests/fixtures/sample_truth.json` y la verificación de las respuestas esperadas de
`eval/questions.yaml` salen de acá.
"""

from __future__ import annotations

YEARS_FINANCE = [2019, 2020, 2021, 2022, 2023]
DEPARTMENTS = ["Capital", "Norte", "Valle Alto", "Llanura", "Costa Sur"]
MONTHS = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]  # fmt: skip

# Cuadro 1 — Finanzas del sector público provincial, millones de pesos corrientes.
FINANCE: dict[str, list[float]] = {
    "Ingresos totales": [182450.3, 241880.7, 368912.4, 702115.8, 1854320.6],
    "Gastos totales": [190120.5, 268430.2, 375004.9, 698540.1, 1902775.3],
    "Gasto en ciencia y tecnología": [2150.4, 2874.1, 4390.8, 8612.7, 21940.2],
}
FINANCE["Resultado financiero"] = [
    round(i - g, 1)
    for i, g in zip(FINANCE["Ingresos totales"], FINANCE["Gastos totales"], strict=True)
]

# Cuadro 2 — Tasa de desempleo por departamento (%). None = sin dato ("s/d").
UNEMPLOYMENT_YEARS = [2021, 2022, 2023]
UNEMPLOYMENT: dict[str, list[float | None]] = {
    "Capital": [8.4, 7.9, 7.1],
    "Norte": [10.2, 9.6, 9.8],
    "Valle Alto": [6.1, 5.8, 6.4],
    "Llanura": [7.3, 7.0, 6.6],
    "Costa Sur": [None, 8.7, 8.2],
}

# Cuadro 3 — Salario bruto promedio mensual por sector, en pesos (no aclara nominal/real).
WAGE_YEARS = [2021, 2022, 2023]
WAGES: dict[str, list[int | None]] = {
    "Agro": [None, 128450, 312780],
    "Industria": [98320, 187640, 451920],
    "Comercio": [85110, 162870, 389540],
    "Servicios": [92760, 176310, 418250],
}

# Cuadro 4 — Producción por departamento y cultivo, miles de toneladas (encabezado de 2 niveles).
CROPS = ["Soja", "Maíz"]
CROP_YEARS = [2022, 2023]
PRODUCTION: dict[str, dict[str, list[float]]] = {
    "Capital": {"Soja": [12.4, 10.1], "Maíz": [8.2, 7.5]},
    "Norte": {"Soja": [845.3, 702.8], "Maíz": [512.6, 488.1]},
    "Valle Alto": {"Soja": [210.7, 198.4], "Maíz": [340.2, 355.9]},
    "Llanura": {"Soja": [1254.9, 1087.6], "Maíz": [963.4, 901.2]},
    "Costa Sur": {"Soja": [98.5, 85.3], "Maíz": [120.7, 131.0]},
}

# Cuadro 5 — Población (habitantes) y superficie (km²) por departamento, 2023.
POPULATION: dict[str, int] = {
    "Capital": 612450,
    "Norte": 184300,
    "Valle Alto": 97820,
    "Llanura": 143760,
    "Costa Sur": 71215,
}
AREA_KM2: dict[str, int] = {
    "Capital": 1250,
    "Norte": 18430,
    "Valle Alto": 9870,
    "Llanura": 22610,
    "Costa Sur": 14920,
}

# Cuadro 6 — Exportaciones mensuales por grandes rubros, miles de US$ (continúa en otra página).
EXPORT_YEARS = [2022, 2023]
EXPORT_RUBROS = [
    "Productos primarios",
    "Manufacturas de origen agropecuario",
    "Manufacturas de origen industrial",
]
EXPORTS: dict[int, dict[str, list[float]]] = {
    2022: {
        "Productos primarios": [
            41250.3, 38720.8, 45310.2, 52870.4, 61240.9, 58930.1,
            49870.6, 44120.3, 40310.7, 39850.2, 42730.5, 47210.8,
        ],
        "Manufacturas de origen agropecuario": [
            28340.5, 26910.2, 30120.8, 33450.1, 36870.4, 35210.9,
            31980.3, 29870.6, 27650.2, 28120.7, 29940.1, 32010.5,
        ],
        "Manufacturas de origen industrial": [
            12450.8, 11980.3, 13210.6, 13870.2, 14120.5, 13650.9,
            12980.4, 12340.7, 13010.2, 13450.6, 13890.1, 14210.3,
        ],
    },
    2023: {
        "Productos primarios": [
            35120.4, 31870.2, 37940.6, 42310.8, 48760.3, 46120.5,
            40230.9, 36870.1, 34120.6, 33980.4, 36210.7, 40120.3,
        ],
        "Manufacturas de origen agropecuario": [
            25120.9, 23870.4, 26940.2, 29310.6, 32120.8, 30980.1,
            28430.7, 26210.3, 24980.6, 25340.2, 26870.5, 28910.4,
        ],
        "Manufacturas de origen industrial": [
            12980.1, 12310.6, 13640.2, 14210.8, 14590.3, 14020.7,
            13450.2, 12870.9, 13320.4, 13780.6, 14150.2, 14620.8,
        ],
    },
}  # fmt: skip


def export_total(year: int, month_index: int) -> float:
    """Total exportado en un mes (suma de los tres rubros), redondeado a 1 decimal."""
    return round(sum(EXPORTS[year][r][month_index] for r in EXPORT_RUBROS), 1)


# --------------------------------------------------------------------------------------
# Formato argentino de números (punto de miles, coma decimal)
# --------------------------------------------------------------------------------------


def fmt_ar(value: float, decimals: int = 1) -> str:
    """`1234567.8` -> `1.234.567,8`."""
    text = f"{abs(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{text}" if value < 0 else text


def fmt_ar_parens(value: float, decimals: int = 1) -> str:
    """Negativos entre paréntesis, como en los informes contables: `(7.670,2)`."""
    return f"({fmt_ar(abs(value), decimals)})" if value < 0 else fmt_ar(value, decimals)
