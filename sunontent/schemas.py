"""Contrato de dados do pipeline."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Nivel = Literal["iniciante", "intermediario", "avancado"]
Fonte = Literal["copom", "cvm", "b3"]
Modo = Literal["normal", "dev"]


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


class RunManifest(BaseModel):
    """Versões e entrada de um run. Ver docs/arquiteturas.md, Run manifest."""

    run_id: str
    timestamp: datetime
    modo: Modo
    fonte: Fonte
    doc_id: str | None = None
    doc_sha256: str | None = None
    url_origem: str | None = None
    coletado_em: datetime | None = None
    coleta_id: int | None = None
    modelos: dict[str, str]
    prompts: dict[str, int]
    level_specs: dict[Nivel, int]
    glossario_versao: int = Field(ge=1)
    arquivos_sha256: dict[str, str]
    K: int = Field(ge=1)
    custo_total_tokens: int = 0
    custo_total_brl: Decimal = Decimal(0)


class PipelineState(BaseModel):
    """Estado do grafo. Cresce a cada etapa implementada (docs/arquiteturas.md, O objeto de estado)."""

    run_id: str
    manifest: RunManifest
    documento_fonte: DocumentoFonte | None = None  # E0 ou nó de referência
