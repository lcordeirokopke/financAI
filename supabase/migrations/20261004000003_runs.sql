-- Run e RunManifest (docs/arquiteturas.md:187-208).
-- Uma linha por execução do grafo. O manifest é imutável depois de fechado; custos e status são
-- atualizados durante o run.

create table runs (
  run_id             text primary key,
  "timestamp"        timestamptz not null,
  modo               modo_run not null,
  fonte              fonte not null,
  status             status_run not null default 'em_andamento',

  -- Documento processado. No modo normal aponta para a coleta; no --dev não há coleta.
  doc_id             text not null,
  doc_sha256         char(64) not null check (doc_sha256 ~ '^[0-9a-f]{64}$'),
  coleta_id          bigint references coletas (id),

  -- Versões (RunManifest)
  modelos            jsonb not null,  -- {"extractor": snapshot, "adapter": ..., "synthesizer": ..., "judge": ...}
  prompts            jsonb not null,  -- {"extractor": "v1", "adapter": "v3", ...}
  level_specs        jsonb not null,  -- {"iniciante": 1, "intermediario": 1, "avancado": 1}
  glossario_versao   text not null,
  "K"                int not null check ("K" >= 0),

  custo_total_tokens bigint not null default 0,
  custo_total_brl    numeric(14, 6) not null default 0,

  -- Falha do run inteiro (ex: E0 antes de existir célula)
  -- PENDENTE: campos de falha de run não estão definidos na documentação.
  erro_classe        classe_falha,
  erro_mensagem      text,

  criado_em          timestamptz not null default now()
);
-- PENDENTE: no modo normal coleta_id deveria ser obrigatório e no --dev nulo, mas a ordem de
-- gravação run x coleta não está definida; por isso não há check aqui.

-- PENDENTE: formato e quem gera o run_id.
-- PENDENTE: mecanismo de versão do LevelSpec e do glossário (YAMLs ainda vazios).
-- PENDENTE: runs --dev: o PDF de referência fica em tests/fixtures/referencia/ no git;
-- não está definido se ele também é registrado em documentos/Storage. Por isso doc_sha256
-- não tem FK para documentos.

create index runs_doc_sha256_idx on runs (doc_sha256);
create index runs_doc_id_idx on runs (doc_id);
create index runs_timestamp_idx on runs ("timestamp" desc);

alter table coletas
  add constraint coletas_run_id_fkey foreign key (run_id) references runs (run_id);
-- PENDENTE: a coleta é gravada na E0, possivelmente antes do run existir no banco;
-- a ordem de gravação run x coleta não está definida.

-- Checkpoint do LangGraph: as tabelas (checkpoints, checkpoint_blobs, checkpoint_writes,
-- checkpoint_migrations) são criadas pelo PostgresSaver.setup() do langgraph-checkpoint-postgres
-- e não são declaradas aqui. Granularidade: um thread por célula (docs/arquiteturas.md:586).
-- PENDENTE: formato do thread_id (ex: run_id:celula_id) e schema onde ficam as tabelas.
