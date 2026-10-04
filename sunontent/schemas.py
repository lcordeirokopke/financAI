"""Contrato de dados do pipeline."""

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentoFonte(BaseModel):
    """Documento entregue à E1 pela E0 (modo normal) ou pela referência (modo --dev).

    Ver docs/fluxos/ingestao.md, Contrato de saída.
    """

    model_config = ConfigDict(frozen=True)

    caminho: Path
    doc_id: str = Field(min_length=1)
    doc_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    url_origem: str = Field(min_length=1)
    coletado_em: datetime
    coleta_id: int | None = None  # None no modo --dev

    @field_validator("coletado_em")
    @classmethod
    def _utc(cls, valor: datetime) -> datetime:
        if valor.tzinfo is None:
            raise ValueError("coletado_em precisa de fuso horário")
        return valor.astimezone(timezone.utc)
