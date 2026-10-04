-- E6: Scorecard, MetricaResultado e Violacao (docs/arquiteturas.md:161-185).

create table scorecards (
  run_id       text not null,
  celula_id    text not null,
  tentativa    int not null,
  veredito     veredito not null,
  custo_tokens bigint not null,
  duracao_ms   int not null,
  criado_em    timestamptz not null default now(),
  primary key (run_id, celula_id, tentativa),
  foreign key (run_id, celula_id, tentativa) references pecas (run_id, celula_id, tentativa)
);
-- PENDENTE: veredito ERRO_INFRA de geração acontece antes de existir peça; não está definido
-- se gera scorecard.

-- MetricaResultado. valor é float | bool: uma das duas colunas é preenchida.
create table metricas (
  id             bigint generated always as identity primary key,
  run_id         text not null,
  celula_id      text not null,
  tentativa      int not null,
  nome           text not null,  -- PENDENTE: só 'numeric_fidelity' (M1) tem nome fixado; M2 a M6 não.
  valor_num      double precision,
  valor_bool     boolean,
  faixa_esperada text not null,
  passou         boolean not null,
  -- PENDENTE: saídas ricas sem campo na documentação (distribuição de sentenças da M3, termos e
  -- posições da M4, justificativas da M6).
  detalhes       jsonb,
  unique (run_id, celula_id, tentativa, nome),
  foreign key (run_id, celula_id, tentativa) references scorecards (run_id, celula_id, tentativa),
  check ((valor_num is null) <> (valor_bool is null))
);

-- Violacao. instrucao_corretiva é reinjetada no retry (docs/arquiteturas.md:210).
create table violacoes (
  id                  bigint generated always as identity primary key,
  metrica_id          bigint not null references metricas (id),
  metrica             text not null,
  trecho              text not null,
  esperado            text not null,
  obtido              text not null,
  instrucao_corretiva text not null
);

create index violacoes_metrica_idx on violacoes (metrica_id);
