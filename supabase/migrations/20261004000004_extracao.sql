-- E1 (DocumentoProcessado), E2 (FactSheet, Claim, Numero) e E3 (validação de âncoras).
-- Ancora (docs/arquiteturas.md:46-49) é gravada em colunas: pagina, offset_inicio, offset_fim,
-- com offsets de caractere no texto limpo da página.
-- PENDENTE: se pagina é 0- ou 1-indexada.

-- Texto limpo por página. Necessário para reverificar âncoras (docs/arquiteturas.md:331).
-- PENDENTE: DocumentoProcessado não tem schema na documentação.
create table documento_paginas (
  run_id      text not null references runs (run_id),
  pagina      int not null check (pagina >= 0),
  texto_limpo text not null,
  ocr         boolean not null default false,  -- PENDENTE: campo inferido (OCR por página, docs/arquiteturas.md:277)
  primary key (run_id, pagina)
);

-- Chunks por seção lógica (docs/arquiteturas.md:279), usados pela M6 para recuperar contexto.
-- PENDENTE: estrutura do chunk não definida. A documentação descreve o índice vetorial como
-- efêmero (docs/arquiteturas.md:259); persistir o embedding aqui é decisão em aberto.
-- PENDENTE: dimensão do embedding depende do modelo de embedding, ainda não escolhido.
create table chunks (
  run_id        text not null,
  chunk_id      text not null,
  pagina        int not null,
  offset_inicio int not null,
  offset_fim    int not null,
  secao         text,
  texto         text not null,
  embedding     extensions.vector,
  primary key (run_id, chunk_id),
  foreign key (run_id, pagina) references documento_paginas (run_id, pagina),
  check (offset_fim >= offset_inicio)
);

-- FactSheet (docs/arquiteturas.md:82-90). Um por run.
create table factsheets (
  run_id         text primary key references runs (run_id),
  doc_id         text not null,
  tipo_documento tipo_documento not null,
  emissor        text not null,
  data_documento date not null,
  assinado       boolean not null default false
);

-- FactSheet.tabela_numeros: TODOS os números do fonte, com âncora.
-- PENDENTE: a documentação indexa por bruto (docs/arquiteturas.md:88), mas o mesmo bruto pode
-- aparecer em páginas diferentes; aqui a unicidade é por posição.
create table numeros (
  id            bigint generated always as identity primary key,
  run_id        text not null references factsheets (run_id),
  bruto         text not null,
  valor         numeric not null,
  unidade       unidade_numero not null,
  pagina        int not null,
  offset_inicio int not null,
  offset_fim    int not null,
  unique (run_id, pagina, offset_inicio, offset_fim),
  check (offset_fim >= offset_inicio)
);

create index numeros_run_bruto_idx on numeros (run_id, bruto);

-- Claim (docs/arquiteturas.md:67-75). claim_id ("C07") é estável só dentro do documento.
create table claims (
  run_id        text not null references factsheets (run_id),
  claim_id      text not null,
  texto         text not null,
  tipo          tipo_claim not null,
  tags          text[] not null default '{}',
  literal_fonte text not null,
  pagina        int not null,
  offset_inicio int not null,
  offset_fim    int not null,
  primary key (run_id, claim_id),
  check (offset_fim >= offset_inicio)
);

-- Claim.numeros: lista embutida de Numero no claim.
-- PENDENTE: a documentação diz que o claim referencia entradas da tabela_numeros
-- (docs/arquiteturas.md:302), mas o schema embute o Numero completo (docs/arquiteturas.md:70).
-- Aqui guarda o Numero do claim e, quando houver, o vínculo com a entrada da tabela.
create table claim_numeros (
  run_id        text not null,
  claim_id      text not null,
  ordem         int not null,
  bruto         text not null,
  valor         numeric not null,
  unidade       unidade_numero not null,
  pagina        int not null,
  offset_inicio int not null,
  offset_fim    int not null,
  numero_id     bigint references numeros (id),
  primary key (run_id, claim_id, ordem),
  foreign key (run_id, claim_id) references claims (run_id, claim_id)
);

-- Rodadas de correção E3 -> E2 (docs/arquiteturas.md:323-327).
-- PENDENTE: o schema do pedido de correção e o limite do loop E2/E3 não estão definidos.
create table validacoes_ancora (
  run_id   text not null references factsheets (run_id),
  rodada   int not null check (rodada >= 1),
  claim_id text not null,
  passou   boolean not null,
  motivo   text,
  primary key (run_id, rodada, claim_id)
);
