"""E1. Leitura: chama extracao/ e coloca o DocumentoProcessado no estado.

Grava a saída no Supabase e na cópia local antes de devolver o estado.
Dependências vêm de config["configurable"]:
- repositorio: persistencia.Repositorio (Supabase ou, nos testes, em memória);
- raiz_dados: pasta raiz de data/.
"""

from pathlib import Path

from sunontent import persistencia
from sunontent.extracao import leitura as extracao


def leitura(state, config) -> dict:
    configuravel = config["configurable"]
    documento = extracao.processar(state.documento_fonte, state.manifest.fonte)
    persistencia.gravar_documento_processado(
        configuravel["repositorio"], Path(configuravel["raiz_dados"]), state.run_id, documento
    )
    return {"documento": documento}
