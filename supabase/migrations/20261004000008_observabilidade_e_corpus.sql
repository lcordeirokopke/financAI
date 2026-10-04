-- Observabilidade (spans de LLM) e corpus rotulado de calibração.

-- Span por chamada de LLM (docs/arquiteturas.md:622, 657-665).
-- PENDENTE: a documentação não define schema de span; colunas inferidas dos dados citados.
create table llm_spans (
  id             bigint generated always as identity primary key,
  run_id         text not null references runs (run_id),
  celula_id      text,  -- nulo para nós antes do fan-out (E2, E3, E4)
  no             text not null,  -- extractor, adapter, synthesizer, judge
  modelo         text not null,
  tokens_entrada int not null,
  tokens_saida   int not null,
  custo_brl      numeric(14, 6) not null,
  duracao_ms     int not null,
  falha_classe   classe_falha,
  falha_mensagem text,
  criado_em      timestamptz not null default now()
);

create index llm_spans_run_idx on llm_spans (run_id, celula_id);

-- Corpus rotulado por nível pela equipe editorial, para calibrar as faixas do LevelSpec e montar
-- a matriz de confusão de níveis (docs/arquiteturas.md:689-692, 735).
-- PENDENTE: a documentação não define schema; colunas inferidas.
create table corpus_rotulado (
  id             bigint generated always as identity primary key,
  texto          text not null,
  nivel_rotulado nivel not null,
  formato        formato,
  origem         text,
  rotulado_por   text not null,
  metricas       jsonb,  -- valores medidos de M1 a M5 sobre o texto
  criado_em      timestamptz not null default now()
);

-- PENDENTE: base de conceitos financeiros (definições para os agentes) em discussão;
-- não decidido se fica em YAML no git ou em tabela aqui.
-- LevelSpec, glossário, models.yaml e prompts ficam no git; o banco guarda só as versões no run.
