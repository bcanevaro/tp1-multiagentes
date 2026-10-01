"""VC-011 a VC-015, VC-014b: anotación y validación de metadatos."""

from __future__ import annotations

import pytest

from agents.ingestion.prompts import build_messages
from agents.ingestion.schemas import ColumnAnnotation, TableAnnotation, TableContextData, TableDraft
from agents.ingestion.validate import (
    build_metadata,
    count_sentences,
    table_id_for,
    validate_annotation,
)
from tests.ingestion.fakes import good_annotation


@pytest.fixture
def draft() -> TableDraft:
    return TableDraft(
        index=0,
        pages=[2],
        strategy="lines",
        columns=["Departamento", "Población (habitantes)"],
        dtypes=["str", "float64"],
        rows=[["Capital", 612450.0], ["Norte", 184300.0], ["Sur", None]],
        context=TableContextData(
            caption="Cuadro 5. Población por departamento", section_title="4. Población"
        ),
        extraction_notes=["El signo '-' se interpretó como dato faltante."],
    )


def _ann(draft: TableDraft, **changes: object) -> TableAnnotation:
    return good_annotation(draft).model_copy(update=changes)


def test_vc011_annotation_is_valid_table_metadata(draft: TableDraft) -> None:
    ann = good_annotation(draft)
    assert validate_annotation(ann, draft) == []
    meta = build_metadata(ann, draft, table_id="abc-t01", doc_id="abc", pdf_name="x.pdf")
    assert meta.row_headers == ["Capital", "Norte", "Sur"]
    assert [c.dtype for c in meta.columns] == ["str", "float64"]
    assert meta.source.pages == [2] and meta.source.section_title == "4. Población"
    assert "dato faltante" in meta.notes


def test_vc012_missing_column_is_br001(draft: TableDraft) -> None:
    ann = _ann(draft, columns=good_annotation(draft).columns[:1])
    assert any(e.startswith("BR-001") for e in validate_annotation(ann, draft))


def test_br001_renamed_column(draft: TableDraft) -> None:
    cols = good_annotation(draft).columns
    renamed = [cols[0], cols[1].model_copy(update={"name": "Población"})]
    errors = validate_annotation(_ann(draft, columns=renamed), draft)
    assert errors == ["BR-001: la columna 2 se llama 'Población (habitantes)', no 'Población'"]


def test_vc013_row_header_column_must_exist(draft: TableDraft) -> None:
    errors = validate_annotation(_ann(draft, row_header_column="Región"), draft)
    assert any(e.startswith("BR-002") for e in errors)
    numeric = validate_annotation(_ann(draft, row_header_column="Población (habitantes)"), draft)
    assert any(e.startswith("BR-002") for e in numeric)
    assert validate_annotation(_ann(draft, row_header_column=None), draft) == []


@pytest.mark.parametrize("name", ["Tabla 3", "Cuadro 12.", "tabla", "AB"])
def test_vc014_generic_name(draft: TableDraft, name: str) -> None:
    assert any(e.startswith("BR-003") for e in validate_annotation(_ann(draft, name=name), draft))


@pytest.mark.parametrize(
    ("description", "ok"),
    [
        ("Una sola oración.", False),
        ("Uno. Dos. Tres. Cuatro. Cinco.", False),
        ("La tasa fue de 12.5 % en promedio. Cubre 2021 a 2023.", True),
        ("Datos de Andina S.A. de la provincia. Valores en miles.", True),
    ],
)
def test_vc014b_description_sentences(draft: TableDraft, description: str, ok: bool) -> None:
    errors = validate_annotation(_ann(draft, description=description), draft)
    assert (errors == []) is ok


def test_count_sentences() -> None:
    assert count_sentences("Uno. Dos? Tres!") == 3
    assert count_sentences("Valor 1.234,5 pesos. Fin.") == 2


def test_vc015_numeric_column_needs_unit(draft: TableDraft) -> None:
    cols = good_annotation(draft).columns
    empty = [cols[0], cols[1].model_copy(update={"unit": " "})]
    assert any(
        e.startswith("BR-004") for e in validate_annotation(_ann(draft, columns=empty), draft)
    )
    unknown = [cols[0], cols[1].model_copy(update={"unit": "desconocida"})]
    assert validate_annotation(_ann(draft, columns=unknown), draft) == []


def test_br005_table_ids() -> None:
    assert table_id_for("0ca85a35fc1876be", 0) == "0ca85a35fc1876be-t01"
    assert table_id_for("0ca85a35fc1876be", 10) == "0ca85a35fc1876be-t11"


def test_prompt_has_exact_columns_context_and_previous_errors(draft: TableDraft) -> None:
    system, human = build_messages(draft, "anuario.pdf", ["BR-001: falta una columna"])
    text = str(human.content)
    assert "'Población (habitantes)' (tipo: float64)" in text
    assert "Epígrafe: Cuadro 5. Población por departamento" in text
    assert "BR-001: falta una columna" in text
    assert "de 2 a 4 oraciones" in str(system.content)
    first = str(build_messages(draft, "anuario.pdf")[1].content)
    assert "Corregí estos errores" not in first


def test_column_annotation_schema_requires_all_fields() -> None:
    with pytest.raises(ValueError):
        ColumnAnnotation(name="x")  # type: ignore[call-arg]


def _wage_draft(caption: str) -> TableDraft:
    return TableDraft(
        index=2,
        pages=[1],
        strategy="hrules",
        columns=["Sector", "2023"],
        dtypes=["str", "float64"],
        rows=[["Agro", 312780.0], ["Industria", 451920.0]],
        context=TableContextData(
            caption=caption, footnotes="Trabajadores asalariados registrados."
        ),
    )


def test_vc015b_nominal_real_requires_support_in_document() -> None:
    draft = _wage_draft("Cuadro 3. Salario bruto promedio mensual por sector. En pesos")
    ann = good_annotation(draft)
    nominal_col = [ann.columns[0], ann.columns[1].model_copy(update={"value_type": "nominal"})]
    errors = validate_annotation(ann.model_copy(update={"columns": nominal_col}), draft)
    assert any(e.startswith("BR-004b: la columna '2023'") for e in errors)
    invented = ann.model_copy(
        update={"description": "Salarios por sector en 2023. Se presentan en pesos corrientes."}
    )
    assert any("BR-004b: la descripción" in e for e in validate_annotation(invented, draft))
    honest = ann.model_copy(
        update={
            "description": "Salarios por sector en 2023. El documento no indica si los montos "
            "están ajustados por inflación."
        }
    )
    assert validate_annotation(honest, draft) == []


def test_vc015b_supported_by_caption_or_column_name() -> None:
    draft = _wage_draft("Cuadro 3. Salario promedio. En pesos corrientes")
    ann = good_annotation(draft)
    cols = [ann.columns[0], ann.columns[1].model_copy(update={"value_type": "nominal"})]
    ok = ann.model_copy(update={"columns": cols, "description": "Salarios. En pesos corrientes."})
    assert validate_annotation(ok, draft) == []
    real = ann.model_copy(update={"description": "Salarios. Valores a precios constantes."})
    assert any("BR-004b" in e for e in validate_annotation(real, draft))
    indec = _wage_draft("Cuadro 4. Índices")
    indec = indec.model_copy(
        update={"columns": ["Rubro", "A precios corrientes | Millones de USD"]}
    )
    ann4 = good_annotation(indec).model_copy(
        update={"description": "Valores a precios corrientes. Fin."}
    )
    assert validate_annotation(ann4, indec) == []
