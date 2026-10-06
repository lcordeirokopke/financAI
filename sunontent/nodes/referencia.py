"""Entrada do modo --dev no lugar da E0: chama ingestao/referencia.py e coloca o DocumentoFonte no estado.

Dependências vêm de config["configurable"]:
- repositorio: persistencia.Repositorio (Supabase ou, nos testes, em memória);
- pasta_referencia: pasta com <fonte>.pdf e <fonte>.json (tests/fixtures/referencia/).
"""

from pathlib import Path

from sunontent.ingestao import referencia as ingestao_referencia


def referencia(state, config) -> dict:
    configuravel = config["configurable"]
    documento = ingestao_referencia.carregar(
        run_id=state.run_id,
        fonte=state.manifest.fonte,
        repositorio=configuravel["repositorio"],
        pasta_referencia=Path(configuravel["pasta_referencia"]),
    )
    return {"documento_fonte": documento}
