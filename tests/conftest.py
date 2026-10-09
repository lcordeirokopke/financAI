"""Configuração comum dos testes.

- Trava: interrompe o pytest antes da coleta se SUPABASE_URL ou SUPABASE_DB_URL apontarem
  para um host diferente de localhost, 127.0.0.1 ou ::1. O .env não é carregado aqui.
- Marker `supabase`: testes de integração com a cópia local do Supabase CLI.
- Repositório em memória no lugar do Supabase e retentativa sem espera.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest

from sunontent import retentativa
from sunontent.persistencia import Coleta
from sunontent.retentativa import FalhaRetriavel, FalhaTerminal

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}
FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "supabase: integração com a cópia local do Supabase CLI (supabase start)"
    )
    for variavel in ("SUPABASE_URL", "SUPABASE_DB_URL"):
        valor = os.environ.get(variavel)
        if not valor:
            continue
        host = urlparse(valor).hostname
        if host not in HOSTS_LOCAIS:
            raise pytest.UsageError(
                f"{variavel} aponta para {host!r}. Os testes só usam o Supabase local "
                f"({', '.join(sorted(HOSTS_LOCAIS))})."
            )


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    esperas = []
    monkeypatch.setattr(retentativa, "_dormir", esperas.append)
    return esperas


@dataclass
class RepositorioMemoria:
    """Repositório em memória com as mesmas regras do Supabase usadas pela E0.

    `falhas` injeta exceções por método, consumidas uma a cada chamada.
    `perder_resposta_da_transacao` grava a transação e depois levanta FalhaRetriavel.
    """

    runs: dict[str, dict] = field(default_factory=dict)
    documentos: dict[str, dict] = field(default_factory=dict)
    objetos: dict[str, bytes] = field(default_factory=dict)
    coletas: list[Coleta] = field(default_factory=list)
    falhas: dict[str, list[Exception]] = field(default_factory=dict)
    perder_resposta_da_transacao: int = 0
    chamadas: dict[str, int] = field(default_factory=dict)
    paginas: dict[tuple, dict] = field(default_factory=dict)
    chunks: dict[tuple, dict] = field(default_factory=dict)
    numeros: dict[tuple, dict] = field(default_factory=dict)

    def registrar_run(self, run_id: str) -> None:
        self.runs[run_id] = {"coleta_id": None}

    def _entrar(self, metodo: str) -> None:
        self.chamadas[metodo] = self.chamadas.get(metodo, 0) + 1
        fila = self.falhas.get(metodo)
        if fila:
            raise fila.pop(0)

    def documento_existe(self, doc_sha256: str) -> bool:
        self._entrar("documento_existe")
        return doc_sha256 in self.documentos

    def enviar_pdf(self, caminho_storage: str, dados: bytes) -> None:
        self._entrar("enviar_pdf")
        if caminho_storage in self.objetos:
            return  # Asset Already Exists: reaproveita
        self.objetos[caminho_storage] = dados

    def registrar_coleta(self, *, run_id, fonte, tipo_documento, doc_sha256, tamanho_bytes,
                         doc_id, url_origem, coletado_em: datetime) -> Coleta:
        self._entrar("registrar_coleta")
        run = self.runs.get(run_id)
        if run is None or run["coleta_id"] is not None:
            raise FalhaTerminal(f"run {run_id} não existe em runs ou já tem coleta vinculada")
        self.documentos.setdefault(
            doc_sha256,
            {"fonte": fonte, "tipo_documento": tipo_documento,
             "storage_path": f"{fonte}/{doc_sha256}.pdf", "tamanho_bytes": tamanho_bytes},
        )
        coleta = Coleta(len(self.coletas) + 1, doc_id, doc_sha256, url_origem, coletado_em)
        self.coletas.append(coleta)
        run["coleta_id"] = coleta.coleta_id
        run["coleta"] = coleta
        if self.perder_resposta_da_transacao:
            self.perder_resposta_da_transacao -= 1
            raise FalhaRetriavel("conexão perdida depois do commit")
        return coleta

    def coleta_do_run(self, run_id: str) -> Coleta | None:
        self._entrar("coleta_do_run")
        run = self.runs.get(run_id, {})
        return run.get("coleta")

    def registrar_documento_referencia(self, *, run_id, fonte, tipo_documento, doc_sha256,
                                       tamanho_bytes, doc_id, url_origem, coletado_em: datetime) -> None:
        self._entrar("registrar_documento_referencia")
        run = self.runs.get(run_id)
        if run is None or run.get("doc_sha256") not in (None, doc_sha256):
            raise FalhaTerminal(f"run {run_id} não existe em runs ou já está vinculado a outro documento")
        self.documentos.setdefault(
            doc_sha256,
            {"fonte": fonte, "tipo_documento": tipo_documento,
             "storage_path": f"{fonte}/{doc_sha256}.pdf", "tamanho_bytes": tamanho_bytes},
        )
        run.update(doc_id=doc_id, doc_sha256=doc_sha256, url_origem=url_origem, coletado_em=coletado_em)

    def gravar_documento_processado(self, run_id, documento) -> None:
        """Mesmas regras do Supabase: o run existe, linhas repetidas ficam como estão, tudo ou nada."""
        self._entrar("gravar_documento_processado")
        if run_id not in self.runs:
            raise FalhaTerminal(f"run {run_id} não existe em runs")
        paginas = {(run_id, p.pagina): {"texto_limpo": p.texto_limpo, "ocr": p.ocr} for p in documento.paginas}
        chunks = {(run_id, c.chunk_id): c.model_dump() for c in documento.chunks}
        numeros = {
            (run_id, n.ancora.pagina, n.ancora.offset_inicio, n.ancora.offset_fim): n.model_dump()
            for n in documento.tabela_numeros
        }
        for destino, novos in ((self.paginas, paginas), (self.chunks, chunks), (self.numeros, numeros)):
            for chave, valor in novos.items():
                destino.setdefault(chave, valor)

    def criar_run(self, manifest) -> None:
        self._entrar("criar_run")
        self.runs.setdefault(manifest.run_id, {"coleta_id": None, "manifest": manifest,
                                               "status": "em_andamento"})

    def concluir_run(self, run_id) -> None:
        self._entrar("concluir_run")
        run = self.runs.get(run_id)
        if run is None or run["status"] != "em_andamento":
            raise FalhaTerminal(f"run {run_id} não existe em runs ou não está em_andamento")
        run["status"] = "concluido"

    def abortar_run(self, run_id, erro_classe, erro_mensagem) -> None:
        self._entrar("abortar_run")
        run = self.runs.get(run_id)
        if run is not None and run["status"] == "em_andamento":
            run.update(status="abortado", erro_classe=erro_classe, erro_mensagem=erro_mensagem)


@pytest.fixture
def repositorio():
    repo = RepositorioMemoria()
    repo.registrar_run("copom_20261004T142205Z_9f2c1a")
    return repo


@pytest.fixture
def run_id():
    return "copom_20261004T142205Z_9f2c1a"


def referencia(fonte: str) -> tuple[bytes, dict] | None:
    """Bytes e metadados do documento de referência, ou None se ainda não foi congelado."""
    pdf = FIXTURES / "referencia" / f"{fonte}.pdf"
    meta = FIXTURES / "referencia" / f"{fonte}.json"
    if not (pdf.exists() and meta.exists()):
        return None
    return pdf.read_bytes(), json.loads(meta.read_text(encoding="utf-8"))
